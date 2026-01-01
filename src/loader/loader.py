#!/bin/env python3
__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, 2024, 2025 J. B. Otterson N1KDO.
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
__version__ = '0.10.7'  # 2025-12-31

"""
Note: to edit linux forced device names, edit
/etc/udev/rules.d/99-usb-serial.rules
see: https://programmador.com/posts/2023/linux-usb-serial-device-name-binding/
see: https://k4sbc.com/consistently-name-usb-serial-ports/
"""
import argparse
import hashlib
import json
import os
import sys
import time

# need pyserial to enumerate com ports.
from serial.tools.list_ports import comports
from serial import SerialException
from pyboard import Pyboard, PyboardError

_BAUD_RATE = 115200
_BUFFER_SIZE = 2048

_WATCHDOG_PY = 'watchdog.py'

class BytesConcatenator:
    """
    this is used to collect data from pyboard functions that otherwise do not return data.
    """
    __slots__ = ('data',)

    def __init__(self):
        self.data = bytearray()

    def write_bytes(self, b):
        self.data.extend(b.replace(b"\x04", b""))

    def __str__(self):
        return self.data.decode('utf-8', errors='replace').replace('\r', '')


def get_ports_list():
    return sorted(x.device for x in comports())


# noinspection PyUnusedLocal
def put_file_progress_callback(bytes_so_far, bytes_total):
    print(f'{bytes_so_far:05d}/{bytes_total:05d} bytes sent.\r', end='', flush=True)


def put_file(filename, target, source_directory='.', src_file_name=None):
    if src_file_name is None:
        src_file_name = source_directory + filename
    else:
        src_file_name = source_directory + src_file_name

    if filename.endswith('/'):  # does it end in a slash?
        filename = filename[:-1]
        try:
            print(f'creating target directory {filename}')
            target.fs_mkdir(filename)
        except PyboardError as exc:
            if 'EEXIST' not in str(exc):
                print(f'failed to create target directory {filename}')
                return False
    else:
        try:
            os.stat(src_file_name)
            print(f'sending file {src_file_name} to {filename}')
            target.fs_put(src_file_name, filename, progress_callback=put_file_progress_callback)
            print()
        except OSError:
            print(f'cannot find source file {src_file_name}')
            return False
    return True


def loader_bootloader(target):
    cmd = f"""import machine
machine.bootloader()
"""
    target.exec_raw_no_follow(cmd)


def loader_implementation(target):
    data = BytesConcatenator()
    cmd = f"""import sys
nm = sys.implementation.name
ver = sys.implementation.version
ver = '{{}}.{{}}.{{}}'.format(ver[0], ver[1], ver[2])
mach = sys.implementation._machine
print('{{}}|{{}}|{{}}'.format(nm, ver, mach))
"""
    target.exec_(cmd, data_consumer=data.write_bytes)
    return str(data).rstrip('\n').split('|')


def loader_ls(target, src='/'):
    files_found = []
    files_data = BytesConcatenator()
    cmd = f"""import uos
for f in uos.ilistdir('{src}'):
    print('{{}}{{}}'.format(f[0], '/' if f[1] & 0x4000 else ''))
"""
    #print(cmd)
    target.exec_(cmd, data_consumer=files_data.write_bytes)
    files = str(files_data).split('\n')
    for phile in files:
        if len(phile) > 0:
            if phile.endswith('/'):
                children = loader_ls(target, phile)
                for child in children:
                    files_found.append(f'{phile}{child}')
            files_found.append(phile)
    return files_found


def loader_reset(target):
    files_data = BytesConcatenator()
    cmd = f"""import machine
machine.reset()
"""
    target.exec_(cmd, data_consumer=files_data.write_bytes)


def loader_sha1(target, file=''):
    hash_data = BytesConcatenator()
    cmd = f"""import hashlib
hasher = hashlib.sha1()
with open('{file}', 'rb') as fp:
  while True:
    buffer = fp.read(2048)
    if buffer is None or len(buffer) == 0:
      break
    hasher.update(buffer)
print(bytes.hex(hasher.digest()))
"""
    target.exec_(cmd, data_consumer=hash_data.write_bytes)
    return str(hash_data).strip()


def local_sha1(file):
    hasher = hashlib.sha1()
    with open(file, 'rb') as fp:
        while True:
            buffer = fp.read(_BUFFER_SIZE)
            if buffer is None or len(buffer) == 0:
                break
            hasher.update(buffer)
    return bytes.hex(hasher.digest())


