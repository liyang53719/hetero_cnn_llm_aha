"""Exact read-only nonhierarchical probes; no compiler/simulator invocation.

16 MiB is an engineering input bound, not a claim about future generated size.
Synthetic header tests do not establish actual full-Top generated member names.
"""
import argparse
import hashlib
import json
import pathlib
import re

SCHEMA_SHA = '75088081cf6c3425eba9af3b44c78244f8c62697b4390f992ad63e21f16c7de4'
MODULE_PATHS = {'HostBlockTopV4': '', 'QwenOwnerKernel': 'owner', 'MatrixPipelineService': 'owner.matrix', 'HostRuntimeOwnerGuardV5': 'runtimeGuard'}
DENY = {'TransposedDenseDownOwner', 'bf16_context_lane_cluster16_rev8b_b_candidate', 'qwen2_matrix_command_endpoint'}
ROOT_TYPE = 'VHostBlockTopV4___024root'
HEADER_CAP = 16 << 20
IDENT = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')
P = pathlib.Path

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(path, exists=True):
    path = P(path)
    need(path.is_absolute() and str(path) == str(path.resolve()), 'canonical absolute path required')
    for part in (path, *path.parents):
        need(not part.is_symlink(), 'symlink forbidden')
    if exists:
        need(path.is_file(), 'regular file required')
    else:
        need(not path.exists() and path.parent.is_dir(), 'fresh output with existing parent required')
    return path

def read(path, cap):
    path = canonical(path)
    before = path.stat()
    need(0 < before.st_size <= cap, 'bounded nonempty input')
    raw = path.read_bytes()
    after = path.stat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'input changed')
    need(len(raw) == before.st_size and b'\0' not in raw, 'input bytes')
    return raw

def pin(path, raw, text=False):
    result = dict(path=str(path), bytes=len(raw), sha256=digest(raw))
    if text:
        result['text'] = raw.decode('utf-8')
    return result

def load_schema(path):
    raw = read(path, 256 << 10)
    need(digest(raw) == SCHEMA_SHA, 'fixed schema bytes required')
    doc = json.loads(raw)
    need(doc['schema'] == 'FIXED_NONHIER_PRETHROW_SCHEMA_V1' and doc['root_module'] == 'HostBlockTopV4', 'schema identity')
    need(set(doc['allowed_modules']) == set(MODULE_PATHS) and set(doc['deny_hier_modules']) == DENY, 'exact module domains')
    need(doc['extra_eval_or_clock'] is False and doc['read_hier_child_internals'] is False and doc['payload_data_or_addresses'] is False, 'read-only scope')
    rows = doc['signals']
    need(len(rows) == doc['signal_count'] == 114 and sum(r['width_bits'] for r in rows) == doc['total_scalar_bits'] == 327, 'fixed scalar inventory')
    keys = [r['symbol_key'] for r in rows]
    pairs = [(r['module'], r['sv_var']) for r in rows]
    need(len(set(keys)) == len(keys) and len(set(pairs)) == len(pairs), 'unique symbols')
    for r in rows:
        need(r['module'] in MODULE_PATHS and r['module'] not in DENY and r['instance_path'] == MODULE_PATHS[r['module']], 'exact nonhier instance')
        need(IDENT.fullmatch(r['sv_var']) and IDENT.fullmatch(r['symbol_key']) and r['sv_var'] == r['signal'], 'plain exact identifier')
        need(type(r['width_bits']) is int and 1 <= r['width_bits'] <= 64, 'scalar width')
        need(all(k in keys for k in r['validity']['all_true_symbol_keys']), 'qualification references')
    return doc, raw

def config_bytes(doc):
    return ('`verilator_config\n' + ''.join('public_flat_rd -module "' + r['module'] + '" -var "' + r['sv_var'] + '"\n' for r in doc['signals'])).encode('ascii')

def write_config(schema_path, output):
    doc, _ = load_schema(schema_path)
    output = canonical(output, False)
    raw = config_bytes(doc)
    with output.open('xb') as stream:
        stream.write(raw)
    return pin(output, raw, True)

def mask_comments(text):
    """Mask comments/strings, retaining only exact numeric width comments.
    No regex can make a declaration hidden inside a comment into live code.
    """
    out = []; i = 0
    while i < len(text):
        if text.startswith('//', i):
            end = text.find('\n', i)
            if end < 0: end = len(text)
            out.append(' ' * (end-i)); i = end
        elif text.startswith('/*', i):
            end = text.find('*/', i+2)
            need(end >= 0, 'unterminated header comment')
            token = text[i:end+2]
            out.append(token if re.fullmatch(r'/\*\d+:\d+\*/', token) else ''.join('\n' if c == '\n' else ' ' for c in token))
            i = end+2
        elif text[i] in ('"', "'"):
            quote = text[i]; start = i; i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == '\\': i += 1
                i += 1
            need(i < len(text), 'unterminated header literal')
            i += 1; out.append(' ' * (i-start))
        else:
            out.append(text[i]); i += 1
    return ''.join(out)

def expected_member(row):
    if row['module'] == 'HostBlockTopV4' and row['sv_var'] == 'io_resetRequired':
        return 'io_resetRequired', True
    parts = ['HostBlockTopV4'] + ([*row['instance_path'].split('.')] if row['instance_path'] else []) + [row['sv_var']]
    return '__DOT__'.join(parts), False

