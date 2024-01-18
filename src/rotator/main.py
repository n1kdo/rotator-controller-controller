#
# main.py -- this is the web server for the Raspberry Pi Pico W Web Rotator Controller.
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, J. B. Otterson N1KDO.
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

# disable pylint import error
# pylint: disable=E0401

import gc
import json
import os
import re
import sys
import time

from http_server import HttpServer
from morse_code import MorseCode
from dcu1_rotator import Rotator
import n1mm_udp

upython = sys.implementation.name == 'micropython'

# disable pylint import error
# pylint: disable=E0401

if upython:
    import network
    from machine import Pin
    import uasyncio as asyncio
    network_status_map = {
        network.STAT_IDLE: 'no connection and no activity',  # 0
        network.STAT_CONNECTING: 'connecting in progress',  # 1
        network.STAT_CONNECTING+1: 'connected no IP address',  # 2, this is undefined, but returned.
        network.STAT_GOT_IP: 'connection successful',  # 3
        network.STAT_WRONG_PASSWORD: 'failed due to incorrect password',  # -3
        network.STAT_NO_AP_FOUND: 'failed because no access point replied',  # -2
        network.STAT_CONNECT_FAIL: 'failed due to other problems',  # -1
        }
else:
    import asyncio
    import socket


    class Machine:
        """
        fake micropython stuff
        """

        @staticmethod
        def soft_reset():
            print('Machine.soft_reset()')

        @staticmethod
        def reset():
            print('Machine.reset()')

        class Pin:
            OUT = 1
            IN = 0
            PULL_UP = 0

            def __init__(self, name, options=0, value=0):
                self.name = name
                self.options = options
                self.state = value

            def on(self):
                self.state = 1

            def off(self):
                self.state = 0

            def value(self):
                return self.state

    machine = Machine()

# noinspection PyUnboundLocalVariable
onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
onboard.on()
morse_led = machine.Pin(2, machine.Pin.OUT, value=0)  # status LED
reset_button = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_UP)

BUFFER_SIZE = 4096
CONFIG_FILE = 'data/config.json'
CONTENT_DIR = 'content/'
DANGER_ZONE_FILE_NAMES = [
    'config.html',
    'files.html',
    'rotator.html',
]
DEFAULT_SECRET = 'NorthSouth'
DEFAULT_SSID = 'Rotator'
DEFAULT_TCP_PORT = 73
DEFAULT_WEB_PORT = 80

N1MM_ROTOR_BROADCAST_PORT = 12040
N1MM_BROADCAST_FROM_ROTOR_PORT = 13010

# globals
restart = False
http_server = HttpServer(content_dir='content/')
morse_code_sender = MorseCode(morse_led)
rotator = Rotator()


def read_config():
    try:
        with open(CONFIG_FILE, 'r') as config_file:
            config = json.load(config_file)
    except Exception as ex:
        print('failed to load configuration, using default...', type(ex), ex)
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


def safe_int(value, default=-1):
    if isinstance(value, int):
        return value
    return int(value) if value.isdigit() else default


def milliseconds():
    # disable pylint no-member, time.ticks_ms() is only Micropython.
    # pylint: disable=E1101
    if upython:
        return time.ticks_ms()
    return int(time.time() * 1000)


def valid_filename(filename):
    if filename is None:
        return False
    match = re.match('^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?.[a-zA-Z0-9_-]+$', filename)
    if match is None:
        return False
    if match.group(0) != filename:
        return False
    extension = filename.split('.')[-1].lower()
    if HttpServer.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension) is None:
        return False
    return True


