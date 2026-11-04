"""Strict bounded diagnostic projection only; no acceptance or execution authority."""
import json
import math
import re

PRODUCER_SOURCE_PINS = {'one_job_model_candidate.py': 'cbf9bc665bcc247c3f51125683ee56b2c52003babd54ecbb30b812ea3d1e54e4', 'bootstrap_model_candidate.py': '45a362c04532e39f5d198748817ac1721ecf4dd95b007e35d26902bcfb3e8930', 'candidate_diagnostic.py': 'bf91ce15f2adc4ff407e1393f8e18d3c1a28146000d2775a199371b96746be58', 'original_ir_diagnostic.py': '2665c932f197573e72ca6915f285ca14fce9cf1a226dcb7be58464f63599e7bf'}
BUILD_STAGES = ('compile_model_sources', 'helper_compile', 'original_high', 'canonical_micro', 'canonical_full', 'transform_new_toolchain', 'emit_host', 'sv_identity', 'emit_fma', 'subset', 'frontend', 'frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d', 'frontend_native_Vqwen2_matrix_command_endpoint_0', 'frontend_native_VTransposedDenseDownOwner', 'frontend_native_VHostBlockTopV4', 'archive_bf16_context_lane_cluster16_rev8b_b_candidate_d', 'archive_qwen2_matrix_command_endpoint_0', 'archive_TransposedDenseDownOwner', 'host_archive', 'host_link', 'UNKNOWN_STAGE')
BUILD_ERROR_CATEGORIES = ('AGGREGATE_TREE_CAP', 'DISK_RESERVE', 'ENTRY_CAP', 'FILE_CAP', 'LOG_CAP', 'LOG_EOF_MISSING', 'LOG_READER_FAILURE', 'MONITOR_SIGALRM', 'MONITOR_SIGINT', 'MONITOR_SIGTERM', 'NONREGULAR_OUTPUT', 'OBSERVED_IDENTITIES_REMAIN', 'OBSERVED_PROCESS_CAP', 'OUTPUT_LINK_FORBIDDEN', 'POST_CLEANUP_DEADLINE', 'PRELAUNCH_DEADLINE', 'PRELAUNCH_DISK_GATE', 'PRELAUNCH_MEMORY_GATE', 'PROC_ENUMERATION_CAP', 'READER_DEADLINE', 'RSS_TELEMETRY_CAP', 'SAMPLED_CPU_CAP', 'SAMPLED_RSS_CAP', 'STAGE_TREE_CAP', 'TRACKED_PID_REUSED', 'WALL_CAP')
BOOTSTRAP_STAGES = ('jdk', 'compile_tools', 'jars', 'verilator', 'idma', 'matrix', 'fresh_host', 'binding', 'UNKNOWN_STAGE')
BOOTSTRAP_ERROR_CATEGORIES = ('AGGREGATE_TREE_CAP', 'DISK_RESERVE', 'ENTRY_CAP', 'FILE_CAP', 'LOG_CAP', 'LOG_EOF_MISSING', 'LOG_READER_FAILURE', 'MONITOR_SIGALRM', 'POST_CLEANUP_DEADLINE', 'PRELAUNCH_DEADLINE', 'PRELAUNCH_DISK_GATE', 'PRELAUNCH_MEMORY_GATE', 'READER_DEADLINE', 'SAMPLED_CPU_CAP', 'SAMPLED_RSS_CAP', 'STAGE_TREE_CAP', 'WALL_CAP')
EXCEPTION_CLASSES = ('BlockingIOError', 'BrokenPipeError', 'ChildProcessError', 'CleanupFailure', 'ConnectionError', 'FileExistsError', 'FileNotFoundError', 'IndexError', 'InterruptedError', 'IsADirectoryError', 'KeyError', 'KeyboardInterrupt', 'MemoryError', 'NotADirectoryError', 'OSError', 'OverflowError', 'PermissionError', 'ProcessLookupError', 'RuntimeError', 'StopIteration', 'SystemExit', 'TimeoutError', 'TypeError', 'UnicodeDecodeError', 'ValueError', '_Deadline', '_Invalid', 'UNKNOWN')
OS_EXCEPTION_CLASSES = ('BlockingIOError', 'BrokenPipeError', 'ChildProcessError', 'ConnectionError', 'FileExistsError', 'FileNotFoundError', 'InterruptedError', 'IsADirectoryError', 'NotADirectoryError', 'OSError', 'PermissionError', 'ProcessLookupError', 'TimeoutError')
POST_BUILD_PHASES = ('COMPILE_OUTPUTS', 'COPY', 'ENRICH', 'FINAL', 'IDENTITY', 'OBSERVATION', 'SOURCE_PINS', 'STAGE_RECEIPTS', 'UNKNOWN')
POST_BUILD_REASONS = ('SOURCE_PIN_HASH_FORMAT', 'SOURCE_PIN_HASH_MISMATCH', 'SOURCE_PIN_PATH', 'SOURCE_PIN_SET', 'SOURCE_PIN_SIZE', 'STAGE_VALIDATION_FAILED', 'UNCLASSIFIED')
POST_BUILD_CLASSES = ('FileNotFoundError', 'JSONDecodeError', 'OSError', 'OTHER', 'PermissionError', 'TypeError', 'UnicodeDecodeError', 'ValueError')
CANDIDATE_STAGES = ('canonical_full', 'emit_host', 'transform_new_toolchain')
CANDIDATE_REASONS = ('ANNOTATION_CLASS_TARGET', 'ANNOTATION_ROUNDTRIP', 'BANK_SUBTREE_HASH', 'CANONICAL_IDENTITY', 'DENSE_ACC_LOCAL_SHAPE', 'FIFO_LOCAL_SHAPE', 'FINAL_CONNECTORS', 'FIXED_MODULE_HASH', 'FIXED_PROVIDER_BINDINGS', 'HIGH_ROUNDTRIP', 'INPUT_BOUNDS_OR_PIN', 'INTERNAL_UNCLASSIFIED', 'LOW_LOWERING', 'LOW_SERIALIZATION', 'METADATA_BOUNDS', 'NONE', 'SV_EMISSION', 'TOP_PORT_ABI')
CANDIDATE_NUMBERS = ('annotation_bytes', 'annotation_count', 'bank_subtree_module_index', 'dense_bulk_writes', 'dense_zero_elements', 'dense_zero_rows', 'dense_zero_tiles', 'fixed_module_index', 'high_bytes', 'low_port_count', 'module_count', 'reachable_instance_count', 'target_dir_count')
CANDIDATE_DENSE_PREDICATES = ('BULK_SOURCES', 'CANONICAL_FORMAT', 'CAT_NONEMPTY', 'CONDITIONAL_STRUCTURE', 'CORE_INFO', 'CORE_INTEGRITY', 'CORE_PORTS', 'DENSE_REFERENCE_COUNT', 'DENSE_REGISTER', 'FRESH_NAMES', 'GATE_INFO', 'GATE_MODULE_COUNT', 'GATE_PORTS', 'INDEX_REGISTERS', 'INTERNAL_UNCLASSIFIED', 'NONREPLACED_STRUCTURE', 'NO_OLD_STORAGE_PORTS', 'ONE_CORE', 'OTHER_MODULE_IDENTITY', 'POST_MEMORY_SHAPE', 'POST_NO_REGISTERS', 'POST_ONE_CORE', 'POST_ONE_MEMORY', 'READ_CONSUMER', 'READ_EXACT', 'READ_INDEX_NODES', 'REWRITE_COUNTS', 'UNIQUE_NODES', 'ZERO_CLOSURE_COUNTS', 'ZERO_DECLARATIONS', 'ZERO_EXACT_LITERAL', 'ZERO_ORDER', 'ZERO_REFERENCE_CLOSURE', 'ZERO_ROW_DRIVERS', 'ZERO_SAME_BLOCK', 'ZERO_TILE_DRIVERS', 'ZERO_TILE_NAMES')
CANDIDATE_HASHES = ('annotations_sha256', 'canonical_sha256', 'failing_module_sha256', 'high_sha256')

