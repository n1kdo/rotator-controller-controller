#!/bin/env python3

import os
import pyboard
from serial.tools.list_ports import comports
BAUD_RATE = 115200

SRC_DIR = '../pico-w/'
FILES_LIST = [
    'content/',
    'data/',
    'main.py',
    'pico_rotator.py',
    'content/compass-background.png',
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
    print('\n\nPower cycle device')


def main():
    ports = get_ports_list()
    print(ports)
    port = 'com10'
    load_device(port)


if __name__ == "__main__":
    main()
