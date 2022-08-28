#
# main.py -- this is the web server for the Raspberry Pi Pico W Web Rotator Controller.
#
__author__ = 'J. B. Otterson'
__copyright__ = "Copyright 2022, J. B. Otterson N1KDO."
#
# Copyright 2022, J. B. Otterson N1KDO.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#  1. Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#  2. Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import os
import sys
import time

upython = sys.implementation.name == 'micropython'

if upython:
    import network
    from machine import Pin
    import uasyncio as asyncio
    from pico_rotator import get_rotator_bearing, set_rotator_bearing
else:
    import asyncio
    from windows_rotator import get_rotator_bearing, set_rotator_bearing

if upython:
    onboard = Pin('LED', Pin.OUT, value=0)
    onboard.on()
    blinky = Pin(2, Pin.OUT, value=0)  # blinky external LED
    button = Pin(3, Pin.IN, Pin.PULL_UP)
    ap_mode = button.value() == 0
    print('read button as {}'.format(button.value()))
    print('ap_mode={}'.format(ap_mode))
else:
    ap_mode = False

HTTP_STATUS_TEXT = {
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    204: 'No Content',
    301: 'Moved Permanently',
    302: 'Moved Temporarily',
    304: 'Not Modified',
    400: 'Bad Request',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Not Found',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
}

CT_TEXT_TEXT = 'text/text'
CT_TEXT_HTML = 'text/html'
CT_APP_JSON = 'application/json'
CT_APP_WWW_FORM = 'application/x-www-form-urlencoded'

FILE_EXTENSION_TO_CONTENT_TYPE_MAP = {
    'gif': 'image/gif',
    'html': CT_TEXT_HTML,
    'ico': 'image/vnd.microsoft.icon',
    'json': CT_APP_JSON,
    'jpeg': 'image/jpeg',
    'jpg': 'image/jpeg',
    'png': 'image/png',
    'txt': CT_TEXT_TEXT,
    '*': 'application/octet-stream',
}
CONFIG_FILE = 'data/config.json'
DEFAULT_SSID = 'Rotator'
DEFAULT_SECRET = 'North'
DEFAULT_TCP_PORT = 73
DEFAULT_WEB_PORT = 80

PERIOD = 0.150  # the speed of the morse code is set by the dit length of 150 ms.
DIT = PERIOD
ESP = DIT  # inter-element space
DAH = 3 * PERIOD
LSP = DAH  # inter-letter space

""" 
patterns are list of ON,OFF durations.  Always an even number!
these are Morse code letters. 
"""
BLINK_PATTERNS = {
    'A': [DIT, ESP, DAH, LSP],  # dit dah
    'C': [DAH, ESP, DIT, ESP, DAH, ESP, DIT, LSP],  # dah dit dah dit
    'E': [DIT, LSP],  # dit
    'I': [DIT, ESP, DIT, LSP],  # dit dit
    'S': [DIT, ESP, DIT, ESP, DIT, LSP],  # dit dit dit
    'H': [DIT, ESP, DIT, ESP, DIT, ESP, DIT, LSP],  # dit dit dit dit
    'O': [DAH, ESP, DAH, ESP, DAH, LSP],  # dah dah dah
    'N': [DAH, ESP, DIT, LSP],  # dah dit
    'D': [DAH, ESP, DIT, ESP, DIT, LSP],  # dah dit dit
    'B': [DAH, ESP, DIT, ESP, DIT, ESP, DIT, LSP],  # dah dit dit dit
}

blink_code = 'O'
restart = False
content_cache = {}


def read_config():
    config = {}
    try:
        with open(CONFIG_FILE, 'r') as config_file:
            config = json.load(config_file)
    except Exception as ex:
        print('failed to load configuration!', type(ex), ex)
    return config


def save_config(config):
    with open(CONFIG_FILE, 'w') as config_file:
        json.dump(config, config_file)


def safe_int(s, default=-1):
    if type(s) == int:
        return s
    else:
        return int(s) if s.isdigit() else default


def milliseconds():
    if upython:
        return time.ticks_ms()
    else:
        return int(time.time() * 1000)