RESOURCE_DIAGNOSTIC_SOURCE_SHA256 = '97454e9a114370d0f6282ad5da693b9b3386003f3d5180f60798a9c9a3c25865'
EXECUTION_STAGES = ('jdk', 'compile_tools', 'jars', 'verilator', 'idma', 'matrix', 'fresh_host', 'binding', 'compile_model_sources', 'helper_compile', 'original_high', 'canonical_micro', 'canonical_full', 'transform_new_toolchain', 'emit_host', 'sv_identity', 'emit_fma', 'subset', 'frontend', 'frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d', 'frontend_native_Vqwen2_matrix_command_endpoint_0', 'frontend_native_VTransposedDenseDownOwner', 'frontend_native_VHostBlockTopV4', 'archive_bf16_context_lane_cluster16_rev8b_b_candidate_d', 'archive_qwen2_matrix_command_endpoint_0', 'archive_TransposedDenseDownOwner', 'host_archive', 'host_link', 'UNKNOWN_STAGE')
EXECUTION_PRE_CODES = {'RESOURCE_REQUEST': 'INVALID_STAGE_RESOURCE_REQUEST', 'CONTROLLER_BINDING': 'CONTROLLER_BINDING_REJECTED', 'RESOURCE_GATE': 'RESOURCE_GATE_REJECTED', 'RUNTIME_ALIAS': 'RUNTIME_ALIAS_REJECTED', 'DISK': 'DISK_GATE_REJECTED', 'DEADLINE': 'DEADLINE_REJECTED', 'NATIVE_ENVIRONMENT': 'NATIVE_ENVIRONMENT_REJECTED'}
EXECUTION_SERIAL_CODES = ('ARGFILE_SYMLINK', 'ARGUMENT_CARDINALITY', 'CHILD_WRAPPER_CARDINALITY', 'FRONTEND_ONLY_REQUIRED', 'HIERARCHICAL_CHILD_REQUIRED', 'HOST_CPP_MISSING', 'HOST_HEADER_MISSING', 'HOST_RECURSIVE_SCAN', 'INITIAL_HIERARCHICAL_ARGV', 'INPUT_SYMLINK', 'MDIR_MISMATCH', 'NATIVE_STAGE_INCOMPLETE', 'OWNED_OBJ_MISMATCH', 'PLAN_DRIFT', 'PLAN_ONLY_OUTPUT', 'PLAN_PREFIX_SET', 'PREFIX_MISMATCH', 'SERIAL_OPTIONS', 'SERIAL_FRONTEND_UNCLASSIFIED')
EXECUTION_EXCEPTION_CLASSES = ('BlockingIOError', 'BrokenPipeError', 'ChildProcessError', 'CleanupFailure', 'ConnectionError', 'FileExistsError', 'FileNotFoundError', 'IndexError', 'InterruptedError', 'IsADirectoryError', 'KeyError', 'KeyboardInterrupt', 'MemoryError', 'NotADirectoryError', 'OSError', 'OverflowError', 'PermissionError', 'ProcessLookupError', 'RuntimeError', 'StopIteration', 'SystemExit', 'TimeoutError', 'TypeError', 'UnicodeDecodeError', 'ValueError', '_Deadline', '_Invalid', 'OTHER')
EXECUTION_SCHEMAS = ("GDN32_MODEL_PRE_SUPERVISOR_DIAGNOSTIC_V1", "GDN32_MODEL_SUPERVISOR_EXCEPTION_V1", "GDN32_MODEL_SERIAL_PLAN_DIAGNOSTIC_V1")

