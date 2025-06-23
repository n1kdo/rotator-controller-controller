#
# serial port access
# compatible with both pyserial on cpython and machine.UART on micropython
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2023, J. B. Otterson N1KDO.
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
__version__ = '0.9.0'

# disable pylint import error
# pylint: disable=E0401

import sys

impl_name = sys.implementation.name
upython = impl_name == 'micropython'
if upython:
    import machine
else:
    import serial


class SerialPort:
    def __init__(self, name='', baudrate=19200, timeout=0.040):
        if impl_name == 'cpython':
            if name == '':
                name = 'com1:'
            self.port = serial.Serial(port=name,
                                      baudrate=baudrate,
                                      parity=serial.PARITY_NONE,
                                      bytesize=serial.EIGHTBITS,
                                      stopbits=serial.STOPBITS_ONE,
                                      timeout=timeout)
            # reliable at 0.040 for 4800
        elif impl_name == 'micropython':
            if name == '':
                name = '0'
            if name == '0':
                tx_pin = machine.Pin(0)
                rx_pin = machine.Pin(1)
            elif name == '1':
                tx_pin = machine.Pin(4)
                rx_pin = machine.Pin(5)
            timeout_msec = int(timeout * 1000)
            timeout_char_msec = int(timeout * 100)
            self.port = machine.UART(int(name),
                                     baudrate=baudrate,
                                     parity=None,
                                     stop=1,
                                     timeout=timeout_msec,
                                     timeout_char=timeout_char_msec,
                                     tx=tx_pin,
                                     rx=rx_pin)
        else:
            raise RuntimeError(f'no support for {impl_name}.')

    def close(self):
        self.port.close()

    def any(self):
        if upython:
            return self.port.any()
        else:
            x = self.port.in_waiting
            return x != 0

    def flush_input(self):
        if upython:
            if self.any():
                _ = self.port.read()
        else:
            self.port.reset_input_buffer()

    def write(self, buffer):
        self.port.write(buffer)

    def read(self, size=16):
        buffer = self.port.read(size)
        return b'' if buffer is None else buffer  # micropython machine.UART returns None on timeout.

    def readinto(self, buf):
        result = self.port.readinto(buf)
        return 0 if result is None else result

    def flush(self):
        self.port.flush()
