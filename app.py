from flask import Flask, render_template, request
from windows_rotator import get_rotator_bearing, set_rotator_bearing
from web_templates import get_page_template, apply_page_template

app = Flask(__name__)


@app.route('/', methods=['POST', 'GET'])
def control_rotator():
    current_bearing = get_rotator_bearing()
    for k, v in request.values.items():
        print(k, v)
    requested_bearing = int(request.values.get('requested_bearing') or current_bearing)
    last_requested_bearing = int(request.values.get('last_requested_bearing') or current_bearing)

    print(' current  bearing {:05n}'.format(current_bearing))
    print('requested bearing {:05n}\n\n'.format(requested_bearing))
    if abs(current_bearing - requested_bearing) > 5 and requested_bearing != last_requested_bearing:
        set_rotator_bearing(requested_bearing)
        last_requested_bearing = requested_bearing

    template = get_page_template('rotator')
    result = apply_page_template(template,
                                 current_bearing=current_bearing,
                                 requested_bearing=requested_bearing,
                                 last_requested_bearing=last_requested_bearing)
    return result


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)


