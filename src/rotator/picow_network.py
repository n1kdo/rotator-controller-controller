#
# picow_network.py -- Raspberry Pi Pico W connect to Wi-Fi Network.
#
__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2024, 2025 J. B. Otterson N1KDO.'
__version__ = '0.10.2'  # 2025-12-31
#
# Copyright 2024, 2025, J. B. Otterson N1KDO.
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
from utils import upython

if upython:
    # noinspection PyUnresolvedReferences
    import machine
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    import network
else:
    raise ImportError('picow_network is only available on Micropython.')


class PicowNetwork:
    network_status_map = {
        network.STAT_IDLE:           'not connected',  # 0  CYW43_LINK_DOWN
        network.STAT_CONNECTING:     'connecting...',  # 1  CYW43_LINK_JOIN
        network.STAT_CONNECTING + 1: 'connected no IP addr',  # 2  CYW43_LINK_NOIP
        network.STAT_GOT_IP:         'connection successful',  # 3 CYW43_LINK_UP
        network.STAT_WRONG_PASSWORD: 'failed, bad password',  # -3 CYW43_LINK_FAIL
        network.STAT_NO_AP_FOUND:    'failed no AP replied',  # -2 CYW43_LINK_NONET
        network.STAT_CONNECT_FAIL:   'failed other problem',  # -1 CYW43_LINK_FAIL
    }

    def __init__(self,
                 config: dict,
                 default_ssid:str='PICO-W',
                 default_secret:str='PICO-W',
                 message_func=None,
                 long_messages=False) -> None:
        self._connected = False
        self._connecting = False
        self._default_secret = default_secret
        self._default_ssid = default_ssid
        self._keepalive = False
        self._message_func = message_func
        self._long_messages = long_messages
        self._ssid = config.get('SSID') or default_ssid
        if len(self._ssid) == 0 or len(self._ssid) > 64:
            self._ssid = default_ssid
        self._secret = config.get('secret') or default_secret
        if self._secret is None or len(self._secret) == 0:
            self._secret = default_secret
        if len(self._secret) > 64:
            self._secret = self._secret[:64]

        self._hostname = config.get('hostname')
        if self._hostname is None or self._hostname == '':
            self._hostname = 'pico-w'

        self._access_point_mode = config.get('ap_mode', False)

        self._is_dhcp = config.get('dhcp', True)
        if self._is_dhcp:
            self._ip_address = None
            self._netmask = None
            self._gateway = None
            self._dns_server = None
        else:
            self._ip_address = config.get('ip_address')
            self._netmask = config.get('netmask')
            self._gateway = config.get('gateway')
            self._dns_server = config.get('dns_server')
        self._message = ''
        self._status = 0
        if self._long_messages:
            self._message = 'Network INIT'
        else:
            self._message = 'INIT'
        self._status = 0
        self._wlan = None
        asyncio.create_task(self.keep_alive())

    def get_ip_address(self):
        return self._ip_address

    def get_netmask(self):
        return self._netmask

    def is_connected(self):
        return self._connected

    async def set_message(self, message: str, status:int = 0) -> None:
        self._message = message
        self._status = status
        if self._message_func:
            await self._message_func(self._message, self._status)

    async def _connect(self) -> None:
        network.country('US')
        network.ipconfig(prefer=4)  # this is an IPv4 network
        sleep = asyncio.sleep
        wl_status = 0

        if self._access_point_mode:
            if self._long_messages:
                await self.set_message('Starting setup WLAN...')
            logging.info('Starting setup WLAN...', 'PicowNetwork:connect_to_network')
            self._wlan = network.WLAN(network.WLAN.IF_AP)
            self._wlan.config(pm=self._wlan.PM_NONE)  # disable power save, this is a server.
            await sleep(0.1)
            logging.debug('Starting setup WLAN...1', 'PicowNetwork:connect_to_network')
            logging.info(f'  wlan.active()={self._wlan.active()}', 'PicowNetwork:connect_to_network (new)')
            # wlan.deinit turns off the onboard LED because it is connected to the CYW43
            # turn it on again.
            onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
            onboard.on()
            try:
                if self._long_messages:
                    await self.set_message(f'Setting hostname "{self._hostname}"')
                logging.info(f'  Setting hostname "{self._hostname}"', 'PicowNetwork:connect_to_network')
                network.hostname(self._hostname)
            except ValueError:
                if self._long_messages:
                    await self.set_message('Failed to set hostname.', -10)
                else:
                    await self.set_message('ERROR ', -10)
                logging.error('Failed to set hostname.', 'PicowNetwork:connect_to_network')

            # security choices are 'SEC_OPEN', 'SEC_WPA2_WPA3', 'SEC_WPA3', 'SEC_WPA_WPA2'
            # see https://github.com/micropython/micropython/blob/master/extmod/network_cyw43.c#L584
            if len(self._secret) == 0:
                security = network.WLAN.SEC_OPEN
            else:
                security = network.WLAN.SEC_WPA2_WPA3  # CYW43_AUTH_WPA2_AES_PSK

            mac_addr = self._wlan.config('mac')
            mac = ''
            if mac_addr is not None:
                mac = ''.join([f'{b:02x}' for b in mac_addr])
                if len(mac) == 12:
                    self._default_ssid = self._default_ssid + '-' + mac[6:]
            self._wlan.config(ssid=self._default_ssid, key=self._default_secret, security=security)
            self._wlan.active(True)
            logging.info(f'  wlan.active()={self._wlan.active()}', 'PicowNetwork:connect_to_network')
            logging.info(f'  ssid={self._wlan.config("ssid")}', 'PicowNetwork:connect_to_network')
            logging.debug(f'  key={self._default_secret}', 'PicowNetwork:connect_to_network')
            logging.info(f'  ipconfig addr4={self._wlan.ipconfig("addr4")}', 'PicowNetwork:connect_to_network')
            self._connected = True
        else:
            if self._long_messages:
                await self.set_message('Connecting to WLAN...')
            logging.info('Connecting to WLAN...', 'PicowNetwork:connect_to_network')
            self._wlan = network.WLAN(network.WLAN.IF_STA)
            self._wlan.config(pm=self._wlan.PM_NONE)  # disable power save, this is a server.
            await sleep(0.1)
            logging.debug('Connecting to WLAN...1', 'PicowNetwork:connect_to_network')
            self._wlan.active(True)
            await sleep(0.1)
            logging.info(f'  wlan.active()={self._wlan.active()}', 'PicowNetwork:connect_to_network (new)')
            # wlan.deinit turns off the onboard LED because it is connected to the CYW43
            # turn it on again.
            onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
            onboard.on()
            try:
                if self._long_messages:
                    await self.set_message(f'Setting hostname\n{self._hostname}')
                logging.info(f'...setting hostname "{self._hostname}"', 'PicowNetwork:connect_to_network')
                network.hostname(self._hostname)
                logging.debug('Connecting to WLAN...5', 'PicowNetwork:connect_to_network')
            except ValueError:
                if self._long_messages:
                    await self.set_message('Failed to set hostname.', -10)
                else:
                    await self.set_message('ERROR ', -10)
                logging.error('Failed to set hostname.', 'PicowNetwork:connect_to_network')
            logging.debug('Connecting to WLAN...6', 'PicowNetwork:connect_to_network')
            await sleep(0.1)

            logging.info(f'scanning for best signal for SSID "{self._ssid}".', 'PicowNetwork:connect_to_network')
            # scan ssid option is not documented.  Using it here to reduce the result set size.
            # see https://github.com/micropython/micropython/blob/master/extmod/network_cyw43.c#L192
            try:
                scan_results = self._wlan.scan(ssid=self._ssid, passive=True)
            except OSError as ose:
                scan_results = []
                logging.exception('WiFi scan() failed', 'PicowNetwork:connect_to_network', ose)
            logging.debug('Connecting to WLAN...7', 'PicowNetwork:connect_to_network')
            bssid = None
            best_rssi = -100
            for result in scan_results:
                scan_ssid = result[0].decode()
                scan_bssid = ''.join([f'{b:02x}' for b in result[1]])
                scan_channel = result[2]
                scan_rssi = result[3]
                scan_security = result[4]
                scan_hidden = result[5]
                logging.info(f'Found SSID "{scan_ssid}", BSSID "{scan_bssid}", channel {scan_channel}, RSSI {scan_rssi}, security {scan_security}, hidden {scan_hidden}',
                              'PicowNetwork:connect_to_network')
                if scan_ssid == self._ssid:
                    if scan_rssi > best_rssi:
                        best_rssi = scan_rssi
                        bssid = result[1]
            if bssid is not None:
                bssid_str = ''.join([f'{b:02x}' for b in bssid])
                logging.info(f'Found best RSSI for SSID "{self._ssid}" on BSSID "{bssid_str}" RSSI {best_rssi}',
                              'PicowNetwork:connect_to_network')
            else:
                logging.warning('cannot find SSID in scan', 'PicowNetwork:connect_to_network')

            if not self._is_dhcp:
                if self._ip_address is not None and self._netmask is not None and self._gateway is not None and self._dns_server is not None:
                    logging.info('...configuring network with static IP', 'PicowNetwork:connect_to_network')
                    self._wlan.ipconfig(addr4=(self._ip_address, self._netmask),gw4=self._gateway,dhcp4=False)
                else:
                    logging.warning('Cannot use static IP, data is missing.', 'PicowNetwork:connect_to_network')
                    logging.warning('Configuring network with DHCP....', 'PicowNetwork:connect_to_network')
                    self._is_dhcp = True
            if self._is_dhcp:
                self._wlan.ipconfig(dhcp4=True)
                logging.info(f'...configuring network with DHCP', 'PicowNetwork:connect_to_network')
            else:
                logging.info(f'...configuring network with {self._wlan.ipconfig("addr4")}', 'PicowNetwork:connect_to_network')

            connect_timeout = 15
            st = ''
            if self._long_messages:
                await self.set_message(f'Connecting to\n{self._ssid}')
            try:
                if bssid is not None:
                    self._wlan.connect(self._ssid, self._secret, bssid=bssid)
                else:
                    self._wlan.connect(self._ssid, self._secret)
            except OSError as ose:
                logging.exception('got exception on wlan.connect', 'PicowNetwork:connect_to_network', ose)
            logging.info(f'...connecting to "{self._ssid}"...', 'PicowNetwork:connect_to_network')
            # logging.debug(f'...using secret "{self._secret}"...', 'PicowNetwork:connect_to_network')
            last_wl_status = -9
            while connect_timeout > 0:
                wl_status = self._wlan.status()
                logging.debug(f'wlan.status()={wl_status}', 'PicowNetwork:connect_to_network')
                if wl_status != last_wl_status:
                    last_wl_status = wl_status
                    st = self.network_status_map.get(wl_status) or 'undefined'
                    logging.info(f'...network status: {wl_status} {st}', 'PicowNetwork:connect_to_network')
                if wl_status < 0 or wl_status >= 3:
                    break
                connect_timeout -= 1
                await sleep(1)
            if wl_status != network.STAT_GOT_IP:
                logging.warning(f'...network connect failed: {wl_status}, pausing...', 'PicowNetwork:connect_to_network')
                if self._long_messages:
                    await self.set_message(f'Error {wl_status}\n{st}', -wl_status)
                else:
                    await self.set_message('ERROR ', -wl_status)
                self._wlan.active(False)
                await sleep(1)
                self._wlan.deinit()
                await sleep(10)  # pause after connection failure.
                return
            await sleep(0.5)

        logging.info(f'...connected: {self._wlan.ipconfig("addr4")}', 'PicowNetwork:connect_to_network')
        onboard.on()  # turn on the LED, WAN is up.
        ifconfig = self._wlan.ifconfig()
        self._ip_address = ifconfig[0]
        self._netmask = ifconfig[1]
        self._gateway = ifconfig[2]
        self._dns_server = ifconfig[3]
        self._connected = True

        ssid = self._wlan.config('ssid')
        if self._long_messages:
            if self._access_point_mode:
                msg = f'{ssid}\nAP: {self._ip_address}'
            else:
                msg = f'{ssid}\n{self._ip_address}'
        else:
            if self._access_point_mode:
                msg = f'AP {self._ip_address} '
            else:
                msg = f'{self._ip_address} '
        await self.set_message(msg, 1)

    def ifconfig(self):
        if self._wlan is not None:
            return self._wlan.ifconfig()
        else:
            return None

    def status(self):
        """
        get the status of the wlan
        :return:
        """
        keys = ['antenna',
                'channel',
                'hostname',
                # 'hidden',
                # 'key',
                'mac',
                'pm',
                # 'secret',
                'security',
                'ssid',
                # 'reconnects',
                'txpower']
        # note that there is also 'trace' and 'monitor' that appear to be write-only

        if self._wlan is not None:
            for k in keys:
                try:
                    data = self._wlan.config(k)
                    if isinstance(data, str):
                        logging.info(f'WLAN.config("{k}")="{data}"', 'PicowNetwork:status')
                    elif isinstance(data, int):
                        logging.info(f'WLAN.config("{k}")={data}', 'PicowNetwork:status')
                    elif isinstance(data, bytes):
                        mac = ':'.join([f'{b:02x}' for b in data])
                        logging.info(f'WLAN.config("{k}")={mac}', 'PicowNetwork:status')
                    else:
                        logging.info(f'WLAN.config("{k}")={data} {type(data)}', 'PicowNetwork:status')

                except Exception as exc:
                    logging.warning(f'{exc}: "{k}"', 'PicowNetwork:status')
        else:
            logging.warning('Network not initialized.', 'PicowNetwork:status')

    async def keep_alive(self):
        self._keepalive = True
        sleep = asyncio.sleep
        while self._keepalive:
            if self._access_point_mode:
                self._connected = self._wlan is not None and self._wlan.active()
            else:
                self._connected = self._wlan is not None and \
                                  self._wlan.status() == network.STAT_GOT_IP
            if logging.should_log(logging.DEBUG):
                logging.debug(f'connected = {self._connected}', 'PicowNetwork.keepalive')

            if not self._connected and not self._connecting:
                logging.warning('Not connected...  attempting network connect...', 'PicowNetwork:keep_alive')
                self._connecting = True
                try:
                    await self._connect()
                finally:
                    self._connecting = False
                if self._access_point_mode:
                    self._connected = self._wlan is not None and self._wlan.active()
                else:
                    self._connected = self._wlan is not None and \
                                      self._wlan.status() == network.STAT_GOT_IP
                if self._connected:
                    logging.info(f'Network connected', 'PicowNetwork:keep_alive')
                else:
                    logging.warning(f'Failed to connect', 'PicowNetwork:keep_alive')
            await sleep(30 if self._connected else 5)  # check network every 30 seconds when connected, every 5 when not.
        logging.info('keepalive exit', 'PicowNetwork.keepalive loop exit.')

    def get_message(self) -> str:
        return self._message

    def get_status(self) -> int:
        return self._status
