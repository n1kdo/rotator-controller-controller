#
# lightweight http server for MicroPython IOT things.
#

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2022, 2024, 2025, 2026 J. B. Otterson N1KDO.
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
__version__ = '0.1.22'  # 2026-09-03

import asyncio
import os
import re
import micro_logging as logging

from utils import milliseconds, elapsed_ms, safe_int, upython, LineReader
if upython:
    import json
    from asyncio import TimeoutError
else:
    import compatible_json as json
    from asyncio.exceptions import TimeoutError

    def const(i):
        return i

# these are the HTTP responses that will be sent.
# noinspection PyUnboundLocalVariable
HTTP_STATUS_OK = const(200)
HTTP_STATUS_CREATED = const(201)
HTTP_STATUS_MOVED_PERMANENTLY = const(301)
HTTP_STATUS_BAD_REQUEST = const(400)
HTTP_STATUS_FORBIDDEN = const(403)
HTTP_STATUS_CONFLICT = const(409)
HTTP_STATUS_NOT_FOUND = const(404)
HTTP_STATUS_LENGTH_REQUIRED = const(411)
HTTP_STATUS_CONTENT_TOO_LARGE = const(413)
HTTP_STATUS_INTERNAL_SERVER_ERROR = const(500)

HTTP_VERB_GET = b'GET'
HTTP_VERB_POST = b'POST'
_HTTP_VERBS = (HTTP_VERB_GET, HTTP_VERB_POST)
_HTTP_PROTOCOLS = (b'HTTP/1.0', b'HTTP/1.1')

_BUFFER_SIZE = const(4096)
_MP_START_BOUND = const(1)
_MP_HEADERS = const(2)
_MP_DATA = const(3)
_MP_END_BOUND = const(4)

_MAX_UPLOAD_SIZE = const(65536)  # biggest allowed file upload.
_REQUEST_TIMEOUT = const(30)  # seconds to wait for the client's request.
_MAX_HEADERS = const(32)  # reject requests with more headers than this.
DOTS = '..'
SEP = '/'

def _safe_content_path(content_dir: str, filename: str) -> str:
    """
    Return a 'safe' content path for a relative filename,
    or raise ValueError if filename contains '/' or '..'.
    """
    if SEP in filename or DOTS in filename:
        raise ValueError('forbidden path traversal')
    if content_dir.endswith(SEP):
        joined = content_dir + filename
    else:
        joined = content_dir + SEP + filename
    return joined


class _WriterCounter:
    # Per-request wrapper that counts the bytes handed to write().  Lets _handle_request
    # know whether a failing callback had already started sending its response, in which
    # case an error page can no longer be sent without corrupting the stream.
    def __init__(self, writer):
        self._writer = writer
        self.bytes_written = 0

    def write(self, data):
        self.bytes_written += len(data)
        self._writer.write(data)

    async def drain(self):
        await self._writer.drain()

    def close(self):
        self._writer.close()

    async def wait_closed(self):
        await self._writer.wait_closed()

    def get_extra_info(self, name):
        return self._writer.get_extra_info(name)


