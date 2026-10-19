"""Pinned data-only 4VLT generation. No native execution or ABI/runtime claim."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Python -I -S -B is required.')
if __name__ == '__main__':
    raise SystemExit('Use the pinned same-buffer entry in ENTRY.json.')
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat

SV_PIN = (76366612, '2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61')
BRIDGE = 'development_snapshots/canonical_host_bridge_source_20261018/'
PROFILE = 'candidates/qwen2_resident_matrix/production_qk16_rebase/seed_dma_provider_checkpoint/full_profile/'
PINS = {
    BRIDGE + 'generated_binding.hpp': (164037, '84b1e85078f9864610a1dbee1c68a7ff40e4ba847dd239f54fd079151e066afe'),
    BRIDGE + 'n0_fields.hpp': (9848, '62d991f0d09da96ac9af406c3469113a64384aa2e426234658467439499a40c7'),
    'development_snapshots/canonical_host93_same_sv_source_20261018/checker/CONTRACT.json': (20536, 'c3ec7c4753df9100a90bc3963843b23c153c2335be06035a5cac4f6f27018d0d'),
    PROFILE + 'structural_hints.vlt': (591, '476e42bac40bd8eb43423cb898339300be4c1ff88dfc77ef9ae5d539cc318aca'),
    PROFILE + 'WARNINGS.json': (12084, '95b34f5ad0712b1582082647ed1e8516edacac4805c02ae215c11aa71ba4b706'),
}
IDMA_META = {
    'SHA256SUMS.json': (104165, 'a699b8074b8099e00859d5174c0a5fb6b5a171a28cad30bab8dd96226dc67b19'),
    'SOURCE_CLOSURE.json': (73326, 'a3161f06be82894bbab48e3efae325e868385ea204d5f2aab47978ce9bd10aa1'),
}
PATHS = {
    '': 'HostBlockTop', 'cmd': 'HostBlockCommands',
    'dma': 'RetainedIdmaWeightBurstAdapter', 'hub': 'SharedMemoryArbiter',
    'hub.arb': 'RRArbiter', 'owner': 'QwenOwnerKernel',
    'owner.core': 'Qwen2ContinuousBlock', 'owner.core.writeback': 'BlockWritebackFence',
    'owner.qkvRouter': 'Public21QkvReductionRouter',
    'owner.resident': 'FfnResidentCoordinator', 'owner.resident.bridge': 'FfnTileSiluBridge',
    'owner.silu': 'ScheduledSiluOwner', 'owner.silu.dut': 'VectorSiluOwner',
    'owner.silu.dut.vector': 'SiluVectorUnit', 'owner.matrix': 'MatrixPipelineService',
}
MATRIX = {'steps': 64, 'wideSteps': 64, 'stalls': 64, 'group_sliceMask': 8,
          'io_port_step_valid': 1, 'io_port_step_ready': 1, 'legalStep': 1,
          'state': 3, 'poison': 1}
IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
WARNING_PREFIX = 'idma_source_export_attempt_v8_20261017/source/idma_export/'
CONFIG_NAMES = ('hierarchy.vlt', 'readonly.vlt', 'dma_hints.vlt', 'precision_warnings.vlt')
LIMITS = {'wall_seconds': 60, 'cpu_seconds': 45, 'address_space_bytes': 768 * 1024**2,
          'file_bytes': 512 * 1024, 'output_tree_bytes': 1024 * 1024}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def path_parts(value):
    need(type(value) is str and 0 < len(value) <= 4096 and not value.startswith('/'), 'relative path required')
    need(not any(c in value for c in ('\\', '\x00', '"', '*', '?', '[', ']', '\n', '\r')), 'unsafe path character')
    parts = value.split('/')
    need(all(p not in ('', '.', '..') and len(p) <= 255 for p in parts), 'unsafe path component')
    return parts


def absolute(path):
    value = os.fspath(path)
    need(value.startswith('/') and value != '/', 'absolute non-root path required')
    path_parts(value[1:])
    return Path(value)


def parent_fd(path):
    parts = path_parts(str(absolute(path))[1:])
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def identity(st):
    return tuple(getattr(st, 'st_' + name) for name in ('dev', 'ino', 'mode', 'size', 'mtime_ns', 'ctime_ns'))


def checked_read(path, digest, size=None, cap=80 * 1024**2):
    need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None, 'invalid expected digest')
    parent, name = parent_fd(path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap, 'input type/size bound')
            need(size is None or (type(size) is int and before.st_size == size), 'input exact size')
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(before.st_size + 1)
            need(len(raw) == before.st_size and sha(raw) == digest, 'input size/SHA mismatch')
            need(identity(before) == identity(os.fstat(fd)) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'input changed during read')
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def add_field(fields, origins, module, name, width, origin):
    need(module in PATHS.values() and re.fullmatch(IDENT, name) is not None, 'unknown module/field identifier')
    need(type(width) is int and 1 <= width <= 512, 'field width bound')
    key = (module, name)
    need(key not in fields or fields[key] == width, 'overlapping field width disagreement')
    fields[key] = width
    origins.setdefault(key, set()).add(origin)


def member_parts(member):
    parts = member.split('__DOT__')
    need(len(parts) >= 2 and parts[0] == 'HostBlockTop' and all(re.fullmatch(IDENT, p) for p in parts), 'unknown member form')
    logical = '.'.join(parts[1:-1])
    need(logical in PATHS, 'unknown logical path')
    return PATHS[logical], parts[-1], '__'.join(parts[:-1])


def derive_fields(binding, n0, contract):
    fields, origins = {}, {}
    text = binding.decode('utf-8')
    pattern = re.compile(r'registered\(s\.__Vscopep_(' + IDENT + r'),"(' + IDENT + r')",&r\.(' + IDENT + r'),(\d+),VLVT_(UINT8|UINT16|UINT32),syms_\);')
    rows = pattern.findall(text)
    need(len(rows) == 468 and text.count('registered(s.') == 468, 'binding row/unknown-extra count')
    need(len({r[2] for r in rows}) == 468, 'binding duplicate member')
    for scope, name, member, width, kind in rows:
        module, actual_name, actual_scope = member_parts(member)
        width = int(width)
        need((name, scope) == (actual_name, actual_scope), 'binding scope/member disagreement')
        need(kind == ('UINT8' if width <= 8 else 'UINT16' if width <= 16 else 'UINT32'), 'binding type/width mismatch')
        add_field(fields, origins, module, name, width, 'binding')
    text = n0.decode('utf-8')
    scalar = re.findall(r'scalar<(\d+)>\(r\.(' + IDENT + r')\)', text)
    wide = re.findall(r'words\(r\.(' + IDENT + r')\)', text)
    need(len(scalar) == 78 and len(wide) == 3 and text.count('(r.HostBlockTop') == 81, 'N0 row/unknown-extra count')
    need(len({m for w, m in scalar} | set(wide)) == 81, 'N0 duplicate member')
    for width, member in scalar + [('512', m) for m in wide]:
        module, name, unused_scope = member_parts(member)
        add_field(fields, origins, module, name, int(width), 'n0')
    need(len(fields) == 546, 'binding/N0 union count')
    taps = contract.get('TAPS')
    need(type(taps) is dict and set(taps) == {'FfnTileSiluBridge', 'Qwen2ContinuousBlock', 'SiluVectorUnit', 'VectorSiluOwner'}, 'tap module set')
    need(all(type(t) is dict for t in taps.values()) and sum(map(len, taps.values())) == 75, 'tap field count')
    for module, entries in taps.items():
        for name, width in entries.items():
            need(name.startswith('canonical'), 'unknown extra tap')
            add_field(fields, origins, module, name, width, 'same_sv_contract')
    need(len(fields) == 601, 'tap union count')
    for name, width in MATRIX.items():
        add_field(fields, origins, 'MatrixPipelineService', name, width, 'matrix_nine')
    need(len(fields) == 610, 'readonly field set must be exactly 610')
    return fields, origins


def clean_lines(raw):
    # Fixed emitted format only. Comments cannot create declarations; strings are
    # replaced by one opaque token and are never searched for declarations.
    block = False
    for number, raw_line in enumerate(io.BytesIO(raw), 1):
        need(len(raw_line) <= 65536, 'SV line length bound')
        line = raw_line.decode('utf-8').rstrip('\r\n')
        if not block and '"' not in line and '/*' not in line:
            yield number, line.split('//', 1)[0].strip()
            continue
        out, i = [], 0
        while i < len(line):
            if block:
                end = line.find('*/', i)
                if end < 0:
                    break
                block, i = False, end + 2
                out.append(' ')
            elif line.startswith('//', i):
                break
            elif line.startswith('/*', i):
                block, i = True, i + 2
                out.append(' ')
            elif line[i] == '"':
                out.append('"OPAQUE"')
                i += 1
                while i < len(line) and line[i] != '"':
                    i += 2 if line[i] == '\\' else 1
                need(i < len(line), 'unsupported multiline SV string')
                i += 1
            else:
                out.append(line[i])
                i += 1
        yield number, ''.join(out).strip()
    need(not block, 'unterminated SV block comment')


def expected_edges(paths):
    result = set()
    for logical, module in paths.items():
        if logical:
            parent, separator, name = logical.rpartition('.')
            result.add((paths[parent], name, module))
    return result


def scan_declarations(raw, fields, paths):
    # Deliberately not a general SV parser. Admit exactly emitted ANSI ports
    # with one declarator per line, inherited ANSI widths, and wire/reg scalars
    # or descending numeric [N:0] vectors; initialized wires may continue.
    modules = set(paths.values())
    need(set(m for m, n in fields) <= modules, 'field module outside paths')
    wanted_edges = expected_edges(paths)
    seen_modules, seen_fields, seen_edges = set(), {}, set()
    current, in_ports, port_width = None, False, None
    for line_no, line in clean_lines(raw):
        if not line:
            continue
        start = re.fullmatch(r'module (' + IDENT + r')\(', line)
        if start:
            need(current is None, 'nested module')
            current = start[1]
            in_ports, port_width = True, None
            if current in modules:
                need(current not in seen_modules, 'duplicate selected module')
                seen_modules.add(current)
            continue
        if line == 'endmodule':
            need(current is not None and (current not in modules or not in_ports), 'module boundary')
            current = None
            continue
        if current not in modules:
            continue
        if in_ports:
            if line == ');':
                in_ports = False
                continue
            declaration = re.fullmatch(r'(input|output)\s+(?:\[(\d+):0\]\s+)?(' + IDENT + r')(,?)', line)
            continuation = re.fullmatch(r'(' + IDENT + r')(,?)', line)
            need(declaration is not None or (continuation is not None and port_width is not None), 'unsupported ANSI declaration')
            if declaration:
                name = declaration[3]
                port_width = int(declaration[2]) + 1 if declaration[2] else 1
            else:
                name = continuation[1]
            key = (current, name)
            if key in fields:
                need(key not in seen_fields, 'duplicate requested declaration')
                need(port_width == fields[key], 'requested declaration width mismatch')
                seen_fields[key] = {'line': line_no, 'width': port_width}
            continue
        declaration = re.match(r'(wire|reg)\s+(?:\[(\d+):0\]\s+)?(' + IDENT + r')\b(.*)', line)
        if declaration:
            name, tail = declaration[3], declaration[4]
            key = (current, name)
            if key in fields:
                need(re.fullmatch(r'\s*;\s*', tail) is not None or re.match(r'\s*=\s*', tail) is not None, 'unsupported requested declaration shape')
                width = int(declaration[2]) + 1 if declaration[2] else 1
                need(key not in seen_fields, 'duplicate requested declaration')
                need(width == fields[key], 'requested declaration width mismatch')
                seen_fields[key] = {'line': line_no, 'width': width}
        instance = re.fullmatch(r'(' + IDENT + r')\s+(' + IDENT + r')\s+\(', line)
        if instance and instance[1] in modules:
            edge = (current, instance[2], instance[1])
            need(edge in wanted_edges and edge not in seen_edges, 'unknown extra or duplicate selected hierarchy edge')
            seen_edges.add(edge)
    need(current is None, 'unterminated module')
    need(seen_modules == modules, 'missing selected module')
    need(seen_edges == wanted_edges, 'missing selected hierarchy edge')
    missing = sorted(set(fields) - set(seen_fields))
    need(not missing, 'missing requested declarations: ' + repr(missing[:5]))
    return seen_fields


def warning_rows(warnings, sums, closure):
    need(type(warnings) is dict and warnings.get('counts') == {'PINMISSING': 1, 'WIDTHEXPAND': 19, 'WIDTHTRUNC': 4}, 'warning inventory counts')
    entries = warnings.get('warnings')
    admitted = closure.get('admitted_input_hashes')
    need(type(sums) is dict and type(admitted) is dict and type(entries) is list and len(entries) == 24, 'warning/manifest shape')
    rows, seen_rules = set(), {}
    for entry in entries:
        need(type(entry) is dict and entry.get('rule') in {'PINMISSING', 'WIDTHEXPAND', 'WIDTHTRUNC'}, 'unknown extra warning rule')
        rule = entry['rule']
        seen_rules[rule] = seen_rules.get(rule, 0) + 1
        original = entry.get('file')
        need(type(original) is str and original.startswith(WARNING_PREFIX), 'warning file prefix')
        relative = original[len(WARNING_PREFIX):]
        path_parts(relative)
        digest, line = entry.get('source_sha256'), entry.get('line')
        need(type(line) is int and 1 <= line <= 100000, 'warning line bounds')
        need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None, 'warning source digest')
        need(sums.get(relative) == admitted.get(relative) == digest, 'warning sourceSHA disagrees with iDMA manifests')
        if rule.startswith('WIDTH'):
            rows.add((relative, line, rule, digest))
    need(seen_rules == warnings['counts'] and len(rows) == 21, 'precision WIDTH rule/file/line count')
    return sorted(rows)


def render(fields, hints, rows, idma_root):
    need(len(fields) == 610 and len(rows) == 21, 'render exact item counts')
    readonly = ['`verilator_config']
    for (module, name), width in sorted(fields.items()):
        need(re.fullmatch(IDENT, module) and re.fullmatch(IDENT, name) and type(width) is int and 1 <= width <= 512, 'invalid output field')
        readonly.append('public_flat_rd -module "' + module + '" -var "' + name + '"')
    precision = ['`verilator_config']
    root = absolute(idma_root)
    for relative, line, rule, digest in rows:
        path_parts(relative)
        need(rule in ('WIDTHEXPAND', 'WIDTHTRUNC') and type(line) is int and 1 <= line <= 100000, 'invalid output warning')
        precision.append('lint_off -rule ' + rule + ' -file "' + str(root / relative) + '" -lines ' + str(line))
    need(len(set(readonly)) == 611 and len(set(precision)) == 22, 'duplicate config directive')
    return {
        'hierarchy.vlt': b'`verilator_config\nhier_block -module "qwen2_matrix_command_endpoint"\n',
        'readonly.vlt': ('\n'.join(readonly) + '\n').encode(),
        'dma_hints.vlt': hints,
        'precision_warnings.vlt': ('\n'.join(precision) + '\n').encode(),
    }


def write_fresh(out, files):
    need(set(files) == set(CONFIG_NAMES) | {'MANIFEST.json'}, 'output file set')
    need(sum(map(len, files.values())) <= LIMITS['output_tree_bytes'] and all(len(raw) <= LIMITS['file_bytes'] for raw in files.values()), 'output size bound')
    parent, name = parent_fd(out)
    try:
        os.mkdir(name, 0o700, dir_fd=parent)  # EEXIST always fails, even an empty directory.
        root = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            for filename in CONFIG_NAMES + ('MANIFEST.json',):
                raw = files[filename]
                fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                verify = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root)
                with os.fdopen(verify, 'rb') as stream:
                    observed = stream.read(len(raw) + 1)
                    need(observed == raw and sha(observed) == sha(raw), 'output readback mismatch')
            need(set(os.listdir(root)) == set(files), 'output tree changed')
            os.fsync(root)
        finally:
            os.close(root)
    finally:
        os.close(parent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'sv', 'idma-root', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    repo, sv, idma, out = map(absolute, (args.repo, args.sv, args.idma_root, args.out))
    for source in (repo, idma, sv, Path(__file__).absolute().parent):
        need(out != source and source not in out.parents and out not in source.parents, 'output overlaps input/source root')
    out_parent, out_name = parent_fd(out)
    try:
        try:
            os.stat(out_name, dir_fd=out_parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError('fresh output root already exists')
    finally:
        os.close(out_parent)
    signal.alarm(LIMITS['wall_seconds'])
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS['cpu_seconds'], LIMITS['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS['address_space_bytes'], LIMITS['address_space_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['file_bytes'], LIMITS['file_bytes']))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    inputs = {p: checked_read(repo / p, digest, size) for p, (size, digest) in PINS.items()}
    contract_path = 'development_snapshots/canonical_host93_same_sv_source_20261018/checker/CONTRACT.json'
    fields, origins = derive_fields(inputs[BRIDGE + 'generated_binding.hpp'], inputs[BRIDGE + 'n0_fields.hpp'], unique_json(inputs[contract_path]))
    sv_raw = checked_read(sv, SV_PIN[1], SV_PIN[0])
    declarations = scan_declarations(sv_raw, fields, PATHS)
    del sv_raw
    meta = {p: unique_json(checked_read(idma / p, digest, size)) for p, (size, digest) in IDMA_META.items()}
    rows = warning_rows(unique_json(inputs[PROFILE + 'WARNINGS.json']), meta['SHA256SUMS.json'], meta['SOURCE_CLOSURE.json'])
    source_records = {}
    for relative, line, rule, digest in rows:
        if relative not in source_records:
            raw = checked_read(idma / relative, digest, cap=2 * 1024**2)
            source_records[relative] = {'bytes': len(raw), 'sha256': digest, 'lines': len(raw.splitlines())}
        need(line <= source_records[relative]['lines'], 'warning line exceeds verified source')
    files = render(fields, inputs[PROFILE + 'structural_hints.vlt'], rows, idma)
    manifest = {
        'schema': 1, 'status': 'CONFIGURATION_GENERATED_NOT_NATIVE_OR_RUNTIME_QUALIFIED',
        'source_identity': globals().get('__verified_source_pin__'),
        'sv': {'bytes': SV_PIN[0], 'sha256': SV_PIN[1]},
        'repo_source_inputs': {p: {'bytes': v[0], 'sha256': v[1]} for p, v in PINS.items()},
        'idma_manifest_inputs': {p: {'bytes': v[0], 'sha256': v[1]} for p, v in IDMA_META.items()},
        'idma_warning_sources': source_records,
        'readonly_count': 610, 'readonly_source_counts': {'binding_unique': 468, 'n0_unique': 81, 'contract_taps': 75, 'matrix_fields': 9},
        'readonly_fields': [{'module': m, 'signal': n, 'width': w, 'declaration_line': declarations[m, n]['line'], 'origins': sorted(origins[m, n])} for (m, n), w in sorted(fields.items())],
        'hierarchy': {'hier_block': ['qwen2_matrix_command_endpoint'], 'verified_paths': PATHS},
        'precision_warning_directives': 21,
        'dma_hints': {'original_bytes': True, 'isolate_assignments_count': 5, 'split_var_count': 3, 'optimization_claim': False, 'note': 'The five isolate_assignments directives have no effect in 5.053. split_var grammar support alone proves no optimization.'},
        'boundaries': {'native_executed': False, 'large_sv_full_checker_executed': False, 'abi_verified': False, 'eight_handles_verified': False, 'runtime_verified': False, 'production_modified': False},
        'files': {p: {'bytes': len(raw), 'sha256': sha(raw)} for p, raw in files.items()},
    }
    need(manifest['source_identity'] is not None, 'verified same-buffer loader identity required')
    files['MANIFEST.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    write_fresh(out, files)
    print(json.dumps({'status': manifest['status'], 'out': str(out), 'readonly': 610, 'precision_warnings': 21, 'files': manifest['files']}, sort_keys=True))
    return 0