MAX_RECORD_BYTES = 8192
MAX_LINE_BYTES = MAX_RECORD_BYTES + 64
MAX_INPUT_BYTES = 8 << 20
MAX_WRITE_BYTES = 1 << 20
MAX_OUTPUT_BYTES = 1 << 20
MAX_OUTPUT_RECORDS = 128
PREFIX_SCHEMAS = {
    'BUILD_STAGE_DIAGNOSTIC ': 'BOUNDED_BUILD_STAGE_DIAGNOSTIC_V1',
    'BOOTSTRAP_STAGE_DIAGNOSTIC ': 'BOUNDED_BOOTSTRAP_STAGE_DIAGNOSTIC_V1',
    'MODEL_POST_BUILD_DIAGNOSTIC ': 'MODEL_POST_BUILD_FAILURE_DIAGNOSTIC_V1',
    'MODEL_CANDIDATE_DIAGNOSTIC ': ('MODEL_CANDIDATE_DIAGNOSTIC_V1', 'MODEL_CANDIDATE_DIAGNOSTIC_UNAVAILABLE_V1'),
}
DEFERRED_PREFIXES = ('MODEL_ORIGINAL_IR_DIAGNOSTIC ', 'MODEL_JAR_STATUS ')
CAP_FIELDS = ('wall_seconds', 'cleanup_seconds', 'rss_bytes', 'cpu_seconds',
              'per_process_as_bytes', 'per_process_cpu_seconds', 'file_bytes',
              'tree_bytes', 'watch_tree_bytes', 'max_entries')
