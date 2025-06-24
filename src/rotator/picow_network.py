#
# picow_network.py -- Raspberry Pi Pico W connect to Wifi Network.
# this is pulled out to its own module because it is used widely.
#

__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2024, 2025 J. B. Otterson N1KDO.'
__version__ = '0.9.5'

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

from utils import upython

if upython:
    # noinspection PyUnresolvedReferences
    import machine
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    import network
    # noinspection PyUnresolvedReferences
    import uasyncio as asyncio
    import micro_logging as logging
else:
    import asyncio
    import logging

import socket


class PicowNetwork:
    network_status_map = {
        network.STAT_IDLE: 'no connection and no activity',  # 0
        network.STAT_CONNECTING: 'connecting in progress',  # 1
        network.STAT_CONNECTING + 1: 'connected no IP address',  # 2, this is undefined, but returned.
        network.STAT_GOT_IP: 'connection successful',  # 3
        network.STAT_WRONG_PASSWORD: 'failed due to incorrect password',  # -3
        network.STAT_NO_AP_FOUND: 'failed because no access point replied',  # -2
        network.STAT_CONNECT_FAIL: 'failed due to other problems',  # -1
    }

    def __init__(self,
                 config: dict,
                 default_ssid:str='PICO-W',
                 default_secret:str='PICO-W',
                 message_func=None) -> None:
        self._keepalive = False
        self._message_func = message_func
        self._default_ssid = default_ssid
        self._default_secret = default_secret
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
        self._wlan = None
        self._noisy = self._message_func is not None
        if self._noisy:
            self.set_message('Network INIT', 0)
        asyncio.create_task(self.keep_alive())

    def get_ip_address(self):
        return self._ip_address

    def get_netmask(self):
        return self._netmask

    async def set_message(self, message: str, status:int = 0) -> None:
        self._message = message
        self._status = status
        if self._message_func:
            await self._message_func(self._message, self._status)

    async def connect(self):
        network.country('US')
        sleep = asyncio.sleep
        wl_status = 0

        if self._access_point_mode:
            if self._noisy:
                await self.set_message('Starting setup WLAN...')
            logging.info('Starting setup WLAN...', 'PicowNetwork:connect_to_network')
            self._wlan = network.WLAN(network.AP_IF)
            self._wlan.deinit()
            self._wlan.active(False)
            await sleep(1)

            self._wlan = network.WLAN(network.AP_IF)
            self._wlan.config(pm=self._wlan.PM_NONE)  # disable power save, this is a server.
            # wlan.deinit turns off the onboard LED because it is connected to the CYW43
            # turn it on again.
            onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
            onboard.on()

            try:
                if self._noisy:
                    await self.set_message(f'Setting hostname "{self._hostname}"')
                logging.info(f'  Setting hostname "{self._hostname}"', 'PicowNetwork:connect_to_network')
                network.hostname(self._hostname)
            except ValueError:
                if self._noisy:
                    await self.set_message('Failed to set hostname.', -10)
                logging.error('Failed to set hostname.', 'PicowNetwork:connect_to_network')

            #
            #define CYW43_AUTH_OPEN (0)                     ///< No authorisation required (open)
            #define CYW43_AUTH_WPA_TKIP_PSK   (0x00200002)  ///< WPA authorisation
            #define CYW43_AUTH_WPA2_AES_PSK   (0x00400004)  ///< WPA2 authorisation (preferred)
            #define CYW43_AUTH_WPA2_MIXED_PSK (0x00400006)  ///< WPA2/WPA mixed authorisation
            #

            if len(self._secret) == 0:
                security = 0
            else:
                security = 0x00400004  # CYW43_AUTH_WPA2_AES_PSK

            mac_addr = self._wlan.config('mac')
            mac = ''
            if mac_addr is not None:
                for b in mac_addr:
                    mac = mac + f'{b:02x}'
                if len(mac) == 12:
                    self._default_ssid = self._default_ssid + '-' + mac[6:]
            self._wlan.config(ssid=self._default_ssid, key=self._default_secret, security=security)
            self._wlan.active(True)
            logging.info(f'  wlan.active()={self._wlan.active()}', 'PicowNetwork:connect_to_network')
            logging.info(f'  ssid={self._wlan.config("ssid")}', 'PicowNetwork:connect_to_network')
            logging.info(f'  ifconfig={self._wlan.ifconfig()}', 'PicowNetwork:connect_to_network')
        else:
            if self._noisy:
                await self.set_message('Connecting to WLAN...')
            logging.info('Connecting to WLAN...', 'PicowNetwork:connect_to_network')
            self._wlan = network.WLAN(network.STA_IF)
            self._wlan.disconnect()
            self._wlan.deinit()
            self._wlan.active(False)
            await sleep(1)
            # get a new one.
            self._wlan = network.WLAN(network.STA_IF)
            # wlan.deinit turns off the onboard LED because it is connected to the CYW43
            # turn it on again.
            onboard = machine.Pin('LED', machine.Pin.OUT, value=0)
            onboard.on()
            try:
                if self._noisy:
                    await self.set_message(f'Setting hostname\n{self._hostname}')
                logging.info(f'...setting hostname "{self._hostname}"', 'PicowNetwork:connect_to_network')
                network.hostname(self._hostname)
            except ValueError:
                if self._noisy:
                    await self.set_message('Failed to set hostname.', -10)
                logging.error('Failed to set hostname.', 'PicowNetwork:connect_to_network')
            self._wlan.active(True)
            self._wlan.config(pm=self._wlan.PM_NONE)  # disable power save, this is a server.

            if not self._is_dhcp:
                if self._ip_address is not None and self._netmask is not None and self._gateway is not None and self._dns_server is not None:
                    logging.info('...configuring network with static IP', 'PicowNetwork:connect_to_network')
                    self._wlan.ifconfig((self._ip_address, self._netmask, self._gateway, self._dns_server))
                    # TODO FIXME wlan.ifconfig is deprecated, "dns" parameter is not found in the doc
                    # https://docs.micropython.org/en/latest/library/network.html
                    # but it is not defined for the cyc43 on pico-w
                    #self.wlan.ipconfig(addr4=(self.ip_address, self.netmask),
                    #                   gw4=self.gateway,
                    #                   dns=self.dns_server)
                else:
                    logging.warning('Cannot use static IP, data is missing.', 'PicowNetwork:connect_to_network')
                    logging.warning('Configuring network with DHCP....', 'PicowNetwork:connect_to_network')
                    self._is_dhcp = True
            if self._is_dhcp:
                self._wlan.ipconfig(dhcp4=True)
                logging.info(f'...configuring network with DHCP {self._wlan.ifconfig()}', 'PicowNetwork:connect_to_network')
            else:
                logging.info(f'...configuring network with {self._wlan.ifconfig()}', 'PicowNetwork:connect_to_network')

            max_wait = 15
            st = ''
            if self._noisy:
                await self.set_message(f'Connecting to\n{self._ssid}')
            self._wlan.connect(self._ssid, self._secret)
            ssid = self._wlan.config('ssid')
            logging.info(f'...connecting to "{self._ssid}"...', 'PicowNetwork:connect_to_network')
            last_wl_status = -9
            while max_wait > 0:
                wl_status = self._wlan.status()
                if wl_status != last_wl_status:
                    last_wl_status = wl_status
                    st = self.network_status_map.get(wl_status) or 'undefined'
                    logging.info(f'...network status: {wl_status} {st}', 'PicowNetwork:connect_to_network')
                if wl_status < 0 or wl_status >= 3:
                    break
                max_wait -= 1
                await sleep(1)
            if wl_status != network.STAT_GOT_IP:
                logging.warning(f'...network connect timed out: {wl_status}', 'PicowNetwork:connect_to_network')
                if self._noisy:
                    await self.set_message(f'Error {wl_status}\n{st}', wl_status)
                else:
                    await self.set_message('ERR')

                return None
            logging.info(f'...connected: {self._wlan.ifconfig()}', 'PicowNetwork:connect_to_network')

        onboard.on()  # turn on the LED, WAN is up.
        #wl_config = self._wlan.ipconfig('addr4') # get use str param name.
        ifconfig = self._wlan.ifconfig()
        self._ip_address = ifconfig[0]
        self._netmask = ifconfig[1]
        self._gateway = ifconfig[2]
        self._dns_server = ifconfig[3]

        ssid = self._wlan.config('ssid')
        if self._noisy:
            if self._access_point_mode:
                msg = f'{ssid}\nAP: {self._ip_address}'
            else:
                msg = f'{ssid}\n{self._ip_address}'
        else:
            if self._access_point_mode:
                msg = f'AP {self._ip_address}'
            else:
                msg = self._ip_address
        await self.set_message(msg, wl_status)
        return

    def ifconfig(self):
        return self._wlan.ifconfig()

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

    def is_connected(self):
        return self._wlan.isconnected() if self._wlan is not None else False

    def has_wan(self):
        if not self.is_connected():
            return False
        test_host = 'www.google.com'
        try:
            addr = socket.getaddrinfo(test_host, 80)
            if addr is not None and len(addr) > 0:
                addr = addr[0][4][0]
            else:
                return False
        except Exception as exc:
            logging.error(f'cannot lookup {test_host}: {exc}')
            return False
        logging.info(f'has_wan found IP {addr}')
        return True

    def has_router(self):
        if not self.is_connected():
            return False
        s = None
        try:
            router_ip = self._wlan.ifconfig()[2]
            addr = socket.getaddrinfo(router_ip, 80)[0][-1]
            s = socket.socket()
            s.connect(addr)
            s.send(b'GET / HTTP/1.1\r\n\r\n')
            data = s.recv(128)
            if data is not None and len(data) > 0:
                # print(f'got some data: "{str(data)}".')
                return True
        except Exception as exc:
            logging.error(f'cannot lookup or connect to router: {exc}')
            return False
        finally:
            if s is not None:
                s.close()
                s = None

    async def keep_alive(self):
        self._keepalive = True
        # eliminate >1 dict lookup
        sleep = asyncio.sleep
        while self._keepalive:
            connected = self.is_connected()
            logging.debug(f'self.is_connected() = {self.is_connected()}','PicowNetwork.keepalive')
            if not connected:
                logging.warning('not connected...  attempting network connect...', 'PicowNetwork:keep_alive')
                await self.connect()
            else:
                logging.debug(f'connected = {connected}', 'PicowNetwork.keepalive')
            await sleep(10)  # check network every 10 seconds
        logging.info('keepalive exit', 'PicowNetwork.keepalive loop exit.')

    def get_message(self):
        return self._message

    def get_status(self):
        return self._status