def serve_content(writer, filename):
    BUFFER_SIZE = 4096
    filename = 'content/' + filename
    try:
        content_length = safe_int(os.stat(filename)[6], -1)
    except Exception as stat_exception:
        content_length = -1
    if content_length < 0:
        response = b'<html><body><p>that which you seek is not here.</p></body></html>'
        http_status = 404
        return send_simple_response(writer, http_status, CT_TEXT_HTML, response), http_status
    else:
        extension = filename.split('.')[-1]
        content_type = FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension)
        if content_type is None:
            content_type = FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get('*')
        http_status = 200
        start_response(writer, 200, content_type, content_length)
        try:
            with open(filename, 'rb', BUFFER_SIZE) as infile:
                while True:
                    buffer = infile.read(BUFFER_SIZE)
                    writer.write(buffer)
                    if len(buffer) < BUFFER_SIZE:
                        break
        except Exception as e:
            print(type(e), e)
        return content_length, http_status


def start_response(writer, http_status=200, response_content_type=None, response_size=0, response_extra_headers=[]):
    status_text = HTTP_STATUS_TEXT.get(http_status) or 'Confused'
    protocol = 'HTTP/1.0'
    writer.write('{} {} {}\r\n'.format(protocol, http_status, status_text).encode('utf-8'))
    if response_content_type is not None and len(response_content_type) > 0:
        writer.write('Content-type: {}; charset=UTF-8\r\n'.format(response_content_type).encode('utf-8'))
    if response_size > 0:
        writer.write('Content-length: {}\r\n'.format(response_size).encode('utf-8'))
    for header in response_extra_headers:
        writer.write('{}\r\n'.format(header).encode('utf-8'))
    writer.write(b'\r\n')


def send_simple_response(writer, http_status=200, response_content_type=None, response=None, response_extra_headers=[]):
    content_length = len(response) if response else 0
    start_response(writer, http_status, response_content_type, content_length, response_extra_headers)
    if response is not None and len(response) > 0:
        writer.write(response)
    return content_length


def connect_to_network(ssid, secret, access_point_mode=False):
    global blink_code
    if access_point_mode:
        print('Starting setup WLAN...')
        wlan = network.WLAN(network.AP_IF)
        wlan.active(False)
        wlan.config(pm=0xa11140)  # disable power save, this is a server.
        """
        #define CYW43_AUTH_OPEN (0)                     ///< No authorisation required (open)
        #define CYW43_AUTH_WPA_TKIP_PSK   (0x00200002)  ///< WPA authorisation
        #define CYW43_AUTH_WPA2_AES_PSK   (0x00400004)  ///< WPA2 authorisation (preferred)
        #define CYW43_AUTH_WPA2_MIXED_PSK (0x00400006)  ///< WPA2/WPA mixed authorisation
        """
        ssid = DEFAULT_SSID
        secret = ''
        if len(secret) == 0:
            security = 0
        else:
            security = 0x00400004
        wlan.config(ssid=ssid, key=secret, security=security)
        wlan.active(True)
        print(wlan.active())
        print('ssid={}'.format(wlan.config('ssid')))
        blink_code = 'A'

    else:
        print('Connecting to WLAN...')
        blink_code = 'C'  # for connection
        wlan = network.WLAN(network.STA_IF)
        wlan.config(pm=0xa11140)  # disable power save, this is a server.
        wlan.active(True)
        wlan.connect(ssid, secret)
        max_wait = 10
        while max_wait > 0:
            status = wlan.status()
            if status < 0 or status >= 3:
                break
            max_wait -= 1
            print('Waiting for connection to come up, status={}'.format(status))
            time.sleep(1)
        if wlan.status() != network.STAT_GOT_IP:
            raise RuntimeError('Network connection failed')
        blink_code = 'O'

    onboard.off()
    status = wlan.ifconfig()
    ip_address = status[0]
    print('my ip = {}'.format(ip_address))
    return ip_address


def unpack_args(s):
    args_dict = {}
    if s is not None:
        args_list = s.split('&')
        for arg in args_list:
            arg_parts = arg.split('=')
            if len(arg_parts) == 2:
                args_dict[arg_parts[0]] = arg_parts[1]
    return args_dict