def connect_to_network(config):
    network.country('US')
    ssid = config.get('SSID') or ''
    if len(ssid) == 0 or len(ssid) > 64:
        ssid = DEFAULT_SSID
    secret = config.get('secret') or ''
    if len(secret) > 64:
        secret = ''
    access_point_mode = config.get('ap_mode') or False

    if access_point_mode:
        print('Starting setup WLAN...')
        wlan = network.WLAN(network.AP_IF)
        wlan.active(False)
        wlan.config(pm=0xa11140)  # disable power save, this is a server.

        hostname = config.get('hostname')
        if hostname is not None:
            try:
                network.hostname(hostname)
            except ValueError:
                print('could not set hostname.')

        # wlan.ifconfig(('10.0.0.1', '255.255.255.0', '0.0.0.0', '0.0.0.0'))

        """
        #define CYW43_AUTH_OPEN (0)                     ///< No authorisation required (open)
        #define CYW43_AUTH_WPA_TKIP_PSK   (0x00200002)  ///< WPA authorisation
        #define CYW43_AUTH_WPA2_AES_PSK   (0x00400004)  ///< WPA2 authorisation (preferred)
        #define CYW43_AUTH_WPA2_MIXED_PSK (0x00400006)  ///< WPA2/WPA mixed authorisation
        """
        ssid = DEFAULT_SSID
        secret = DEFAULT_SECRET
        if len(secret) == 0:
            security = 0
        else:
            security = 0x00400004  # CYW43_AUTH_WPA2_AES_PSK
        wlan.config(ssid=ssid, key=secret, security=security)
        wlan.active(True)
        print(wlan.active())
        print(f'ssid={wlan.config("ssid")}')
    else:
        print('Connecting to WLAN...')
        wlan = network.WLAN(network.STA_IF)
        wlan.config(pm=0xa11140)  # disable power save, this is a server.

        hostname = config.get('hostname')
        if hostname is not None:
            try:
                print(f'setting hostname {hostname}')
                network.hostname(hostname)
            except ValueError:
                print('hostname is still not supported on Pico W')

        is_dhcp = config.get('dhcp') or True
        if not is_dhcp:
            ip_address = config.get('ip_address')
            netmask = config.get('netmask')
            gateway = config.get('gateway')
            dns_server = config.get('dns_server')
            if ip_address is not None and netmask is not None and gateway is not None and dns_server is not None:
                print('configuring network with static IP')
                wlan.ifconfig((ip_address, netmask, gateway, dns_server))
            else:
                print('cannot use static IP, data is missing, configuring network with DHCP')
                wlan.ifconfig('dhcp')
        else:
            print('configuring network with DHCP')
            # wlan.ifconfig('dhcp')  #  this does not work.  network does not come up.  no errors, either.

        wlan.active(True)
        max_wait = 10
        wl_status = wlan.status()
        print('connecting...')
        wlan.connect(ssid, secret)
        while max_wait > 0:
            wl_status = wlan.status()
            st = network_status_map.get(wl_status) or 'undefined'
            print(f'network status: {wl_status} {st}')
            if wl_status < 0 or wl_status >= 3:
                break
            max_wait -= 1
            time.sleep(1)
        if wl_status != network.STAT_GOT_IP:
            morse_code_sender.set_message('ERR')
            # return None
            raise RuntimeError(f'Network connection failed, status={wl_status}')

    wl_config = wlan.ifconfig()
    ip_address = wl_config[0]
    netmask = wl_config[1]
    message = f'AP {ip_address} ' if access_point_mode else f'{ip_address} '
    message = message.replace('.', ' ')
    morse_code_sender.set_message(message)
    print(message)
    return ip_address, netmask


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
    print(f'\nserial client connected from {partner}')
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

    except Exception as ex:
        print('exception in serve_serial_client:', type(ex), ex)
    tc = milliseconds()
    print(f'serial client disconnected, elapsed time {(tc - t0) / 1000.0:6.3f} seconds')


