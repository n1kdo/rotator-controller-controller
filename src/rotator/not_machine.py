#
# not_machine -- mock micropython machine implementation
#

__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2024 J. B. Otterson N1KDO.'
__version__ = '0.0.1'

#
# Copyright 2024 J. B. Otterson N1KDO.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#  1. Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#  2. Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.

import micro_logging as logging

PWRON_RESET = 1
WDT_RESET = 3


class Machine(object):
    """
    fake micropython Machine to make PyCharm happier.
    """

    @staticmethod
    def reset_cause() -> int:
        return PWRON_RESET

    @staticmethod
    def soft_reset():
        logging.warning('Machine.soft_reset()', 'main:Machine:soft_reset()')

    @staticmethod
    def freq(f:int=None) -> int:
        return 0 if f is None else f

    @staticmethod
    def unique_id() -> bytes:
        return b'\x00\x00\x00\x00\x00\x00'

    class Pin(object):
        OUT = 1
        IN = 0
        PULL_UP = 0

        def __init__(self, name, options=0, value=0):
            self.value = value
            self.name = name
            self.options = options

        def on(self):
            self.value = 1

        def off(self):
            self.value = 0

        def value(self, new_value=None) -> int:
            if new_value is not None:
                self.value = 1 if new_value else 0
            return self.value

    class I2C(object):
        def __init__(self, id, sda, scl):
            self.id = id
            self.sda = sda
            self.scl = scl


machine = Machine()


