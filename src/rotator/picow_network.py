#
# picow_network.py -- Raspberry Pi Pico W connect to Wi-Fi Network.
#
__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2024, 2025, 2026  J. B. Otterson N1KDO.'
__version__ = '0.10.14'  # 2026-09-23

#
# Copyright 2024, 2025, 2026 J. B. Otterson N1KDO.
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
        network.STAT_IDLE: b'not connected',  # 0  CYW43_LINK_DOWN
        network.STAT_CONNECTING: b'connecting...',  # 1  CYW43_LINK_JOIN
        network.STAT_CONNECTING + 1: b'connected no IP addr',  # 2  CYW43_LINK_NOIP
        network.STAT_GOT_IP: b'connection successful',  # 3 CYW43_LINK_UP
        network.STAT_WRONG_PASSWORD: b'failed, bad password',  # -3 CYW43_LINK_FAIL
        network.STAT_NO_AP_FOUND: b'failed no AP replied',  # -2 CYW43_LINK_NONET
        network.STAT_CONNECT_FAIL: b'failed other problem',  # -1 CYW43_LINK_FAIL
    }

    def __init__(self,
                 config,  # must be ConfigData or subclass
                 default_ssid: str = 'PICO-W',
                 default_secret: str = 'PICO-WIFI',
                 message_func=None,
                 long_messages=False,
                 access_point_mode: bool = False) -> None:
        self._connected = False
        self._connecting = False
        self._default_secret = default_secret
        self._default_ssid = default_ssid
        self._keepalive = False
        self._message_func = message_func
        self._long_messages = long_messages
        self._ssid = config.get('SSID')
        self._ssid_bytes = config.get_bytes('SSID')
        if not self._ssid or not isinstance(self._ssid, str) or len(self._ssid) > 32:
            self._ssid = default_ssid
            self._ssid_bytes = self._ssid.encode()
        if self._ssid_bytes is None:
            self._ssid_bytes = self._ssid.encode()
        self._secret = config.get('secret')
        if self._secret is None or not isinstance(self._secret, str):
            self._secret = default_secret
        if len(self._secret) > 63:
            self._secret = self._secret[:63]

        self._hostname = config.get('hostname')
        if self._hostname is None or self._hostname == '':
            self._hostname = 'pico-w'
        self._hostname_bytes = config.get_bytes('hostname')
        if self._hostname_bytes is None:
            self._hostname_bytes = self._hostname.encode()

        self._access_point_mode = access_point_mode

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
        self._message = b''
        self._status = 0
        if self._long_messages:
            self._message = b'Network INIT'
        else:
            self._message = b'INIT'
        self._status = 0
        self._wlan = None
        self._keepalive = True
        self._keepalive_task = asyncio.create_task(self.keep_alive())

    def deinit(self) -> None:
        if self._wlan is not None:
            self._wlan.active(False)
            # self._wlan.deinit()   # is this needed?
        self._keepalive = False
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    def get_ip_address(self):
        return self._ip_address

    def get_netmask(self):
        return self._netmask

    def get_dns_servers(self):
        # tuple of dotted-quad strings (DHCP) or a single string (static config); None in AP mode
        return self._dns_server

    def is_connected(self):
        return self._connected

    async def set_message(self, message: bytes, status: int = 0) -> None:
        self._message = message
        self._status = status
        if self._message_func:
            try:
                await self._message_func(self._message, self._status)
            except Exception as exc:
                logging.exception('set_message failed', 'PicowNetwork:set_message', exc)

    async def _connect(self) -> None:
        network.country('US')
        network.ipconfig(prefer=4)  # this is an IPv4 network
        sleep = asyncio.sleep
        wl_status = 0

        onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
        onboard.on()
        if self._access_point_mode:
            if self._long_messages:
                await self.set_message(b'Starting setup WLAN.')
            logging.info('Starting setup WLAN...', 'PicowNetwork:connect_to_network')
            self._wlan = network.WLAN(network.WLAN.IF_AP)
            self._wlan.config(pm=self._wlan.PM_NONE)  # disable power save, this is a server.
            await sleep(0.1)
            logging.debug('Starting setup WLAN...1', 'PicowNetwork:connect_to_network')
            logging.info(b'  wlan.active()=%d' % self._wlan.active(), 'PicowNetwork:connect_to_network (new)')
            # wlan.deinit turns off the onboard LED because it is connected to the CYW43
            # turn it on again.
            onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
            onboard.on()
            try:
                if self._long_messages:
                    await self.set_message(b'Setting hostname %s' % self._hostname_bytes)
                logging.info(b'  Setting hostname "%s"' % self._hostname, 'PicowNetwork:connect_to_network')
                network.hostname(self._hostname)
            except ValueError:
                if self._long_messages:
                    await self.set_message(b'Failed to set hostname.', -10)
                else:
                    await self.set_message(b'ERROR ', -10)
                logging.error('Failed to set hostname.', 'PicowNetwork:connect_to_network')

            # security choices are 'SEC_OPEN', 'SEC_WPA2_WPA3', 'SEC_WPA3', 'SEC_WPA_WPA2'
            # see https://github.com/micropython/micropython/blob/master/extmod/network_cyw43.c#L584
            # Access Point mode always uses security and always uses the default secret.
            security = network.WLAN.SEC_WPA2_WPA3  # CYW43_AUTH_WPA2_AES_PSK

            mac_addr = self._wlan.config('mac')
            mac = ''
            if mac_addr is not None:
                mac = ''.join(['%02x' % b for b in mac_addr])
                if len(mac) == 12:
                    suffix = '-' + mac[6:]
                    if not self._default_ssid.endswith(suffix):
                        self._default_ssid = self._default_ssid + suffix
            self._wlan.config(ssid=self._default_ssid, key=self._default_secret, security=security)
            self._wlan.active(True)
            logging.info(b'  wlan.active()=%d' % self._wlan.active(), 'PicowNetwork:connect_to_network')
            logging.info(b'  ssid=%s' % self._wlan.config("ssid"), 'PicowNetwork:connect_to_network')
            logging.debug(b'  key=%s' % self._default_secret, 'PicowNetwork:connect_to_network')
            logging.info(b'  ipconfig addr4=%s' % self._wlan.ipconfig("addr4"), 'PicowNetwork:connect_to_network')
            self._connected = True
        else:
            if self._long_messages:
                await self.set_message(b'Connecting to WLAN.')
            logging.info('Connecting to WLAN...', 'PicowNetwork:connect_to_network')
            self._wlan = network.WLAN(network.WLAN.IF_STA)
            self._wlan.config(pm=self._wlan.PM_NONE)  # disable power save, this is a server.
            await sleep(0.1)
            logging.debug('Connecting to WLAN...1', 'PicowNetwork:connect_to_network')
            self._wlan.active(True)
            await sleep(0.1)
            logging.info(b'  wlan.active()=%d' % self._wlan.active(), 'PicowNetwork:connect_to_network (new)')
            # wlan.deinit turns off the onboard LED because it is connected to the CYW43
            # turn it on again.
            onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
            onboard.on()
            try:
                if self._long_messages:
                    await self.set_message(b'Setting hostname\n%s' % self._hostname_bytes)
                logging.info(b'...setting hostname "%s"' % self._hostname, 'PicowNetwork:connect_to_network')
                network.hostname(self._hostname)
                logging.debug('Connecting to WLAN...5', 'PicowNetwork:connect_to_network')
            except ValueError:
                if self._long_messages:
                    await self.set_message(b'Failed to set hostname.', -10)
                else:
                    await self.set_message(b'ERROR ', -10)
                logging.error('Failed to set hostname.', 'PicowNetwork:connect_to_network')
            logging.debug('Connecting to WLAN...6', 'PicowNetwork:connect_to_network')
            await sleep(0.1)

            logging.info(b'scanning for best signal for SSID "%s"' % self._ssid, 'PicowNetwork:connect_to_network')
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
                scan_ssid = result[0].decode('utf-8', 'replace')
                scan_bssid = b''.join([b'%02x' % b for b in result[1]])
                scan_channel = result[2]
                scan_rssi = result[3]
                scan_security = result[4]
                scan_hidden = result[5]
                if logging.should_log(logging.DEBUG):
                    logging.debug(
                        b'Found SSID "%s", BSSID "%s", channel %d, RSSI %d, security %d, hidden %d' % (scan_ssid,
                                                                                                       scan_bssid,
                                                                                                       scan_channel,
                                                                                                       scan_rssi,
                                                                                                       scan_security,
                                                                                                       scan_hidden),
                        'PicowNetwork:connect_to_network')
                if scan_ssid == self._ssid:
                    if scan_rssi > best_rssi:
                        best_rssi = scan_rssi
                        bssid = result[1]
            if bssid is not None:
                bssid_bytes = b''.join([b'%02x' % b for b in bssid])
                logging.info(b'Found best RSSI for SSID "%s" on BSSID "%s" RSSI %d'
                             % (self._ssid, bssid_bytes, best_rssi), 'PicowNetwork:connect_to_network')
            else:
                logging.warning('cannot find SSID in scan', 'PicowNetwork:connect_to_network')

            if not self._is_dhcp:
                if self._ip_address is not None and self._netmask is not None and self._gateway is not None:
                    logging.info('...configuring network with static IP', 'PicowNetwork:connect_to_network')
                    if not self._dns_server or self._dns_server == '0.0.0.0':
                        self._dns_server = '8.8.8.8'
                    self._wlan.ipconfig(addr4=(self._ip_address, self._netmask), gw4=self._gateway, dhcp4=False)
                    # the driver has no dns4 setting; set lwIP's DNS server explicitly.
                    network.ipconfig(dns=self._dns_server)
                else:
                    logging.warning('Cannot use static IP, data is missing.', 'PicowNetwork:connect_to_network')
                    logging.warning('Configuring network with DHCP....', 'PicowNetwork:connect_to_network')
                    self._is_dhcp = True
            if self._is_dhcp:
                self._wlan.ipconfig(dhcp4=True)
                logging.info('...configuring network with DHCP', 'PicowNetwork:connect_to_network')
            else:
                logging.info(b'...configuring network with %s' % self._wlan.ipconfig("addr4"),
                             'PicowNetwork:connect_to_network')

            connect_timeout = 15
            st = b''
            if self._long_messages:
                await self.set_message(b'Connecting to\n%s' % self._ssid_bytes)
            try:
                if bssid is not None:
                    self._wlan.connect(self._ssid, self._secret, bssid=bssid)
                else:
                    self._wlan.connect(self._ssid, self._secret)
            except OSError as ose:
                logging.exception('got exception on wlan.connect', 'PicowNetwork:connect_to_network', ose)
            logging.info(b'...connecting to "%s"...' % self._ssid, 'PicowNetwork:connect_to_network')
            # logging.debug(b'...using secret "%s"...' % self._secret, 'PicowNetwork:connect_to_network')
            last_wl_status = -9
            while connect_timeout > 0:
                try:
                    wl_status = self._wlan.status()
                except OSError as ose:
                    logging.exception('wlan.status() failed', 'PicowNetwork:connect_to_network', ose)
                    wl_status = network.STAT_CONNECT_FAIL
                    break
                logging.debug(b'wlan.status()=%d' % wl_status, 'PicowNetwork:connect_to_network')
                if wl_status != last_wl_status:
                    last_wl_status = wl_status
                    st = self.network_status_map.get(wl_status) or b'undefined'
                    logging.info(b'...network status: %d %s' % (wl_status, st), 'PicowNetwork:connect_to_network')
                if wl_status < 0 or wl_status >= 3:
                    break
                connect_timeout -= 1
                await sleep(1)
            if wl_status != network.STAT_GOT_IP:
                logging.warning(b'...network connect failed: %d, pausing...' % wl_status,
                                'PicowNetwork:connect_to_network')
                if self._long_messages:
                    await self.set_message(b'Error %d\n%s' % (wl_status, st), -wl_status)
                else:
                    await self.set_message(b'ERROR ', -wl_status)
                try:
                    self._wlan.active(False)
                    await sleep(1)
                    self._wlan.deinit()
                except OSError as exc:
                    logging.exception('wlan deinit failed', 'PicowNetwork:connect_to_network', exc)
                self._wlan = None
                await sleep(10)  # pause after connection failure.
                return
            await sleep(0.5)

        onboard.on()  # turn on the LED, WAN is up.
        ifconfig = self._wlan.ifconfig()
        self._ip_address = ifconfig[0]
        self._netmask = ifconfig[1]
        self._gateway = ifconfig[2]
        self._dns_server = ifconfig[3]
        logging.info(
            b'...connected: %s, %s, %s, %s' % (self._ip_address, self._netmask, self._gateway, self._dns_server),
            'PicowNetwork:connect_to_network')
        self._connected = True

        ssid = self._wlan.config('ssid')
        if self._long_messages:
            if self._access_point_mode:
                msg = b'%s\nAP: %s' % (ssid.encode(), self._ip_address.encode())
            else:
                msg = b'%s\n%s' % (ssid.encode(), self._ip_address.encode())
        else:
            if self._access_point_mode:
                msg = b'AP %s' % self._ip_address.encode()
            else:
                msg = self._ip_address.encode()
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
                        logging.info(b'WLAN.config("%s")="%s"' % (k, data), 'PicowNetwork:status')
                    elif isinstance(data, int):
                        logging.info(b'WLAN.config("%s")=%d' % (k, data), 'PicowNetwork:status')
                    elif isinstance(data, bytes):
                        mac = b':'.join([b'%02x' % b for b in data])
                        logging.info(b'WLAN.config("%s")=%s' % (k, mac), 'PicowNetwork:status')
                    else:
                        logging.info(b'WLAN.config("%s")=%s %s' % (k, data, type(data)), 'PicowNetwork:status')

                except Exception as exc:
                    logging.warning(b'%s: "%s"' % (exc, k), 'PicowNetwork:status')
        else:
            logging.warning('Network not initialized.', 'PicowNetwork:status')

    def _refresh_connected(self):
        # a failed status query means we cannot confirm the link; treat it as disconnected.
        try:
            if self._access_point_mode:
                self._connected = self._wlan is not None and self._wlan.active()
            else:
                self._connected = self._wlan is not None and \
                                  self._wlan.status() == network.STAT_GOT_IP
        except OSError as exc:
            logging.exception('keepalive failed', 'PicowNetwork:keep_alive', exc)
            self._connected = False

    async def keep_alive(self):
        last_is_connected = False
        sleep = asyncio.sleep
        await sleep(1)  # give the hardware time to settle
        while self._keepalive:
            try:
                self._refresh_connected()

                if logging.should_log(logging.DEBUG):
                    logging.debug(b'connected = %d' % self._connected, 'PicowNetwork.keepalive')

                if not self._connected and not self._connecting:
                    logging.warning('Not connected...  attempting network connect...', 'PicowNetwork:keep_alive')
                    self._connecting = True
                    try:
                        await self._connect()
                    except Exception as exc:
                        logging.exception('network connect failed', 'PicowNetwork:keep_alive', exc)
                        self._connected = False
                    finally:
                        self._connecting = False
                    self._refresh_connected()

                    if self._connected:
                        logging.info('Network connected', 'PicowNetwork:keep_alive')
                    else:
                        logging.warning('Failed to connect', 'PicowNetwork:keep_alive')
                if last_is_connected != self._connected:
                    # detect edge when self._connected changes
                    last_is_connected = self._connected
                    if not self._connected:
                        logging.warning('Network disconnected', 'PicowNetwork:keep_alive')
                        # send a disconnect message up from here.
                        if self._long_messages:
                            await self.set_message(b'not connected', -1)
                        else:
                            await self.set_message(b'NO NET', -1)
                await sleep(30 if self._connected else 5)  # check every 30 seconds when connected, every 5 when not.
            except Exception as exc:
                logging.exception('keep_alive loop error', 'PicowNetwork:keep_alive', exc)
        logging.info('keepalive exit', 'PicowNetwork.keepalive loop exit.')

    def get_message(self) -> bytes:
        return self._message

    def get_status(self) -> int:
        return self._status
