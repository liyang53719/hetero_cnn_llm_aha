"""Bounded, unauthenticated traceback observations; never qualification evidence.

The caller owns the current log, verifies source bytes, and supplies their exact
absolute names and pinned relative metadata. This module performs no file reads,
imports producer code, or inspects exception objects. Printed traceback syntax
can be forged, so even an OBSERVED result never authenticates the failure cause.
"""
import json
import re

MAX_RAW_BYTES = 65536
MAX_OUTPUT_BYTES = 8192
MAX_LINES = 2048
MAX_LINE_BYTES = 4096
MAX_SOURCE_FILES = 1024
MAX_SOURCE_LINES = 1000000
MAX_FRAMES = 64
MAX_KNOWN_FRAMES = 8
HEADER = 'Traceback (most recent call last):'
_CHAINS = (
    'During handling of the above exception, another exception occurred:',
    'The above exception was the direct cause of the following exception:',
)
_EXCEPTIONS = {
    'AssertionError': 'PYTHON_ASSERTION_ERROR',
    'AttributeError': 'PYTHON_ATTRIBUTE_ERROR',
    'BrokenPipeError': 'PYTHON_BROKEN_PIPE_ERROR',
    'ConnectionError': 'PYTHON_CONNECTION_ERROR',
    'ConnectionResetError': 'PYTHON_CONNECTION_RESET_ERROR',
    'FileNotFoundError': 'PYTHON_FILE_NOT_FOUND_ERROR',
    'ImportError': 'PYTHON_IMPORT_ERROR',
    'IndexError': 'PYTHON_INDEX_ERROR',
    'InterruptedError': 'PYTHON_INTERRUPTED_ERROR',
    'KeyError': 'PYTHON_KEY_ERROR',
    'MemoryError': 'PYTHON_MEMORY_ERROR',
    'ModuleNotFoundError': 'PYTHON_MODULE_NOT_FOUND_ERROR',
    'NotImplementedError': 'PYTHON_NOT_IMPLEMENTED_ERROR',
    'OSError': 'PYTHON_OS_ERROR',
    'OverflowError': 'PYTHON_OVERFLOW_ERROR',
    'PermissionError': 'PYTHON_PERMISSION_ERROR',
    'RecursionError': 'PYTHON_RECURSION_ERROR',
    'RuntimeError': 'PYTHON_RUNTIME_ERROR',
    'TimeoutError': 'PYTHON_TIMEOUT_ERROR',
    'TypeError': 'PYTHON_TYPE_ERROR',
    'ValueError': 'PYTHON_VALUE_ERROR',
    'http.client.IncompleteRead': 'PYTHON_HTTP_INCOMPLETE_READ',
    'http.client.RemoteDisconnected': 'PYTHON_HTTP_REMOTE_DISCONNECTED',
    'ssl.SSLError': 'PYTHON_SSL_ERROR',
    'ssl.SSLCertVerificationError': 'PYTHON_SSL_CERT_VERIFICATION_ERROR',
    'urllib.error.HTTPError': 'PYTHON_URLLIB_HTTP_ERROR',
    'urllib.error.URLError': 'PYTHON_URLLIB_URL_ERROR',
}
_FRAME = re.compile(r'^  File "([^"\r\n]+)", line ([1-9][0-9]{0,6}), in ([^\r\n]+)$')
_TERMINAL = re.compile(r'^([A-Za-z_][A-Za-z0-9_.]*)(?:: [^\r\n]*)?$')
_RELATIVE = re.compile(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.py')
_SHA = re.compile(r'[0-9a-f]{64}')


def _result(status, reason, *, exception_class=None, frames=None,
            unknown_frames_omitted=0, known_frames_omitted=0):
    return dict(schema=1, status=status, reason=reason,
        error_code=_EXCEPTIONS.get(exception_class), exception_class=exception_class,
        frames=[] if frames is None else frames,
        unknown_frames_omitted=unknown_frames_omitted,
        known_frames_omitted=known_frames_omitted,
        diagnostic_only=True, origin_authenticated=False)


def _unavailable(reason):
    return _result('UNAVAILABLE', reason)


def _metadata_valid(value):
    if type(value) is not dict or not 1 <= len(value) <= MAX_SOURCE_FILES:
        return False
    relative_names = set()
    for absolute, item in value.items():
        if (type(absolute) is not str or not 1 < len(absolute) <= 4096
                or not absolute.startswith('/') or '\\' in absolute or '"' in absolute
                or any(ord(char) < 32 or ord(char) == 127 for char in absolute)
                or any(part in ('', '.', '..') for part in absolute[1:].split('/'))):
            return False
        if type(item) is not dict or set(item) != {'path', 'sha256', 'lines'}:
            return False
        name, digest, lines = item['path'], item['sha256'], item['lines']
        if (type(name) is not str or not 1 <= len(name) <= 512
                or _RELATIVE.fullmatch(name) is None
                or any(part in ('.', '..') for part in name.split('/'))
                or not absolute.endswith('/' + name) or name in relative_names
                or type(digest) is not str or _SHA.fullmatch(digest) is None
                or type(lines) is not int or not 1 <= lines <= MAX_SOURCE_LINES):
            return False
        relative_names.add(name)
    return True


def extract(raw, source_metadata):
    """Return only bounded allowlisted JSON, with an explicit unavailable reason.

Only one complete standard terminal traceback is supported. Prefix log output
is ignored, but a second or malformed traceback header, chained exceptions,
multiline exception messages, notes, groups, and abbreviated recursion fail
closed. Unknown source frames are omitted; at least one pinned frame is needed.
The last eight known frames are retained when a complete trace contains more.
"""
    if type(raw) is not bytes:
        return _unavailable('INVALID_RAW_TYPE')
    if not raw:
        return _unavailable('EMPTY_LOG')
    if len(raw) > MAX_RAW_BYTES:
        return _unavailable('LOG_TOO_LARGE')
    if not _metadata_valid(source_metadata):
        return _unavailable('INVALID_SOURCE_METADATA')
    if not raw.endswith(b'\n'):
        return _unavailable('INCOMPLETE_LOG')
    try:
        text = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        return _unavailable('INVALID_ENCODING')
    if any(ord(char) < 32 and char not in '\n\t' or ord(char) == 127 for char in text):
        return _unavailable('UNSUPPORTED_CONTROL_CHARACTER')
    lines = text.split('\n')[:-1]
    if len(lines) > MAX_LINES:
        return _unavailable('TOO_MANY_LINES')
    if any(len(line.encode('utf-8')) > MAX_LINE_BYTES for line in lines):
        return _unavailable('LINE_TOO_LONG')
    if any(line in _CHAINS for line in lines):
        return _unavailable('CHAINED_TRACEBACK')
    headers = [index for index, line in enumerate(lines) if HEADER in line]
    if not headers:
        return _unavailable('NO_TRACEBACK')
    if len(headers) != 1 or lines[headers[0]] != HEADER:
        return _unavailable('AMBIGUOUS_TRACEBACK')
    start = headers[0] + 1
    if start >= len(lines) - 1:
        return _unavailable('INCOMPLETE_TRACEBACK')
    terminal = _TERMINAL.fullmatch(lines[-1])
    if terminal is None:
        return _unavailable('UNSUPPORTED_TERMINAL')
    exception_class = terminal.group(1)
    if exception_class not in _EXCEPTIONS:
        return _unavailable('UNSUPPORTED_EXCEPTION_CLASS')
    known, unknown, count, details = [], 0, 0, 0
    for line in lines[start:-1]:
        frame = _FRAME.fullmatch(line)
        if frame is not None:
            count += 1
            details = 0
            if count > MAX_FRAMES:
                return _unavailable('TOO_MANY_FRAMES')
            number = int(frame.group(2))
            if number > MAX_SOURCE_LINES:
                return _unavailable('INVALID_FRAME_LINE')
            item = source_metadata.get(frame.group(1))
            if item is None:
                unknown += 1
            else:
                if number > item['lines']:
                    return _unavailable('SOURCE_LINE_OUT_OF_RANGE')
                known.append(dict(path=item['path'], sha256=item['sha256'], line=number))
        elif count and line.startswith('    ') and details < 2:
            # Source and optional position markers are consumed but never kept.
            details += 1
        else:
            return _unavailable('MALFORMED_TRACEBACK')
    if not count:
        return _unavailable('INCOMPLETE_TRACEBACK')
    if not known:
        return _unavailable('NO_PINNED_FRAME')
    result = _result('OBSERVED', 'COMPLETE_SINGLE_TRACEBACK',
        exception_class=exception_class, frames=known[-MAX_KNOWN_FRAMES:],
        unknown_frames_omitted=unknown, known_frames_omitted=max(0, len(known)-MAX_KNOWN_FRAMES))
    if len(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()) > MAX_OUTPUT_BYTES:
        return _unavailable('OUTPUT_TOO_LARGE')
    return result
