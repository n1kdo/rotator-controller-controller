#
# this is async_web_main.py
#

import network
import time
import settings

from machine import Pin
import uasyncio as asyncio
#
#import asyncio

from pico_rotator import get_rotator_bearing, set_rotator_bearing
from web_templates import get_page_template, apply_page_template

onboard = Pin("LED", Pin.OUT, value=0)
wlan = network.WLAN(network.STA_IF)


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


async def serve_client(reader, writer):
    t0 = time.ticks_ms()
    response = ''
    http_status = 200
    
    print('\n\nClient connected')
    request_line = await reader.readline()
    request = request_line.decode()
    # print("Request:", request_line)

    # We are not interested in HTTP request headers, skip them
    while True:
        header = await reader.readline()
        if len(header) == 0:
            print('empty header line, eof?')
            break
        if header == b'\r\n':
            break
        else:
            pass
            #print('header', header)
    
    t1 = time.ticks_ms()
    request = request_line.decode()
    print("Request (str):", request)
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
            args = pieces[1]
        else:
            args = None
    else:
        verb = ''
        target = ''
        protocol = ''
        args = ''
        http_status = 500
        response = '<html><body><p>Bad Request</p></body></html>'
    print('{} {} {}'.format(verb, target, protocol))

    if verb == 'GET' and target == '/':
        args_dict = {}
        if args is not None:
            args_list = args.split('&')
            for arg in args_list:
                arg_parts = arg.split('=')
                if len(arg_parts) == 2:
                    args_dict[arg_parts[0]] = arg_parts[1]
        # print('GET /')
        # print(args_dict)
        
        current_bearing = get_rotator_bearing()

        requested_bearing = int(args_dict.get('requested_bearing') or current_bearing)
        last_requested_bearing = int(args_dict.get('last_requested_bearing') or current_bearing)

        print('       current_bearing {:05n}'.format(current_bearing))
        print('last_requested_bearing {:05n}'.format(last_requested_bearing))
        print('     requested_bearing {:05n}\n\n'.format(requested_bearing))
        print('abs {}'.format(abs(current_bearing - requested_bearing)))
        if abs(current_bearing - requested_bearing) > 4  and requested_bearing != last_requested_bearing:
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
        writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        writer.write(response)
        #print('wrote response')
    else:
        writer.write('HTTP/1.0 404 Not Found\r\nContent-type: text/html\r\n\r\n')
        writer.write('<html><body><p>that which you seek is not here.</p></body></html>')

    #tw = time.ticks_ms()
    #print('wrote {:6.3f}'.format((tw - t0)/1000.0))

    await writer.drain()
    #td = time.ticks_ms()
    #print('drained {:6.3f}'.format((td - t0)/1000.0))
    writer.close()
    await writer.wait_closed()
    tc = time.ticks_ms()
    print('closed {:6.3f}'.format((tc - t0)/1000.0))


async def main():
    connect_to_network()

    print('Starting web server...')
    asyncio.create_task(asyncio.start_server(serve_client, "0.0.0.0", 80))

    while True:
        onboard.on()
        #print("heartbeat")
        await asyncio.sleep(0.2)
        onboard.off()
        await asyncio.sleep(0.2)


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
    
print('done')