async def serve_serial_client(reader, writer):
    """
    this provides serial compatible control.
    use com0com with com2tcp to interface legacy apps on windows.

    this code provides a serial endpoint that implements part of the DCU-3 protocol.

    all commands start with 'A'
    all commands end with ';' or CR (ascii 13)
    """
    requested = -1
    t0 = milliseconds()
    partner = writer.get_extra_info('peername')[0]
    print('\nserial client connected from {}'.format(partner))
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
                                if command == 'AI1;' or command == 'AI1\r':  # get direction
                                    bearing = get_rotator_bearing()
                                    response = ';{:03n}'.format(bearing)
                                    writer.write(response.encode('UTF-8'))
                                    await writer.drain()
                                elif command.startswith('AP1') and command[-1] == '\r':  # set bearing and move rotator
                                    requested = safe_int(command[3:-1], -1)
                                    if 0 <= requested <= 360:
                                        set_rotator_bearing(requested)
                                elif command.startswith('AP1') and command[-1] == ';':  # set bearing
                                    requested = safe_int(command[3:-1], -1)
                                elif command == 'AM1;' and 0 <= requested <= 360:  # move rotator
                                    set_rotator_bearing(requested)
        writer.close()
        await writer.wait_closed()

    except Exception as ex:
        print('exception in serve_serial_client:', type(ex), ex)
    tc = milliseconds()
    print('serial client disconnected, elapsed time {:6.3f} seconds'.format((tc - t0) / 1000.0))


async def serve_http_client(reader, writer):
    global restart
    t0 = milliseconds()
    http_status = 418  # can only make tea, sorry.
    partner = writer.get_extra_info('peername')[0]
    print('\nweb client connected from {}'.format(partner))
    request_line = await reader.readline()
    request = request_line.decode().strip()
    print(request)
    pieces = request.split(' ')
    if len(pieces) != 3:  # does the http request line look approximately correct?
        http_status = 400
        response = b'<html><body><p>400 Bad Request</p></body></html>'
        bytes_sent = send_simple_response(writer, http_status, CT_TEXT_HTML, response);
    else:
        verb = pieces[0]
        target = pieces[1]
        protocol = pieces[2]
        # should validate protocol here...
        if '?' in target:
            pieces = target.split('?')
            target = pieces[0]
            query_args = pieces[1]
        else:
            query_args = ''

        # HTTP request headers
        request_content_length = 0
        request_content_type = ''
        while True:
            header = await reader.readline()
            if len(header) == 0:
                # empty header line, eof?
                break
            if header == b'\r\n':
                # blank line at end of headers
                break
            else:
                # process headers.  look for those we are interested in.
                # print(header)
                parts = header.decode().strip().split(':', 1)
                if parts[0] == 'Content-Length':
                    request_content_length = int(parts[1].strip())
                elif parts[0] == 'Content-Type':
                    request_content_type = parts[1].strip()

        args = {}
        if verb == 'GET':
            args = unpack_args(query_args)

        if verb == 'POST':
            if request_content_length > 0:
                data = await reader.read(request_content_length)
                if request_content_type == CT_APP_WWW_FORM:
                    args = unpack_args(data.decode())
                elif request_content_type == CT_APP_JSON:
                    args = json.loads(data.decode())
                else:
                    print('warning: unhandled content_type {}'.format(request_content_type))
                    args = data.decode()

        if target == '/':
            http_status = 301
            bytes_sent = send_simple_response(writer, http_status, None, None, ['Location: /rotator.html'])
        elif target == '/rotator/bearing':
            requested_bearing = args.get('set')
            if requested_bearing:
                try:
                    requested_bearing = int(requested_bearing)
                    if 0 <= requested_bearing <= 360:
                        print('sending rotor command')
                        result = set_rotator_bearing(requested_bearing)
                        http_status = 200
                        response = '{}\r\n'.format(result).encode('utf-8')
                        bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
                    else:
                        http_status = 400
                        response = 'parameter out of range\r\n'.encode('utf-8')
                        bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
                except Exception as ex:
                    http_status = 500
                    response = 'uh oh: {}'.format(ex).encode('utf-8')
                    bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
            else:
                current_bearing = get_rotator_bearing()
                http_status = 200
                response = '{}\r\n'.format(current_bearing).encode('utf-8')
                bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
        elif target == '/config':
            if verb == 'GET':
                payload = read_config()
                # payload.pop('secret')  # do not return the secret
                response = json.dumps(payload).encode('utf-8')
                http_status = 200
                bytes_sent = send_simple_response(writer, http_status, CT_APP_JSON, response)
            elif verb == 'POST':
                tcp_port = args.get('tcp_port') or '-1'
                web_port = args.get('web_port') or '-1'
                tcp_port_int = safe_int(tcp_port, -2)
                web_port_int = safe_int(web_port, -2)
                ssid = args.get('SSID') or ''
                secret = args.get('secret') or ''
                if 0 <= web_port_int <= 65535 and 0 <= tcp_port_int <= 65535 and 0 < len(ssid) <= 64 and len(
                        secret) < 64 and len(args) == 4:
                    config = {'SSID': ssid, 'secret': secret, 'tcp_port': tcp_port, 'web_port': web_port}
                    # config = json.dumps(args)
                    save_config(config)
                    response = 'ok\r\n'.encode('utf-8')
                    http_status = 200
                    bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
                else:
                    response = 'parameter out of range\r\n'.encode('utf-8')
                    http_status = 400
                    bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
        elif target == '/restart' and upython:
            restart = True
            response = 'ok\r\n'.encode('utf-8')
            http_status = 200
            bytes_sent = send_simple_response(writer, http_status, CT_TEXT_TEXT, response)
        else:
            content_file = target[1:] if target[0] == '/' else target
            bytes_sent, http_status = serve_content(writer, content_file)

    await writer.drain()
    writer.close()
    await writer.wait_closed()
    tc = milliseconds()
    print('{} {} {}'.format(request, http_status, bytes_sent))
    print('web client disconnected, elapsed time {} ms'.format(tc - t0))


