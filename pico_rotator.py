#
# rotator controller Raspberry Pi Pico W
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
        