# noinspection PyUnusedLocal
async def slash_callback(http, verb, args, reader, writer, request_headers=None):  # callback for '/'
    http_status = 301
    bytes_sent = http.send_simple_response(writer, http_status, None, None, ['Location: /rotator.html'])
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_config_callback(http, verb, args, reader, writer, request_headers=None):  # callback for '/api/config'
    if verb == 'GET':
        payload = read_config()
        # payload.pop('secret')  # do not return the secret
        response = json.dumps(payload).encode('utf-8')
        http_status = 200
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    elif verb == 'POST':
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
            bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        else:
            response = b'parameter out of range\r\n'
            http_status = 400
            bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        response = b'GET or PUT only.'
        http_status = 400
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_get_files_callback(http, verb, args, reader, writer, request_headers=None):
    if verb == 'GET':
        payload = os.listdir(http.content_dir)
        response = json.dumps(payload).encode('utf-8')
        http_status = 200
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    else:
        http_status = 400
        response = b'only GET permitted'
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_upload_file_callback(http, verb, args, reader, writer, request_headers=None):
    if verb == 'POST':
        boundary = None
        request_content_type = request_headers.get('content-type') or ''
        if ';' in request_content_type:
            pieces = request_content_type.split(';')
            request_content_type = pieces[0]
            boundary = pieces[1].strip()
            if boundary.startswith('boundary='):
                boundary = boundary[9:]
        if request_content_type != http.CT_MULTIPART_FORM or boundary is None:
            response = b'multipart boundary or content type error'
            http_status = 400
        else:
            response = b'unhandled problem'
            http_status = 500
            request_content_length = int(request_headers.get('content-length') or '0')
            remaining_content_length = request_content_length
            start_boundary = http.HYPHENS + boundary
            end_boundary = start_boundary + http.HYPHENS
            state = http.MP_START_BOUND
            filename = None
            output_file = None
            writing_file = False
            more_bytes = True
            leftover_bytes = []
            while more_bytes:
                buffer = await reader.read(BUFFER_SIZE)
                remaining_content_length -= len(buffer)
                if remaining_content_length == 0:  # < BUFFER_SIZE:
                    more_bytes = False
                if len(leftover_bytes) != 0:
                    buffer = leftover_bytes + buffer
                    leftover_bytes = []
                start = 0
                while start < len(buffer):
                    if state == http.MP_DATA:
                        if not output_file:
                            output_file = open(http.content_dir + 'uploaded_' + filename, 'wb')
                            writing_file = True
                        end = len(buffer)
                        for i in range(start, len(buffer) - 3):
                            if buffer[i] == 13 and buffer[i + 1] == 10 and buffer[i + 2] == 45 and \
                                    buffer[i + 3] == 45:
                                end = i
                                writing_file = False
                                break
                        if end == BUFFER_SIZE:
                            if buffer[-1] == 13:
                                leftover_bytes = buffer[-1:]
                                buffer = buffer[:-1]
                                end -= 1
                            elif buffer[-2] == 13 and buffer[-1] == 10:
                                leftover_bytes = buffer[-2:]
                                buffer = buffer[:-2]
                                end -= 2
                            elif buffer[-3] == 13 and buffer[-2] == 10 and buffer[-1] == 45:
                                leftover_bytes = buffer[-3:]
                                buffer = buffer[:-3]
                                end -= 3
                        output_file.write(buffer[start:end])
                        if not writing_file:
                            # print('closing file')
                            state = http.MP_END_BOUND
                            output_file.close()
                            output_file = None
                            response = f'Uploaded {filename} successfully'.encode('utf-8')
                            http_status = 201
                        start = end + 2
                    else:  # must be reading headers or boundary
                        line = ''
                        for i in range(start, len(buffer) - 1):
                            if buffer[i] == 13 and buffer[i + 1] == 10:
                                line = buffer[start:i].decode('utf-8')
                                start = i + 2
                                break
                        if state == http.MP_START_BOUND:
                            if line == start_boundary:
                                state = http.MP_HEADERS
                            else:
                                print('expecting start boundary, got ' + line)
                        elif state == http.MP_HEADERS:
                            if len(line) == 0:
                                state = http.MP_DATA
                            elif line.startswith('Content-Disposition:'):
                                pieces = line.split(';')
                                fn = pieces[2].strip()
                                if fn.startswith('filename="'):
                                    filename = fn[10:-1]
                                    if not valid_filename(filename):
                                        response = b'bad filename'
                                        http_status = 500
                                        more_bytes = False
                                        start = len(buffer)
                            # else:
                            #     print('processing headers, got ' + line)
                        elif state == http.MP_END_BOUND:
                            if line == end_boundary:
                                state = http.MP_START_BOUND
                            else:
                                print('expecting end boundary, got ' + line)
                        else:
                            http_status = 500
                            response = f'unmanaged state {state}'.encode('utf-8')
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        response = b'PUT only.'
        http_status = 400
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_remove_file_callback(http, verb, args, reader, writer, request_headers=None):
    filename = args.get('filename')
    if valid_filename(filename) and filename not in DANGER_ZONE_FILE_NAMES:
        filename = http.content_dir + filename
        try:
            os.remove(filename)
            http_status = 200
            response = b'removed\r\n'
        except OSError as ose:
            http_status = 409
            response = str(ose).encode('utf-8')
    else:
        http_status = 409
        response = b'bad file name\r\n'
    bytes_sent = http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)