def match_header(doc, raw):
    text = raw.decode('ascii')
    need('\r' not in text, 'LF ASCII header required')
    # Only ordinary generated include guards/includes. No hidden #if 0 branches.
    directives = [x.strip() for x in text.splitlines() if x.lstrip().startswith('#')]
    guard = 'VERILATED_VHOSTBLOCKTOPV4___024ROOT_H_'
    need(sum(x == '#ifndef ' + guard for x in directives) == 1 and
         sum(x == '#define ' + guard + '  // guard' or x == '#define ' + guard for x in directives) == 1 and
         sum(bool(re.fullmatch(r'#endif(?:\s*//[^\n]*)?', x)) for x in directives) == 1, 'exact root header guard')
    for d in directives:
        need(d in ('#ifndef '+guard, '#define '+guard, '#define '+guard+'  // guard') or re.fullmatch(r'#endif(?:\s*//[^\n]*)?', d) or d.startswith('#include '), 'unexpected preprocessor branch')
        if d.startswith('#include '): need(re.fullmatch(r'#include "[A-Za-z0-9_.]+"', d), 'plain generated include')
    cleaned = mask_comments(text)
    declaration = 'class alignas(VL_CACHE_LINE_BYTES) ' + ROOT_TYPE + ' final : public VerilatedModule {'
    need(cleaned.count(declaration) == 1, 'unique actual root class')
    body = cleaned.split(declaration, 1)[1]
    need(body.count('\n};') == 1, 'one generated class closure')
    body = body.split('\n};', 1)[0]
    mappings = []
    for row in doc['signals']:
        name, port = expected_member(row)
        need(len(re.findall(r'\b' + re.escape(name) + r'\b', body)) == 1, 'missing or ambiguous exact member')
        if port:
            regex = r'^\s*VL_OUT8\(' + re.escape(name) + r',(\d+),(\d+)\);\s*$'
            matches = list(re.finditer(regex, body, re.M))
            need(len(matches) == 1 and int(matches[0][1]) == row['width_bits']-1 and int(matches[0][2]) == 0, 'exact top output width')
            declaration_text = matches[0][0].strip()
        else:
            regex = r'^\s*(CData|SData|IData|QData)/\*(\d+):(\d+)\*/\s+' + re.escape(name) + r';\s*$'
            matches = list(re.finditer(regex, body, re.M))
            need(len(matches) == 1, 'exact scalar declaration required')
            m = matches[0]; width = row['width_bits']
            expected_type = 'CData' if width <= 8 else 'SData' if width <= 16 else 'IData' if width <= 32 else 'QData'
            need(m[1] == expected_type and int(m[2]) == width-1 and int(m[3]) == 0, 'exact scalar storage/width')
            declaration_text = m[0].strip()
        mappings.append(dict(symbol_key=row['symbol_key'], module=row['module'], instance_path=row['instance_path'], sv_var=row['sv_var'], width_bits=row['width_bits'], member=name, declaration=declaration_text))
    return mappings

def accessor_bytes(mappings):
    lines = ['#pragma once', '#include <array>', '#include <cstddef>', '#include <cstdint>', '#include "VHostBlockTopV4.h"', '#include "VHostBlockTopV4___024root.h"', 'namespace readonly_first_fault_access {', 'inline constexpr std::size_t field_count = 114;', 'inline constexpr char schema_sha256[] = "'+SCHEMA_SHA+'";', 'using Values = std::array<std::uint64_t, field_count>;', 'inline Values capture(const VHostBlockTopV4& dut) noexcept {', '  const VHostBlockTopV4___024root* const root = dut.rootp;', '  return Values{{']
    lines.extend('    static_cast<std::uint64_t>(root->'+m['member']+'),' for m in mappings)
    lines += ['  }};', '}', '}  // namespace readonly_first_fault_access', '']
    return '\n'.join(lines).encode('ascii')

def generate(schema_path, config_path, root_header, accessor_path, evidence_path):
    doc, schema_raw = load_schema(schema_path)
    config_raw = read(config_path, 64 << 10)
    need(config_raw == config_bytes(doc), 'exact read-only config bytes')
    root_raw = read(root_header, HEADER_CAP)
    need(P(root_header).name == ROOT_TYPE+'.h', 'exact generated header basename')
    mappings = match_header(doc, root_raw)
    accessor_path = canonical(accessor_path, False); evidence_path = canonical(evidence_path, False)
    need(accessor_path != evidence_path and accessor_path.name == 'readonly_first_fault_access.hpp', 'distinct fixed accessor output')
    access_raw = accessor_bytes(mappings)
    evidence = dict(schema='ACTUAL_NONHIER_READONLY_ACCESSOR_EVIDENCE_V1', scope='READ_ONLY_GENERATED_HEADER_DECLARATIONS_NOT_NUMERICAL_ACCEPTANCE', schema_input=pin(schema_path, schema_raw), config=pin(config_path, config_raw, True), root_header=pin(root_header, root_raw), accessor=pin(accessor_path, access_raw, True), mappings=mappings, field_count=114, reads_hier_child_internals=False, extra_eval_or_clock=False)
    encoded = (json.dumps(evidence, indent=2)+'\n').encode()
    need(len(encoded) <= 128 << 10, 'bounded complete accessor evidence')
    with accessor_path.open('xb') as f: f.write(access_raw)
    with evidence_path.open('xb') as f: f.write(encoded)
    return evidence

def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('config'); c.add_argument('--schema', type=P, required=True); c.add_argument('--output', type=P, required=True)
    g = sub.add_parser('generate')
    for name in ('schema', 'config', 'root-header', 'accessor', 'evidence'): g.add_argument('--'+name, type=P, required=True)
    a = p.parse_args()
    if a.command == 'config': write_config(a.schema, a.output)
    else: generate(a.schema, a.config, a.root_header, a.accessor, a.evidence)
    print('READONLY_PROBE_SOURCE_GENERATION_COMPLETE_NOT_EXECUTION_ACCEPTANCE')

if __name__ == '__main__': main()
