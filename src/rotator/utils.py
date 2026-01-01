#
# some helper functions for micropython
#
__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2023, 2025 J. B. Otterson N1KDO.
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
__version__ = '0.9.4'  # 2025-12-29

import sys
import time

BITS = bytes([0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4])

upython = sys.implementation.name == 'micropython'
if upython:
    import micropython
else:
    # provide no-op native and viper decorators
    class _MP:
        @staticmethod
        def native(f):
            return f
        @staticmethod
        def viper(f):
            return f
    micropython = _MP()


@micropython.native
def get_timestamp(tt=None):
    if tt is None:
        tt = time.gmtime()
    return f'{tt[0]:04d}-{tt[1]:02d}-{tt[2]:02d} {tt[3]:02d}:{tt[4]:02d}:{tt[5]:02d}Z'


@micropython.native
def get_timestamp_from_secs(secs=None):
    tt = time.gmtime(secs)
    return f'{tt[0]:04d}-{tt[1]:02d}-{tt[2]:02d} {tt[3]:02d}:{tt[4]:02d}:{tt[5]:02d}Z'


def milliseconds():
    return time.ticks_ms() if upython else int(time.time() * 1000)


@micropython.native
def safe_int(value, default:int=-1) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except ValueError:
        return default


@micropython.native
def num_bits_set(n: int) -> int:
    #       0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1111
    nn = n
    set_bits = 0
    while nn:
        set_bits += BITS[nn & 0x0f]
        nn >>= 4
    return set_bits

