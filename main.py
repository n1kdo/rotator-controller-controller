#
# this is async_web_main.py
#
import sys

from web_templates import get_page_template, apply_page_template
import settings

upython = sys.platform == 'rp2'

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
    wlan = network.WLAN(network.STA_IF)


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


def milliseconds():
    if upython:
        return time.ticks_ms()
    else:
        return int(time.time()*1000)


def connect_to_network():
    print('Connecting to WLAN...')
    wlan.active(True)
    wlan.connect(settings.SSID, settings.SECRET)

    max_wait = 10
    while max_wait > 0:
        status = wlan.status()
        if status < 0 or status >= 3:
            break
    max_wait -= 1
    print('Waiting for connection to come up, status={}'.format(status))
    time.sleep(1)

    if wlan.status() != 3:
        raise RuntimeError('Network connection failed')
    else:
        print('WLAN is up')
        status = wlan.ifconfig()
        print('ip = ' + status[0])


def unpack_args(s):
    args_dict = {}
    if s is not None:
        args_list = s.split('&')
        for arg in args_list:
            arg_parts = arg.split('=')
            if len(arg_parts) == 2:
                args_dict[arg_parts[0]] = arg_parts[1]
    return args_dict


async def serve_client(reader, writer):
    t0 = milliseconds()
    response = b'<html><body>500 Bad Request</body></html>'
    http_status = 500
    response_content_type = 'text/html'
    
    print('\nClient connected')
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

        if target == '/':
            current_bearing = get_rotator_bearing()

            #current_bearing = 45

            requested_bearing = int(args.get('requested_bearing') or current_bearing)
            last_requested_bearing = int(args.get('last_requested_bearing') or current_bearing)

            if False:
                print('       current_bearing {:05n}'.format(current_bearing))
                print('last_requested_bearing {:05n}'.format(last_requested_bearing))
                print('     requested_bearing {:05n}\n\n'.format(requested_bearing))
            if current_bearing >= 0 and abs(current_bearing - requested_bearing) > 4 and requested_bearing != last_requested_bearing:
                print('sending rotor command')
                set_rotator_bearing(requested_bearing)
                last_requested_bearing = requested_bearing
            #else:
            #    print('not applying rotor command')

            template = get_page_template('rotator')
            response = apply_page_template(template,
                                           current_bearing=current_bearing,
                                           requested_bearing=requested_bearing,
                                           last_requested_bearing=last_requested_bearing)
            response = response.encode('utf-8')
            http_status = 200

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
    print('client disconnected, elapsed time {:6.3f} seconds'.format((tc - t0)/1000.0))


async def main():
    if upython:
        connect_to_network()

    print('Starting web server...')
    asyncio.create_task(asyncio.start_server(serve_client, '0.0.0.0', 80))

    while True:
        if upython:
            onboard.on()
            #print('heartbeat')
            await asyncio.sleep(0.1)
            onboard.off()
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(1.0)


try:
    asyncio.run(main())
except KeyboardInterrupt as e:
    pass
finally:
    asyncio.new_event_loop()
    
print('done')
