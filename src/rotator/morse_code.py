#
# morse code sender
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, 2024, 2025 J. B. Otterson N1KDO.
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
__version__ = '0.9.6'  # 2025-12-29

# disable pylint import error
# pylint: disable=E0401

import asyncio
import micro_logging as logging


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
        'E': (MORSE_DIT, ), # note that this comma is important, it is a tuple with one element
        'H': (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        'I': (MORSE_DIT, MORSE_DIT),
        'N': (MORSE_DAH, MORSE_DIT),
        'O': (MORSE_DAH, MORSE_DAH, MORSE_DAH),
        'P': (MORSE_DIT, MORSE_DAH, MORSE_DAH, MORSE_DIT),
        'R': (MORSE_DIT, MORSE_DAH, MORSE_DIT),
        'S': (MORSE_DIT, MORSE_DIT, MORSE_DIT),
        'T': (MORSE_DAH, ),
    }

    def __init__(self, led):
        self.led = led
        self.message = 'START '
        self.keep_running = True
        asyncio.create_task(self.morse_sender())

    def set_message(self, new_message):
        # do not send periods in Morse code, send a space instead.
        new_message = new_message.upper().replace('.', ' ')
        if self.message != new_message:
            logging.info(f'new message "{new_message}")', 'morse_code:set_message')
            self.message = new_message

    async def morse_sender(self):
        # these next several lines are optimizations for micropython, intended to eliminate dict lookups on self & etc.
        morse_esp = self.MORSE_ESP
        morse_lsp = self.MORSE_LSP
        led = self.led
        sleep = asyncio.sleep
        patterns = self.MORSE_PATTERNS

        while self.keep_running:
            msg = self.message
            logging.debug(f'starting message "{msg}"', 'morse_code:morse_sender')
            for morse_letter in msg:
                blink_pattern = patterns.get(morse_letter)
                if blink_pattern is None:
                    logging.debug(f'No pattern for letter "{morse_letter}" ({ord(morse_letter)})',
                                  'morse_code:morse_sender')
                    blink_pattern = patterns.get(' ')
                for blink_time in blink_pattern:
                    if blink_time > 0:
                        # blink time is in milliseconds!, but data is in 10 msec
                        led.on()
                        await sleep(blink_time / 100)  # dit or dah
                        led.off()
                    await sleep(morse_esp / 100)  # dit length element space
                await sleep(morse_lsp / 100)  # + inter-letter space
