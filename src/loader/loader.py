#!/bin/env python3
__author__ = 'J. B. Otterson'
__copyright__ = 'Copyright 2022, J. B. Otterson N1KDO.'

import os
import pyboard
import serial
from serial.tools.list_ports import comports
BAUD_RATE = 115200

SRC_DIR = '../rotator/'
FILES_LIST = [
    'content/',
    'data/',
    'dcu3_rotator.py',
    'http_server.py',
    'main.py',
    'morse_code.py',
    'serialport.py',
    'content/compass-background.png',
    'content/favicon.ico',
    'content/files.html',
    'content/rotator.html',
    'content/setup.html',
    'data/config.json',
]


def get_ports_list():
    ports = comports()
    ports_list = []
    for port in ports:
        ports_list.append(port.device)
    return sorted(ports_list, key=lambda k: int(k[3:]))


def put_file_progress_callback(a,b):
    print('.', end='')


def put_file(filename, target):
    src_file_name = SRC_DIR + filename
    if filename[-1:] == '/':
        filename = filename[:-1]
        try:
            target.fs_mkdir(filename)
            print('created directory {}'.format(filename))
        except Exception as e:
            if 'EEXIST' not in str(e):
                print('failed to create directory {}'.format(filename))
                print(type(e), e)
    else:
        try:
            os.stat(src_file_name)
            print('sending file {} '.format(filename), end='')
            target.fs_put(src_file_name, filename, progress_callback=put_file_progress_callback)
            print()
        except OSError as e:
            print('cannot find source file {}'.format(src_file_name))


def load_device(port):
    target = pyboard.Pyboard(port, BAUD_RATE)
    target.enter_raw_repl()
    for file in FILES_LIST:
        put_file(file, target)
    target.exit_raw_repl()
    target.close()

    # this is a hack that allows the Pico-W to be restarted by this script.
    # it exits the REPL by sending a control-D.
    # why this functionality is not the Pyboard module is a good question.
    with serial.Serial(port=port,
                       baudrate=BAUD_RATE,
                       parity=serial.PARITY_NONE,
                       bytesize=serial.EIGHTBITS,
                       stopbits=serial.STOPBITS_ONE,
                       timeout=1) as pyboard_port:
        pyboard_port.write(b'\x04')
    print('\nDevice should restart.')


def main():
    print('Disconnect the Pico-W if it is connected.')
    input('(press enter to continue...)')
    ports_1 = get_ports_list()
    print('Detected serial ports: ' + ' '.join(ports_1))
    print('\nConnect the Pico-W to USB port. Wait for the USB connected sound.')
    input('(press enter to continue...)')
    ports_2 = get_ports_list()
    print('Detected serial ports: ' + ' '.join(ports_2))

    picow_port = None
    for port in ports_2:
        if port not in ports_1:
            picow_port = port
            break

    if picow_port is None:
        print('Could not identify Pico-W communications port.  Exiting.')
        exit(1)

    print('\nAttempting to load device on port {}'.format(picow_port))
    load_device(picow_port)


if __name__ == "__main__":
    main()