class HttpServer:
    CT_TEXT_TEXT = b'text/plain'
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
        HTTP_STATUS_MOVED_PERMANENTLY: b'Moved Permanently',
        #302: b'Moved Temporarily',
        #304: b'Not Modified',
        HTTP_STATUS_BAD_REQUEST: b'Bad Request',
        #401: b'Unauthorized',
        HTTP_STATUS_FORBIDDEN: b'Forbidden',
        HTTP_STATUS_NOT_FOUND: b'Not Found',
        HTTP_STATUS_CONFLICT: b'Conflict',
        HTTP_STATUS_INTERNAL_SERVER_ERROR: b'Internal Server Error',
        #501: b'Not Implemented',
        #502: b'Bad Gateway',
        #503: b'Service Unavailable',
    }

    DANGER_ZONE_FILE_NAMES = (
        'files.html',
        'network.html',
        'setup.html',
    )

    def __init__(self, content_dir):
        self.content_dir = content_dir
        self.uri_map = {b'/api/get_files': api_get_files_callback,
                        b'/api/upload_file': api_upload_file_callback,
                        b'/api/remove_file': api_remove_file_callback,
                        b'/api/rename_file': api_rename_file_callback,
                        }

        self.buffer = bytearray(_BUFFER_SIZE)
        self.bmv = memoryview(self.buffer)
        self._content_lock = asyncio.Lock()

    def route(self, uri):
        if isinstance(uri, str):
            logging.error(f'uri {uri} is str not bytes', 'http_server:route')
            raise RuntimeError(f'uri {uri} is str not bytes')

        def decorator(func):
            self.uri_map[uri] = func
            return func
        return decorator

    async def serve_content(self, writer, filename : str):
        try:
            filename = _safe_content_path(self.content_dir, filename)
        except ValueError:
            response = b'<html><body><p>403 -- Forbidden.</p></body></html>'
            return (await self.send_simple_response(writer, HTTP_STATUS_FORBIDDEN, self.CT_TEXT_HTML, response),
                    HTTP_STATUS_FORBIDDEN)
        try:
            content_length = file_size(filename)
        except OSError:
            content_length = -1
        if content_length < 0:
            response = b'<html><body><p>404 -- File not found.</p></body></html>'
            return (await self.send_simple_response(writer, HTTP_STATUS_NOT_FOUND, self.CT_TEXT_HTML, response),
                    HTTP_STATUS_NOT_FOUND)
        extension = filename.split('.')[-1].lower()
        content_type = self.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension, b'application/octet-stream')
        await self.start_response(writer, HTTP_STATUS_OK, content_type, content_length)
        try:
            async with self._content_lock:
                with open(filename, 'rb', buffering=_BUFFER_SIZE) as infile:
                    bytes_since_drain = 0
                    # Drain after every chunk so the asyncio write buffer never holds more than one
                    # chunk at a time; keeps peak memory low on the Pico-W regardless of file size.
                    drain_threshold = _BUFFER_SIZE
                    while True:
                        bytes_read = infile.readinto(self.buffer)
                        if bytes_read:
                            writer.write(self.bmv[:bytes_read])
                            bytes_since_drain += bytes_read
                            if bytes_since_drain >= drain_threshold:
                                await writer.drain()
                                bytes_since_drain = 0
                        if bytes_read < _BUFFER_SIZE:
                            break
                    # EOF reached; ensure pending bytes are flushed.
                    if bytes_since_drain:
                        await writer.drain()
        except Exception as exc:
            logging.exception(f'error serving {filename}', 'http_server:serve_content', exc_info=exc)
        return content_length, HTTP_STATUS_OK

    async def start_response(self, writer, http_status:int=HTTP_STATUS_OK, content_type:bytes=b'', response_size:int=0, extra_headers:list[bytes]=None):
        status_text = self.HTTP_STATUS_TEXT.get(http_status) or b'Confused'
        writer.write(b'HTTP/1.0 %d %s\r\n' % (http_status, status_text))
        writer.write(b'Access-Control-Allow-Origin: *\r\n')  # CORS override
        if content_type is not None and len(content_type) > 0:
            writer.write(b'Content-type: ')
            writer.write(content_type)
            if content_type in (HttpServer.CT_TEXT_TEXT, HttpServer.CT_TEXT_HTML, HttpServer.CT_APP_JSON):
                writer.write(b'; charset=UTF-8\r\n')
            else:
                writer.write(b'\r\n')
        if response_size >= 0:
            writer.write(b'Content-length: %d\r\n' % response_size)
        if extra_headers is not None:
            for header in extra_headers:
                writer.write(header)
                writer.write(b'\r\n')
        writer.write(b'\r\n')
        await writer.drain()

    async def send_simple_response(self, writer, http_status=HTTP_STATUS_OK, content_type=b'', response=None, extra_headers=None):
        content_length = 0
        if response is None:
            await self.start_response(writer, http_status, content_type, content_length, extra_headers)
        else:
            if isinstance(response, str):
                response = response.encode()
            if isinstance(response, bytes):
                content_length = len(response)
                await self.start_response(writer, http_status, content_type, content_length, extra_headers)
                if response is not None and len(response) > 0:
                    writer.write(response)
            elif isinstance(response, dict) or isinstance(response, list):
                response = json.dumps(response).encode('utf-8')  # yes, need to send bytes here.
                content_length = len(response)
                content_type = HttpServer.CT_APP_JSON
                await self.start_response(writer, http_status, content_type, content_length, extra_headers)
                if content_length > 0:
                    writer.write(response)
            else:
                logging.error(f'trying to serialize response of type {type(response)}.',
                              'http_server:send_simple_response')
        await writer.drain()
        return content_length

    @classmethod
    def url_unquote(cls, s : str):
        s = s.replace('+', ' ')
        res = s.split('%')
        for i in range(1, len(res)):
            item = res[i]
            try:
                res[i] = chr(int(item[:2], 16)) + item[2:]
            except ValueError:
                res[i] = '%' + item
        return ''.join(res)

    @classmethod
    def unpack_args(cls, value : bytes):
        """
        accept a byte string and unpack it into a dict(str, str)
        """
        if not value:
            return {}
        args = {}
        args_list = value.split(b'&')
        for arg in args_list:
            arg_parts = arg.split(b'=', 1)
            if len(arg_parts) == 2:
                args[cls.url_unquote(arg_parts[0].decode())] = cls.url_unquote(arg_parts[1].decode())
        if logging.should_log(logging.DEBUG):
            logging.debug(f'unpack_args: {value} -> {args}', 'http_server:unpack_args')
        return args

    async def serve_http_client(self, reader, writer):
        partner = writer.get_extra_info('peername')[0]
        try:
            await self._handle_request(reader, writer)
        except Exception as ex:
            # don't let a bad client or a callback exception leak the socket;
            # the connection is simply closed in the finally block below.
            logging.exception(f'exception serving {partner}',
                              'http_server:serve_http_client', ex)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass  # the peer may have gone away already.

    async def _handle_request(self, reader, writer):
        # micropython.mem_info()
        t0 = milliseconds()
        http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
        bytes_sent = 0
        partner = writer.get_extra_info('peername')[0]
        if logging.should_log(logging.DEBUG):
            logging.debug(f'web client connected from {partner}', 'http_server:serve_http_client')
        lines = LineReader(reader, max_line_length=_BUFFER_SIZE)
        try:
            request_line = await asyncio.wait_for(lines.readline(), _REQUEST_TIMEOUT)  # returns bytes
        except TimeoutError:
            logging.info(f'client {partner} timed out sending the request line', 'http_server:_handle_request')
            return
        except ValueError:  # request line exceeded LineReader's limit
            http_status = HTTP_STATUS_BAD_REQUEST
            response = b'request line too long'
            bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            return
        request = request_line.strip()
        if logging.should_log(logging.DEBUG):
            logging.debug(b'request: %s' % request, 'http_server:serve_http_client')
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
                pieces = target.split(b'?', 1)
                target = pieces[0]
                query_args = pieces[1]
            else:
                query_args = b''
            if verb not in _HTTP_VERBS:
                http_status = HTTP_STATUS_BAD_REQUEST
                logging.warning(f'Bad request, wrong verb {verb}', 'http_server:serve_http_client')
                response = b'<html><body><p>only GET and POST are supported</p></body></html>'
                bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            elif protocol not in _HTTP_PROTOCOLS:
                logging.warning(f'bad request, wrong http protocol {protocol}', 'http_server:serve_http_client')
                http_status = HTTP_STATUS_BAD_REQUEST
                response = b'protocol %s is not supported' % protocol
                bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_HTML, response)
            else:
                # get HTTP request headers
                request_content_length = 0
                request_content_type = b''
                request_headers = {}
                dispatch = True
                header_count = 0
                while True:
                    header_count += 1
                    if header_count > _MAX_HEADERS:
                        http_status = HTTP_STATUS_BAD_REQUEST
                        response = b'too many request headers'
                        bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)
                        dispatch = False
                        break
                    try:
                        header = await asyncio.wait_for(lines.readline(), _REQUEST_TIMEOUT)
                    except TimeoutError:
                        logging.info(f'client {partner} timed out sending headers', 'http_server:_handle_request')
                        http_status = HTTP_STATUS_BAD_REQUEST
                        response = b'request timed out'
                        bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)
                        dispatch = False
                        break
                    except ValueError:  # header line exceeded LineReader's limit
                        http_status = HTTP_STATUS_BAD_REQUEST
                        response = b'header line too long'
                        bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)
                        dispatch = False
                        break
                    if header in (b'', b'\r\n'):
                        break
                    if not header.endswith(b'\n'):  # EOF arrived mid-header; the line is truncated.
                        http_status = HTTP_STATUS_BAD_REQUEST
                        response = b'malformed request headers'
                        bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)
                        dispatch = False
                        break
                    # process headers.  look for those we are interested in.
                    if b':' not in header:  # ignore malformed header
                        continue
                    parts = header.split(b':', 1)
                    header_name = parts[0].strip().lower()
                    header_value = parts[1].strip()
                    request_headers[header_name] = header_value
                    if header_name == b'content-length':
                        request_content_length = safe_int(header_value, -1)
                    elif header_name == b'content-type':
                        request_content_type = header_value
                args = {}
                if dispatch and verb == HTTP_VERB_GET:
                    args = self.unpack_args(query_args)
                elif dispatch and verb == HTTP_VERB_POST:
                    if request_content_length > 0:
                        if request_content_type.startswith(self.CT_APP_WWW_FORM) or request_content_type.startswith(self.CT_APP_JSON):
                            if request_content_length > _BUFFER_SIZE:
                                http_status = HTTP_STATUS_CONTENT_TOO_LARGE
                                response = b'POST payload too large'
                                bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)
                                dispatch = False  # prevent further processing
                            else:
                                try:
                                    data = await asyncio.wait_for(lines.readexactly(request_content_length), _REQUEST_TIMEOUT)
                                except (EOFError, TimeoutError):
                                    http_status = HTTP_STATUS_BAD_REQUEST
                                    response = b'incomplete POST body'
                                    bytes_sent = await self.send_simple_response(writer, http_status, self.CT_TEXT_TEXT, response)
                                    dispatch = False
                                else:
                                    if request_content_type.startswith(self.CT_APP_WWW_FORM):
                                        args = self.unpack_args(data)
                                    elif request_content_type.startswith(self.CT_APP_JSON):
                                        try:
                                            args = json.loads(data)
                                        except Exception as e:
                                            args = {}
                                            logging.error(f'cannot decode posted JSON "{data}": {e}',
                                                          'http_server:serve_http_client')
                        elif not request_content_type.startswith(self.CT_MULTIPART_FORM):
                            logging.warning(f'warning: unhandled content_type {request_content_type}',
                                            'http_server:serve_http_client')
                            logging.warning(f'request_content_length={request_content_length}',
                                            'http_server:serve_http_client')

                if dispatch:
                    counting_writer = _WriterCounter(writer)
                    try:
                        callback = self.uri_map.get(target)
                        if callback is not None:
                            # pass the LineReader (not the raw stream) so callbacks that
                            # read the request body get any bytes readline() pulled ahead.
                            bytes_sent, http_status = await callback(self, verb, args, lines, counting_writer, request_headers)
                        else:
                            content_file = (target[1:] if target.startswith(b'/') else target).decode()  # filename must be str
                            bytes_sent, http_status = await self.serve_content(counting_writer, content_file)
                    except Exception as ex:
                        logging.exception(f'exception serving {target} from {partner}: {type(ex)} {ex}',
                                          'http_server:_handle_request', ex)
                        if counting_writer.bytes_written == 0:
                            # nothing has been sent yet, so the client can still get a proper error page.
                            try:
                                bytes_sent = await self.send_simple_response(writer, HTTP_STATUS_INTERNAL_SERVER_ERROR,
                                                                             self.CT_TEXT_HTML,
                                                                             b'<html><body><p>500 -- Internal Server Error.</p></body></html>')
                            except Exception:
                                pass  # socket is already broken; serve_http_client closes it.
                        else:
                            bytes_sent = counting_writer.bytes_written  # response was cut short mid-stream
                        http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR

        await writer.drain()
        elapsed = elapsed_ms(t0)
        if logging.should_log(logging.INFO):
            logging.info(f'{partner} {request} {http_status} {bytes_sent} {elapsed} ms',
                         'http_server:serve_http_client')

