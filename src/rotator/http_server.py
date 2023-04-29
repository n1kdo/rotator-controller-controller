#
# lightweight http server for MicroPython IOT things.
#

#
# Copyright 2023, J. B. Otterson N1KDO.
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
#

import gc
import json
import os
import sys
import time
impl_name = sys.implementation.name


def milliseconds():
    if impl_name == 'cpython':
        return int(time.time() * 1000)
    return time.ticks_ms()


class HttpServer:
    BUFFER_SIZE = 4096
    CT_TEXT_TEXT = 'text/text'
    CT_TEXT_HTML = 'text/html'
    CT_APP_JSON = 'application/json'
    CT_APP_WWW_FORM = 'application/x-www-form-urlencoded'
    CT_MULTIPART_FORM = 'multipart/form-data'

    FILE_EXTENSION_TO_CONTENT_TYPE_MAP = {
        'gif': 'image/gif',
        'html': CT_TEXT_HTML,
        'ico': 'image/vnd.microsoft.icon',
        'json': CT_APP_JSON,
        'jpeg': 'image/jpeg',
        'jpg': 'image/jpeg',
        'png': 'image/png',
        'txt': CT_TEXT_TEXT,
        '*': 'application/octet-stream',
    }
    HYPHENS = '--'
    HTTP_STATUS_TEXT = {
        200: 'OK',
        201: 'Created',
        202: 'Accepted',
        204: 'No Content',
        301: 'Moved Permanently',
        302: 'Moved Temporarily',
        304: 'Not Modified',
        400: 'Bad Request',
        401: 'Unauthorized',
        403: 'Forbidden',
        404: 'Not Found',
        409: 'Conflict',
        500: 'Internal Server Error',
        501: 'Not Implemented',
        502: 'Bad Gateway',
        503: 'Service Unavailable',
    }
    MP_START_BOUND = 1
    MP_HEADERS = 2
    MP_DATA = 3
    MP_END_BOUND = 4

    def __init__(self, content_dir):
        self.content_dir = content_dir
        self.verbosity = 3
        self.uri_map = {}

    def add_uri_callback(self, uri, callback):
        self.uri_map[uri] = callback

    def serve_content(self, writer, filename):
        filename = self.content_dir + filename
        try:
            content_length = os.stat(filename)[6]
            if not isinstance(content_length, int):
                if content_length.isdigit():
                    content_length = int(content_length)
                else:
                    content_length = -1
        except OSError:
            content_length = -1
        if content_length < 0:
            response = b'<html><body><p>404.  Means &quot;no got&quot;.</p></body></html>'
            http_status = 404
            return self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response), http_status
        extension = filename.split('.')[-1]
        content_type = self.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension)
        if content_type is None:
            content_type = self.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get('*')
        http_status = 200
        self.start_response(writer, 200, content_type, content_length)
        try:
            with open(filename, 'rb', self.BUFFER_SIZE) as infile:
                while True:
                    buffer = infile.read(self.BUFFER_SIZE)
                    writer.write(buffer)
                    if len(buffer) < self.BUFFER_SIZE:
                        break
        except Exception as exc:
            print(type(exc), exc)
        return content_length, http_status

    def start_response(self, writer, http_status=200, content_type=None, response_size=0, extra_headers=None):
        status_text = self.HTTP_STATUS_TEXT.get(http_status) or 'Confused'
        protocol = 'HTTP/1.0'
        writer.write(f'{protocol} {http_status} {status_text}\r\n'.encode('utf-8'))
        if content_type is not None and len(content_type) > 0:
            writer.write(f'Content-type: {content_type}; charset=UTF-8\r\n'.encode('utf-8'))
        if response_size > 0:
            writer.write(f'Content-length: {response_size}\r\n'.encode('utf-8'))
        if extra_headers is not None:
            for header in extra_headers:
                writer.write(f'{header}\r\n'.encode('utf-8'))
        writer.write(b'\r\n')

    def send_simple_response(self, writer, http_status=200, content_type=None, response=None, extra_headers=None):
        content_length = len(response) if response else 0
        self.start_response(writer, http_status, content_type, content_length, extra_headers)
        if response is not None and len(response) > 0:
            writer.write(response)
        return content_length

    @classmethod
    def unpack_args(cls, value):
        args_dict = {}
        if value is not None:
            args_list = value.split('&')
            for arg in args_list:
                arg_parts = arg.split('=')
                if len(arg_parts) == 2:
                    args_dict[arg_parts[0]] = arg_parts[1]
        return args_dict

    async def serve_http_client(self, reader, writer):
        t0 = milliseconds()
        http_status = 418  # can only make tea, sorry.
        bytes_sent = 0
        partner = writer.get_extra_info('peername')[0]
        if self.verbosity >= 4:
            print(f'\nweb client connected from {partner}')
        request_line = await reader.readline()
        request = request_line.decode().strip()
        if self.verbosity >= 4:
            print(request)
        pieces = request.split(' ')
        if len(pieces) != 3:  # does the http request line look approximately correct?
            http_status = 400
            response = b'Bad Request !=3'
            bytes_sent = self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
        else:
            verb = pieces[0]
            target = pieces[1]
            protocol = pieces[2]
            # should validate protocol here...
            if '?' in target:
                pieces = target.split('?')
                target = pieces[0]
                query_args = pieces[1]
            else:
                query_args = ''
            if verb not in ['GET', 'POST']:
                http_status = 400
                response = b'<html><body><p>only GET and POST are supported</p></body></html>'
                bytes_sent = self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            elif protocol not in ['HTTP/1.0', 'HTTP/1.1']:
                http_status = 400
                response = b'that protocol is not supported'
                bytes_sent = self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            else:
                # get HTTP request headers
                request_content_length = 0
                request_content_type = ''
                while True:
                    header = await reader.readline()
                    request_headers = {}
                    if len(header) == 0:
                        # empty header line, eof?
                        break
                    if header == b'\r\n':
                        # blank line at end of headers
                        break
                    else:
                        # process headers.  look for those we are interested in.
                        parts = header.decode().strip().split(':', 1)
                        request_headers[parts[0].strip().lower()] = parts[1].strip()
                        if parts[0] == 'Content-Length':
                            request_content_length = int(parts[1].strip())
                        elif parts[0] == 'Content-Type':
                            request_content_type = parts[1].strip()

                args = {}
                if verb == 'GET':
                    args = self.unpack_args(query_args)
                elif verb == 'POST':
                    if request_content_length > 0:
                        if request_content_type == self.CT_APP_WWW_FORM:
                            data = await reader.read(request_content_length)
                            args = self.unpack_args(data.decode())
                        elif request_content_type == self.CT_APP_JSON:
                            data = await reader.read(request_content_length)
                            args = json.loads(data.decode())
                        # else:
                        #    print('warning: unhandled content_type {}'.format(request_content_type))
                        #    print('request_content_length={}'.format(request_content_length))
                else:  # bad request
                    http_status = 400
                    response = b'only GET and POST are supported'
                    bytes_sent = self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)

                if verb in ('GET', 'POST'):
                    callback = self.uri_map.get(target)
                    if callback is not None:
                        bytes_sent, http_status = await callback(self, verb, args, reader, writer, request_headers)
                    else:
                        content_file = target[1:] if target[0] == '/' else target
                        bytes_sent, http_status = self.serve_content(writer, content_file)

        await writer.drain()
        writer.close()
        await writer.wait_closed()
        elapsed = milliseconds() - t0
        if http_status == 200:
            if self.verbosity > 2:
                print(f'{partner} {request} {http_status} {bytes_sent} {elapsed} ms')
        else:
            if self.verbosity >= 1:
                print(f'{partner} {request} {http_status} {bytes_sent} {elapsed} ms')
        gc.collect()
