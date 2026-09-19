# micropython compatible JSON serializer/deserializer.
# this encodes bytes to str at serialization time for CPython compatibility.

__author__ = 'J. B. Otterson'
__copyright__ = """
Copyright 2026 J. B. Otterson N1KDO.
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
__version__ = '0.1.0'  # 2026-09-03

import json

class _CompatibleEncoder(json.JSONEncoder):
    """Encodes bytes values to UTF-8 strings automatically during json.dumps."""
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='ignore')
        return super().default(obj)

def _convert_bytes_keys(obj):
    """Recursively ensures dictionary keys are decoded since standard json ignores default()."""
    if isinstance(obj, dict):
        return {
            (k.decode('utf-8', errors='ignore') if isinstance(k, bytes) else k): _convert_bytes_keys(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_convert_bytes_keys(i) for i in obj]
    return obj

def dumps(obj, **kwargs):
    """Serialize obj to a JSON formatted str. Handles bytes keys and values."""
    # Handle dictionary keys explicitly before encoder kicks in
    cleaned_obj = _convert_bytes_keys(obj)
    kwargs['cls'] = _CompatibleEncoder
    return json.dumps(cleaned_obj, **kwargs)

def dump(obj, fp, **kwargs):
    """Serialize obj as a JSON formatted stream to fp."""
    cleaned_obj = _convert_bytes_keys(obj)
    kwargs['cls'] = _CompatibleEncoder
    return json.dump(cleaned_obj, fp, **kwargs)

def loads(s, **kwargs):
    return json.loads(s, **kwargs)

def load(fp, **kwargs):
    return json.load(fp, **kwargs)
