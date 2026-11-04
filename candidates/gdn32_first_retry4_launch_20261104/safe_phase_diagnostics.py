"""Project source-bound identity and fixed selected-phase captures, never acceptance."""
import hashlib
import json
import os
import pathlib
import re
import stat
import zlib

SCHEMA_SHA256 = '58e70615311343c4fdf0b830d43775b241dc062d7691404cf85efdc15819d56d'
EMITTER_SOURCE_PINS = {'locked_phase.py': '34864b03fe92162ec57ca2f1356b319ad5422e579346bd4b6541ee0729669d4a', 'runtime_abi_owned.py': '11dae378bdf32feb82153cd1ae48aa166a65c7e959d6cecbed42b9ab0a85d3f6'}
EXECUTION_SCHEMA_SHA256 = '6d01b53b81516814ca586e38184b97b6329bd575289492047a12463129b2e986'
EXECUTION_EMITTER_SOURCE_PINS = {'connect_owned.py': 'a7fe8ba93c04afdf2b548d0a92e1cb6e6f06fb5c19e349d4b855ce20ff92f0ac', 'consumer_owned.py': '3498a9d7dd40ba1dd834148e17ab58cf8a527b953af907999eaed37b3ec0caa5'}
EXECUTION_SCHEMA = 'GDN32_EXECUTION_DIAGNOSTIC_V1'
EXECUTION_PHASES = {'CONNECT_OWNED': ('CLI', 'OWNED_ENVIRONMENT', 'SOURCE_GUARD', 'ARTIFACT', 'CONTEXT', 'BUILD', 'ABI', 'BUNDLE_INPUT', 'P0_HYDRATION', 'P0_POLICY', 'BUNDLE_OUTPUT', 'BINDING', 'ARGUMENT_RECEIPT'), 'CONSUMER_OWNED': ('CLI', 'OWNED_ENVIRONMENT', 'ADMISSION', 'ARTIFACT', 'CONTEXT', 'BINDING', 'BUILD', 'ABI', 'RUNTIME_INPUTS', 'REFERENCE', 'OUTPUT', 'PRE_EXECUTION', 'DUT_POPEN', 'OUT_OF_SCOPE', 'FINISH')}
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
SELECTED_PHASES = {1: ('startup_abi', 'p1_p12_provider', 'p1_initialize', 'p1_connect', 'p1_dut')}
CONTEXT_COMPONENTS = {'startup_abi': ('LOCKED_PHASE', 'STARTUP_ABI'), 'p1_p12_provider': ('LOCKED_PHASE',), 'p1_initialize': ('LOCKED_PHASE',), 'p1_connect': ('LOCKED_PHASE', 'CONNECT_OWNED'), 'p1_dut': ('LOCKED_PHASE', 'CONSUMER_OWNED')}
REASONS = frozenset({'PHASE_NOT_ALLOWED', 'PROFILE_NOT_ALLOWED', 'RECEIPT_MISSING', 'RECEIPT_INVALID', 'CAPTURE_UNPROVEN', 'LOG_UNAVAILABLE', 'LOG_LIMIT', 'LOG_DIGEST', 'GZIP_INVALID', 'RAW_DIGEST', 'DIAGNOSTIC_INVALID', 'DIAGNOSTIC_COUNT', 'NO_FIXED_EVENT_OBSERVED', 'FIXED_DIAGNOSTIC_OBSERVED', 'READ_UNAVAILABLE'})


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
    need(type(value['schema']) is str and value['schema'] in (SCHEMA, EXECUTION_SCHEMA) and value['status'] == 'FAILED', 'DIAGNOSTIC_INVALID')
    domain = PHASES if value['schema'] == SCHEMA else EXECUTION_PHASES
    component = value['component']; phase = value['phase']
    need(type(component) is str and component in domain and type(phase) is str and phase in domain[component], 'DIAGNOSTIC_INVALID')
    need(value['code'] == phase + '_REJECTED' and type(value['exception_class']) is str and value['exception_class'] in CLASSES, 'DIAGNOSTIC_INVALID')
    unverified = component != 'STARTUP_ABI'
    need(value['stage'] == ('UNVERIFIED' if unverified else 'startup_abi'), 'DIAGNOSTIC_INVALID')
    need(value['native_started'] is None and value['dut_started'] is (None if unverified else False) and value['numerical_pass'] is False, 'DIAGNOSTIC_INVALID')
    # Reconstruct the exact fields; unknown strings/objects are never returned.
    return {key: value[key] for key in sorted(FIELDS)}


