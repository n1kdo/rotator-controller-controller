#
# some helper functions for micropython
#
__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2023, 2025, 2026 J. B. Otterson N1KDO.
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
__version__ = '0.9.8'  # 2026-09-18

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


def elapsed_ms(start):
    """
    milliseconds elapsed since `start` (a value from milliseconds()).
    uses time.ticks_diff() on MicroPython so the result stays correct
    across the ticks_ms() wraparound (~12.4 days on the Pico-W).
    """
    if upython:
        return time.ticks_diff(time.ticks_ms(), start)
    return int(time.time() * 1000) - start


@micropython.native
def safe_int(value, default: int = -1) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except ValueError:
        return default


# conservative hostname character set: RFC 1123 plus underscore. A dotted-quad
# IPv4 address is a valid member of this set, so is_hostname() accepts both.
_HOSTNAME_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_'


def is_ipv4(value) -> bool:
    """
    Return True if value is a dotted-quad IPv4 address string (0.0.0.0 through
    255.255.255.255). Non-str values, whitespace and non-ASCII digits are
    rejected.
    """
    if not isinstance(value, str):
        return False
    parts = value.split('.')
    if len(parts) != 4:
        return False
    for part in parts:
        if not part or len(part) > 3:
            return False
        for c in part:
            if c < '0' or c > '9':
                return False
        if int(part) > 255:
            return False
    return True


def is_hostname(value) -> bool:
    """
    Return True if value is a conservative hostname: 1-63 characters drawn from
    [A-Za-z0-9.-_]. Accepts dotted-quad IPv4 addresses as well.
    """
    if not isinstance(value, str):
        return False
    if not (0 < len(value) <= 63):
        return False
    for c in value:
        if c not in _HOSTNAME_CHARS:
            return False
    return True


class LineReader:
    """
    wraps an asyncio stream reader to provide a length-limited readline().

    MicroPython's Stream.readline() accumulates bytes without bound until it
    finds a newline or EOF, so a hostile or broken client could exhaust the
    heap by streaming data that contains no newline.  This wrapper reads in
    small chunks, keeps any surplus bytes past the newline for the next call,
    and raises ValueError if a line exceeds max_line_length.

    return value semantics match reader.readline(): b'' on a clean EOF and
    the partial line (without trailing newline) if EOF arrives mid-line.

    read() and readexactly() also serve bytes that readline() pulled past the
    end of a line, so callers can safely mix line reads and body reads on the
    same stream without losing data.

    self._pending is persisted before every await, so if the caller's task is
    cancelled mid-read (e.g. by an asyncio.wait_for timeout), no already-
    received bytes are lost; the next call resumes with all data read so far.
    """

    def __init__(self, reader, max_line_length=1024, chunk_size=256):
        self._reader = reader
        self._max_line_length = max_line_length
        self._chunk_size = chunk_size
        self._pending = b''

    async def readline(self):
        pending = self._pending
        while True:
            idx = pending.find(b'\n')
            if idx >= 0:
                if idx + 1 > self._max_line_length:  # the line itself is too long.
                    self._pending = b''
                    raise ValueError('line too long')
                line = pending[:idx + 1]
                self._pending = pending[idx + 1:]
                return line
            if len(pending) >= self._max_line_length:  # no newline in max_line_length bytes.
                self._pending = b''
                raise ValueError('line too long')
            # Persist before the await so cancellation cannot lose data.
            self._pending = pending
            data = await self._reader.read(self._chunk_size)
            if not data:  # EOF
                self._pending = b''
                return pending
            pending += data

    async def read(self, n):
        """
        read up to n bytes.  any surplus held by readline() is served first;
        returns b'' on EOF.
        """
        if self._pending:
            data = self._pending[:n]
            self._pending = self._pending[n:]
            return data
        return await self._reader.read(n)

    async def readexactly(self, n):
        """
        read exactly n bytes or raise EOFError.  any surplus held by
        readline() is served first.
        """
        pending = self._pending
        while len(pending) < n:
            # Persist before the await so cancellation cannot lose data.
            self._pending = pending
            data = await self._reader.read(self._chunk_size)
            if not data:  # EOF
                self._pending = b''
                raise EOFError('unexpected end of stream')
            pending += data
        self._pending = pending[n:]
        return pending[:n]


@micropython.native
def num_bits_set(n: int) -> int:
    #       0000 0001 0010 0011 0100 0101 0110 0111 1000 1001 1010 1011 1100 1101 1111
    if not isinstance(n, int):
        raise TypeError(f"num_bits_set expects an integer, got {type(n).__name__}")

    nn = n
    set_bits = 0
    if nn < 0:
        # negative: count the bits of the 32-bit two's complement representation.
        # bit 31 is always set; bits 0-30 are n & 0x7fffffff.
        set_bits = 1
        nn &= 0x7fffffff
    while nn:
        set_bits += BITS[nn & 0x0f]
        nn >>= 4
    return set_bits
