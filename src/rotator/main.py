#
# main.py -- this is the web server for the Raspberry Pi Pico W Web Rotator Controller.
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, 2025, J. B. Otterson N1KDO.
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
__version__ = '0.1.0'

import asyncio
import gc
import json
import socket
import micro_logging as logging

from http_server import (HttpServer,
                         api_rename_file_callback,
                         api_remove_file_callback,
                         api_upload_file_callback,
                         api_get_files_callback,
                         HTTP_VERB_GET, HTTP_VERB_POST)
from morse_code import MorseCode
import n1mm_udp
from dcu1_rotator import Rotator
from utils import milliseconds, safe_int, upython
from picow_network import PicowNetwork

if upython:
    # disable pylint import error
    # pylint: disable=E0401
    from machine import Pin
else:
    from not_machine import machine

# noinspection PyUnboundLocalVariable
onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
onboard.on()
morse_led = machine.Pin(2, machine.Pin.OUT, value=0)  # status LED
reset_button = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_UP)

CONFIG_FILE = 'data/config.json'
CONTENT_DIR = 'content/'
DEFAULT_SECRET = 'NorthSouth'
DEFAULT_SSID = 'Rotator'
DEFAULT_TCP_PORT = 73
DEFAULT_WEB_PORT = 80

N1MM_ROTOR_BROADCAST_PORT = 12040
N1MM_BROADCAST_FROM_ROTOR_PORT = 13010

# globals
keep_running = True
rotator = None


def read_config():
    try:
        with open(CONFIG_FILE, 'r') as config_file:
            config = json.load(config_file)
    except Exception as ex:
        logging.exception('failed to load configuration, using default...',
                          'main:read_config', exc_info= ex)
        config = {
            'SSID': 'set your SSID here',
            'secret': 'secret', 
            'dhcp': True,
            'ip_address': '192.168.1.73',
            'netmask': '255.255.255.0',
            'gateway': '192.168.1.1',
            'dns_server': '8.8.8.8',
            'hostname': 'rotator',
            'n1mm': False,
            'tcp_port': '73',
            'web_port': '80',
        }
    return config


def save_config(config):
    with open(CONFIG_FILE, 'w') as config_file:
        json.dump(config, config_file)


async def serve_serial_client(reader, writer):
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
            if data is None:
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
                                command = ''.join(map(chr, buffer))
                                if command in ('AI1;', 'AI1\r'):  # get direction
                                    bearing = await rotator.get_rotator_bearing()
                                    response = f';{bearing:03n}'
                                    writer.write(response.encode('UTF-8'))
                                    await writer.drain()
                                elif command.startswith('AP1') and command[-1] == '\r':  # set bearing and move rotator
                                    requested = safe_int(command[3:-1], -1)
                                    if 0 <= requested <= 360:
                                        await rotator.set_rotator_bearing(requested)
                                elif command.startswith('AP1') and command[-1] == ';':  # set bearing
                                    requested = safe_int(command[3:-1], -1)
                                elif command == 'AM1;' and 0 <= requested <= 360:  # move rotator
                                    await rotator.set_rotator_bearing(requested)
        writer.close()
        await writer.wait_closed()
        gc.collect()

    except Exception as exc:
        logging.exception('exception in serve_serial_client:', 'main:serve_serial_client', exc_info=exc)
    tc = milliseconds()
    logging.info(f'serial client disconnected, elapsed time {(tc - t0) / 1000.0:6.3f} seconds',
                 'main:serve_serial_client')


