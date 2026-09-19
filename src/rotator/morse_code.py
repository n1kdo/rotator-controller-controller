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
__version__ = '0.10.0'  # 2026-09-18

# disable pylint import error
# pylint: disable=E0401

import asyncio
import micro_logging as logging


class MorseCode:
    MORSE_PERIOD = 150  # the speed of the morse code is set by the dit length of 150 ms.
    MORSE_DIT = MORSE_PERIOD
    MORSE_ESP = MORSE_DIT  # inter-element space
    MORSE_DAH = 3 * MORSE_PERIOD
    MORSE_LSP = 5 * MORSE_PERIOD  # more space between letters
    MORSE_PATTERNS = {  # sparse to save space
        32 : (0, 0, 0, 0, 0),  # 5 element spaces then a letter space = 10 element pause  # space is 0x20 ascii
        48: (MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH),  # 0 is 0x30 ascii
        49: (MORSE_DIT, MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH),
        50: (MORSE_DIT, MORSE_DIT, MORSE_DAH, MORSE_DAH, MORSE_DAH),
        51: (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DAH, MORSE_DAH),
        52: (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DAH),
        53: (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        54: (MORSE_DAH, MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        55: (MORSE_DAH, MORSE_DAH, MORSE_DIT, MORSE_DIT, MORSE_DIT),
        56: (MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DIT, MORSE_DIT),
        57: (MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DAH, MORSE_DIT),  # 9 is 57 ASCII
        65: (MORSE_DIT, MORSE_DAH), # 'A' is 0x41 ascii
        69: (MORSE_DIT, ), # E, note that this comma is important, it is a tuple with one element
        72: (MORSE_DIT, MORSE_DIT, MORSE_DIT, MORSE_DIT), # H
        73: (MORSE_DIT, MORSE_DIT), #I
        78: (MORSE_DAH, MORSE_DIT), #N
        79: (MORSE_DAH, MORSE_DAH, MORSE_DAH), # O
        80: (MORSE_DIT, MORSE_DAH, MORSE_DAH, MORSE_DIT), # P
        82: (MORSE_DIT, MORSE_DAH, MORSE_DIT), # R
        83: (MORSE_DIT, MORSE_DIT, MORSE_DIT), # S
        84: (MORSE_DAH, ), # T
    }

    def __init__(self, led):
        self.led = led
        self.message = b'START '
        self.keep_running = True
        asyncio.create_task(self.morse_sender())

    def set_message(self, new_message : bytes):
        new_message = new_message.upper().replace(b'.', b' ')
        if self.message != new_message:
            logging.info(b'new message "%s"' % new_message, 'morse_code:set_message')
            self.message = new_message

    async def morse_sender(self):
        # these next several lines are optimizations for micropython, intended to eliminate dict lookups on self & etc.
        morse_esp = self.MORSE_ESP
        morse_lsp = self.MORSE_LSP
        led = self.led
        try:
            sleep_ms = asyncio.sleep_ms
        except AttributeError:
            async def sleep_ms(ms):
                await asyncio.sleep(ms / 1000)
        patterns = self.MORSE_PATTERNS

        while self.keep_running:
            msg = self.message
            if not msg:
                await sleep_ms(morse_esp)  # empty message: nothing to send; yield so we don't hog the loop
                continue
            logging.debug(f'starting message "{msg}"', 'morse_code:morse_sender')
            for morse_letter in msg:
                blink_pattern = patterns.get(morse_letter)
                if blink_pattern is None:
                    logging.warning(f'No pattern for letter "{morse_letter}"',
                                    'morse_code:morse_sender')
                    blink_pattern = patterns.get(32)  # space
                for blink_time in blink_pattern:
                    if blink_time > 0:
                        led.on()
                        await sleep_ms(blink_time)  # dit or dah
                        led.off()
                    await sleep_ms(morse_esp)  # dit length element space
                await sleep_ms(morse_lsp)  # + inter-letter space
