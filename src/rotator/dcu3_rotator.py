#
# DCU-3 and compatible rotator control.
# only tested on Rotor-EZ so far.
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
from serialport import SerialPort


class Rotator:
    BAUD_RATE = 4800
    ERROR_NO_DATA = -10
    ERROR_BAD_DATA = -11
    ERROR_ASYNC = -12
    ERROR_BUSY = -13
    ERROR_UNKNOWN = -99

    def __init__(self):
        self.last_bearing = Rotator.ERROR_UNKNOWN
        self.last_requested_bearing = Rotator.ERROR_UNKNOWN
        self.serial_port_locked = False
        self.serial_port = SerialPort(baudrate=Rotator.BAUD_RATE, timeout=0.1)

    def get_rotator_bearing(self):
        if self.serial_port_locked:
            return Rotator.ERROR_BUSY
        else:
            self.serial_port_locked = True
            try:
                self.serial_port.write(b'AI1\r')
                result_bytes = self.serial_port.read(4)
                if result_bytes is None or len(result_bytes) == 0:
                    self.last_bearing = Rotator.ERROR_NO_DATA
                else:
                    result = result_bytes.decode()
                    if result[0] == ';':
                        self.last_bearing = int(result[1:])
                    else:
                        self.last_bearing = Rotator.ERROR_BAD_DATA
            except Exception as ex:
                print(ex)
                self.last_bearing = Rotator.ERROR_ASYNC
            finally:
                self.serial_port_locked = False
        return self.last_bearing

    def set_rotator_bearing(self, bearing):
        if self.serial_port_locked:
            result = Rotator.ERROR_BUSY
        else:
            self.serial_port_locked = True
            try:
                message = 'soAP1{:03n}\r'.format(int(bearing)).encode('utf-8')
                self.serial_port.write(message)
                self.last_requested_bearing = bearing
                result = bearing
            except Exception as ex:
                print(ex)
                result = Rotator.ERROR_ASYNC
            finally:
                self.serial_port_locked = False
        return result