async def main():
    config = read_config()
    tcp_port = safe_int(config.get('tcp_port') or DEFAULT_TCP_PORT, DEFAULT_TCP_PORT)
    if tcp_port < 0 or tcp_port > 65535:
        tcp_port = DEFAULT_TCP_PORT
    web_port = safe_int(config.get('web_port') or DEFAULT_WEB_PORT, DEFAULT_WEB_PORT)
    if web_port < 0 or web_port > 65535:
        web_port = DEFAULT_WEB_PORT
    ssid = config.get('SSID') or ''
    if len(ssid) == 0 or len(ssid) > 64:
        ssid = DEFAULT_SSID
    secret = config.get('secret') or ''
    if len(secret) > 64:
        secret = ''

    connected = True
    if upython:
        try:
            connect_to_network(ssid=ssid, secret=secret, access_point_mode=ap_mode)
        except Exception as ex:
            connected = False
            print(type(ex), ex)

    if connected:
        print('Starting web service on port {}'.format(web_port))
        asyncio.create_task(asyncio.start_server(serve_http_client, '0.0.0.0', web_port))
        print('Starting tcp service on port {}'.format(tcp_port))
        asyncio.create_task(asyncio.start_server(serve_serial_client, '0.0.0.0', tcp_port))
    else:
        print('no network connection')

    while True:
        if upython:
            blink_pattern = BLINK_PATTERNS.get(blink_code) or [0.50, 0.50]
            blink_list = [elem for elem in BLINK_PATTERNS[blink_code]]
            while len(blink_list) > 0:
                onboard.on()
                blinky.on()
                await asyncio.sleep(blink_list.pop(0))
                onboard.off()
                blinky.off()
                await asyncio.sleep(blink_list.pop(0))
            if restart:
                machine.soft_reset()
        else:
            await asyncio.sleep(1.0)
            print('\x08|', end='')
            await asyncio.sleep(1.0)
            print('\x08/', end='')
            await asyncio.sleep(1.0)
            print('\x08-', end='')
            await asyncio.sleep(1.0)
            print('\x08\\', end='')


print('starting')
try:
    asyncio.run(main())
except KeyboardInterrupt as e:
    print('bye')
finally:
    asyncio.new_event_loop()

print('done')
