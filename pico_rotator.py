#
# rotator controller Raspberry Pi Pico W
#
BAUD_RATE = 4800

ERROR_NO_DATA = -10
ERROR_BAD_DATA = -11
ERROR_ASYNC = -12

from machine import Pin, UART

def get_rotator_bearing():
    current_bearing = None
    try:
        uart = UART(0, baudrate=BAUD_RATE, parity=None, stop=1, timeout=100, tx=Pin(0), rx=Pin(1))
        uart.write(b'AI1\r')
        result_bytes = uart.read(4)
        if result_bytes is None or len(result_bytes) == 0:
            return ERROR_NO_DATA
        else:
            result = result_bytes.decode()
            if result[0] == ';':
                return int(result[1:])
            else:
                return ERROR_BAD_DATA
    except:
        return ERROR_ASYNC
    #finally:
        #uart.deinit()
        
def set_rotator_bearing(bearing):
    message = 'soAP1{:03n}\r'.format(int(bearing)).encode('utf-8')
    try:
        uart = UART(0, baudrate=BAUD_RATE, parity=None, stop=1, timeout=100, tx=Pin(0), rx=Pin(1))
        uart.write(message)
        #print(message)
        return bearing
    except:
        #print('oops')
        return ERROR_ASYNC
    #finally:
        #uart.deinit()
        
