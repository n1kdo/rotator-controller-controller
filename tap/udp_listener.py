import logging
import socket
import time
from line_tap import hexdump_buffer

ROTOR_BROADCAST_BUF_SIZE = 512
N1MM_ROTOR_BROADCAST_PORT = 12040
N1MM_OTHER_BROADCAST_PORT = 13010

my_name = 'rotor-50'


# rotor talks back on 13010, see https://n1mmwp.hamdocs.com/setup/interfacing/#rotator-udp-packet-information
# """rotor on com1 @ 650"""

run = True


class RotorBroadcaster:
    """
    class to send UDP datagrams to N1MM
    """

    def __init__(self, target_ip, target_port=N1MM_OTHER_BROADCAST_PORT):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.sockaddr = socket.getaddrinfo(target_ip, target_port)[0][-1]

    def send(self, payload):
        self.socket.sendto(payload.encode(), self.sockaddr)


def get_element(src, name):
    i = src.index(f'<{name}>')
    if i > 0:
        start = i + 2 + len(name)
        ii = src.index('<', start)
        if ii > start:
            return src[start:ii]
    return None


def main():
    rotor_broadcaster = RotorBroadcaster('192.168.1.255')
    degrees = 0
    counter = 0

    try:
        receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            #receive_socket.bind(('', N1MM_BROADCAST_PORT))
            #receive_socket.bind(('127.0.0.1', N1MM_BROADCAST_PORT))
            sockaddr = socket.getaddrinfo('192.168.1.102', N1MM_ROTOR_BROADCAST_PORT)[0][-1]
            receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            #receive_socket.setblocking(0)
            receive_socket.bind(sockaddr)
            receive_socket.settimeout(0.001)
            global run
            while run:
                try:
                    udp_data = receive_socket.recv(ROTOR_BROADCAST_BUF_SIZE)
                    print(udp_data)
                    message = udp_data.decode('utf-8')
                    rotor_name = get_element(message, 'rotor')
                    print(f'rotor_name="{rotor_name}"')
                    goazi = get_element(message, 'goazi')
                    print(f'goazi={goazi}')

                    #print(hexdump_buffer(udp_data))

                # """<N1MMRotor><rotor>*</rotor><goazi>66.0</goazi><offset>0.0</offset><bidirectional>0</bidirectional><freqband>28.0</freqband></N1MMRotor>"""

                except socket.timeout:
                    # print('read timed out')
                    pass
                except BlockingIOError as bie:
                    # print(bie)
                    pass
                except Exception as exc:
                    print(exc, type(exc))
                time.sleep(0.1)
                # send rotor position to n1mm
                if counter < 0: # 9:
                    counter += 1
                else:
                    counter = 0
                    degrees = (degrees + 10) % 360
                    bcast_message = f'{my_name} @ {degrees*10}'
                    # print(bcast_message)
                    rotor_broadcaster.send(bcast_message)


        finally:
            if receive_socket is not None:
                receive_socket.close()
    except KeyboardInterrupt:
        run = False


if __name__ == '__main__':
    main()

