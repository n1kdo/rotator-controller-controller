#
# serial port listener
#
# listens on com3 for traffic sent
# listens on com4 for traffic received
# this uses a hardware tap and two serial ports to sniff the traffic.
#
import logging
import serial
import sys
import time

BAUD_RATE = 4800


def hexdump_buffer(buffer):
    result = ''
    hex_bytes = ''
    printable = ''
    offset = 0
    ofs = '{:04x}'.format(offset)
    for b in buffer:
        hex_bytes += '{:02x} '.format(b)
        printable += chr(b) if 32 <= b <= 126 else '.'
        offset += 1
        if len(hex_bytes) >= 48:
            result += ofs + '  ' + hex_bytes + '  ' + printable +'\n'
            hex_bytes = ''
            printable = ''
            ofs = '{:04x}'.format(offset)
    if len(hex_bytes) > 0:
        hex_bytes += ' ' * 47
        hex_bytes = hex_bytes[0:47]
        result += ofs + '  ' + hex_bytes + '   ' + printable + '\n'
    return result


def dump_buffer(name, buffer, dump_all=False):
    print(f'{name}: {len(buffer)} bytes:')
    print(hexdump_buffer(buffer))


def main():
    verbosity = 5
    try:
        tx_port = serial.Serial(port='com3:',
                                baudrate=BAUD_RATE,
                                parity=serial.PARITY_NONE,
                                bytesize=serial.EIGHTBITS,
                                stopbits=serial.STOPBITS_ONE,
                                timeout=0)
        rx_port = serial.Serial(port='com4:',
                                baudrate=BAUD_RATE,
                                parity=serial.PARITY_NONE,
                                bytesize=serial.EIGHTBITS,
                                stopbits=serial.STOPBITS_ONE,
                                timeout=0)

        tx_buffer = bytearray()
        rx_buffer = bytearray()

        while True:
            while True:
                buf = tx_port.read(32)
                if buf is not None and len(buf) > 0:
                    dump_buffer('tx', buf, True)
                else:
                    break
            while True:
                buf = rx_port.read(32)
                if buf is not None and len(buf) > 0:
                    dump_buffer('rx', buf, True)
                else:
                    break

    except IOError as e:
        print(e)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:{}',
                        level=logging.INFO,
                        stream=sys.stdout)
    logging.Formatter.converter = time.gmtime
    main()
