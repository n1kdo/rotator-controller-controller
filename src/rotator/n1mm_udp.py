
__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2023, J. B. Otterson N1KDO.
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

import socket
import sys

impl_name = sys.implementation.name
if impl_name == 'cpython':
    import asyncio
else:
    import uasyncio as asyncio

ROTOR_BROADCAST_BUF_SIZE = 512


def calculate_broadcast_address(ip_address, netmask):
    # calculate the subnet's broadcast address using ip_address and netmask
    ip_int = sum([int(x) << 8 * i for i, x in enumerate(reversed(ip_address.split('.')))])
    mask_int = sum([int(x) << 8 * i for i, x in enumerate(reversed(netmask.split('.')))])
    mask_mask = mask_int ^ 0xffffffff
    bcast_int = ip_int | mask_mask
    bcast_addr = ".".join(map(str, [
        ((bcast_int >> 24) & 0xff),
        ((bcast_int >> 16) & 0xff),
        ((bcast_int >> 8) & 0xff),
        (bcast_int & 0xff),
    ]))
    return bcast_addr


def get_element(src, name):
    i = src.index(f'<{name}>')
    if i > 0:
        start = i + 2 + len(name)
        ii = src.index('<', start)
        if ii > start:
            return src[start:ii]
    return None


class SendBroadcastFromN1MM:
    """
    class to send UDP datagrams to N1MM
    """

    def __init__(self, target_ip, target_port, rotator=None, my_name=None):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sockaddr = socket.getaddrinfo(target_ip, target_port)[0][-1]
        self.rotator = rotator
        self.my_name = my_name
        self.run = True

    def send(self, payload):
        self.socket.sendto(payload.encode(), self.sockaddr)

    async def send_datagrams(self):
        while self.run:
            bearing = await self.rotator.get_rotator_bearing()
            message = f'{self.my_name} @ {bearing*10}'
            self.send(message)
            await asyncio.sleep(1.50)

    def stop(self):
        self.run = False


class ReceiveBroadcastsFromN1MM:
    """
    class that receives rotor control datagrams from N1MM
    """

    def __init__(self, receive_ip, receive_port, rotator=None, my_name=None):
        self.receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rotator = rotator
        self.my_name = my_name
        self.run = True
        try:
            sockaddr = socket.getaddrinfo(receive_ip, receive_port)[0][-1]
            self.receive_socket.bind(sockaddr)
            self.receive_socket.settimeout(0.001)
        except Exception as exc:
            print(exc, type(exc))

    async def wait_for_datagram(self):
        while self.run:
            try:
                udp_data = self.receive_socket.recv(ROTOR_BROADCAST_BUF_SIZE)
                message = udp_data.decode('utf-8')
                rotor_name = get_element(message, 'rotor')
                if rotor_name == self.my_name:
                    goazi = get_element(message, 'goazi')
                    bearing = int(float(goazi))
                    result = await self.rotator.set_rotator_bearing(bearing)
                    if result < 0:
                        print(f'set_rotator_bearing result={result}')
            except OSError as ose:
                pass
            except Exception as exc:
                print(exc, type(exc))
            await asyncio.sleep(0.1)
        while self.run:
            pass

    def stop(self):
        self.run = False
