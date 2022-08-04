#
# This is microdot_main.py
#
import network
import time

import settings

from web_templates import get_page_template, apply_page_template
from pico_rotator import get_rotator_bearing, set_rotator_bearing

from microdot import Microdot

app = Microdot()

wlan = network.WLAN(network.STA_IF)


@app.route('/', methods=['POST', 'GET'])
def control_rotator(request):
    print('control_rotator')
    current_bearing = get_rotator_bearing()
    requested_bearing = current_bearing
    last_requested_bearing = current_bearing
    if request.method == 'POST':
        #for k, v in request.form.items():
        #    print(k, v)
        requested_bearing = int(request.form.get('requested_bearing') or current_bearing)
        last_requested_bearing = int(request.form.get('last_requested_bearing') or current_bearing)

    print(' current  bearing {:05n}'.format(current_bearing))
    print('requested bearing {:05n}\n\n'.format(requested_bearing))
    if abs(current_bearing - requested_bearing) > 5 and requested_bearing != last_requested_bearing:
        set_rotator_bearing(requested_bearing)
        last_requested_bearing = requested_bearing

    if False:
        result = '<html><body><p>hi there</p></body></html>'
    else:
        template = get_page_template('rotator')
        result = apply_page_template(template,
                                     current_bearing=current_bearing,
                                     requested_bearing=requested_bearing,
                                     last_requested_bearing=last_requested_bearing)
    headers = {'Content-Type': 'text/html'}
    print(result)
    return result, headers


def connect_to_network():
    print('connecting to WLAN')
    wlan.active(True)
    wlan.config(pm = 0xa11140) # Disable power-save mode
    wlan.connect(settings.SSID, settings.SECRET)

    max_wait = 30
    while max_wait > 0:
        status = wlan.status()
        if status < 0 or status >= 3:
            break
        max_wait -= 1
        print('waiting for connection...{}'.format(status))
        time.sleep(1)

    if wlan.status() != 3:
        raise RuntimeError('network connection failed')
    else:
        print('connected')
        status = wlan.ifconfig()
        print(status)
        print('ip = ' + status[0])


if __name__ == '__main__':
    connect_to_network()
    print('starting app')
    
    #app.run(host='0.0.0.0', port=80)
    app.run(port=80, debug=True)

