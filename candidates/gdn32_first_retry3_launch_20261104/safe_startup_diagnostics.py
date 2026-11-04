"""Read one fixed completed startup capture; emit typed observations, not acceptance."""
import hashlib
import json
import os
import pathlib
import re
import stat
import zlib

SCHEMA_SHA256 = '58e70615311343c4fdf0b830d43775b241dc062d7691404cf85efdc15819d56d'
EMITTER_SOURCE_PINS = {'locked_phase.py': '34864b03fe92162ec57ca2f1356b319ad5422e579346bd4b6541ee0729669d4a', 'runtime_abi_owned.py': '11dae378bdf32feb82153cd1ae48aa166a65c7e959d6cecbed42b9ab0a85d3f6'}
SCHEMA = 'GDN32_STARTUP_DIAGNOSTIC_V1'
PHASES = {
    'LOCKED_PHASE': ('CLI', 'PHASE_PIN', 'PHASE_JSON', 'SESSION', 'SOURCE_PINS', 'ENVIRONMENT', 'CENSUS', 'LIVE_ADMISSION', 'ADMISSION_RECEIPT', 'FILE_LIMIT', 'ARGV', 'EXECVE'),
    'STARTUP_ABI': ('CLI', 'CONFIGURATION', 'INPUTS', 'ELF', 'LOADER_IDENTITY', 'LOADER_CONFIG', 'LOADER_LIST', 'LOADER_PARSE', 'LIBRARY_PINS', 'POSTCHECK', 'RECEIPT', 'WORKSPACE'),
}
CLASSES = ('ValueError', 'TypeError', 'KeyError', 'IndexError', 'OSError', 'FileNotFoundError', 'PermissionError', 'JSONDecodeError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'TimeoutExpired', 'SystemExit', 'OverflowError', 'MemoryError', 'RuntimeError', 'IsADirectoryError', 'NotADirectoryError', 'FileExistsError', 'error', 'OTHER')
FIELDS = {'schema', 'component', 'stage', 'phase', 'status', 'code', 'exception_class', 'native_started', 'dut_started', 'numerical_pass'}
RECEIPT_LIMIT = 1 << 20
COMPRESSED_LIMIT = 256 << 10
RAW_LIMIT = 256 << 10
RECORD_LIMIT = 4096
OUTPUT_LIMIT = 8192
REASONS = frozenset({'RECEIPT_MISSING', 'RECEIPT_INVALID', 'CAPTURE_UNPROVEN', 'LOG_UNAVAILABLE', 'LOG_LIMIT', 'LOG_DIGEST', 'GZIP_INVALID', 'RAW_DIGEST', 'DIAGNOSTIC_INVALID', 'DIAGNOSTIC_COUNT', 'NO_FIXED_EVENT_OBSERVED', 'FIXED_DIAGNOSTIC_OBSERVED', 'READ_UNAVAILABLE'})


class Refusal(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in REASONS else 'READ_UNAVAILABLE'
        super().__init__(self.reason)


def need(value, reason):
    if not value:
        raise Refusal(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hex64(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('DUPLICATE_KEY')
        result[key] = value
    return result


def nonfinite(_):
    raise ValueError('NONFINITE')


def decode(raw):
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def project_event(value):
    need(type(value) is dict and set(value) == FIELDS, 'DIAGNOSTIC_INVALID')
    need(value['schema'] == SCHEMA and value['status'] == 'FAILED', 'DIAGNOSTIC_INVALID')
    component = value['component']; phase = value['phase']
    need(type(component) is str and component in PHASES and type(phase) is str and phase in PHASES[component], 'DIAGNOSTIC_INVALID')
    need(value['code'] == phase + '_REJECTED' and type(value['exception_class']) is str and value['exception_class'] in CLASSES, 'DIAGNOSTIC_INVALID')
    locked = component == 'LOCKED_PHASE'
    need(value['stage'] == ('UNVERIFIED' if locked else 'startup_abi'), 'DIAGNOSTIC_INVALID')
    need(value['native_started'] is None and value['dut_started'] is (None if locked else False) and value['numerical_pass'] is False, 'DIAGNOSTIC_INVALID')
    # Reconstruct the exact fields; unknown strings/objects are never returned.
    return {key: value[key] for key in sorted(FIELDS)}


def project_line(raw):
    """An individual bare JSON event only; never parse traceback prose."""
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= RECORD_LIMIT or b'\n' in raw or b'\r' in raw:
            return None
        value = decode(raw)
        if type(value) is not dict or value.get('schema') != SCHEMA:
            return None
        return project_event(value)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return None


def read_regular(path, limit):
    """Walk fixed absolute components using no-follow directory descriptors."""
    path = pathlib.Path(path)
    need(path.is_absolute() and '..' not in path.parts and 1 < len(path.parts) <= 64, 'READ_UNAVAILABLE')
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    directory = os.open('/', flags | os.O_DIRECTORY)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory); directory = child
        fd = os.open(path.name, flags | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'LOG_LIMIT')
        result = bytearray()
        while len(result) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(result)))
            if not block:
                break
            result.extend(block)
        after = os.fstat(fd)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(all(getattr(before, key) == getattr(after, key) for key in keys) and len(result) == before.st_size and len(result) <= limit, 'READ_UNAVAILABLE')
        return bytes(result)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def inflate(compressed, expected_size):
    need(integer(expected_size, 0, RAW_LIMIT), 'LOG_LIMIT')
    try:
        decoder = zlib.decompressobj(31)
        raw = decoder.decompress(compressed, RAW_LIMIT + 1)
        need(len(raw) <= RAW_LIMIT and not decoder.unconsumed_tail, 'LOG_LIMIT')
        need(decoder.eof and not decoder.unused_data, 'GZIP_INVALID')
        need(len(raw) == expected_size, 'RAW_DIGEST')
        return raw
    except zlib.error:
        raise Refusal('GZIP_INVALID') from None


def capture(work):
    """Only work/materials/numeric/runs/startup_abi/{RESULT.json,frontend.log.gz}."""
    row = dict(schema='GDN32_STARTUP_CAPTURE_SUMMARY_V1', stage='startup_abi',
               context_source='FIXED_STARTUP_SUPERVISOR_CAPTURE',
               status='UNOBSERVED', reason='RECEIPT_MISSING', native_exit=None,
               receipt_sha256=None, compressed_bytes=None, compressed_sha256=None,
               raw_bytes=None, raw_sha256=None, diagnostics=[], numerical_pass=False)
    stage = pathlib.Path(work) / 'materials/numeric/runs/startup_abi'
    try:
        try:
            receipt_raw = read_regular(stage / 'RESULT.json', RECEIPT_LIMIT)
        except FileNotFoundError:
            return row
        except (OSError, Refusal):
            raise Refusal('RECEIPT_INVALID') from None
        row['status'] = 'REFUSED'; row['receipt_sha256'] = digest(receipt_raw)
        try:
            receipt = decode(receipt_raw)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise Refusal('RECEIPT_INVALID') from None
        need(type(receipt) is dict, 'RECEIPT_INVALID')
        native = receipt.get('native_exit')
        need(integer(native, -255, 255), 'RECEIPT_INVALID')
        row['native_exit'] = native
        cleanup = receipt.get('cleanup_proof'); log = receipt.get('log_capture')
        need(receipt.get('worker_started') is True and type(cleanup) is dict and cleanup.get('status') == 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP', 'CAPTURE_UNPROVEN')
        need(type(log) is dict and log.get('format') == 'gzip-lossless' and log.get('pipe_eof_observed') is True and log.get('gzip_finalized') is True and log.get('capture_cap_hit') is False, 'CAPTURE_UNPROVEN')
        need(integer(log.get('compressed_bytes'), 1, COMPRESSED_LIMIT) and integer(log.get('raw_bytes'), 0, RAW_LIMIT), 'LOG_LIMIT')
        need(hex64(log.get('compressed_sha256')) and hex64(log.get('raw_sha256')), 'RECEIPT_INVALID')
        try:
            compressed = read_regular(stage / 'frontend.log.gz', COMPRESSED_LIMIT)
        except Refusal:
            raise
        except OSError:
            raise Refusal('LOG_UNAVAILABLE') from None
        need(len(compressed) == log['compressed_bytes'] and digest(compressed) == log['compressed_sha256'], 'LOG_DIGEST')
        raw = inflate(compressed, log['raw_bytes'])
        need(digest(raw) == log['raw_sha256'], 'RAW_DIGEST')
        # Source evidence is disclosed only after the complete bounded capture verifies.
        for key in ('compressed_bytes', 'compressed_sha256', 'raw_bytes', 'raw_sha256'):
            row[key] = log[key]
        events = []
        for line in raw.split(b'\n')[:-1]:
            if not 0 < len(line) <= RECORD_LIMIT or b'\r' in line:
                continue
            try:
                value = decode(line)
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                continue
            if type(value) is dict and value.get('schema') == SCHEMA:
                events.append(project_event(value))
                need(len(events) <= 1, 'DIAGNOSTIC_COUNT')
        need(not events or native != 0, 'DIAGNOSTIC_INVALID')
        row['diagnostics'] = events
        row['status'] = 'OBSERVED' if events else 'NO_DIAGNOSTIC'
        row['reason'] = 'FIXED_DIAGNOSTIC_OBSERVED' if events else 'NO_FIXED_EVENT_OBSERVED'
        need(len(json.dumps(row, sort_keys=True, allow_nan=False).encode()) <= OUTPUT_LIMIT, 'DIAGNOSTIC_INVALID')
    except Refusal as exc:
        row['status'] = 'REFUSED'; row['reason'] = exc.reason; row['diagnostics'] = []
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        row['status'] = 'REFUSED'; row['reason'] = 'READ_UNAVAILABLE'; row['diagnostics'] = []
    return row