def project_line(raw):
    """An individual bare JSON event only; never parse traceback prose."""
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= RECORD_LIMIT or b'\n' in raw or b'\r' in raw:
            return None
        value = decode(raw)
        if type(value) is not dict or value.get('schema') not in (SCHEMA, EXECUTION_SCHEMA):
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


def capture(work, phase='startup_abi', selected_profile=1):
    """Only a literal selected-profile stage name selects either fixed file."""
    need(type(selected_profile) is int and selected_profile in SELECTED_PHASES, 'PROFILE_NOT_ALLOWED')
    need(type(phase) is str and phase in SELECTED_PHASES[selected_profile], 'PHASE_NOT_ALLOWED')
    row = dict(schema='GDN32_SELECTED_PHASE_CAPTURE_SUMMARY_V1', stage=phase, selected_profile=selected_profile,
               context_source='FIXED_SELECTED_PHASE_SUPERVISOR_CAPTURE',
               status='UNOBSERVED', reason='RECEIPT_MISSING', native_exit=None,
               receipt_sha256=None, compressed_bytes=None, compressed_sha256=None,
               raw_bytes=None, raw_sha256=None, diagnostics=[], numerical_pass=False)
    stage = pathlib.Path(work) / 'materials/numeric/runs' / phase
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
            if type(value) is dict and value.get('schema') in (SCHEMA, EXECUTION_SCHEMA):
                event = project_event(value)
                need(event['component'] in CONTEXT_COMPONENTS[phase], 'DIAGNOSTIC_INVALID')
                events.append(event)
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


def capture_selected(work, selected_profile):
    need(type(selected_profile) is int and selected_profile in SELECTED_PHASES, 'PROFILE_NOT_ALLOWED')
    return [capture(work, phase, selected_profile) for phase in SELECTED_PHASES[selected_profile]]


CHECKPOINT_FIELDS = {'schema', 'status', 'scope', 'source_commit', 'hardware_generation_sha256',
                     'model_generation_sha256', 'source_catalog_sha256', 'artifact_manifest_sha256',
                     'verified_files', 'source_manifest', 'sv', 'binary', 'structural_acceptance',
                     'numerical_pass', 'final_rtl_acceptance'}


def project_checkpoint_line(line, identity, hardware, generation, catalog):
    try:
        if type(line) is not str or '\n' in line or '\r' in line or not 0 < len(line.encode()) <= RECORD_LIMIT:
            return None
        row = decode(line)
        need(type(row) is dict and set(row) == CHECKPOINT_FIELDS, 'DIAGNOSTIC_INVALID')
        need(row['schema'] == 'GDN32_VERIFIED_ARTIFACT_IDENTITY_V1' and row['status'] == 'VERIFIED_IDENTITY_ONLY' and row['scope'] == 'READ_ONLY_SOURCE_BUILD_IDENTITY_NOT_DUT_EXECUTION', 'DIAGNOSTIC_INVALID')
        need(type(identity) is dict and type(row['source_commit']) is str and re.fullmatch('[0-9a-f]{40}', row['source_commit']) is not None and row['source_commit'] == identity['source_commit'], 'DIAGNOSTIC_INVALID')
        for key, expected in (('hardware_generation_sha256', hardware), ('model_generation_sha256', generation), ('source_catalog_sha256', catalog)):
            need(hex64(row[key]) and hex64(expected) and row[key] == expected, 'DIAGNOSTIC_INVALID')
        need(hex64(row['artifact_manifest_sha256']) and type(row['verified_files']) is int and row['verified_files'] == 7, 'DIAGNOSTIC_INVALID')
        for key, cap in (('source_manifest', 16 << 20), ('sv', 4 << 30), ('binary', 4 << 30)):
            pin = row[key]
            need(type(pin) is dict and set(pin) == {'bytes', 'sha256'} and integer(pin['bytes'], 1, cap) and hex64(pin['sha256']), 'DIAGNOSTIC_INVALID')
        need(row['structural_acceptance'] is False and row['numerical_pass'] is False and row['final_rtl_acceptance'] is False, 'DIAGNOSTIC_INVALID')
        return json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return None