def load_device(port, force=False,
                manifest_filename='loader_manifest.json',
                no_watchdog=False,
                bootloader=False):
    try:
        with open(manifest_filename, 'r') as manifest_file:
            manifest = json.load(manifest_file)
            files_list = manifest.get('files', [])
            special_files_list = manifest.get('special_files', [])
            source_directory = manifest.get('source_directory', '.')
    except FileNotFoundError:
        print(f'cannot open manifest file {manifest_filename}.')
        sys.exit(1)

    try:
        target = Pyboard(port, _BAUD_RATE)
    except PyboardError:
        print(f'cannot connect to device {port}')
        sys.exit(1)

    target.enter_raw_repl()
    #
    restart = False
    if True:
        existing_files = loader_ls(target)
        if _WATCHDOG_PY in existing_files:
            print(f'removing existing file {_WATCHDOG_PY}')
            target.fs_rm(_WATCHDOG_PY)
            restart = True

    if restart:
        try:
            print('resetting target device...')
            loader_reset(target)
        except SerialException as e:
            time.sleep(3)
        else:
            print('expected disconnect on reset, something is wrong?')

        try:
            print('reconnecting to target device...')
            target = Pyboard(port, _BAUD_RATE)
        except PyboardError:
            print(f'cannot connect to device {port}')
            sys.exit(1)

        target.enter_raw_repl()

    target_impl = loader_implementation(target)
    print(target_impl)

    if bootloader:
        print('starting boot loader')
        loader_bootloader(target)
        target.close()
        print('Either upload firmware file (uf2) or power cycle device to exit bootloader mode.')
        return

    # clean up files that do not belong here.
    existing_files = loader_ls(target)
    for existing_file in existing_files:
        if existing_file in special_files_list:
            continue  # do not delete any special file
        safe_to_delete = True
        if existing_file[-1] == '/':
            for special_file in special_files_list:
                if existing_file in special_file:
                    safe_to_delete = False
                    break
        if not safe_to_delete:
            continue #  do not (try to) delete any directory containing special files
        if force or existing_file not in files_list:
            if existing_file[-1] == '/':
                print(f'removing directory {existing_file[:-1]}')
                target.fs_rmdir(existing_file[:-1])
            else:
                print(f'removing file {existing_file}')
                target.fs_rm(existing_file)

    # now add the files that do belong here.
    existing_files = loader_ls(target)
    for file in files_list:
        if not file.endswith('/'):
            if no_watchdog and file.endswith(_WATCHDOG_PY):
                print(f'Skipping {file}')
                continue
            # if this is not a directory, get the sha1 hash of the pico-w file
            # and compare it with the sha1 hash of the local file.
            # do not send unchanged files.  This makes subsequent loader invocations much faster.
            if file in existing_files:
                picow_hash = loader_sha1(target, file)
                local_hash = local_sha1(source_directory + file)
                if picow_hash == local_hash:
                    continue
            put_file(file, target, source_directory=source_directory)
        else:
            if file not in existing_files:
                put_file(file, target, source_directory=source_directory)

    # this is logic that will not overwrite any of the SPECIAL FILES if present,
    # if it is not present, it will use the contents of $file.example
    for file in special_files_list:
        if file not in existing_files:
            put_file(file, target, source_directory=source_directory, src_file_name=f'{file}.example')
    target.exit_raw_repl()
    # done updating file system, restart the device and show the output
    print('Device should restart.')
    target.serial.write(b"\x04")  # control-D -- restart
    try:
        while True:
            b = target.serial.read(1)
            sys.stdout.write(b.decode())
    except SerialException:
        print('Error: Serial Exception, did the port go away?  Did you unplug the USB cable?')
    except KeyboardInterrupt:
        print('Keyboard Interrupt, bye bye.')
    except Exception as e:
        print(str(e))
        print(type(e))

    target.close()


def main():
    parser = argparse.ArgumentParser(
        prog='Loader',
        description='Load an application to a micropython device')
    parser.add_argument('--bootloader',
                        action='store_true',
                        help='restart device in boot loader mode')
    parser.add_argument('--force',
                        action='store_true',
                        help='force all files to be replaced')
    parser.add_argument('--no-watchdog',
                        action='store_true',
                        help='do not load watchdog.py.')
    parser.add_argument('--port',
                        help='name of serial port, otherwise it will be detected.')
    parser.add_argument('--manifest-filename',
                        help='name of manifest file',
                        default='loader_manifest.json')
    args = parser.parse_args()
    if 'bootloader' in args:
        bootloader = args.bootloader
    else:
        bootloader = False
    if 'force' in args:
        force = args.force
    else:
        force = False
    if 'no_watchdog' in args:
        no_watchdog = args.no_watchdog
    else:
        no_watchdog = False
    if 'port' in args and args.port is not None:
        picow_port = args.port
    else:
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
        sys.exit(1)

    print(f'Loading device on {picow_port}...')
    load_device(picow_port,
                force,
                manifest_filename=args.manifest_filename,
                no_watchdog=no_watchdog,
                bootloader=bootloader)


if __name__ == "__main__":
    main()
