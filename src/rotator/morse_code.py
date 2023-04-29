#
# morse code sender
#

#
# Copyright 2023, J. B. Otterson N1KDO.
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
#

import sys
impl_name = sys.implementation.name
if impl_name == 'cpython':
    import asyncio
else:
    import uasyncio as asyncio


class MorseCode:
    MORSE_PERIOD = 15  # x 10 to MS: the speed of the morse code is set by the dit length of 150 ms.
    MORSE_DIT = MORSE_PERIOD
    MORSE_ESP = MORSE_DIT  # inter-element space
    MORSE_DAH = 3 * MORSE_PERIOD
    MORSE_LSP = 5 * MORSE_PERIOD  # more space between letters
    MORSE_PATTERNS = {  # sparse to save space
        ' ': (0, 0, 0, 0, 0),  # 5 element spaces then a letter space = 10 element pause  # space is 0x20 ascii
        '0': (MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH),  # 0 is 0x30 ascii
        '1': (MORSE_DIT, MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH),
        '2': (MORSE_DIT, MORSE_DIT, MORSE_DAH, MORSE_DAH, MORSE_DAH),
        '3': (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DAH, MORSE_DAH),
        '4': (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DAH),
        '5': (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        '6': (MORSE_DAH, MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        '7': (MORSE_DAH, MORSE_DAH, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        '8': (MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DIT, MORSE_DIT),
        '9': (MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DIT),
        'A': (MORSE_DIT, MORSE_DAH),                                    # 'A' is 0x41 ascii
        #  'B': (MORSE_DAH, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        #  'C': (MORSE_DAH, MORSE_DIT, MORSE_DAH, MORSE_DIT),
        #  'D': (MORSE_DAH, MORSE_DIT, MORSE_DIT),
        'E': (MORSE_DIT, ),
        'H': (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        'I': (MORSE_DIT, MORSE_DIT),
        #  'O': (MORSE_DAH, MORSE_DAH, MORSE_DAH),
        #  'N': (MORSE_DAH, MORSE_DIT),
        'R': (MORSE_DIT, MORSE_DAH, MORSE_DIT),
        #  'S': (MORSE_DIT, MORSE_DIT, MORSE_DIT),
    }

    def __init__(self, led):
        self.led = led
        self.message = ''

    def set_message(self, message):
        self.message = message

    async def morse_sender(self):
        while True:
            msg = self.message
            for morse_letter in msg:
                blink_pattern = self.MORSE_PATTERNS.get(morse_letter)
                if blink_pattern is None:
                    print(f'Warning: no pattern for letter {morse_letter}')
                    blink_pattern = self.MORSE_PATTERNS.get(' ')
                blink_list = list(blink_pattern)
                while len(blink_list) > 0:
                    blink_time = blink_list.pop(0)
                    if blink_time > 0:
                        # blink time is in milliseconds!, but data is in 10 msec
                        self.led.on()
                        await asyncio.sleep(blink_time/100)
                        self.led.off()
                    await asyncio.sleep(self.MORSE_ESP / 100 if len(blink_list) > 0 else self.MORSE_LSP / 100)
