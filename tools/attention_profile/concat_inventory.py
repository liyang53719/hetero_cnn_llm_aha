# SPDX-License-Identifier: Apache-2.0
"""Bounded, read-only generated-C++ concat evidence; never attributes sampled ELF PCs.

collect(build, output) creates a NEW output directory containing JSON evidence
and a capped selection of generated source/header bytes. No model data or
driver inputs are read. Unknown syntax is reported, not inferred as a caller.
"""
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

MAX_FILES = 50000
MAX_SCAN_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_CALLS = 100000
MAX_EVIDENCE_CHARACTERS = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_TEXT = 4096
MAX_PARAMETERS = 16384
MAX_IDENTIFIERS = 128
PRIORITY_CPP = (
    'obj/VHostBlockTop___024root__DepSet_h74254c49__13.cpp',
    'obj/VHostBlockTop___024root__DepSet_h74254c49__94.cpp',
)
CALL = re.compile(r'\bVL_CONCAT_WWI\s*\(')
FUNCTION = re.compile(
    r'^\s*(?:(?:static|inline|VL_INLINE_OPT|extern)\s+)*'
    r'(?:[A-Za-z_]\w*(?:::\w+)*(?:\s*[*&])?\s+)'
    r'([A-Za-z_]\w*(?:::\w+)*)\s*\(', re.MULTILINE)
