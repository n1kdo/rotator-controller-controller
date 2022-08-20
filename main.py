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

import json
import sys

from web_templates import get_page_template, apply_page_template

upython = sys.implementation.name == 'micropython'

if upython:
    import network
    import time
    from machine import Pin
    import uasyncio as asyncio
    from pico_rotator import get_rotator_bearing, set_rotator_bearing
else:
    import asyncio
    import time
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
CONFIG_FILE = 'data/config.json'
DEFAULT_SSID = 'Rotator'
DEFAULT_SECRET = 'North'
DEFAULT_TCP_PORT = 73
DEFAULT_WEB_PORT = 80

def read_config():
    config = {}
    try:
        with open(CONFIG_FILE, 'r') as config_file:
            config = json.load(config_file)
    except Exception as ex:
        print('failed to load configuration!', ex)
    return config


def save_config(config):
    with open(CONFIG_FILE, 'w') as config_file:
        json.dump(config_file, config)


def safe_int(s, default=-1):
    return int(s) if s.isdigit() else default


def milliseconds():
    if upython:
        return time.ticks_ms()
    else:
        return int(time.time()*1000)


def connect_to_network(ssid, secret, access_point_mode=False):
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
    else:
        print('Connecting to WLAN...')
        wlan = network.WLAN(network.STA_IF)
        wlan.config(pm=0xa11140)  # disable power save, this is a server.
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

    status = wlan.ifconfig()
    print('my ip = ' + status[0])


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
    print('\nserial client connected')
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
    print('serial client disconnected, elapsed time {:6.3f} seconds'.format((tc - t0)/1000.0))


async def serve_http_client(reader, writer):
    t0 = milliseconds()
    response = b'<html><body>500 Bad Request</body></html>'
    http_status = 500
    response_content_type = 'text/html'
    
    print('\nweb client connected')
    request_line = await reader.readline()
    request = request_line.decode().strip()
    print(request)
    pieces = request.split(' ')
    if len(pieces) != 3:  # does the http request line look approximately correct?
        http_status = 400
        response = b'<html><body><p>Bad Request</p></body></html>'
    else:
        verb = pieces[0]
        target = pieces[1]
        protocol = pieces[2]
        if '?' in target:
            pieces = target.split('?')
            target = pieces[0]
            query_args = pieces[1]
        else:
            query_args = ''

        #print('{} {} {} {}'.format(verb, target, protocol, query_args))

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
                #print(header)
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
                if request_content_type == 'application/x-www-form-urlencoded':
                    args = unpack_args(data.decode())
                elif request_content_type == 'application/json':
                    args = json.loads(data.decode())
                else:
                    print('warning: unhandled content_type {}'.format(request_content_type))
                    args = data.decode()

        if target == '/':
            response = get_page_template('rotator.html')
            response = response.encode('utf-8')
            http_status = 200

        elif target == '/rotator/bearing':
            requested_bearing = args.get('set')
            if requested_bearing:
                #print(requested_bearing)
                try:
                    requested_bearing = int(requested_bearing)
                    if 0 <= requested_bearing <= 360:
                        print('sending rotor command')
                        result = set_rotator_bearing(requested_bearing)
                        http_status = 200
                        response = '{}\r\n'.format(result).encode('utf-8')
                    else:
                        http_status = 400
                        response = 'parameter out of range\r\n'.encode('utf-8')
                except Exception as ex:
                    http_status = 500
                    response = 'uh oh: {}'.format(ex).encode('utf-8')
            else:
                current_bearing = get_rotator_bearing()
                response = '{}\r\n'.format(current_bearing).encode('utf-8')
                http_status = 200
            response_content_type = 'text/text'
        elif target == '/config':
            if verb == 'GET':
                payload = read_config()
                payload.pop('secret')  # do not return the secret
                response = json.dumps(payload).encode('utf-8')
                response_content_type = 'application/json'
                http_status = 200
            elif verb == 'POST':
                web_port = args.get('web_port') or -1
                tcp_port = args.get('tcp_port') or -1
                ssid = args.get('SSID') or ''
                secret = args.get('secret') or ''
                if 0 <= web_port <= 65535 and 0 <= tcp_port <= 65535 and 0 < len(ssid) <= 64 and len(secret) < 64:
                    config = {'SSID':ssid, 'secret':secret, 'tcp_port':tcp_port, 'web_port':web_port}
                    save_config(config)
                    http_status = 200
                    response = 'ok\r\n'.encode('utf-8')
                    response_content_type = 'text/text'
                else:
                    response = 'parameter out of range\r\n'.encode('utf-8')
                    http_status = 400
                    response_content_type = 'text/text'
        else:
            http_status = 404
            response = b'<html><body><p>that which you seek is not here.</p></body></html>'

    status_text = HTTP_STATUS_TEXT.get(http_status) or 'Confused'
    rr = '{} {} {}\r\n'.format(protocol, http_status, status_text)
    rr += 'Content-type: {}; charset=UTF-8\r\n'.format(response_content_type)
    rr += 'Content-length: {}\r\n\r\n'.format(len(response))
    response = rr.encode('utf-8') + response
    writer.write(response)

    await writer.drain()
    writer.close()
    await writer.wait_closed()
    tc = milliseconds()
    print('{} {} {}'.format(request, http_status, len(response)))
    print('web client disconnected, elapsed time {:6.3f} seconds'.format((tc - t0)/1000.0))


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

    if upython:
        connect_to_network(ssid=ssid, secret=secret, access_point_mode=ap_mode)

    print('Starting web service on port {}'.format(web_port))
    asyncio.create_task(asyncio.start_server(serve_http_client, '0.0.0.0', web_port))
    print('Starting tcp service on port {}'.format(tcp_port))
    asyncio.create_task(asyncio.start_server(serve_serial_client, '0.0.0.0', tcp_port))

    while True:
        if upython:
            onboard.on()
            #print('heartbeat')
            await asyncio.sleep(0.1)
            onboard.off()
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(1.0)
            print('\x08|', end='')
            await asyncio.sleep(1.0)
            print('\x08/', end='')
            await asyncio.sleep(1.0)
            print('\x08-', end='')
            await asyncio.sleep(1.0)
            print('\x08\\', end='')


try:
    asyncio.run(main())
except KeyboardInterrupt as e:
    print('bye')
finally:
    asyncio.new_event_loop()
    
print('done')
