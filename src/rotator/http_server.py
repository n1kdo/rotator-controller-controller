#
# lightweight http server for MicroPython IOT things.
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, 2024, 2025, J. B. Otterson N1KDO.
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
__version__ = '0.1.3'

import gc
import json
import os
import re

from utils import milliseconds, safe_int, upython
if upython:
    import micro_logging as logging
else:
    import logging
    def const(i):
        return i

# these are the HTTP responses that will be sent.
HTTP_STATUS_OK = const(200)
HTTP_STATUS_CREATED = const(201)
HTTP_STATUS_BAD_REQUEST = const(400)
HTTP_STATUS_CONFLICT = const(409)
HTTP_STATUS_NOT_FOUND = const(404)
HTTP_STATUS_INTERNAL_SERVER_ERROR = const(500)

HTTP_VERB_GET = b'GET'
HTTP_VERB_POST = b'POST'

_BUFFER_SIZE = const(4096)
_MP_START_BOUND = const(1)
_MP_HEADERS = const(2)
_MP_DATA = const(3)
_MP_END_BOUND = const(4)


class HttpServer:
    CT_TEXT_TEXT = b'text/text'
    CT_TEXT_HTML = b'text/html'
    CT_APP_JSON = b'application/json'
    CT_APP_WWW_FORM = b'application/x-www-form-urlencoded'
    CT_MULTIPART_FORM = b'multipart/form-data'

    FILE_EXTENSION_TO_CONTENT_TYPE_MAP = {
        'gif': b'image/gif',
        'html': CT_TEXT_HTML,
        'ico': b'image/vnd.microsoft.icon',
        'json': CT_APP_JSON,
        'jpeg': b'image/jpeg',
        'jpg': b'image/jpeg',
        'png': b'image/png',
        'txt': CT_TEXT_TEXT,
        '*': b'application/octet-stream',
    }
    HYPHENS = b'--'
    HTTP_STATUS_TEXT = {
        HTTP_STATUS_OK: b'OK',
        HTTP_STATUS_CREATED: b'Created',
        #202: b'Accepted',
        #204: b'No Content',
        #301: b'Moved Permanently',
        #302: b'Moved Temporarily',
        #304: b'Not Modified',
        HTTP_STATUS_BAD_REQUEST: b'Bad Request',
        #401: b'Unauthorized',
        #403: b'Forbidden',
        HTTP_STATUS_NOT_FOUND: b'Not Found',
        HTTP_STATUS_CONFLICT: b'Conflict',
        HTTP_STATUS_INTERNAL_SERVER_ERROR: b'Internal Server Error',
        #501: b'Not Implemented',
        #502: b'Bad Gateway',
        #503: b'Service Unavailable',
    }

    DANGER_ZONE_FILE_NAMES = [
        'network.html',
        'files.html',
    ]

    def __init__(self, content_dir):
        self.content_dir = content_dir
        self.uri_map = {}
        self.buffer = bytearray(_BUFFER_SIZE)
        self.bmv = memoryview(self.buffer)

    def add_uri_callback(self, uri, callback):
        if isinstance(uri, str):
            logging.warning(f'uri {uri} is str not bytes', 'http_server:add_uri_callback')
            uri = uri.encode('utf-8')
        self.uri_map[uri] = callback

    async def serve_content(self, writer, filename):
        filename = self.content_dir + filename
        try:
            content_length = os.stat(filename)[6]
            content_length = safe_int(content_length, -1)
        except OSError:
            content_length = -1
        if content_length < 0:
            response = b'<html><body><p>404 -- File not found.</p></body></html>'
            http_status = HTTP_STATUS_NOT_FOUND
            return await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response), http_status
        extension = filename.split('.')[-1]
        content_type = self.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension)
        if content_type is None:
            content_type = self.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get('*')
        http_status = HTTP_STATUS_OK
        await self.start_response(writer, HTTP_STATUS_OK, content_type, content_length)
        try:
            with open(filename, 'rb', _BUFFER_SIZE) as infile:
                while True:
                    # readinto is supported by micropython
                    bytes_read = infile.readinto(self.bmv)
                    if bytes_read == _BUFFER_SIZE:
                        writer.write(self.bmv)
                    else:
                        writer.write(self.bmv[0:bytes_read])
                    await writer.drain()
                    if bytes_read < _BUFFER_SIZE:
                        break
        except Exception as exc:
            logging.error(f'{type(exc)} {exc}', 'http_server:serve_content')
        return content_length, http_status

    async def start_response(self, writer, http_status:int=HTTP_STATUS_OK, content_type:bytes=None, response_size:int=0, extra_headers:list[bytes]=None):
        status_text = self.HTTP_STATUS_TEXT.get(http_status) or b'Confused'
        writer.write(b'HTTP/1.0 %d %s\r\n' % (http_status, status_text))
        writer.write(b'Access-Control-Allow-Origin: *\r\n')  # CORS override
        if content_type is not None and len(content_type) > 0:
            writer.write(b'Content-type: ')
            writer.write(content_type)
            writer.write(b'; charset=UTF-8\r\n')
        if response_size > 0:
            writer.write(b'Content-length: %d \r\n' % response_size)
        if extra_headers is not None:
            for header in extra_headers:
                writer.write(header)
                writer.write(b'\r\n')
        writer.write(b'\r\n')
        await writer.drain()

    async def send_simple_response(self, writer, http_status=HTTP_STATUS_OK, content_type=None, response=None, extra_headers=None):
        content_length = 0
        typ = type(response)
        if response is None:
            await self.start_response(writer, http_status, None, 0, extra_headers)
        elif typ == bytes:
            content_length = len(response)
            await self.start_response(writer, http_status, content_type, content_length, extra_headers)
            if response is not None and len(response) > 0:
                writer.write(response)
        elif typ in [dict, list]:
            response = json.dumps(response).encode('utf-8')
            content_length = len(response)
            content_type = HttpServer.CT_APP_JSON
            await self.start_response(writer, http_status, content_type, content_length, extra_headers)
            if content_length > 0:
                writer.write(response)
        else:
            logging.error(f'trying to serialize {typ} response.', 'http_server:send_simple_response')
        await writer.drain()
        return content_length

    @classmethod
    def unpack_args(cls, value):
        args_dict = {}
        if value is not None:
            value = value.decode()
            args_list = value.split('&')
            for arg in args_list:
                arg_parts = arg.split('=')
                if len(arg_parts) == 2:
                    args_dict[arg_parts[0]] = arg_parts[1]
        return args_dict

    async def serve_http_client(self, reader, writer):
        gc.collect()
        # micropython.mem_info()
        t0 = milliseconds()
        http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
        bytes_sent = 0
        partner = writer.get_extra_info('peername')[0]
        if logging.should_log(logging.DEBUG):
            logging.debug(f'web client connected from {partner}', 'http_server:serve_http_client')
        request_line = await reader.readline()
        request = request_line.strip()
        if logging.should_log(logging.DEBUG):
            logging.debug(f'request: {request}', 'http_server:serve_http_client')
        pieces = request.split(b' ')
        if len(pieces) != 3:  # does the http request line look approximately correct?
            http_status = HTTP_STATUS_BAD_REQUEST
            response = b'Bad Request !=3'
            logging.warning(f'Bad request, wrong number of pieces: {pieces}')
            bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
        else:
            verb = pieces[0]
            target = pieces[1]
            protocol = pieces[2]
            # should validate protocol here...
            if b'?' in target:
                pieces = target.split(b'?')
                target = pieces[0]
                query_args = pieces[1]
            else:
                query_args = b''
            if verb not in [HTTP_VERB_GET, HTTP_VERB_POST]:
                http_status = HTTP_STATUS_BAD_REQUEST
                logging.warning(b'Bad request, wrong verb {verb}', 'http_server:serve_http_client')
                response = b'<html><body><p>only GET and POST are supported</p></body></html>'
                bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            elif protocol not in [b'HTTP/1.0', b'HTTP/1.1']:
                logging.warning(f'bad request, wrong http protocol {protocol}', 'http_server:serve_http_client')
                http_status = HTTP_STATUS_BAD_REQUEST
                response = b'protocol %s is not supported' % protocol
                bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            else:
                # get HTTP request headers
                request_content_length = 0
                request_content_type = b''
                request_headers = {}
                while True:
                    header = await reader.readline()
                    if len(header) == 0:
                        # empty header line, eof?
                        break
                    if header == b'\r\n':
                        # blank line at end of headers
                        break
                    # process headers.  look for those we are interested in.
                    parts = header.split(b':', 1)
                    header_name = parts[0].strip()
                    header_value = parts[1].strip()
                    request_headers[header_name] = header_value
                    if header_name == b'Content-Length':
                        request_content_length = int(header_value)
                    elif header_name == b'Content-Type':
                        request_content_type = header_value
                args = {}
                if verb == HTTP_VERB_GET:
                    args = self.unpack_args(query_args)
                elif verb == HTTP_VERB_POST:
                    if request_content_length > 0:
                        if request_content_type == self.CT_APP_WWW_FORM:
                            data = await reader.read(request_content_length)
                            args = self.unpack_args(data)
                        elif request_content_type == self.CT_APP_JSON:
                            data = await reader.read(request_content_length)
                            args = json.loads(data.decode())
                        elif not request_content_type.startswith(self.CT_MULTIPART_FORM):
                            logging.warning(f'warning: unhandled content_type {request_content_type}',
                                            'http_server:serve_http_client')
                            logging.warning(f'request_content_length={request_content_length}',
                                            'http_server:serve_http_client')
                else:  # bad request
                    http_status = HTTP_STATUS_BAD_REQUEST
                    response = b'only GET and POST are supported'
                    logging.warning(response, 'http_server:serve_http_client')
                    bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)

                if verb in (HTTP_VERB_GET, HTTP_VERB_POST):
                    callback = self.uri_map.get(target)
                    if callback is not None:
                        bytes_sent, http_status = await callback(self, verb, args, reader, writer, request_headers)
                    else:
                        content_file = target[1:] if target[0] == '/' else target
                        bytes_sent, http_status = await self.serve_content(writer, content_file.decode())

        await writer.drain()
        writer.close()
        await writer.wait_closed()
        elapsed = milliseconds() - t0
        logging.info(f'{partner} {request} {http_status} {bytes_sent} {elapsed} ms',
                     'http_server:serve_http_client')
        gc.collect()

#
# common file operations callbacks, here because just about every app will use them...
#


def valid_filename(filename):
    if filename is None:
        return False
    match = re.match('^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?.[a-zA-Z0-9_-]+$', filename)
    if match is None:
        return False
    if match.group(0) != filename:
        return False
    extension = filename.split('.')[-1].lower()
    if HttpServer.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension) is None:
        return False
    return True


def file_size(filename):
    try:
        return os.stat(filename)[6]
    except OSError:
        return -1


# noinspection PyUnusedLocal
async def api_get_files_callback(http, verb, args, reader, writer, request_headers=None):
    if verb == HTTP_VERB_GET:
        response = os.listdir(http.content_dir)
        http_status = HTTP_STATUS_OK
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    else:
        http_status = HTTP_STATUS_BAD_REQUEST
        response = b'only GET permitted'
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_upload_file_callback(http, verb, args, reader, writer, request_headers=None):
    if verb == HTTP_VERB_POST:
        logging.debug('http post handler', 'http_server:api_upload_file_callback')
        boundary = None
        request_content_type = request_headers.get(b'Content-Type') or ''
        if ';' in request_content_type:
            pieces = request_content_type.split(b';')
            request_content_type = pieces[0]
            boundary = pieces[1].strip()
            if boundary.startswith(b'boundary='):
                boundary = boundary[9:]
        if request_content_type != http.CT_MULTIPART_FORM or boundary is None:
            response = b'multipart boundary or content type error'
            http_status = HTTP_STATUS_BAD_REQUEST
        else:
            response = b'unhandled problem'
            http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
            request_content_length = int(request_headers.get(b'Content-Length') or '0')
            remaining_content_length = request_content_length
            logging.info(f'upload content length {request_content_length}', 'main:api_upload_file_callback')
            start_boundary = http.HYPHENS + boundary
            end_boundary = start_boundary + http.HYPHENS
            state = _MP_START_BOUND
            filename = None
            output_file = None
            writing_file = False
            more_bytes = True
            leftover_bytes = []
            while more_bytes:
                buffer = await reader.read(_BUFFER_SIZE)
                remaining_content_length -= len(buffer)
                if remaining_content_length == 0:  # < BUFFER_SIZE:
                    more_bytes = False
                if len(leftover_bytes) != 0:
                    buffer = leftover_bytes + buffer
                    leftover_bytes = []
                start = 0
                while start < len(buffer):
                    if state == _MP_DATA:
                        if not output_file:
                            output_file = open(http.content_dir + 'uploaded_' + filename, 'wb')
                            writing_file = True
                        end = len(buffer)
                        for i in range(start, len(buffer) - 3):
                            if buffer[i] == 13 and buffer[i + 1] == 10 and buffer[i + 2] == 45 and \
                                    buffer[i + 3] == 45:
                                end = i
                                writing_file = False
                                break
                        if end == _BUFFER_SIZE:
                            if buffer[-1] == 13:
                                leftover_bytes = buffer[-1:]
                                buffer = buffer[:-1]
                                end -= 1
                            elif buffer[-2] == 13 and buffer[-1] == 10:
                                leftover_bytes = buffer[-2:]
                                buffer = buffer[:-2]
                                end -= 2
                            elif buffer[-3] == 13 and buffer[-2] == 10 and buffer[-1] == 45:
                                leftover_bytes = buffer[-3:]
                                buffer = buffer[:-3]
                                end -= 3
                        output_file.write(buffer[start:end])
                        if not writing_file:
                            state = _MP_END_BOUND
                            output_file.close()
                            output_file = None
                            response = b'Uploaded %s successfully' % filename
                            http_status = HTTP_STATUS_CREATED
                        start = end + 2
                    else:  # must be reading headers or boundary
                        line = ''
                        for i in range(start, len(buffer) - 1):
                            if buffer[i] == 13 and buffer[i + 1] == 10:
                                line = buffer[start:i]
                                start = i + 2
                                break
                        if state == _MP_START_BOUND:
                            if line == start_boundary:
                                state = _MP_HEADERS
                            else:
                                logging.error(f'expecting start boundary, got {line}', 'main:api_upload_file_callback')
                        elif state == _MP_HEADERS:
                            if len(line) == 0:
                                state = _MP_DATA
                            elif line.startswith(b'Content-Disposition:'):
                                pieces = line.split(b';')
                                fn = pieces[2].strip()
                                if fn.startswith(b'filename="'):
                                    filename = fn[10:-1].decode()
                                    if not valid_filename(filename):
                                        response = b'bad filename'
                                        http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
                                        more_bytes = False
                                        start = len(buffer)
                        elif state == _MP_END_BOUND:
                            if line == end_boundary:
                                state = _MP_START_BOUND
                            else:
                                logging.error(f'expecting end boundary, got {line}', 'main:api_upload_file_callback')
                        else:
                            http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
                            response = b'unmanaged state %d' % state
        logging.warning(f'upload response: {response}', 'http_server:api_upload_file_callback')
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    else:
        response = b'POST only.'
        http_status = HTTP_STATUS_BAD_REQUEST
        bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_remove_file_callback(http, verb, args, reader, writer, request_headers=None):
    filename = args.get('filename')
    if valid_filename(filename) and filename not in HttpServer.DANGER_ZONE_FILE_NAMES:
        filename = http.content_dir + filename
        try:
            os.remove(filename)
            http_status = HTTP_STATUS_OK
            response = f'removed {filename}'.encode('utf-8')
        except OSError as ose:
            http_status = HTTP_STATUS_CONFLICT
            response = str(ose).encode('utf-8')
    else:
        http_status = HTTP_STATUS_CONFLICT
        response = b'bad file name'
    bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_rename_file_callback(http, verb, args, reader, writer, request_headers=None):
    filename = args.get('filename')
    newname = args.get('newname')
    if valid_filename(filename) and valid_filename(newname):
        filename = http.content_dir + filename
        newname = http.content_dir + newname
        if file_size(newname) >= 0:
            http_status = HTTP_STATUS_CONFLICT
            response = f'new file {newname} already exists'.encode('utf-8')
        else:
            try:
                os.remove(newname)
            except OSError:
                pass  # swallow exception.
            try:
                os.rename(filename, newname)
                http_status = HTTP_STATUS_OK
                response = f'renamed {filename} to {newname}'.encode('utf-8')
            except Exception as ose:
                http_status = HTTP_STATUS_CONFLICT
                response = str(ose).encode('utf-8')
    else:
        http_status = HTTP_STATUS_CONFLICT
        response = b'bad file name'
    bytes_sent = await http.send_simple_response(writer, http_status, http.CT_APP_JSON, response)
    return bytes_sent, http_status
