#
# main.py -- this is the web server for the Raspberry Pi Pico W Web Rotator Controller.
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, 2025, 2026 J. B. Otterson N1KDO.
Redistribution and use in source and binary forms, with or without modification, 
are permitted provided that the following conditions are met:
  1. Redistributions of source code must retain the above copyright notice, 
     this list of conditions and the following disclaimer.
  2. Redistributions in binary form must reproduce the above copyright notice, 
     this list of conditions and the following disclaimer in the documentation 
     and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND 
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, 
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE 
OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.
"""
__version__ = '0.2.2'  # 2026-09-20

import asyncio
import gc
import socket
import micro_logging as logging

from http_server import (HttpServer,
                         HTTP_STATUS_OK, HTTP_STATUS_BAD_REQUEST, HTTP_STATUS_MOVED_PERMANENTLY,
                         HTTP_STATUS_INTERNAL_SERVER_ERROR, HTTP_VERB_GET, HTTP_VERB_POST)
from morse_code import MorseCode
from n1mm_rotator_udp import RotatorData, calculate_broadcast_address, ReceiveBroadcastsFromN1MM, SendBroadcastsToN1MM
from dcu1_rotator import Rotator
from utils import elapsed_ms, is_ipv4, milliseconds, safe_int, upython

if upython:
    # disable pylint import error
    # pylint: disable=E0401
    from picow_network import PicowNetwork
    import machine
else:
    from not_machine import machine

# noinspection PyUnboundLocalVariable
onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
onboard.on()
morse_led = machine.Pin(2, machine.Pin.OUT, value=0)  # status LED
reset_button = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_UP)

CONTENT_DIR = 'content/'

N1MM_ROTOR_BROADCAST_PORT = 12040
N1MM_BROADCAST_FROM_ROTOR_PORT = 13010

from config_data import (ConfigData,
                         DEFAULT_SSID, DEFAULT_SECRET, DEFAULT_WEB_PORT,
                         DEFAULT_TCP_PORT_1, DEFAULT_TCP_PORT_2)

# globals
keep_running = True
rotator_1 = None
rotator_2 = None

# picow_network
picow_network = None

# config data
config = ConfigData()

# http server
http_server = HttpServer(content_dir=CONTENT_DIR)

class RotatorTelnetServer:
    def __init__(self, rotator):
        self._rotator = rotator

    async def serve_serial_client(self, reader, writer):
        """
        this provides serial compatible control.
        use com0com with com2tcp to interface legacy apps on Windows.

        this code provides a serial endpoint that implements part of the DCU-3 protocol.

        all commands start with 'A'
        all commands end with ';' or CR (ascii 13)
        """
        requested = -1
        t0 = milliseconds()
        partner = writer.get_extra_info('peername')[0]
        logging.info(f'serial client connected from {partner}', 'main:connect_to_network')
        buffer = []

        try:
            while True:
                data = await reader.read(1)
                if not data:
                    break
                else:
                    if len(data) == 1:
                        b = data[0]
                        if b == ord('A'):  # commands always start with A, so reset the buffer.
                            buffer = [b]
                        else:
                            if len(buffer) < 8:  # anti-gibberish test
                                buffer.append(b)
                                if b == ord(';') or b == 13:  # command terminator
                                    command = bytes(buffer)
                                    buffer = []  # discard the completed command
                                    if command in (b'AI1;', b'AI1\r'):  # get direction
                                        bearing = await self._rotator.get_rotator_bearing()
                                        writer.write(b';%03d' % bearing)
                                        await writer.drain()
                                    elif command.startswith(b'AP1') and command[-1] == 13:  # set + move
                                        requested = safe_int(command[3:-1], -1)
                                        if 0 <= requested <= 360:
                                            await self._rotator.set_rotator_bearing(requested)
                                    elif command.startswith(b'AP1') and command[-1] == ord(';'):  # set bearing
                                        requested = safe_int(command[3:-1], -1)
                                    elif command == b'AM1;' and 0 <= requested <= 360:  # move rotator
                                        await self._rotator.set_rotator_bearing(requested)
        except Exception as exc:
            logging.exception('exception in serve_serial_client:', 'RotatorTelnetServer:serve_serial_client', exc_info=exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as exc:
                logging.exception('exception closing serial client:', 'RotatorTelnetServer:serve_serial_client', exc_info=exc)
            gc.collect()
        logging.info(f'serial client disconnected, elapsed time {elapsed_ms(t0) / 1000.0:6.3f} seconds',
                     'RotatorTelnetServer:serve_serial_client')


# noinspection PyUnusedLocal
@http_server.route(b'/')
async def slash_callback(http, verb, args, reader, writer, request_headers=None):  # callback for '/'
    http_status = HTTP_STATUS_MOVED_PERMANENTLY
    bytes_sent = await http.send_simple_response(writer, http_status, None, None, [b'Location: /rotator.html'])
    return bytes_sent, http_status


# noinspection PyUnusedLocal
@http_server.route(b'/api/config')
async def api_config_callback(http, verb, args, reader, writer, request_headers=None):  # callback for '/api/config'
    if verb == HTTP_VERB_GET:
        payload = config.get_data().copy()
        payload.pop('secret')  # do not return the secret in the api response.
        http_status = HTTP_STATUS_OK
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, payload)
    elif verb == HTTP_VERB_POST:
        errors = []
        tcp_port_1 = safe_int(args.get('tcp_port_1'), -2)
        tcp_port_2 = safe_int(args.get('tcp_port_2'), -2)
        web_port = safe_int(args.get('web_port'), -2)
        if 0 <= tcp_port_1 <= 65535:
            config['tcp_port_1'] = tcp_port_1
        else:
            errors.append(b'tcp_port_1')
        if 0 <= tcp_port_2 <= 65535:
            config['tcp_port_2'] = tcp_port_2
        else:
            errors.append(b'tcp_port_2')
        if 0 <= web_port <= 65535:
            config['web_port'] = web_port
        else:
            errors.append(b'web_port')
        # a port of zero means that rotor's tcp service is disabled; it cannot collide with anything.
        effective_tcp_port_1 = tcp_port_1 if 1 <= tcp_port_1 <= 65535 else None
        effective_tcp_port_2 = tcp_port_2 if 1 <= tcp_port_2 <= 65535 else None
        effective_web_port = web_port if 1 <= web_port <= 65535 else DEFAULT_WEB_PORT
        if effective_tcp_port_1 is not None and effective_tcp_port_1 == effective_web_port:
            errors.append(b'tcp_port_1 (collides with web_port)')
        if effective_tcp_port_2 is not None and \
                effective_tcp_port_2 in (effective_tcp_port_1, effective_web_port):
            errors.append(b'tcp_port_2 (collides with tcp_port_1 or web_port)')
        ssid = args.get('SSID')
        if ssid is not None:
            if 0 < len(ssid) < 64:
                config['SSID'] = ssid
            else:
                errors.append(b'SSID')
        secret = args.get('secret')
        if secret is not None and len(secret) != 0:
            if 8 <= len(secret) < 32:
                config['secret'] = secret
            else:
                errors.append(b'secret')
        config['ap_mode'] = False
        n1mm_arg = args.get('n1mm')
        if n1mm_arg is not None:
            n1mm = n1mm_arg == 1
            config['n1mm'] = n1mm
        dhcp_arg = args.get('dhcp')
        if dhcp_arg is not None:
            dhcp = dhcp_arg == 1
            config['dhcp'] = dhcp
        hostname_arg = args.get('hostname')
        if hostname_arg is not None:
            if 0 <= len(hostname_arg) < 16:
                config['hostname'] = hostname_arg
            else:
                errors.append(b'hostname')
        rotor_1_name = args.get('rotor_1_name')
        if rotor_1_name is not None:
            if isinstance(rotor_1_name, str) and 1 <= len(rotor_1_name) <= 16 and \
                    not any(ch in ' \t\r\n\f' for ch in rotor_1_name):
                config['rotor_1_name'] = rotor_1_name
            else:
                errors.append(b'rotor_1_name')
        rotor_1_primitive = args.get('rotor_1_primitive')
        if rotor_1_primitive is not None:
            config['rotor_1_primitive'] = rotor_1_primitive == 1
        rotor_2_name = args.get('rotor_2_name')
        if rotor_2_name is not None:
            if isinstance(rotor_2_name, str) and len(rotor_2_name) <= 16:
                config['rotor_2_name'] = rotor_2_name
            else:
                errors.append(b'rotor_2_name')
        rotor_2_primitive = args.get('rotor_2_primitive')
        if rotor_2_primitive is not None:
            config['rotor_2_primitive'] = rotor_2_primitive == 1
        ip_address = args.get('ip_address')
        if ip_address is not None:
            if is_ipv4(ip_address):
                config['ip_address'] = ip_address
            else:
                errors.append(b'ip_address')
        netmask = args.get('netmask')
        if netmask is not None:
            if is_ipv4(netmask):
                config['netmask'] = netmask
            else:
                errors.append(b'netmask')
        gateway = args.get('gateway')
        if gateway is not None:
            if is_ipv4(gateway):
                config['gateway'] = gateway
            else:
                errors.append(b'gateway')
        dns_server = args.get('dns_server')
        if dns_server is not None:
            if is_ipv4(dns_server):
                config['dns_server'] = dns_server
            else:
                errors.append(b'dns_server')
        if not errors:
            response = b'ok\r\n'
            http_status = HTTP_STATUS_OK
            bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        else:
            response = b'parameter(s) out of range\r\n' + b', '.join(errors) + b'\r\n'
            http_status = HTTP_STATUS_BAD_REQUEST
            bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        response = b'GET or PUT only.'
        http_status = HTTP_STATUS_BAD_REQUEST
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
@http_server.route(b'/api/restart')
async def api_restart_callback(http, verb, args, reader, writer, request_headers=None):
    global keep_running
    if upython:
        keep_running = False
        response = b'ok\r\n'
        http_status = HTTP_STATUS_OK
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        http_status = HTTP_STATUS_BAD_REQUEST
        response = b'not permitted except on PICO-W'
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status


# rotator web actions
# noinspection PyUnusedLocal
@http_server.route(b'/api/bearing')
async def api_bearing_callback(http, verb, args, reader, writer, request_headers=None):
    requested_bearing = args.get('set')
    rotor_number = args.get('rotor', '1')
    if rotor_number == '1':
        rotator = rotator_1
        rotor_name = config.get_bytes('rotor_1_name')
    elif rotor_number == '2':
        rotator = rotator_2
        rotor_name = config.get_bytes('rotor_2_name')
    else:
        response = b'parameter out of range\r\n'
        http_status = HTTP_STATUS_BAD_REQUEST
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        return bytes_sent, http_status

    if requested_bearing is not None and requested_bearing != '':
        try:
            requested_bearing = int(requested_bearing)
            if 0 <= requested_bearing <= 360:
                bearing = await rotator.set_rotator_bearing(requested_bearing)
                http_status = HTTP_STATUS_OK
                response = b'{\r\n  "bearing": %d,\r\n  "rotor": "%s"\r\n}\r\n' % (bearing, rotor_name)
                bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
            else:
                http_status = HTTP_STATUS_BAD_REQUEST
                response = b'parameter out of range\r\n'
                bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        except Exception as ex:
            http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
            response = b'uh oh: %s' % str(ex).encode()
            bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        bearing = await rotator.get_rotator_bearing()
        http_status = HTTP_STATUS_OK
        response = b'{\r\n  "bearing": %d,\r\n  "rotor": "%s"\r\n}\r\n' % (bearing, rotor_name)
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status


async def main():
    global config, keep_running, picow_network, rotator_1, rotator_2

    if reset_button.value() == 0:
        # device was powered up with button pressed, select AP mode.
        config['ap_mode'] = True

    rotator_1 = Rotator('0', config.get('rotor_1_primitive'))
    rotator_2 = Rotator('1', config.get('rotor_2_primitive'))

    if upython:
        picow_network = PicowNetwork(config, DEFAULT_SSID, DEFAULT_SECRET)
        morse_code_sender = MorseCode(morse_led)
    else:
        picow_network = None
        morse_code_sender = None

    # a port of zero means the rotor's tcp service is disabled; missing/invalid values fall back to defaults.
    tcp_port_1 = safe_int(config.get('tcp_port_1', DEFAULT_TCP_PORT_1), DEFAULT_TCP_PORT_1)
    if not 0 <= tcp_port_1 <= 65535:
        tcp_port_1 = DEFAULT_TCP_PORT_1
    tcp_port_2 = safe_int(config.get('tcp_port_2', DEFAULT_TCP_PORT_2), DEFAULT_TCP_PORT_2)
    if not 0 <= tcp_port_2 <= 65535:
        tcp_port_2 = DEFAULT_TCP_PORT_2
    web_port = safe_int(config.get('web_port') or DEFAULT_WEB_PORT, DEFAULT_WEB_PORT)
    if web_port < 0 or web_port > 65535:
        web_port = DEFAULT_WEB_PORT

    connected = False
    last_connected = False
    n1mm_sender = None
    n1mm_receiver = None
    web_server = None
    tcp1_server = None
    tcp2_server = None
    last_message = b''
    ap_mode = config.get('ap_mode', False)
    while keep_running:
        await asyncio.sleep(1.0)
        last_connected = connected
        try:
            if picow_network is not None:
                connected = picow_network.is_connected()
                if not connected:
                    logging.debug('waiting for picow network', 'main:main')
            else:
                connected = True

            if connected and not last_connected: # just connected.
                try:
                    if picow_network is not None:
                        ip_address = picow_network.get_ip_address()
                        netmask = picow_network.get_netmask()
                    else:
                        ip_address = socket.gethostbyname_ex(socket.gethostname())[2][-1]
                        netmask = '255.255.255.0'
                    logging.info(f'ip_address {ip_address}, netmask {netmask}', 'main:main')

                    logging.info(f'Starting web service on port {web_port}', 'main:main')
                    web_server = await asyncio.start_server(http_server.serve_http_client, '0.0.0.0', web_port)
                    if tcp_port_1 > 0:
                        logging.info(f'Starting rotator 1 tcp service on port {tcp_port_1}', 'main:main')
                        tcp1_server = await asyncio.start_server(RotatorTelnetServer(rotator_1).serve_serial_client,
                                                                 '0.0.0.0', tcp_port_1)
                    else:
                        logging.info('rotor 1 tcp service disabled (port 0)', 'main:main')
                    if tcp_port_2 > 0:
                        logging.info(f'Starting rotator 2 tcp service on port {tcp_port_2}', 'main:main')
                        tcp2_server = await asyncio.start_server(RotatorTelnetServer(rotator_2).serve_serial_client,
                                                                 '0.0.0.0', tcp_port_2)
                    else:
                        logging.info('rotor 2 tcp service disabled (port 0)', 'main:main')
                    n1mm_mode = config.get('n1mm')
                    if n1mm_mode and not ap_mode:
                        rotator_1_data = RotatorData(rotator_1, config.get_bytes('rotor_1_name'))
                        rotator_2_data = RotatorData(rotator_2, config.get_bytes('rotor_2_name'))
                        rotators_data = [rotator_1_data, rotator_2_data]
                        logging.info(f'configuring N1MM Mode with ip address {ip_address} net mask {netmask}',
                                     'main:main')
                        broadcast_address = calculate_broadcast_address(ip_address, netmask)
                        logging.info(f'Broadcast address (to N1MM) is {broadcast_address}', 'main:main')
                        logging.info(f'Starting rotor position broadcasts for N1MM on port {N1MM_BROADCAST_FROM_ROTOR_PORT}',
                                     'main:main')
                        send_broadcast_from_n1mm = SendBroadcastsToN1MM(broadcast_address,
                                                                        target_port=N1MM_BROADCAST_FROM_ROTOR_PORT,
                                                                        rotators_data=rotators_data)
                        logging.info(f'Starting listener for UDP position broadcasts from N1MM on port {N1MM_ROTOR_BROADCAST_PORT}',
                                     'main:main')
                        receive_broadcast_from_n1mm = ReceiveBroadcastsFromN1MM(ip_address,
                                                                                receive_port=N1MM_ROTOR_BROADCAST_PORT,
                                                                                rotators_data=rotators_data)
                        n1mm_sender = asyncio.create_task(send_broadcast_from_n1mm.send_datagrams())
                        n1mm_receiver = asyncio.create_task(receive_broadcast_from_n1mm.wait_for_datagram())
                except Exception as ex:
                    logging.exception(f'failed to start services', 'main:main', ex)

            elif not connected and last_connected: # just disconnected
                logging.info('network lost, stopping services', 'main:main')
                for server in (web_server, tcp1_server, tcp2_server):
                    if server is not None:
                        server.close()
                web_server = tcp1_server = tcp2_server = None
                if n1mm_sender is not None:
                    n1mm_sender.cancel()
                    n1mm_sender = None
                if n1mm_receiver is not None:
                    n1mm_receiver.cancel()
                    n1mm_receiver = None

            if picow_network is not None and picow_network.get_message() != last_message:
                last_message = picow_network.get_message()
                morse_code_sender.set_message(last_message)

        except Exception as ex:
            logging.exception(f'main loop error', 'main:main', ex)

        gc.collect()
        if logging.should_log(logging.DEBUG) and upython:
            free = gc.mem_free()
            alloc = gc.mem_alloc()
            logging.debug(f'Memory: {alloc} allocated, {free} free ({free / (free + alloc) * 100:6.2f}% free)')

    if upython:
        if config is not None:
            config.flush()
        machine.soft_reset()


if __name__ == '__main__':
    logging.loglevel = logging.INFO
    # logging.loglevel = logging.DEBUG
    logging.info('starting', 'main:__main__')

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('bye', 'main:main')
    finally:
        logging.info('finally', 'main:__main__')
    if picow_network is not None:
        picow_network.deinit()
    if config is not None:
        config.flush()
    logging.info('done', 'main:main')