# noinspection PyUnusedLocal
async def api_rename_file_callback(http, verb, args, reader, writer, request_headers=None):
    filename = args.get('filename')
    newname = args.get('newname')
    if valid_filename(filename) and valid_filename(newname):
        filename = http.content_dir + filename
        newname = http.content_dir + newname
        try:
            os.remove(newname)
        except OSError:
            pass  # swallow exception.
        try:
            os.rename(filename, newname)
            http_status = 200
            response = b'renamed\r\n'
        except Exception as ose:
            http_status = 409
            response = str(ose).encode('utf-8')
    else:
        http_status = 409
        response = b'bad file name'
    bytes_sent = http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_restart_callback(http, verb, args, reader, writer, request_headers=None):
    global restart
    if upython:
        restart = True
        response = b'ok\r\n'
        http_status = 200
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        http_status = 400
        response = b'not permitted except on PICO-W'
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
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
                bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
            else:
                http_status = 400
                response = b'parameter out of range\r\n'
                bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
        except Exception as ex:
            http_status = 500
            response = f'uh oh: {ex}'.encode('utf-8')
            bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        bearing = await rotator.get_rotator_bearing()
        http_status = 200
        response = f'{bearing}\r\n'.encode('utf-8')
        bytes_sent = http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


async def main():
    global restart

    config = read_config()

    http_server.add_uri_callback('/', slash_callback)
    http_server.add_uri_callback('/api/config', api_config_callback)
    http_server.add_uri_callback('/api/get_files', api_get_files_callback)
    http_server.add_uri_callback('/api/upload_file', api_upload_file_callback)
    http_server.add_uri_callback('/api/remove_file', api_remove_file_callback)
    http_server.add_uri_callback('/api/rename_file', api_rename_file_callback)
    http_server.add_uri_callback('/api/restart', api_restart_callback)
    # rotator specific
    http_server.add_uri_callback('/api/bearing', api_bearing_callback)

    tcp_port = safe_int(config.get('tcp_port') or DEFAULT_TCP_PORT, DEFAULT_TCP_PORT)
    if tcp_port < 0 or tcp_port > 65535:
        tcp_port = DEFAULT_TCP_PORT
    web_port = safe_int(config.get('web_port') or DEFAULT_WEB_PORT, DEFAULT_WEB_PORT)
    if web_port < 0 or web_port > 65535:
        web_port = DEFAULT_WEB_PORT
    connected = True
    ap_mode = config.get('ap_mode') or False
    if upython:
        try:
            ip_address, netmask = connect_to_network(config)
            connected = ip_address is not None
        except Exception as ex:
            connected = False
            print(type(ex), ex)
    else:
        ip_address = socket.gethostbyname_ex(socket.gethostname())[2][-1]
        netmask = '255.255.255.0'

    if connected:
        print(f'Starting web service on port {web_port}')
        asyncio.create_task(asyncio.start_server(http_server.serve_http_client, '0.0.0.0', web_port))
        print(f'Starting tcp service on port {tcp_port}')
        asyncio.create_task(asyncio.start_server(serve_serial_client, '0.0.0.0', tcp_port))

        n1mm_mode = config.get('n1mm')
        if n1mm_mode:
            hostname = config.get('hostname')
            broadcast_address = n1mm_udp.calculate_broadcast_address(ip_address, netmask)
            print(f'Starting rotor position broadcasts for N1MM on port {N1MM_BROADCAST_FROM_ROTOR_PORT}')
            send_broadcast_from_n1mm = n1mm_udp.SendBroadcastFromN1MM(broadcast_address,
                                                                      target_port=N1MM_BROADCAST_FROM_ROTOR_PORT,
                                                                      rotator=rotator,
                                                                      my_name=hostname)
            print(f'Starting listener for UDP position broadcasts from N1MM on port {N1MM_ROTOR_BROADCAST_PORT}')
            receive_broadcast_from_n1mm = n1mm_udp.ReceiveBroadcastsFromN1MM(ip_address,
                                                                             receive_port=N1MM_ROTOR_BROADCAST_PORT,
                                                                             rotator=rotator,
                                                                             my_name=hostname)
            n1mm_sender = asyncio.create_task(send_broadcast_from_n1mm.send_datagrams())
            n1mm_receiver = asyncio.create_task(receive_broadcast_from_n1mm.wait_for_datagram())
    else:
        print('no network connection')

    if upython:
        asyncio.create_task(morse_code_sender.morse_sender())

    reset_button_pressed_count = 0
    while True:
        if upython:
            await asyncio.sleep(0.25)
            pressed = reset_button.value() == 0
            if pressed:
                reset_button_pressed_count += 1
                if reset_button_pressed_count > 7:
                    ap_mode = not ap_mode
                    config['ap_mode'] = ap_mode
                    save_config(config)
                    restart = True
            else:
                reset_button_pressed_count = 0

            if restart:
                machine.reset()
        else:
            await asyncio.sleep(1.0)


if __name__ == '__main__':
    print('starting')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('bye')
    finally:
        asyncio.new_event_loop()
    print('done')
