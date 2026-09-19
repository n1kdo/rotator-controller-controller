#
# cached_config_file.py -- this is a base class for cached configuration files.
#

__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2026 J. B. Otterson N1KDO.'
__version__ = '0.0.6'  # 2026-09-18

#
# Copyright 2026 J. B. Otterson N1KDO.
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

import asyncio
import micro_logging as logging
import os
from utils import upython
if upython:
    import json
else:
    import compatible_json as json

DEFAULT_WRITE_DELAY = 60


class CachedConfigData:

    def __init__(self, config_file_name):
        self._config_file_name = config_file_name
        self._dirty = False
        self._config_data = None
        self._config_data_bytes = {}
        self._deferred_write_timeout = 0
        self._deferred_writer_task = None

    @staticmethod
    def _default_config_data():
        return {}

    def _read_config_data(self):
        try:
            with open(self._config_file_name, 'r') as config_file:
                self._config_data = json.load(config_file)
                if logging.should_log(logging.DEBUG):
                    logging.debug(f'read configuration from {self._config_file_name}',
                                  'cached_config_data:_read_config_data()')
        except Exception as ex:
            logging.info(f'failed to load configuration from {self._config_file_name},:  {type(ex)}, {ex}',
                         'cached_config_data:_read_config_data()')
            self._config_data = self._default_config_data()
        finally:
            self._dirty = False
        self._config_data_bytes = {}

    def _write_config_data(self):
        tmp_file = self._config_file_name + '.tmp'
        try:
            try:
                os.remove(tmp_file)  # clear any orphan from a previously interrupted write
            except OSError:
                pass
            with open(tmp_file, 'w') as config_file:
                json.dump(self._config_data, config_file)
            os.rename(tmp_file, self._config_file_name)
            logging.info(f'wrote configuration to {self._config_file_name}',
                         'cached_config_data:_write_config_data()')
        except Exception as ex:
            logging.exception(f'failed to write configuration data to {self._config_file_name}',
                              'cached_config_data:_write_config_data()',
                              ex)
            try:
                os.remove(tmp_file)  # don't leave a partial tmp behind
            except OSError:
                pass
        finally:
            # this is suboptimal since failed writes won't be retried, but if
            # it failed once, it is not likely to succeed on retry.
            self._dirty = False

    def get_data(self):
        if self._config_data is None:
            self._read_config_data()
        return self._config_data

    def __getitem__(self, key):
        if self._config_data is None:
            self._read_config_data()
        return self._config_data.get(key)

    def __setitem__(self, key, value):
        self.put(key, value)

    def get(self, key, default=None):
        if self._config_data is None:
            self._read_config_data()
        return self._config_data.get(key, default)

    def get_bytes(self, key, default=None):
        datab = self._config_data_bytes.get(key)
        if datab is None:
            datab = self.get(key, default)
            if isinstance(datab, str):
                datab = datab.encode()
                self._config_data_bytes[key] = datab
            else:
                logging.error(f'tried to get bytes value for "{key}" but "{datab}" is not a string',
                              'cached_config_data:getb')
                return None
        return datab

    def put(self, key, value):
        old_value = self.get(key)
        if value != old_value:
            self._config_data[key] = value
            self._config_data_bytes.pop(key, None)
            self._dirty = True
            self._deferred_write_timeout = DEFAULT_WRITE_DELAY
            if self._deferred_writer_task is None:
                self._deferred_writer_task = asyncio.create_task(self._deferred_writer())

    def put_bytes(self, key, valuebytes):
        value = valuebytes.decode()
        self.put(key, value)
        self._config_data_bytes[key] = valuebytes

    def flush(self):
        if self._dirty:
            self._write_config_data()

    async def _deferred_writer(self):
        try:
            while self._dirty:
                while self._deferred_write_timeout > 0 and self._dirty:
                    await asyncio.sleep(1)
                    self._deferred_write_timeout -= 1
                if self._dirty:
                    self._write_config_data()
        finally:
            self._deferred_writer_task = None