NUMBER_FIELDS = ('elapsed_seconds', 'observed_cpu_seconds', 'observed_peak_rss',
                 'peak_tree_bytes', 'peak_file_bytes')
STAGE_FIELDS = {'schema', 'stage', 'receipt_sha256', 'worker_started', 'native_exit',
                'error_count', 'error_categories', *NUMBER_FIELDS, 'caps',
                'cleanup_complete', 'pipe_eof_observed', 'gzip_finalized',
                'numerical_pass', 'final_rtl_replay'}
ERROR_EXTRA = ('UNCLASSIFIED_SUPERVISOR_ERROR', 'MALFORMED_ERROR',
               'MALFORMED_ERROR_LIST', 'ERROR_LIST_TRUNCATED')


def require(value):
    if not value:
        raise ValueError('INVALID_DIAGNOSTIC')


def enum(value, choices):
    return type(value) is str and value in choices


def number(value):
    return value is None or (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 2**53)


def integer(value, low, high, nullable=False):
    return (nullable and value is None) or (type(value) is int and low <= value <= high)


def digest(value):
    return value is None or (type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None)


def boolean(value, nullable=False):
    return type(value) is bool or (nullable and value is None)


def unique(rows):
    result = {}
    for key, value in rows:
        require(key not in result)
        result[key] = value
    return result


def invalid_constant(_):
    raise ValueError('NONFINITE_DIAGNOSTIC')


def project_stage(d, bootstrap=False):
    detail_fields = set() if bootstrap else {'error_details', 'error_details_truncated'}
    require(type(d) is dict and set(d) == STAGE_FIELDS | detail_fields)
    require(d['schema'] == ('BOUNDED_BOOTSTRAP_STAGE_DIAGNOSTIC_V1' if bootstrap else 'BOUNDED_BUILD_STAGE_DIAGNOSTIC_V1'))
    require(enum(d['stage'], BOOTSTRAP_STAGES if bootstrap else BUILD_STAGES))
    require(digest(d['receipt_sha256']))
    require(boolean(d['worker_started'], True) and integer(d['native_exit'], -128, 255, True))
    require(integer(d['error_count'], 0, 2**31-1, True))
    require(all(number(d[k]) for k in NUMBER_FIELDS))
    require(type(d['caps']) is dict and set(d['caps']) == set(CAP_FIELDS))
    require(all(number(d['caps'][k]) for k in CAP_FIELDS))
    require(boolean(d['cleanup_complete']) and boolean(d['pipe_eof_observed'], True) and boolean(d['gzip_finalized'], True))
    require(d['numerical_pass'] is False and d['final_rtl_replay'] is False)
    allowed = (BOOTSTRAP_ERROR_CATEGORIES if bootstrap else BUILD_ERROR_CATEGORIES) + ERROR_EXTRA
    categories = d['error_categories']
    require(type(categories) is list and len(categories) <= len(allowed) and all(enum(v, allowed) for v in categories))
    require(len(categories) == len(set(categories)))
    count = d['error_count']
    if count is None:
        require(categories == ['MALFORMED_ERROR_LIST'])
    else:
        require('MALFORMED_ERROR_LIST' not in categories)
        require((count > 256) == ('ERROR_LIST_TRUNCATED' in categories))
        base = categories[:-1] if count > 256 else categories
        require((count <= 256 or categories[-1] == 'ERROR_LIST_TRUNCATED') and base == sorted(base))
        require((count == 0) == (len(categories) == 0))
    if not bootstrap:
        rows = d['error_details']
        require(type(rows) is list and len(rows) == (min(count, 16) if count is not None else 0))
        require(d['error_details_truncated'] is (count is not None and count > 16))
        for row in rows:
            require(type(row) is dict and set(row) == {'origin', 'exception_class', 'errno', 'reason_code'})
            require(enum(row['origin'], ('UNKNOWN', 'LOG_READER', 'SUPERVISOR')))
            require(enum(row['exception_class'], EXCEPTION_CLASSES))
            require(enum(row['reason_code'], BUILD_ERROR_CATEGORIES + ('UNCLASSIFIED_SUPERVISOR_ERROR', 'MALFORMED_ERROR')))
            require(integer(row['errno'], 1, 4095, True))
            require(row['errno'] is None or row['exception_class'] in OS_EXCEPTION_CLASSES)
            if row['origin'] == 'UNKNOWN':
                require(row == dict(origin='UNKNOWN', exception_class='UNKNOWN', errno=None, reason_code='MALFORMED_ERROR'))
    return d