#
# common file operations callbacks, here because just about every app will use them...
#
def valid_filename(filename : str):
    if filename is None:
        return False
    match = re.match(r'^[A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9_-]+$', filename)
    if match is None:
        return False
    if match.group(0) != filename:
        return False
    extension = filename.split('.')[-1].lower()
    if HttpServer.FILE_EXTENSION_TO_CONTENT_TYPE_MAP.get(extension) is None:
        return False
    return True


def file_size(filename : str):
    try:
        # note that micropython os.stat()does not return a named tuple, so cannot access with .st_size
        return safe_int(os.stat(filename)[6], -1)
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
        if logging.should_log(logging.DEBUG):
            logging.debug('http post handler', 'http_server:api_upload_file_callback')
        boundary = None
        request_content_type = b''
        request_content_length = -1
        for header_name in request_headers.keys():
            lower_header_name = header_name.lower()
            if lower_header_name == b'content-type':
                request_content_type = request_headers.get(header_name)
            elif lower_header_name == b'content-length':
                request_content_length = safe_int(request_headers.get(header_name), -1)

        if b';' in request_content_type:
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
            if request_content_length == -1:
                response = b'invalid Content-Length'
                http_status = HTTP_STATUS_BAD_REQUEST
            elif request_content_length == 0:
                response = b'file is too small'
                http_status = HTTP_STATUS_LENGTH_REQUIRED
            elif request_content_length > _MAX_UPLOAD_SIZE:
                response = b'file is too big'
                http_status = HTTP_STATUS_CONTENT_TOO_LARGE
            else:
                remaining_content_length = request_content_length
                logging.info(f'upload content length {request_content_length}', 'http_server:api_upload_file_callback')
                start_boundary = http.HYPHENS + boundary
                end_boundary = start_boundary + http.HYPHENS
                search_boundary = b'\r\n' + start_boundary
                keep_len = len(search_boundary) - 1
                state = _MP_START_BOUND
                filename = None
                output_file = None
                part_filename = None
                more_bytes = True
                leftover_bytes = b''
                try:
                    while more_bytes:
                        try:
                            buffer = await asyncio.wait_for(reader.read(_BUFFER_SIZE), _REQUEST_TIMEOUT)  # reader is a LineReader
                        except TimeoutError:
                            logging.warning(f'upload timed out after {request_content_length - remaining_content_length} '
                                            f'of {request_content_length} bytes', 'http_server:api_upload_file_callback')
                            response = b'upload timed out'
                            http_status = HTTP_STATUS_BAD_REQUEST
                            more_bytes = False
                            break
                        if len(buffer) == 0:  # peer closed early; don't spin forever.
                            logging.warning(f'upload ended after {request_content_length - remaining_content_length} '
                                            f'of {request_content_length} bytes', 'http_server:api_upload_file_callback')
                            response = b'upload ended prematurely'
                            http_status = HTTP_STATUS_INTERNAL_SERVER_ERROR
                            more_bytes = False
                            break
                        remaining_content_length -= len(buffer)
                        if remaining_content_length <= 0:
                            more_bytes = False
                        if len(leftover_bytes) != 0:
                            buffer = leftover_bytes + buffer
                            leftover_bytes = b''
                        start = 0
                        while start < len(buffer):
                            if state == _MP_DATA:
                                if not output_file:
                                    output_filename = _safe_content_path(http.content_dir, 'uploaded_' + str(filename))
                                    part_filename = output_filename + '.part'  # never truncate a pre-existing file until the upload succeeds.
                                    output_file = open(part_filename, 'wb')
                                idx = buffer.find(search_boundary, start)
                                if idx != -1:
                                    output_file.write(buffer[start:idx])
                                    state = _MP_END_BOUND
                                    output_file.close()
                                    output_file = None
                                    os.rename(part_filename, output_filename)  # move the completed upload into place.
                                    response = b'Uploaded "uploaded_%s" successfully' % filename.encode()
                                    http_status = HTTP_STATUS_CREATED
                                    start = idx + 2  # Advance past \r\n so the next line parsed is the boundary itself
                                else:
                                    if more_bytes:
                                        hold_len = min(keep_len, len(buffer) - start)  # never write bytes that might be part of the boundary.
                                        leftover_bytes = buffer[-hold_len:]
                                        output_file.write(buffer[start:len(buffer) - hold_len])
                                        start = len(buffer)
                                    else:
                                        output_file.write(buffer[start:])
                                        start = len(buffer)
                            else:  # must be reading headers or boundary
                                idx = buffer.find(b'\r\n', start)
                                if idx != -1:
                                    line = buffer[start:idx]
                                    start = idx + 2
                                    if state == _MP_START_BOUND:
                                        if line == start_boundary or line == b'':
                                            if line == start_boundary:
                                                state = _MP_HEADERS
                                    elif state == _MP_HEADERS:
                                        if len(line) == 0:
                                            if filename is None:  # no filename="..." in Content-Disposition
                                                response = b'filename not specified'
                                                http_status = HTTP_STATUS_BAD_REQUEST
                                                more_bytes = False
                                                start = len(buffer)
                                            else:
                                                state = _MP_DATA
                                        elif line.startswith(b'Content-Disposition:'):
                                            pieces = line.split(b';')
                                            if len(pieces) >= 3:
                                                fn = pieces[2].strip()
                                                if fn.startswith(b'filename="'):
                                                    filename = fn[10:-1].decode()
                                                    if not valid_filename(filename):
                                                        response = b'bad filename'
                                                        http_status = HTTP_STATUS_BAD_REQUEST
                                                        more_bytes = False
                                                        start = len(buffer)
                                    elif state == _MP_END_BOUND:
                                        if line == end_boundary or line == start_boundary or line == b'--':
                                            state = _MP_START_BOUND
                                else:
                                    if more_bytes:
                                        leftover_bytes = buffer[start:]
                                        start = len(buffer)
                                    else:
                                        start = len(buffer)
                finally:
                    if output_file is not None:  # upload was interrupted mid-file.
                        output_file.close()
                        output_file = None
                        try:
                            os.remove(part_filename)  # discard the partial upload; the pre-existing file (if any) is untouched.
                        except OSError:
                            pass
        logging.info(f'upload response: {response}', 'http_server:api_upload_file_callback')
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
        delete_filename = _safe_content_path(http.content_dir, filename)
        try:
            os.remove(delete_filename)
            http_status = HTTP_STATUS_OK
            response = f'removed {filename}'
        except OSError as ose:
            http_status = HTTP_STATUS_CONFLICT
            response = str(ose)
    else:
        http_status = HTTP_STATUS_CONFLICT
        response = b'bad file name'
    bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status


# noinspection PyUnusedLocal
async def api_rename_file_callback(http, verb, args, reader, writer, request_headers=None):
    filename = args.get('filename')
    newname = args.get('newname')
    if valid_filename(filename) and valid_filename(newname):
        content_filename = _safe_content_path(http.content_dir, filename)
        content_newname = _safe_content_path(http.content_dir, newname)
        if file_size(content_newname) >= 0:
            http_status = HTTP_STATUS_CONFLICT
            response = f'new file {newname} already exists'
        else:
            try:
                os.rename(content_filename, content_newname)
                http_status = HTTP_STATUS_OK
                response = f'renamed {filename} to {newname}'
            except Exception as ose:
                http_status = HTTP_STATUS_CONFLICT
                response = str(ose)
    else:
        http_status = HTTP_STATUS_CONFLICT
        response = b'bad file name'
    bytes_sent = await http.send_simple_response(writer, http_status, http.CT_TEXT_TEXT, response)
    return bytes_sent, http_status