TOKEN = re.compile(r'[A-Za-z_]\w*')
INTEGER = re.compile(r'(?:0[xX][0-9a-fA-F]+|0[bB][01]+|[0-9]+)(?:[uU](?:ll|LL|[lL])?|(?:ll|LL|[lL])[uU]?)?\Z')
PARAM_NAMES = ('obits', 'lbits', 'rbits', 'destination', 'left', 'right')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def masked_cpp(text):
    """Mask comments/literals, preserving byte-character positions and newlines."""
    chars = list(text)
    i, n = 0, len(text)
    errors = []
    while i < n:
        start, end = i, None
        if text.startswith('//', i):
            end = text.find('\n', i + 2)
            if end < 0:
                end = n
        elif text.startswith('/*', i):
            close = text.find('*/', i + 2)
            end = n if close < 0 else close + 2
            if close < 0:
                errors.append({'offset': i, 'reason': 'unterminated_comment'})
        elif text.startswith('R"', i):
            opening = text.find('(', i + 2, i + 19)
            if opening >= 0 and not re.search(r'[\s\\)]', text[i + 2:opening]):
                terminator = ')' + text[i + 2:opening] + '"'
                close = text.find(terminator, opening + 1)
                end = n if close < 0 else close + len(terminator)
                if close < 0:
                    errors.append({'offset': i, 'reason': 'unterminated_raw_string'})
        elif text[i] in ('"', "'"):
            quote = text[i]
            end = i + 1
            while end < n:
                if text[end] == '\\':
                    end += 2
                elif text[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            else:
                errors.append({'offset': i, 'reason': 'unterminated_literal'})
        if end is None:
            i += 1
        else:
            end = min(end, n)
            chars[start:end] = ['\n' if ch == '\n' else ' ' for ch in text[start:end]]
            i = end
    return ''.join(chars), errors


def delimiters(mask):
    """Record matched delimiters and mismatches in one pass."""
    stack, pairs, errors = [], {}, []
    closers = {')': '(', ']': '[', '}': '{'}
    for match in re.finditer(r'[()\[\]{}]', mask):
        i, ch = match.start(), match.group()
        if ch in '([{':
            stack.append((ch, i))
        elif stack and stack[-1][0] == closers[ch]:
            _, opening = stack.pop()
            pairs[opening] = i
        else:
            errors.append({'offset': i, 'reason': 'unmatched_closing_delimiter'})
    errors.extend({'offset': i, 'reason': 'unmatched_opening_delimiter'} for _, i in stack)
    return pairs, errors


def literal_int(value):
    value = value.strip()
    while value.startswith('(') and value.endswith(')'):
        value = value[1:-1].strip()
    if len(value) > 64 or not INTEGER.fullmatch(value):
        return None
    digits = re.sub(r'[uUlL]+$', '', value)
    if digits.lower().startswith('0x'):
        return int(digits, 16)
    if digits.lower().startswith('0b'):
        return int(digits, 2)
    if len(digits) > 1 and digits.startswith('0'):
        return int(digits, 8) if all(ch in '01234567' for ch in digits) else None
    return int(digits, 10)


def bounded_text(value, limit=MAX_TEXT):
    return {'text': value[:limit], 'characters': len(value), 'truncated': len(value) > limit}


def parse_source(text, relative, limit=MAX_CALLS, evidence_budget=None):
    """Extract syntactic calls and enclosing generated functions conservatively."""
    mask, lexical_errors = masked_cpp(text)
    pairs, delimiter_errors = delimiters(mask)
    newlines = [-1] + [m.start() for m in re.finditer('\n', text)]
    line = lambda position: bisect_right(newlines, position - 1)
    source_lines = text.splitlines()
    functions, declarations = [], set()
    for match in FUNCTION.finditer(mask):
        # A return statement or `else if` is not a C++ function declaration.
        # Only the small generated-function syntax accepted above is claimed.
        first_word = match.group().split()[0]
        if first_word in ('return', 'else', 'throw', 'case', 'delete', 'new') or match.group(1) in (
                'if', 'for', 'while', 'switch', 'catch', 'sizeof', 'alignof'):
            continue
        opening = mask.find('(', match.start(), match.end())
        close = pairs.get(opening)
        if close is None:
            continue
        after = close + 1
        while after < len(mask) and mask[after].isspace():
            after += 1
        if match.group(1) == 'VL_CONCAT_WWI':
            declarations.add(opening)
        if after < len(mask) and mask[after] == '{' and after in pairs:
            functions.append({'name': match.group(1), 'begin': match.start(),
                              'body': after, 'end': pairs[after],
                              'line_start': line(match.start()), 'line_end': line(pairs[after])})
    functions.sort(key=lambda f: f['body'])
    starts = [f['body'] for f in functions]
    calls, truncated = [], False
    if evidence_budget is None:
        evidence_budget = [MAX_EVIDENCE_CHARACTERS]
    for match in CALL.finditer(mask):
        opening = mask.find('(', match.start(), match.end())
        if opening in declarations:
            continue
        if len(calls) >= limit:
            truncated = True
            break
        close = pairs.get(opening)
        item = {'file': relative, 'line_start': line(match.start()),
                'line_end': line(close) if close is not None else None,
                'character_offset': match.start(), 'function': None,
                'parameters': [], 'parse_status': 'unmatched_call_parenthesis'}
        fi = bisect_right(starts, match.start()) - 1
        if fi >= 0 and functions[fi]['body'] < match.start() < functions[fi]['end']:
            item['function'] = {k: functions[fi][k] for k in ('name', 'line_start', 'line_end')}
        if close is not None:
            spans, begin, pos, unsupported_template = [], opening + 1, opening + 1, False
            while pos < close:
                if mask[pos] in '([{':
                    nested_end = pairs.get(pos)
                    if nested_end is None:
                        break
                    pos = nested_end + 1
                    continue
                if mask[pos] == ',':
                    spans.append((begin, pos)); begin = pos + 1
                # Angle brackets are intentionally not parsed as template syntax.
                if mask[pos] == '<' and pos > opening and re.search(r'\w\s*$', mask[opening + 1:pos]):
                    unsupported_template = True
                pos += 1
            spans.append((begin, close))
            item['argument_count'] = len(spans)
            for index, (a, b) in enumerate(spans):
                value = text[a:b].strip()
                param = dict(index=index, name=PARAM_NAMES[index] if index < 6 else None,
                             **bounded_text(value, MAX_PARAMETERS))
                param['integer_constant'] = literal_int(mask[a:b]) if index < 3 else None
                item['parameters'].append(param)
            item['parse_status'] = ('unsupported_angle_expression' if unsupported_template else
                                    'parsed' if len(spans) == 6 else 'unexpected_argument_count')
            if item['parse_status'] != 'parsed':
                for p in item['parameters']:
                    p['integer_constant'] = None
            widths = {p['name']: p['integer_constant'] for p in item['parameters'][:3]}
            item['width_constants'] = widths
            item['output_words_32'] = ((widths['obits'] + 31) // 32
                if item['parse_status'] == 'parsed' and widths.get('obits') is not None else None)
            call_mask = mask[opening + 1:close]
            tokens = sorted(set(TOKEN.findall(call_mask)))
            signals = [x for x in tokens if '__DOT__' in x]
            temporaries = [x for x in tokens if x.startswith('__Vtemp')]
            item['signal_identifiers'] = [x[:512] for x in signals[:MAX_IDENTIFIERS]]
            item['temporary_identifiers'] = [x[:512] for x in temporaries[:MAX_IDENTIFIERS]]
            item['identifier_list_truncated'] = len(signals) > MAX_IDENTIFIERS or len(temporaries) > MAX_IDENTIFIERS
            item['identifier_text_truncated'] = any(len(x) > 512 for x in tokens)
            item['unclassified_identifiers'] = [x[:512] for x in tokens if '__DOT__' not in x and not x.startswith('__Vtemp')][:128]
        first = max(1, item['line_start'] - 6)
        last = min(len(source_lines), (item['line_end'] or item['line_start']) + 3)
        context = '\n'.join(source_lines[first - 1:last])
        item['nearby_source'] = dict(line_start=first, line_end=last, **bounded_text(context))
        conditions = []
        for index in range(max(0, item['line_start'] - 13), min(len(source_lines), item['line_start'] + 3)):
            if re.search(r'\b(?:if|else|case|switch|for|while)\b|\?', source_lines[index]):
                conditions.append(dict(line=index + 1, **bounded_text(source_lines[index], 512)))
        item['nearby_condition_evidence'] = conditions
        item['condition_interpretation'] = 'Nearby source text only; dominance, activity and sampled caller are unproven.'
        for fragment in [*item['parameters'], item['nearby_source'], *conditions]:
            keep = min(len(fragment['text']), max(0, evidence_budget[0]))
            if keep < len(fragment['text']):
                fragment['truncated'] = True
            fragment['text'] = fragment['text'][:keep]
            evidence_budget[0] -= keep
        calls.append(item)
    return calls, {'call_limit_reached': truncated, 'lexical_errors': lexical_errors,
                   'delimiter_errors': delimiter_errors, 'recognized_functions': len(functions),
                   'text_evidence_budget_exhausted': evidence_budget[0] <= 0}


def runtime_headers(build):
    """Read runtime roots from generated makefiles/receipts, never run a tool."""
    roots = []
    receipt = build / 'verilator_runtime.json'
    if receipt.is_file():
        data = json.loads(receipt.read_text())
        roots += [Path(data[k]) for k in ('runtime_root', 'original_root') if data.get(k)]
    for makefile in sorted((build / 'obj').glob('*.mk')):
        if makefile.stat().st_size > 2 * 1024 * 1024:
            continue
        match = re.search(r'^\s*VERILATOR_ROOT\s*[:?]?=\s*(.*?)\s*$', makefile.read_text(), re.MULTILINE)
        if match and '$' not in match.group(1):
            root = Path(match.group(1))
            if root.is_absolute():
                roots.append(root)
    if not roots and os.environ.get('VERILATOR_ROOT'):
        roots.append(Path(os.environ['VERILATOR_ROOT']))
    seen = set()
    for root in roots:
        candidate = root / 'include/verilated_funcs.h'
        if candidate.is_file() and not candidate.is_symlink() and candidate.resolve() not in seen:
            seen.add(candidate.resolve())
            yield candidate


def collect(build: Path, output: Path) -> dict:
    build, output = Path(build).resolve(strict=True), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('concat inventory output must be new')
    obj = build / 'obj'
    if not obj.is_dir() or obj.is_symlink():
        raise ValueError('generated obj directory required')
    paths, discovery_truncated = [], False
    for path in obj.rglob('*.cpp'):
        if len(paths) >= MAX_FILES:
            discovery_truncated = True
            break
        paths.append(path)
    paths.sort()
    output.mkdir(parents=True)
    manifest, calls, scan, skipped = [], [], [], []
    scanned_bytes = 0
    evidence_budget = [MAX_EVIDENCE_CHARACTERS]
    for index, path in enumerate(paths):
        relative = str(path.relative_to(build))
        if not path.is_file():
            skipped.append({'file': relative, 'reason': 'not_regular_file'}); continue
        if path.is_symlink() or not path.resolve().is_relative_to(obj.resolve()):
            skipped.append({'file': relative, 'reason': 'symlink_or_outside_obj'}); continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            manifest.append({'file': relative, 'bytes': size, 'sha256': file_digest(path)})
            skipped.append({'file': relative, 'reason': 'single_file_parse_budget'}); continue
        if index >= MAX_FILES or scanned_bytes + size > MAX_SCAN_BYTES:
            skipped.append({'file': relative, 'reason': 'scan_budget'}); continue
        raw = path.read_bytes()
        identity = {'file': relative, 'bytes': len(raw), 'sha256': digest(raw)}
        manifest.append(identity)
        scanned_bytes += len(raw)
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            skipped.append({'file': relative, 'reason': 'not_utf8'}); continue
        if len(calls) >= MAX_CALLS:
            skipped.append({'file': relative, 'reason': 'call_budget'}); continue
        items, receipt = parse_source(text, relative, MAX_CALLS - len(calls), evidence_budget)
        calls.extend(items)
        scan.append(dict(file=relative, calls=len(items), **receipt))
    (output / 'cpp_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'calls.json').write_text(json.dumps(calls, indent=2) + '\n')
    (output / 'scan_receipt.json').write_text(json.dumps({'files': scan, 'skipped': skipped}, indent=2) + '\n')

    counts = Counter(item['file'] for item in calls)
    selected, selection_skipped, selected_bytes, candidates = [], [], 0, []
    candidates += [(build / rel, rel, 'sampled_root_translation_unit') for rel in PRIORITY_CPP]
    candidates += [(obj / 'VHostBlockTop___024root.h', 'obj/VHostBlockTop___024root.h', 'root_signal_declarations')]
    for index, header in enumerate(runtime_headers(build)):
        candidates.append((header, f'runtime_{index}/verilated_funcs.h', 'runtime_helper_implementation'))
    sv = build / 'generated/HostBlockTop.sv'
    sv_identity = None
    if sv.is_file() and not sv.is_symlink() and sv.resolve().is_relative_to(build):
        sv_identity = {'file': 'generated/HostBlockTop.sv', 'bytes': sv.stat().st_size, 'sha256': file_digest(sv),
                       'mapping_status': 'not_yet_mapped_to_sampled_ELF_caller'}
        candidates.append((sv, 'generated/HostBlockTop.sv', 'admitted_original_sv_optional'))
    candidates += [(build / rel, rel, 'contains_concat_calls') for rel, _ in counts.most_common()]
    candidates += [(obj / 'VHostBlockTop.h', 'obj/VHostBlockTop.h', 'top_header')]
    seen = set()
    for path, relative, reason in candidates:
        if relative in seen:
            continue
        seen.add(relative)
        if not path.is_file():
            selection_skipped.append({'file': relative, 'reason': 'missing'}); continue
        if path.suffix not in ('.cpp', '.h') and not (path == sv and path.suffix == '.sv'):
            raise ValueError('only generated C++/headers and exact HostBlockTop.sv may be selected')
        if not reason.startswith('runtime_') and path != sv and (path.is_symlink() or not path.resolve().is_relative_to(obj.resolve())):
            selection_skipped.append({'file': relative, 'reason': 'symlink_or_outside_obj'}); continue
        size = path.stat().st_size
        if selected_bytes + size > MAX_SOURCE_BYTES:
            selection_skipped.append({'file': relative, 'bytes': size, 'reason': 'source_byte_budget'}); continue
        raw = path.read_bytes()
        if len(raw) != size or selected_bytes + len(raw) > MAX_SOURCE_BYTES:
            raise ValueError('selected source changed size while reading')
        prior = next((entry for entry in manifest if entry['file'] == relative), None)
        if prior is not None and digest(raw) != prior['sha256']:
            raise ValueError('generated C++ changed after inventory: ' + relative)
        if path == sv and digest(raw) != sv_identity['sha256']:
            raise ValueError('generated SV changed after identity read')
        # Sources are copied byte-for-byte, never silently cut to fit the cap.
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError:
            selection_skipped.append({'file': relative, 'reason': 'not_utf8'}); continue
        destination = output / 'source' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        selected_bytes += len(raw)
        selected.append({'file': relative, 'saved_as': str(destination.relative_to(output)),
                         'bytes': len(raw), 'sha256': digest(raw), 'selection_reason': reason})
    (output / 'selected_source_manifest.json').write_text(json.dumps(selected, indent=2) + '\n')
    required = [*PRIORITY_CPP, 'obj/VHostBlockTop___024root.h']
    saved_names = {entry['file'] for entry in selected}
    required_missing = [name for name in required if name not in saved_names]
    if not any(entry['selection_reason'] == 'runtime_helper_implementation' for entry in selected):
        required_missing.append('runtime/verilated_funcs.h')
    unresolved = sum(item['parse_status'] != 'parsed' or item['function'] is None for item in calls)
    summary = dict(schema='ATTENTION_CONCAT_SOURCE_INVENTORY_V1',
        attribution='Generated source call sites only; no sampled-ELF caller attribution.',
        numerical_acceptance=False, cpp_files_discovered=len(paths), cpp_files_hashed=len(manifest),
        cpp_bytes_hashed=sum(entry['bytes'] for entry in manifest), cpp_bytes_scanned=scanned_bytes,
        calls=len(calls), unresolved_calls=unresolved,
        truncated=bool(discovery_truncated or skipped or any(x['call_limit_reached'] or x['text_evidence_budget_exhausted'] for x in scan)),
        file_discovery_truncated=discovery_truncated,
        syntax_error_files=sum(bool(x['lexical_errors'] or x['delimiter_errors']) for x in scan),
        parameter_or_context_truncation_count=sum(
            item['nearby_source']['truncated'] or any(p['truncated'] for p in item['parameters']) for item in calls),
        calls_by_file=[{'file': name, 'calls': count} for name, count in counts.most_common()],
        literal_output_widths=dict(sorted(Counter(str(item['width_constants'].get('obits'))
            for item in calls if item.get('parse_status') == 'parsed').items())),
        files={'calls': 'calls.json', 'cpp_manifest': 'cpp_manifest.json', 'scan': 'scan_receipt.json',
               'selected_manifest': 'selected_source_manifest.json'},
        selected_source_bytes=selected_bytes, selected_source_limit_bytes=MAX_SOURCE_BYTES,
        selected_source=selected, selection_skipped=selection_skipped,
        required_source_complete=not required_missing, required_source_missing=required_missing,
        original_sv=sv_identity,
        sv_mapping_status='Pending direct review of original SV and generated callers; no inferred mapping.',
        limits=dict(files=MAX_FILES, scan_bytes=MAX_SCAN_BYTES, calls=MAX_CALLS,
                    single_file_parse_bytes=MAX_FILE_BYTES, text_evidence_characters=MAX_EVIDENCE_CHARACTERS,
                    parameter_characters=MAX_PARAMETERS, nearby_source_characters=MAX_TEXT),
        limitations=['Syntactic conditions are not runtime activity or dominance evidence.',
                     'Signal identifiers preserve generated spelling; original SV scope/width needs direct source confirmation.',
                     'Only plain integer width literals are evaluated; expressions and unsupported syntax stay unresolved.',
                     'Identical helper names, compiler clones and multiple callers cannot be disambiguated without ELF evidence.'])
    (output / 'inventory_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary
