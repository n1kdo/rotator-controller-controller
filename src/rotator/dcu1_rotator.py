#
# DCU-1 and compatible rotator control.
# only tested on Rotor-EZ so far.
# should work on DCU-1 and compatibles (e.g. Green Heron)
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

# disable pylint import error
# pylint: disable=E0401

import sys
from serialport import SerialPort
impl_name = sys.implementation.name
if impl_name == 'cpython':
    import asyncio
else:
    import uasyncio as asyncio


class Rotator:
    BAUD_RATE = 4800
    ERROR_NO_DATA = -10
    ERROR_BAD_DATA = -11
    ERROR_ASYNC = -12
    ERROR_BUSY = -13
    ERROR_UNKNOWN = -99

    def __init__(self):
        self.serial_port_locked = True
        self.primitive = True  # use two-command mode for NOT Rotor-EZ or Green Heron
        # self.primitive = False  # use one command to set direction and move (Rotor-EZ, Green Heron)
        self.buffer = bytearray(16)
        self.last_bearing = Rotator.ERROR_UNKNOWN
        self.last_requested_bearing = Rotator.ERROR_UNKNOWN
        self.serial_port = SerialPort(baudrate=Rotator.BAUD_RATE, timeout=0)
        self.initialized = False
        self.serial_port_locked = False

    async def initialize(self):
        #await self.send_and_receive(b'so')  # ROTOR EZ disable Stuck mode, disable Coast mode.
        await self.send_and_receive(b';')
        self.initialized = True

    async def send_and_receive(self, message, timeout=0.05):
        # drain receive buffer
        while len(self.serial_port.read()) > 0:
            pass
        # send the message
        self.serial_port.write(message)
        self.serial_port.flush()
        # wait a short bit
        await asyncio.sleep(timeout)
        bytes_received = self.serial_port.readinto(self.buffer)
        return self.buffer[:bytes_received].decode()

    async def get_rotator_bearing(self):
        if self.serial_port_locked:
            return Rotator.ERROR_BUSY
        self.serial_port_locked = True
        try:
            if not self.initialized:
                await self.initialize()
            result = await self.send_and_receive(b'AI1;')
            if len(result) == 0:
                self.last_bearing = Rotator.ERROR_NO_DATA
            else:
                if result[0] == ';':
                    self.last_bearing = int(result[1:])
                else:
                    print(f'unexpected result: "{result}"')
                    self.last_bearing = Rotator.ERROR_BAD_DATA
        except Exception as ex:
            print(ex)
            self.last_bearing = Rotator.ERROR_ASYNC
        finally:
            self.serial_port_locked = False
        return self.last_bearing

    async def set_rotator_bearing(self, bearing):
        if self.serial_port_locked:
            result = Rotator.ERROR_BUSY
        else:
            self.serial_port_locked = True
            try:
                if not self.initialized:
                    await self.initialize()
                if self.primitive:
                    # Hygain DCU-3 set direction
                    # not expecting any response.
                    message = f'AP1{bearing:03n};'.encode('utf-8')
                    await self.send_and_receive(message)
                    await self.send_and_receive(b'AM1;')
                    self.last_requested_bearing = bearing
                else:
                    message = f'AP1{int(bearing):03n}\r'.encode('utf-8')
                    await self.send_and_receive(message)
                result = bearing
            except Exception as ex:
                print(ex)
                result = Rotator.ERROR_ASYNC
            finally:
                self.serial_port_locked = False
        return result
