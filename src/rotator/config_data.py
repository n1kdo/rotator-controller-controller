#
# config_data.py -- antenna rotator controller controller configuration data class.
#

__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2026 J. B. Otterson N1KDO.'
__version__ = '0.0.1'  # 2026-09-23

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

from cached_config_data import CachedConfigData

CONFIG_FILE = 'data/config.json'
DEFAULT_SECRET = 'NorthSouth'
DEFAULT_SSID = 'Rotator'
DEFAULT_TCP_PORT_1 = 73
DEFAULT_TCP_PORT_2 = 88
DEFAULT_WEB_PORT = 80


class ConfigData(CachedConfigData):
    def __init__(self):
        super().__init__(CONFIG_FILE)

    @staticmethod
    def _default_config_data():
        return {
            'SSID': 'set your SSID here',
            'secret': DEFAULT_SECRET,
            'dhcp': True,
            'ip_address': '192.168.1.73',
            'netmask': '255.255.255.0',
            'gateway': '192.168.1.1',
            'dns_server': '8.8.8.8',
            'hostname': 'pico-w',
            'rotor_1_name': 'rotator1',
            'rotor_1_primitive': False,
            'rotor_2_name': '',  # blank is permitted here and indicates no second rotor.
            'rotor_2_primitive': False,
            'n1mm': False,
            'tcp_port_1': DEFAULT_TCP_PORT_1,
            'tcp_port_2': DEFAULT_TCP_PORT_2,
            'web_port': DEFAULT_WEB_PORT,
        }
