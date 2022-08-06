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
    onboard = Pin("LED", Pin.OUT, value=0)
    onboard.on()
    wlan = network.WLAN(network.STA_IF)


"""
return milliseconds value, useful for elapsed time calculations
"""
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
    response = ''
    http_status = 200
    
    print('\n\nClient connected')
    request_line = await reader.readline()
    request = request_line.decode()
    print("Request:", request)

    # HTTP request headers
    content_length = 0
    content_type = ''
    while True:
        header = await reader.readline()
        if len(header) == 0:
            # empty header line, eof?
            break
        if header == b'\r\n':
            # blank line at end of headers
            break
        else:
            # process header.  look for those we are interested in.
            parts = header.decode().strip().split(':', 1)
            if parts[0] == 'Content-Length':
                content_length = int(parts[1].strip())
                print('content-length = {}'.format(content_length))
            elif parts[0] == 'Content-Type':
                content_type = parts[1].strip()
            print('header', header)
    
    t1 = milliseconds()
    pieces = request.split(' ')
    if len(pieces) == 3:
        verb = pieces[0]
        target = pieces[1]
        protocol = pieces[2]
        #print(verb, target, protocol)
        if '?' in target:
            pieces = target.split('?')
            #print(pieces)
            target = pieces[0]
            query_args = pieces[1]
        else:
            query_args = None
    else:
        verb = ''
        target = ''
        protocol = ''
        query_args = ''
        http_status = 500
        response = '<html><body><p>Bad Request</p></body></html>'
    print('{} {} {}'.format(verb, target, protocol))

    args = {}
    if verb == 'GET':
        args = unpack_args(query_args)

    if verb == "POST":
        print('got a POST')
        if content_length > 0:
            data = await reader.read(content_length)
            print('read complete')
            print(data)
            print(content_type)
            if content_type == 'application/x-www-form-urlencoded':
                args = unpack_args(data.decode())

    if target == '/':
        # print('GET /')
        print(args)
        
        current_bearing = get_rotator_bearing()

        #current_bearing = 45

        requested_bearing = int(args.get('requested_bearing') or current_bearing)
        last_requested_bearing = int(args.get('last_requested_bearing') or current_bearing)

        print('       current_bearing {:05n}'.format(current_bearing))
        print('last_requested_bearing {:05n}'.format(last_requested_bearing))
        print('     requested_bearing {:05n}\n\n'.format(requested_bearing))
        print('abs {}'.format(abs(current_bearing - requested_bearing)))
        if current_bearing >= 0 and abs(current_bearing - requested_bearing) > 4  and requested_bearing != last_requested_bearing:
            print('sending rotor command')
            set_rotator_bearing(requested_bearing)
            last_requested_bearing = requested_bearing
        #else:
        #    print('not applying rotor command')

        template = get_page_template('rotator')
        print('got template')
        response = apply_page_template(template,
                                       current_bearing=current_bearing,
                                       requested_bearing=requested_bearing,
                                       last_requested_bearing=last_requested_bearing)
        #print('applied template')
        writer.write(b'HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        writer.write(response.encode('utf-8'))
        #print('wrote response')
    else:
        writer.write(b'HTTP/1.0 404 Not Found\r\nContent-type: text/html\r\n\r\n')
        writer.write(b'<html><body><p>that which you seek is not here.</p></body></html>')

    #tw = milliseconds()
    #print('wrote {:6.3f}'.format((tw - t0)/1000.0))

    await writer.drain()
    #td = milliseconds()
    #print('drained {:6.3f}'.format((td - t0)/1000.0))
    writer.close()
    await writer.wait_closed()
    tc = milliseconds()
    print('closed {:6.3f}'.format((tc - t0)/1000.0))


async def main():
    if upython:
        connect_to_network()

    print('Starting web server...')
    asyncio.create_task(asyncio.start_server(serve_client, "0.0.0.0", 80))

    while True:
        if upython:
            onboard.on()
            #print("heartbeat")
            await asyncio.sleep(0.1)
            onboard.off()
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(1.0)


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
    
print('done')
