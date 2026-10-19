"""Bounded, read-only generation census and finite fresh wrapper observations.

No compiler or external process is invoked. A caller-verified source map is the
only authority for public source identities; log-derived paths are never opened.
The merged log cannot attribute diagnostics to one subprocess. Header messages
are finite classifications, not raw diagnostic prose. Wrapper observations are
syntactic evidence only, never a proof of combinational or runtime behavior.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat

MAX_LOG_BYTES = 4 * 1024**2
MAX_REPORT_BYTES = 64 * 1024
MAX_RECORDS = 128
MAX_EXAMPLES = 16
MAX_MESSAGE_CHARS = 256
MAX_COORDINATE = 9_999_999
MAX_SOURCE_ROWS = 307
MAX_ARGS_BYTES = 256 * 1024
MAX_WRAPPER_BYTES = 512 * 1024
MAX_DIRECTORY_ENTRIES = 4096
SOURCE_PREFIXES = ('idma/', 'retained/', 'host/')
STATES = frozenset(('NOT_COLLECTED', 'AVAILABLE', 'READ_ERROR', 'SANITIZER_ERROR', 'CONTRACT_ERROR'))
# Frozen ascii rule names from pinned official V3Error.h, SHA256 45d2feddb6872b1f812e9d79a7d82ffe050547fd08105db54bcdb04286d90db4.
RULE_IDS = frozenset(('CONTASSINIT', 'CONSTWRITTEN', 'LIFETIME', 'NEEDTIMINGOPT', 'NOTIMING', 'PORTSHORT', 'TASKNSVAR', 'UNSUPPORTED', 'ALWCOMBORDER', 'ALWNEVER', 'ASCRANGE', 'ASSIGNDLY', 'ASSIGNEQEXPR', 'ASSIGNIN', 'BADSTDPRAGMA', 'BADVLTPRAGMA', 'BLKANDNBLK', 'BLKLOOPINIT', 'BLKSEQ', 'BSSPACE', 'CASEINCOMPLETE', 'CASEOVERLAP', 'CASEWITHX', 'CASEX', 'CASTCONST', 'CDCRSTLOGIC', 'CLKDATA', 'CMPCONST', 'COLONPLUS', 'COMBDLY', 'CONSTRAINTIGN', 'CONTASSREG', 'COVERIGN', 'DECLFILENAME', 'DEFOVERRIDE', 'DEFPARAM', 'DEPRECATED', 'ENCAPSULATED', 'ENDLABEL', 'ENUMITEMWIDTH', 'ENUMVALUE', 'EOFNEWLINE', 'FINALDLY', 'FSMMULTI', 'FUNCTIMECTL', 'FUTURE', 'GENCLK', 'GENUNNAMED', 'HIERBLOCK', 'HIERPARAM', 'IEEEMAYDEPRECATE', 'IFDEPTH', 'IGNOREDRETURN', 'IMPERFECTSCH', 'IMPLICIT', 'IMPLICITSTATIC', 'IMPORTSTAR', 'IMPURE', 'INCABSPATH', 'INFINITELOOP', 'INITIALDLY', 'INSECURE', 'INSIDETRUE', 'LATCH', 'LITENDIAN', 'MINTYPMAXDLY', 'MISINDENT', 'MODDUP', 'MODMISSING', 'MULTIDRIVEN', 'MULTIDRIVENPROC', 'MULTITOP', 'NEVERMATCH', 'NEWERSTD', 'NOEFFECT', 'NOLATCH', 'NONSTD', 'NORETURN', 'NOTREDOP', 'NULLPORT', 'PARAMNODEFAULT', 'PINCONNECTEMPTY', 'PINMISSING', 'PINNOCONNECT', 'PINNOTFOUND', 'PKGNODECL', 'PREPROCZERO', 'PROCASSINIT', 'PROCASSWIRE', 'PROFOUTOFDATE', 'PROTECTED', 'PROTOTYPEMIS', 'RANDC', 'REALCVT', 'REDEFMACRO', 'RISEFALLDLY', 'SELRANGE', 'SHORTREAL', 'SIDEEFFECT', 'SIMILARNAME', 'SPECIFYIGN', 'SPLITVAR', 'STATICVAR', 'STMTDLY', 'SUPERNFIRST', 'SYMRSVDWORD', 'SYNCASYNCNET', 'TICKCOUNT', 'TIMESCALEMOD', 'UNDRIVEN', 'UNOPT', 'UNOPTFLAT', 'UNOPTTHREADS', 'UNPACKED', 'UNSATCONSTR', 'UNSIGNED', 'UNUSED', 'UNUSEDGENVAR', 'UNUSEDLOOP', 'UNUSEDPARAM', 'UNUSEDSIGNAL', 'USERERROR', 'USERFATAL', 'USERINFO', 'USERWARN', 'VARHIDDEN', 'WAITCONST', 'WIDTH', 'WIDTHCONCAT', 'WIDTHEXPAND', 'WIDTHTRUNC', 'WIDTHXZEXPAND', 'ZERODLY', 'ZEROREPL'))
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_REL = re.compile(r'[A-Za-z0-9_.+\-]+(?:/[A-Za-z0-9_.+\-]+)*\Z')
_LEAF = re.compile(r'qwen2_matrix_command_endpoint[A-Za-z0-9_]{0,96}\Z')
_CANDIDATE = re.compile(r'V(qwen2_matrix_command_endpoint[A-Za-z0-9_]{0,96})__hierMkArgs\.f\Z')
_HEADER = re.compile(rb'^%(Warning|Error)(?:-([^:]*))?:[ \t]*(.*)$')
_LOCATION = re.compile(r'^([^:\r\n]{1,2048}):([1-9][0-9]{0,6}):(?:([1-9][0-9]{0,6}):)?[ \t]*(.*)$')
_FATAL = re.compile(r'Exiting due to (?:(?P<errors>[0-9]{1,7}) error\(s\)(?:, (?P<mixed_warnings>[0-9]{1,7}) warning\(s\))?|(?P<warnings>[0-9]{1,7}) warning\(s\))\Z')
_EXAMPLE = re.compile(r'^\s+([^:\r\n]{1,2048}):([1-9][0-9]{0,6}):(?:([1-9][0-9]{0,6}):)?\s+Example path: (.*)$')
_HANDSHAKES = ('seed_begin_valid_i', 'seed_begin_ready_o', 'seed_commit_valid_i',
               'seed_commit_ready_o', 'seed_beat_valid_i', 'seed_beat_ready_o',
               'seed_ack_valid_o', 'seed_ack_ready_i', 'seed_abort_i', 'cmd_valid_i',
               'cmd_ready_o', 'step_valid_i', 'step_ready_o', 'out_valid_o',
               'out_ready_i', 'completion_valid_o', 'completion_ready_i')
_MESSAGES = frozenset(('Circular combinational logic reported.',
                      'Verilator warning reported; unstructured text omitted.',
                      'Verilator error reported; unstructured text omitted.',
                      'Warning-fatal exit summary reported.',
                      'Error-fatal exit summary reported.',
                      'Mixed error/warning-fatal exit summary reported.'))


def canonical_json(report):
    return (json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False) + '\n').encode('ascii')


def _need(ok):
    if not ok:
        raise ValueError('generation diagnostic contract')


def _relative(value):
    return (type(value) is str and 1 <= len(value) <= 240 and _REL.fullmatch(value)
            and all(x not in ('.', '..') for x in value.split('/')))


def _public_source(value):
    return _relative(value) and value.startswith(SOURCE_PREFIXES)


def _absolute(path):
    value = str(path)
    _need(value.startswith('/') and all(x not in ('', '.', '..') for x in value[1:].split('/')))
    return value


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(path):
    parts = [] if str(path) == '/' else _absolute(path)[1:].split('/')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(path, cap):
    path = Path(_absolute(path))
    parent = _directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            _need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap)
            raw = stream.read(cap + 1)
            after = os.fstat(stream.fileno())
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        fresh_parent = _directory(path.parent)
        try:
            original_dir, fresh_dir = os.fstat(parent), os.fstat(fresh_parent)
            _need((original_dir.st_dev, original_dir.st_ino) == (fresh_dir.st_dev, fresh_dir.st_ino))
            _need(_stamp(before) == _stamp(os.stat(path.name, dir_fd=fresh_parent, follow_symlinks=False)))
        finally:
            os.close(fresh_parent)
        _need(len(raw) == before.st_size and len(raw) <= cap and
              _stamp(before) == _stamp(after) == _stamp(current))
        return raw
    finally:
        os.close(parent)


def _identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _empty_wrapper(state='NOT_COLLECTED'):
    return {'state': state, 'args_identity': None, 'top_args_identity': None,
            'wrapper_identity': None, 'module': None, 'specialization': 'UNKNOWN',
            'hierarchical_child': None, 'top_references_wrapper': None,
            'syntax_state': 'NOT_COLLECTED', 'always_comb_count': None, 'always_comb_lines': [],
            'dpi_import_count': None, 'combo_update_import_count': None,
            'combo_update_call_count': None, 'combo_input_count': None,
            'combo_output_count': None, 'handshakes': [],
            'dependency_conclusion': 'NOT_ESTABLISHED'}


def empty_report(state='NOT_COLLECTED'):
    _need(state in STATES)
    return {'schema_version': 1, 'state': state, 'scan_complete': False, 'log_identity': None,
            'counts': {'warning_headers': 0, 'error_headers': 0, 'fatal_summary_headers': 0,
                       'example_paths': 0, 'unparsed_headers': 0},
            'by_rule': {}, 'records': [],
            'fatal_summaries': {'warning_total': None, 'error_total': None,
                                'process_attribution': 'NOT_AVAILABLE',
                                'header_count_comparison': 'NOT_AVAILABLE'},
            'omission': {'records': 0, 'examples': 0},
            'caps': {'record_cap': False, 'example_cap': False, 'report_byte_cap': False,
                     'partial': False}, 'wrapper': _empty_wrapper()}


def _sources(rows):
    _need(type(rows) is list and 1 <= len(rows) <= MAX_SOURCE_ROWS)
    result, aliases = {}, set()
    for row in rows:
        _need(type(row) is dict and set(row) == {'path', 'id', 'bytes', 'sha256'})
        path = _absolute(row['path'])
        _need(type(row['path']) is str and _public_source(row['id']) and
              type(row['bytes']) is int and 0 <= row['bytes'] <= 128 * 1024**2 and
              type(row['sha256']) is str and _HEX.fullmatch(row['sha256']) and
              path not in result and row['id'] not in aliases)
        result[path] = row
        aliases.add(row['id'])
    return result


def _location(match, sources):
    if match is None:
        return {'source_id': 'UNKNOWN_PATH', 'source_sha256': None, 'line': None, 'column': None}
    raw_path, line, column, unused = match.groups()
    source = sources.get(raw_path)
    return {'source_id': source['id'] if source else 'UNKNOWN_PATH',
            'source_sha256': source['sha256'] if source else None,
            'line': int(line), 'column': int(column) if column else None}


def _sanitize(sanitizer, prose, work, aliases):
    # The pinned sanitizer receives unstructured bytes, but only finite recognized
    # classes are published. No sanitized arbitrary filename or identifier escapes.
    result = sanitizer.sanitize_build_context(prose, str(work), aliases)
    _need(type(result) is dict and result.get('context_state') == 'AVAILABLE' and
          type(result.get('merged_log_tail')) is str)
    return result['merged_log_tail']


def _sv_mask(text):
    # Preserve quoted DPI-C while blanking comments and all other strings.
    pattern = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"')
    return pattern.sub(lambda m: '"DPI-C"' if m[0] == '"DPI-C"' else
                       ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def _port(piece):
    # Deliberately finite ANSI/DPI argument grammar. Unknown syntax stays unknown.
    match = re.fullmatch(r'\s*(input|output|inout)\s+(?:(?:wire|logic|bit|reg|integer|int|longint|shortint|byte|chandle|unsigned|signed)\s+)*(?:\[\s*[0-9]+\s*:\s*[0-9]+\s*\]\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*', piece)
    return match.groups() if match else None


def _structure(raw, leaf, result):
    text = raw.decode('ascii')
    if any(ord(c) < 32 and c not in '\r\n\t' for c in text):
        return
    text = _sv_mask(text)
    modules = list(re.finditer(r'\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^;]*?)\)\s*;', text))
    if len(modules) != 1 or modules[0][1] != leaf or len(re.findall(r'\bendmodule\b', text)) != 1:
        return
    comb_blocks = list(re.finditer(r'\balways_comb\b', text))
    result['always_comb_count'] = len(comb_blocks)
    result['always_comb_lines'] = [text.count('\n', 0, m.start()) + 1 for m in comb_blocks[:16]]
    result['dpi_import_count'] = len(re.findall(r'\bimport\s+"DPI-C"\s+(?:(?:context|pure)\s+)?function\b', text))
    symbol = re.escape(leaf) + '_protectlib_combo_update'
    imports = list(re.finditer(r'\bimport\s+"DPI-C"\s+(?:(?:context|pure)\s+)?function\s+longint\s+' + symbol + r'\s*\((.*?)\)\s*;', text, re.S))
    result['combo_update_import_count'] = len(imports)
    calls = list(re.finditer(r'\b' + symbol + r'\s*\((.*?)\)\s*;', text, re.S))
    calls = [m for m in calls if not any(a.start() <= m.start() < a.end() for a in imports)]
    result['combo_update_call_count'] = len(calls)
    ports = [_port(p) for p in modules[0][2].split(',')]
    if not all(ports) or len(imports) != 1 or len(calls) != 1:
        return
    args = imports[0][1].split(',')
    # The generated handle argument has implicit input direction.
    if not args or re.fullmatch(r'\s*chandle\s+handle__V\s*', args[0]) is None:
        return
    parameters = [_port(p) for p in args[1:]]
    call_args = [p.strip() for p in calls[0][1].split(',')]
    if (not all(parameters) or len(call_args) != len(args) or call_args[0] != 'handle__V'
            or any(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', p) is None for p in call_args)):
        return
    directions = dict((name, direction) for direction, name in ports)
    if len(directions) != len(ports) or len({p[1] for p in parameters}) != len(parameters):
        return
    result['combo_input_count'] = sum(direction == 'input' for direction, name in parameters)
    result['combo_output_count'] = sum(direction == 'output' for direction, name in parameters)
    pairs = dict((name, (direction, actual)) for (direction, name), actual in zip(parameters, call_args[1:]))
    selected = []
    for name in _HANDSHAKES:
        if name in directions:
            pair = pairs.get(name)
            declaration = re.search(r'\b' + re.escape(name) + r'\b', modules[0][2])
            declaration_line = text.count('\n', 0, modules[0].start(2) + declaration.start()) + 1
            selected.append({'name': name, 'direction': directions[name], 'declaration_line': declaration_line,
                             'combo_direction': pair[0] if pair else 'NOT_PRESENT',
                             'combo_binding': ('DIRECT' if pair and pair[1] == name else
                                               'COMBO_RESULT' if pair and pair[1] == name + '_combo__V' else
                                               'UNKNOWN' if pair else 'NOT_PRESENT')})
    result['handshakes'] = selected
    result['syntax_state'] = 'FINITE_PARSE_AVAILABLE'


def _wrapper(work):
    result = _empty_wrapper('MISSING')
    try:
        obj = Path(work) / 'obj'
        fd = _directory(obj)
        try:
            candidates = []
            with os.scandir(fd) as entries:
                for index, item in enumerate(entries):
                    _need(index < MAX_DIRECTORY_ENTRIES)
                    if _CANDIDATE.fullmatch(item.name):
                        candidates.append(item.name)
                        _need(len(candidates) <= 1)
        finally:
            os.close(fd)
        if not candidates:
            return result
        candidate = candidates[0]
        args_raw = _read(obj / candidate, MAX_ARGS_BYTES)
        args = shlex.split(args_raw.decode('ascii'))
        def option(name):
            _need(args.count(name) == 1 and args.index(name) + 1 < len(args) and
                  not any(token.startswith(name + '=') for token in args))
            return args[args.index(name) + 1]
        leaf = option('--lib-create')
        _need(_LEAF.fullmatch(leaf) and candidate == 'V' + leaf + '__hierMkArgs.f' and
              option('--hierarchical-child') == '1' and option('--top-module-encoded') == leaf)
        seed = [x.split('=', 1)[1] for x in args if x.startswith('-GENABLE_ACCUMULATOR_SEED=')]
        _need(len(seed) <= 1)
        result.update(args_identity=_identity(args_raw), module='qwen2_matrix_command_endpoint', hierarchical_child=1,
                      specialization=('ENABLED' if seed and seed[0] in
                                      ('1', "32'h1", "32'sh1", "32'd1", "32'sd1", "'sh1") else
                                      'DISABLED' if seed and seed[0] == '0' else 'UNKNOWN'))
        relative = 'V' + leaf + '/' + leaf + '.sv'
        wrapper_raw = _read(obj / relative, MAX_WRAPPER_BYTES)
        result.update(state='AVAILABLE', wrapper_identity=_identity(wrapper_raw), syntax_state='UNRECOGNIZED_SYNTAX')
        try:
            top_raw = _read(obj / 'VHostBlockTop__hierMkArgs.f', MAX_ARGS_BYTES)
            top_tokens = shlex.split(top_raw.decode('ascii'))
            result['top_args_identity'] = _identity(top_raw)
            result['top_references_wrapper'] = relative in top_tokens
        except FileNotFoundError:
            pass
        _structure(wrapper_raw, leaf, result)
        _need(_read(obj / candidate, MAX_ARGS_BYTES) == args_raw and
              _read(obj / relative, MAX_WRAPPER_BYTES) == wrapper_raw)
        if result['top_args_identity'] is not None:
            _need(_read(obj / 'VHostBlockTop__hierMkArgs.f', MAX_ARGS_BYTES) == top_raw)
        return result
    except FileNotFoundError:
        result['state'] = 'MISSING'
    except (OSError, UnicodeError):
        result['state'] = 'READ_ERROR'
    except (ValueError, TypeError):
        result['state'] = 'CONTRACT_ERROR'
    return result


def collect(log_path, work, source_map, sanitizer):
    report = empty_report()
    try:
        work = Path(_absolute(work))
        sources = _sources(source_map)
    except (ValueError, TypeError, KeyError):
        return empty_report('CONTRACT_ERROR')
    try:
        raw = _read(log_path, MAX_LOG_BYTES)
    except (OSError, ValueError, TypeError):
        report['state'] = 'READ_ERROR'
        report['wrapper'] = _wrapper(work)
        return validate_report(report)
    report['state'] = 'AVAILABLE'
    report['log_identity'] = _identity(raw)
    aliases = frozenset(row['id'] for row in source_map)
    records, examples = [], []
    last_ordinal = None
    sanitizer_failed = False
    for raw_line in raw.split(b'\n'):
        header = _HEADER.fullmatch(raw_line)
        if header:
            severity = header[1].decode('ascii').upper()
            count_key = 'warning_headers' if severity == 'WARNING' else 'error_headers'
            report['counts'][count_key] += 1
            rule_raw = header[2]
            rule = rule_raw.decode('ascii') if rule_raw and rule_raw.isascii() else None
            rule = rule if rule in RULE_IDS else 'NONE' if rule_raw is None else 'UNKNOWN'
            report['by_rule'][severity + ':' + rule] = report['by_rule'].get(severity + ':' + rule, 0) + 1
            last_ordinal = report['counts']['warning_headers'] + report['counts']['error_headers']
            body = header[3].decode('utf-8', errors='backslashreplace')
            location = _LOCATION.fullmatch(body)
            fatal = _FATAL.fullmatch(body) if severity == 'ERROR' else None
            if fatal:
                report['counts']['fatal_summary_headers'] += 1
                if report['counts']['fatal_summary_headers'] == 1:
                    warning_value = fatal['warnings'] or fatal['mixed_warnings']
                    report['fatal_summaries']['warning_total'] = int(warning_value) if warning_value is not None else None
                    report['fatal_summaries']['error_total'] = int(fatal['errors']) if fatal['errors'] is not None else None
                else:
                    # Distinct merged-process summaries cannot be summed into
                    # one process total. Values exist only for one summary.
                    report['fatal_summaries']['warning_total'] = None
                    report['fatal_summaries']['error_total'] = None
            if len(records) < MAX_RECORDS:
                try:
                    # Oversized prose is not partially exposed to the sanitizer.
                    sanitized = _sanitize(sanitizer, header[3] if len(header[3]) <= 8192 else b'Unstructured text omitted.', work, aliases)
                except Exception:
                    sanitizer_failed = True
                    sanitized = ''
                message = ('Mixed error/warning-fatal exit summary reported.' if fatal and fatal['mixed_warnings'] is not None else
                           'Warning-fatal exit summary reported.' if fatal and fatal['warnings'] is not None else
                           'Error-fatal exit summary reported.' if fatal else
                           'Circular combinational logic reported.' if rule == 'UNOPTFLAT' and
                           'Signal unoptimizable: Circular combinational logic:' in sanitized else
                           'Verilator warning reported; unstructured text omitted.' if severity == 'WARNING' else
                           'Verilator error reported; unstructured text omitted.')
                record = {'ordinal': last_ordinal, 'severity': severity, 'rule': rule,
                          **_location(location, sources), 'message': message}
                records.append(record)
        elif raw_line.startswith((b'%Warning', b'%Error')):
            report['counts']['unparsed_headers'] += 1
            last_ordinal = None
        elif b'Example path:' in raw_line:
            report['counts']['example_paths'] += 1
            match = _EXAMPLE.fullmatch(raw_line.decode('utf-8', errors='backslashreplace'))
            if match and last_ordinal is not None and len(examples) < MAX_EXAMPLES:
                # Example prose is intentionally not published. Only exact known
                # source identities and bounded coordinates leave the private log.
                examples.append({'record_ordinal': last_ordinal, **_location(match, sources)})
    report['scan_complete'] = True
    report['records'] = records
    report['wrapper'] = _wrapper(work)
    total = report['counts']['warning_headers'] + report['counts']['error_headers']
    report['caps']['record_cap'] = total > MAX_RECORDS
    report['caps']['example_cap'] = report['counts']['example_paths'] > MAX_EXAMPLES
    if report['counts']['fatal_summary_headers'] == 1:
        fatal = report['fatal_summaries']
        matches = ((fatal['warning_total'] is None or fatal['warning_total'] == report['counts']['warning_headers']) and
                   (fatal['error_total'] is None or fatal['error_total'] == report['counts']['error_headers'] - 1))
        fatal['header_count_comparison'] = 'GLOBAL_HEADERS_MATCH' if matches else 'GLOBAL_HEADERS_DIFFER'
    # Every retained heading takes priority over every optional example.
    while len(canonical_json(report)) > MAX_REPORT_BYTES - 512 and records:
        records.pop()
        report['caps']['report_byte_cap'] = True
    kept_ordinals = {r['ordinal'] for r in records}
    for example in examples:
        if example['record_ordinal'] not in kept_ordinals:
            continue
        record = records[example['record_ordinal'] - 1]
        record.setdefault('examples', []).append({k: v for k, v in example.items() if k != 'record_ordinal'})
        if len(canonical_json(report)) > MAX_REPORT_BYTES - 512:
            record['examples'].pop()
            if not record['examples']:
                del record['examples']
            report['caps']['report_byte_cap'] = True
    report['omission']['records'] = total - len(records)
    report['omission']['examples'] = report['counts']['example_paths'] - sum(len(r.get('examples', [])) for r in records)
    report['caps']['partial'] = bool(report['omission']['records'] or report['omission']['examples'] or report['counts']['unparsed_headers'])
    if sanitizer_failed:
        report['state'] = 'SANITIZER_ERROR'
    return validate_report(report)


def _validate_report(report):
    _need(type(report) is dict and set(report) == set(empty_report()) and type(report['schema_version']) is int and report['schema_version'] == 1 and report['state'] in STATES and type(report['scan_complete']) is bool)
    def natural(value, cap=MAX_LOG_BYTES):
        _need(type(value) is int and 0 <= value <= cap)
    def identity(value, cap):
        _need(value is None or (type(value) is dict and set(value) == {'bytes', 'sha256'} and
              type(value['bytes']) is int and 0 <= value['bytes'] <= cap and
              type(value['sha256']) is str and _HEX.fullmatch(value['sha256'])))
    def location(row):
        _need((row['source_id'] == 'UNKNOWN_PATH' and row['source_sha256'] is None) or
              (_public_source(row['source_id']) and type(row['source_sha256']) is str and _HEX.fullmatch(row['source_sha256'])))
        for key in ('line', 'column'):
            _need(row[key] is None or (type(row[key]) is int and 1 <= row[key] <= MAX_COORDINATE))
        _need(row['column'] is None or row['line'] is not None)
    identity(report['log_identity'], MAX_LOG_BYTES)
    _need(report['scan_complete'] == (report['state'] in ('AVAILABLE', 'SANITIZER_ERROR')))
    _need((report['log_identity'] is not None) == report['scan_complete'])
    _need(type(report['counts']) is dict and set(report['counts']) == set(empty_report()['counts']))
    for value in report['counts'].values(): natural(value)
    _need(report['scan_complete'] or not any(report['counts'].values()))
    _need(report['counts']['fatal_summary_headers'] <= report['counts']['error_headers'])
    _need(type(report['by_rule']) is dict)
    for key, value in report['by_rule'].items():
        _need(type(key) is str and ':' in key)
        severity, rule = key.split(':', 1)
        _need(severity in ('WARNING', 'ERROR') and rule in RULE_IDS | {'UNKNOWN', 'NONE'})
        natural(value)
        _need(value > 0)
    _need(type(report['records']) is list and len(report['records']) <= MAX_RECORDS)
    record_counts = {}
    for index, row in enumerate(report['records']):
        _need(type(row) is dict and set(row) in ({'ordinal','severity','rule','source_id','source_sha256','line','column','message'}, {'ordinal','severity','rule','source_id','source_sha256','line','column','message','examples'}))
        _need(type(row['ordinal']) is int and row['ordinal'] == index + 1 and row['severity'] in ('WARNING','ERROR') and row['rule'] in RULE_IDS | {'UNKNOWN','NONE'} and row['message'] in _MESSAGES)
        key = row['severity'] + ':' + row['rule']
        record_counts[key] = record_counts.get(key, 0) + 1
        location(row)
        _need(type(row.get('examples', [])) is list)
        for example in row.get('examples', []):
            _need(type(example) is dict and set(example) == {'source_id','source_sha256','line','column'})
            location(example)
    _need(type(report['omission']) is dict and set(report['omission']) == {'records','examples'})
    for value in report['omission'].values(): natural(value)
    total = report['counts']['warning_headers'] + report['counts']['error_headers']
    _need(sum(report['by_rule'].values()) == total and report['omission']['records'] + len(report['records']) == total)
    _need(all(value <= report['by_rule'].get(key, 0) for key, value in record_counts.items()))
    if report['omission']['records'] == 0:
        _need(record_counts == report['by_rule'])
    for severity, key in (('WARNING:', 'warning_headers'), ('ERROR:', 'error_headers')):
        _need(sum(v for k, v in report['by_rule'].items() if k.startswith(severity)) == report['counts'][key])
    example_count = sum(len(row.get('examples', [])) for row in report['records'])
    _need(example_count <= MAX_EXAMPLES and example_count + report['omission']['examples'] == report['counts']['example_paths'])
    _need(type(report['caps']) is dict and set(report['caps']) == set(empty_report()['caps']) and all(type(v) is bool for v in report['caps'].values()))
    _need(report['caps']['record_cap'] == (total > MAX_RECORDS) and report['caps']['example_cap'] == (report['counts']['example_paths'] > MAX_EXAMPLES))
    _need(report['caps']['partial'] == bool(report['omission']['records'] or report['omission']['examples'] or report['counts']['unparsed_headers']))
    fatal = report['fatal_summaries']
    _need(type(fatal) is dict and set(fatal) == set(empty_report()['fatal_summaries']) and fatal['process_attribution'] == 'NOT_AVAILABLE' and fatal['header_count_comparison'] in ('NOT_AVAILABLE','GLOBAL_HEADERS_MATCH','GLOBAL_HEADERS_DIFFER'))
    for key in ('warning_total', 'error_total'):
        if fatal[key] is not None: natural(fatal[key], MAX_COORDINATE)
    if report['counts']['fatal_summary_headers'] == 1:
        _need(fatal['warning_total'] is not None or fatal['error_total'] is not None)
        matches = ((fatal['warning_total'] is None or fatal['warning_total'] == report['counts']['warning_headers']) and
                   (fatal['error_total'] is None or fatal['error_total'] == report['counts']['error_headers'] - 1))
        _need(fatal['header_count_comparison'] == ('GLOBAL_HEADERS_MATCH' if matches else 'GLOBAL_HEADERS_DIFFER'))
    else:
        _need(fatal['warning_total'] is None and fatal['error_total'] is None)
    _need(report['counts']['fatal_summary_headers'] == 1 or fatal['header_count_comparison'] == 'NOT_AVAILABLE')
    wrapper = report['wrapper']
    _need(type(wrapper) is dict and set(wrapper) == set(_empty_wrapper()) and wrapper['state'] in ('NOT_COLLECTED','AVAILABLE','MISSING','READ_ERROR','CONTRACT_ERROR'))
    identity(wrapper['args_identity'], MAX_ARGS_BYTES)
    identity(wrapper['top_args_identity'], MAX_ARGS_BYTES)
    identity(wrapper['wrapper_identity'], MAX_WRAPPER_BYTES)
    _need(wrapper['module'] is None or wrapper['module'] == 'qwen2_matrix_command_endpoint')
    _need(wrapper['specialization'] in ('UNKNOWN','ENABLED','DISABLED') and (wrapper['hierarchical_child'] is None or (type(wrapper['hierarchical_child']) is int and wrapper['hierarchical_child'] == 1)) and (wrapper['top_references_wrapper'] is None or type(wrapper['top_references_wrapper']) is bool) and wrapper['syntax_state'] in ('NOT_COLLECTED','UNRECOGNIZED_SYNTAX','FINITE_PARSE_AVAILABLE') and wrapper['dependency_conclusion'] == 'NOT_ESTABLISHED')
    for key in ('always_comb_count','dpi_import_count','combo_update_import_count','combo_update_call_count','combo_input_count','combo_output_count'):
        if wrapper[key] is not None: natural(wrapper[key], MAX_WRAPPER_BYTES)
    _need(type(wrapper['always_comb_lines']) is list and len(wrapper['always_comb_lines']) <= 16)
    for line in wrapper['always_comb_lines']:
        _need(type(line) is int and 1 <= line <= MAX_WRAPPER_BYTES)
    _need(wrapper['always_comb_lines'] == sorted(wrapper['always_comb_lines']))
    _need(wrapper['always_comb_count'] is None or len(wrapper['always_comb_lines']) <= wrapper['always_comb_count'])
    _need(type(wrapper['handshakes']) is list and len(wrapper['handshakes']) <= len(_HANDSHAKES))
    seen = set()
    for port in wrapper['handshakes']:
        _need(type(port) is dict and set(port) == {'name','direction','combo_direction','combo_binding','declaration_line'} and port['name'] in _HANDSHAKES and port['name'] not in seen and port['direction'] in ('input','output','inout') and port['combo_direction'] in ('input','output','inout','NOT_PRESENT') and port['combo_binding'] in ('DIRECT','COMBO_RESULT','UNKNOWN','NOT_PRESENT'))
        _need(type(port['declaration_line']) is int and 1 <= port['declaration_line'] <= MAX_WRAPPER_BYTES)
        seen.add(port['name'])
    if wrapper['syntax_state'] == 'FINITE_PARSE_AVAILABLE':
        _need(wrapper['wrapper_identity'] is not None and wrapper['module'] is not None and
              wrapper['combo_update_import_count'] == 1 and wrapper['combo_update_call_count'] == 1 and
              wrapper['combo_input_count'] is not None and wrapper['combo_output_count'] is not None)
    if wrapper['state'] == 'AVAILABLE':
        _need(wrapper['wrapper_identity'] is not None and wrapper['args_identity'] is not None and wrapper['module'] is not None)
    _need(len(canonical_json(report)) <= MAX_REPORT_BYTES)
    return report


def validate_report(report):
    """Validate exact keys, finite fields, arithmetic, scalar types and JSON bound."""
    try:
        return _validate_report(report)
    except (KeyError, TypeError, OverflowError, RecursionError, UnicodeError):
        raise ValueError('generation diagnostic contract') from None