# noinspection PyUnusedLocal
async def slash_callback(http, verb, args, reader, writer, request_headers=None):  # callback for '/'
    http_status = 301
    bytes_sent = await http.send_simple_response(writer, http_status, None, None, ['Location: /rotator.html'])
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_config_callback(http, verb, args, reader, writer, request_headers=None):  # callback for '/api/config'
    if verb == HTTP_VERB_GET:
        payload = read_config()
        # payload.pop('secret')  # do not return the secret
        response = json.dumps(payload).encode('utf-8')
        http_status = 200
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    elif verb == HTTP_VERB_POST:
        config = read_config()
        dirty = False
        errors = False
        tcp_port = args.get('tcp_port')
        if tcp_port is not None:
            tcp_port_int = safe_int(tcp_port, -2)
            if 0 <= tcp_port_int <= 65535:
                config['tcp_port'] = tcp_port
                dirty = True
            else:
                errors = True
        web_port = args.get('web_port')
        if web_port is not None:
            web_port_int = safe_int(web_port, -2)
            if 0 <= web_port_int <= 65535:
                config['web_port'] = web_port
                dirty = True
            else:
                errors = True
        ssid = args.get('SSID')
        if ssid is not None:
            if 0 < len(ssid) < 64:
                config['SSID'] = ssid
                dirty = True
            else:
                errors = True
        secret = args.get('secret')
        if secret is not None:
            if 8 <= len(secret) < 32:
                config['secret'] = secret
                dirty = True
            else:
                errors = True
        remote_username = args.get('username')
        if remote_username is not None:
            if 1 <= len(remote_username) <= 16:
                config['username'] = remote_username
                dirty = True
            else:
                errors = True
        remote_password = args.get('password')
        if remote_password is not None:
            if 1 <= len(remote_password) <= 16:
                config['password'] = remote_password
                dirty = True
            else:
                errors = True
        ap_mode_arg = args.get('ap_mode')
        if ap_mode_arg is not None:
            ap_mode = ap_mode_arg == '1'
            config['ap_mode'] = ap_mode
            dirty = True
        n1mm_arg = args.get('n1mm')
        if n1mm_arg is not None:
            n1mm = n1mm_arg == 1
            config['n1mm'] = n1mm
            dirty = True
        dhcp_arg = args.get('dhcp')
        if dhcp_arg is not None:
            dhcp = dhcp_arg == 1
            config['dhcp'] = dhcp
            dirty = True
        hostname = args.get('hostname')
        if hostname is not None:
            config['hostname'] = hostname
            dirty = True
        ip_address = args.get('ip_address')
        if ip_address is not None:
            config['ip_address'] = ip_address
            dirty = True
        netmask = args.get('netmask')
        if netmask is not None:
            config['netmask'] = netmask
            dirty = True
        gateway = args.get('gateway')
        if gateway is not None:
            config['gateway'] = gateway
            dirty = True
        dns_server = args.get('dns_server')
        if dns_server is not None:
            config['dns_server'] = dns_server
            dirty = True
        if not errors:
            if dirty:
                save_config(config)
            response = b'ok\r\n'
            http_status = 200
            bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        else:
            response = b'parameter out of range\r\n'
            http_status = 400
            bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        response = b'GET or PUT only.'
        http_status = 400
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_restart_callback(http, verb, args, reader, writer, request_headers=None):
    global keep_running
    if upython:
        keep_running = False
        response = b'ok\r\n'
        http_status = 200
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        http_status = 400
        response = b'not permitted except on PICO-W'
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status


# rotator web actions
# noinspection PyUnusedLocal
async def api_bearing_callback(http, verb, args, reader, writer, request_headers=None):
    requested_bearing = args.get('set')
    if requested_bearing:
        try:
            requested_bearing = int(requested_bearing)
            if 0 <= requested_bearing <= 360:
                bearing = await rotator.set_rotator_bearing(requested_bearing)
                http_status = 200
                response = f'{bearing}\r\n'.encode('utf-8')
                bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
            else:
                http_status = 400
                response = b'parameter out of range\r\n'
                bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        except Exception as ex:
            http_status = 500
            response = f'uh oh: {ex}'.encode('utf-8')
            bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        bearing = await rotator.get_rotator_bearing()
        http_status = 200
        response = f'{bearing}\r\n'.encode('utf-8')
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


