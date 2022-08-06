#
# windows serial rotator controller module.  linux is the same, just the port number is different.
#
import serial
from serial import SerialException

ROTOR_PORT = '/dev/ttyUSB0'
ROTOR_PORT = 'COM6:'
BAUD_RATE = 4800

ERROR_NO_DATA = -10
ERROR_BAD_DATA = -11
ERROR_ASYNC = -12


def get_rotator_bearing():
    try:
        with serial.Serial(port=ROTOR_PORT,
                           baudrate=BAUD_RATE,
                           parity=serial.PARITY_NONE,
                           bytesize=serial.EIGHTBITS,
                           stopbits=serial.STOPBITS_ONE,
                           timeout=.1) as rotor_port:
            rotor_port.write(b'AI1\r')
            result = rotor_port.read(4).decode()
            if result is None or len(result) == 0:
                return ERROR_NO_DATA
            else:
                if result[0] == ';':
                    return int(result[1:])
                else:
                    return ERROR_BAD_DATA

    except SerialException as se:
        print(se)
        return ERROR_ASYNC


def set_rotator_bearing(bearing):
    target_bearing = '{:03n}'.format(int(bearing))
    message = 'soAP1{}\r'.format(target_bearing).encode('utf-8')
    # print(message.decode())
    try:
        with serial.Serial(port=ROTOR_PORT,
                           baudrate=BAUD_RATE,
                           parity=serial.PARITY_NONE,
                           bytesize=serial.EIGHTBITS,
                           stopbits=serial.STOPBITS_ONE,
                           timeout=1) as rotor_port:
            rotor_port.write(message)
    except SerialException as se:
        print(se)
        return ERROR_ASYNC
    return bearing