def project_post_build(d):
    require(type(d) is dict and set(d) == {'schema', 'phase', 'pack_phase', 'reason', 'exception_class',
                                         'index', 'bytes', 'expected_sha256', 'actual_sha256',
                                         'numerical_pass', 'post_build_structure_accepted'})
    require(d['schema'] == 'MODEL_POST_BUILD_FAILURE_DIAGNOSTIC_V1')
    require(enum(d['phase'], ('admit_build', 'prepare', 'run', 'pack', 'UNKNOWN')))
    require(enum(d['pack_phase'], POST_BUILD_PHASES) and enum(d['reason'], POST_BUILD_REASONS))
    require(enum(d['exception_class'], POST_BUILD_CLASSES))
    require(integer(d['index'], 0, 1000000, True) and integer(d['bytes'], 0, 4 << 30, True))
    require(digest(d['expected_sha256']) and digest(d['actual_sha256']))
    require(d['numerical_pass'] is False and d['post_build_structure_accepted'] is False)
    return d


def project_candidate(d):
    require(type(d) is dict)
    if d.get('schema') == 'MODEL_CANDIDATE_DIAGNOSTIC_UNAVAILABLE_V1':
        require(set(d) == {'schema', 'stage', 'numerical_pass', 'post_build_structure_accepted'})
        require(enum(d['stage'], CANDIDATE_STAGES + ('UNKNOWN',)))
    else:
        require(set(d) == {'schema', 'stage', 'status', 'reason_code', 'actual', 'numerical_pass', 'post_build_structure_accepted'})
        require(d['schema'] == 'MODEL_CANDIDATE_DIAGNOSTIC_V1' and enum(d['stage'], CANDIDATE_STAGES))
        require(enum(d['status'], ('OBSERVED_COMPLETE_UNREVIEWED', 'REJECTED_UNREVIEWED')) and enum(d['reason_code'], CANDIDATE_REASONS))
        require((d['status'] == 'OBSERVED_COMPLETE_UNREVIEWED') == (d['reason_code'] == 'NONE'))
        actual = d['actual']
        require(type(actual) is dict and set(actual) <= set(CANDIDATE_NUMBERS + CANDIDATE_HASHES + ('dense_predicate_code',)))
        for key, value in actual.items():
            if key == 'dense_predicate_code':
                require(enum(value, CANDIDATE_DENSE_PREDICATES) and d['reason_code'] == 'DENSE_ACC_LOCAL_SHAPE' and d['status'] == 'REJECTED_UNREVIEWED')
            elif key in CANDIDATE_NUMBERS:
                require(integer(value, 0, 2**53))
            else:
                require(type(value) is str and digest(value))
    require(d['numerical_pass'] is False and d['post_build_structure_accepted'] is False)
    return d


