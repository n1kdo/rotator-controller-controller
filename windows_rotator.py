#
# windows serial rotator controller module.  linux is the same, just the port name is different.
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


import serial
from serial import SerialException

#ROTOR_PORT = '/dev/ttyUSB0'
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

