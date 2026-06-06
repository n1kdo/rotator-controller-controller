#
# micro_logging.py -- minimalistic logging for micropython.
#
__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2024, 2025, 2026 J. B. Otterson N1KDO.
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
__version__ = '0.1.4'  # 2026-05-25

from utils import get_timestamp, upython

if not upython:
    def const(i):
        return i

DEBUG = const(5)
INFO = const(4)
WARNING = const(3)
ERROR = const(2)
CRITICAL = const(1)
NOTHING = const(0)
LEVEL_NAMES = ('NOTHING', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG')

loglevel = ERROR


def set_level(level):
    global loglevel
    if isinstance(level, str):
        level = level.upper()
        try:
            level = LEVEL_NAMES.index(level)
        except ValueError:
            level = None

    if isinstance(level, int):
        if NOTHING <= level <= DEBUG:
            if loglevel >= INFO or level >= INFO:
                _log('[INFO]     ', f'setting log level to {LEVEL_NAMES[level]}', 'micro_logging:set_level')
            loglevel = level


# this is used to determine if logging.level() methods should be called,
# purpose is to reduce heap pollution from building complex log messages.
def should_log(level):
    return level <= loglevel


def _log(level: str, message: str|bytes, caller:str = None):
    if isinstance(message, bytes):
        message = message.decode('utf-8', errors='replace')
    if caller is None:
        print(get_timestamp(), level, message)
    else:
        print(get_timestamp(), ' ', level, ' [', caller, '] ', message, sep='')


def debug(message: str|bytes, caller: str = None):
    if loglevel >= DEBUG:
        _log('[DEBUG]    ', message, caller)


def info(message: str|bytes, caller: str = None):
    if loglevel >= INFO:
        _log('[INFO]     ', message, caller)


def warning(message: str|bytes, caller: str = None):
    if loglevel >= WARNING:
        _log('[WARNING]  ', message, caller)


def error(message: str|bytes, caller: str = None):
    if loglevel >= ERROR:
        _log('[ERROR]    ', message, caller)


def exception(message: str|bytes, caller:str = None, exc_info:Exception = None) -> None:
    if exc_info is not None:
        _log('[EXCEPTION]', f'{message} {type(exc_info)} {exc_info}', caller)
    else:
        _log('[EXCEPTION]', message, caller)


def critical(message: str| bytes, caller: str = None):
    if loglevel >= CRITICAL:
        _log('[CRITICAL] ', message, caller)