def project_execution(d):
    require(type(d) is dict and set(d) == {'schema', 'stage', 'phase', 'status', 'code',
                                         'exception_class', 'seconds', 'rss_gib',
                                         'native_started', 'numerical_pass'})
    require(enum(d['schema'], EXECUTION_SCHEMAS) and enum(d['stage'], EXECUTION_STAGES))
    require(d['status'] == 'REFUSED' and d['numerical_pass'] is False)
    require(enum(d['exception_class'], EXECUTION_EXCEPTION_CLASSES))
    require(integer(d['seconds'], 0, 21000, True) and integer(d['rss_gib'], 0, 64, True))
    if d['schema'] == EXECUTION_SCHEMAS[0]:
        require(enum(d['phase'], EXECUTION_PRE_CODES) and d['code'] == EXECUTION_PRE_CODES[d['phase']])
        require(d['native_started'] is False)
    elif d['schema'] == EXECUTION_SCHEMAS[1]:
        require(d['phase'] == 'SUPERVISOR' and d['code'] == 'SUPERVISOR_EXCEPTION')
        require(d['native_started'] is None)
    else:
        require(d['stage'] == 'frontend' and d['phase'] == 'SERIAL_PLAN')
        require(enum(d['code'], EXECUTION_SERIAL_CODES) and d['native_started'] is None)
    return d


def project_line(line):
    """Return canonical safe JSON, or None. Never unescape outer log strings."""
    try:
        require(type(line) is str and '\n' not in line and '\r' not in line)
        require(0 < len(line.encode('utf-8')) <= MAX_LINE_BYTES)
        match = next(((prefix, schema) for prefix, schema in PREFIX_SCHEMAS.items() if line.startswith(prefix)), None)
        prefix, expected = match if match is not None else ('', EXECUTION_SCHEMAS)
        raw = line[len(prefix):]
        require(0 < len(raw.encode('utf-8')) <= MAX_RECORD_BYTES)
        d = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
        require(type(d) is dict and enum(d.get('schema'), expected if type(expected) is tuple else (expected,)))
        if prefix == '': result = project_execution(d)
        elif prefix == 'BUILD_STAGE_DIAGNOSTIC ': result = project_stage(d)
        elif prefix == 'BOOTSTRAP_STAGE_DIAGNOSTIC ': result = project_stage(d, bootstrap=True)
        elif prefix == 'MODEL_POST_BUILD_DIAGNOSTIC ': result = project_post_build(d)
        else: result = project_candidate(d)
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
        require(len(encoded.encode('utf-8')) <= MAX_RECORD_BYTES)
        return encoded
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        return None


class BoundedLines:
    """Bounded line assembly; overlong lines drain through LF, never resync mid-line."""
    def __init__(self):
        self.pending = ''
        self.dropping = False
        self.input_bytes = 0
        self.stopped = False

    def feed(self, text):
        if type(text) is not str or self.stopped:
            return []
        if len(text) > MAX_WRITE_BYTES:
            self.pending = ''; self.stopped = True
            return []
        try:
            size = len(text.encode('utf-8'))
        except UnicodeError:
            self.pending = ''; self.stopped = True
            return []
        self.input_bytes += size
        if size > MAX_WRITE_BYTES or self.input_bytes > MAX_INPUT_BYTES:
            self.pending = ''; self.stopped = True
            return []
        lines = []; start = 0
        while start < len(text):
            end = text.find('\n', start)
            complete = end >= 0
            piece = text[start:end if complete else len(text)]
            start = end + 1 if complete else len(text)
            if self.dropping:
                if complete: self.dropping = False
                continue
            if len(self.pending) + len(piece) > MAX_LINE_BYTES:
                self.pending = ''; self.dropping = not complete
                continue
            self.pending += piece
            if len(self.pending.encode('utf-8')) > MAX_LINE_BYTES:
                self.pending = ''; self.dropping = not complete
                continue
            if complete:
                if self.pending and '\r' not in self.pending:
                    lines.append(self.pending)
                self.pending = ''
        return lines