async def main():
    global keep_running, rotator

    config = read_config()

    rotator = Rotator()

    http_server = HttpServer(content_dir='content/')
    http_server.add_uri_callback(b'/', slash_callback)
    http_server.add_uri_callback(b'/api/config', api_config_callback)
    http_server.add_uri_callback(b'/api/get_files', api_get_files_callback)
    http_server.add_uri_callback(b'/api/upload_file', api_upload_file_callback)
    http_server.add_uri_callback(b'/api/remove_file', api_remove_file_callback)
    http_server.add_uri_callback(b'/api/rename_file', api_rename_file_callback)
    http_server.add_uri_callback(b'/api/restart', api_restart_callback)
    # rotator specific
    http_server.add_uri_callback(b'/api/bearing', api_bearing_callback)

    if upython:
        picow_network = PicowNetwork(config, DEFAULT_SSID, DEFAULT_SECRET)
        morse_code_sender = MorseCode(morse_led)
        morse_code_sender_task = asyncio.create_task(morse_code_sender.morse_sender())
    else:
        picow_network = None
        morse_code_sender = None
        morse_code_sender_task = None

    tcp_port = safe_int(config.get('tcp_port') or DEFAULT_TCP_PORT, DEFAULT_TCP_PORT)
    if tcp_port < 0 or tcp_port > 65535:
        tcp_port = DEFAULT_TCP_PORT
    web_port = safe_int(config.get('web_port') or DEFAULT_WEB_PORT, DEFAULT_WEB_PORT)
    if web_port < 0 or web_port > 65535:
        web_port = DEFAULT_WEB_PORT

    connected = False
    newly_connected = False
    reset_button_pressed_count = 0
    four_count = 0
    last_message = ''
    ap_mode = config.get('ap_mode', False)
    while keep_running:
        await asyncio.sleep(0.25)
        four_count += 1
        if four_count > 3:
            four_count = 0
            if picow_network is not None:
                if not connected:
                    logging.debug('checking network connection', 'main:main')
                    connected = picow_network.is_connected()
                    if connected:
                        logging.info('network connection established', 'main:main')
                        ip_address = picow_network.get_ip_address()
                        netmask = picow_network.get_netmask()
                        newly_connected = True
                    else:
                        logging.info('waiting for picow network', 'main:main')

                else: # is connected, look for disconnect
                    connected = picow_network.is_connected()
                    if not connected:
                        logging.info('network connection disconnected', 'main:main')
            else:
                ip_address = socket.gethostbyname_ex(socket.gethostname())[2][-1]
                netmask = '255.255.255.0'
                connected = True
                newly_connected = True

            if picow_network is not None and picow_network.get_message() != last_message:
                last_message = picow_network.get_message()
                morse_code_sender.set_message(last_message)

        if newly_connected:
            newly_connected = False
            logging.info(f'Starting web service on port {web_port}', 'main:main')
            asyncio.create_task(asyncio.start_server(http_server.serve_http_client, '0.0.0.0', web_port))
            logging.info(f'Starting tcp service on port {tcp_port}', 'main:main')
            asyncio.create_task(asyncio.start_server(serve_serial_client, '0.0.0.0', tcp_port))

            n1mm_mode = config.get('n1mm')
            if n1mm_mode and not ap_mode:
                hostname = config.get('hostname')
                broadcast_address = n1mm_udp.calculate_broadcast_address(ip_address, netmask)
                logging.info(f'My broadcast address (to N1MM) is {broadcast_address}', 'main:main')
                logging.info(f'Starting rotor position broadcasts for N1MM on port {N1MM_BROADCAST_FROM_ROTOR_PORT}',
                             'main:main')
                send_broadcast_from_n1mm = n1mm_udp.SendBroadcastFromN1MM(broadcast_address,
                                                                          target_port=N1MM_BROADCAST_FROM_ROTOR_PORT,
                                                                          rotator=rotator,
                                                                          my_name=hostname)
                logging.info(f'Starting listener for UDP position broadcasts from N1MM on port {N1MM_ROTOR_BROADCAST_PORT}',
                             'main:main')
                receive_broadcast_from_n1mm = n1mm_udp.ReceiveBroadcastsFromN1MM(ip_address,
                                                                                 receive_port=N1MM_ROTOR_BROADCAST_PORT,
                                                                                 rotator=rotator,
                                                                                 my_name=hostname)
                n1mm_sender = asyncio.create_task(send_broadcast_from_n1mm.send_datagrams())
                n1mm_receiver = asyncio.create_task(receive_broadcast_from_n1mm.wait_for_datagram())

        if upython:
            pressed = reset_button.value() == 0
            if pressed:
                reset_button_pressed_count += 1
            else:
                if reset_button_pressed_count > 0:
                    reset_button_pressed_count -= 1
            if reset_button_pressed_count > 7:

                logging.info('reset button pressed', 'main:main')
                ap_mode = not ap_mode
                config['ap_mode'] = ap_mode
                save_config(config)
                keep_running = False

    if upython:
        machine.soft_reset()


if __name__ == '__main__':
    logging.loglevel = logging.INFO  # DEBUG
    logging.loglevel = logging.DEBUG
    logging.info('starting', 'main:__main__')

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info('bye', 'main:main')
    finally:
        asyncio.new_event_loop()
    logging.info('done', 'main:main')
