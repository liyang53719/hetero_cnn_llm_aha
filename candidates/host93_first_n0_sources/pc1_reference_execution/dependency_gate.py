"""Finite compiler dependency gate; only static reads, no discovery or execution."""
import ast
from pathlib import Path
import struct

LIBRARIES = ('ld-linux-x86-64.so.2', 'libc.so.6', 'libm.so.6', 'libmvec.so.1',
             'libstdc++.so.6', 'libgcc_s.so.1', 'libmpfr.so.6', 'libgmp.so.10',
             'libisl.so.23', 'libmpc.so.3', 'libz.so.1', 'libzstd.so.1',
             'libbfd-2.44-system.so', 'libctf.so.0', 'libjansson.so.4', 'libsframe.so.1')


def elf_reader(g, repo):
    name = g.ELF_SOURCE
    raw = g.checked(Path(repo) / name, g.SOURCE_FILES[name])
    lines = raw.splitlines(keepends=True)
    nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'elf_dependencies']
    g.need(len(nodes) == 1, 'one fixed ELF reader')
    n = nodes[0]
    original = b''.join(lines[n.lineno-1:n.end_lineno]) + b'\n'
    # Fixed GCC14 cc1plus: 36,389,344 bytes and DT_STRSZ=1,489,147.
    # Two numeric bounds only; all segment, soname, interpreter and RPATH checks stay.
    replacements = ((b'len(raw)<=32*MIB', b'len(raw)<=64*MIB'),
                    (b'0<stringsz<=MIB', b'0<stringsz<=2*MIB'))
    projected = original
    for old, new in replacements:
        g.need(projected.count(old) == 1 and new not in projected, 'one fixed cap anchor')
        projected = projected.replace(old, new)
    inverse = projected
    for old, new in reversed(replacements):
        inverse = inverse.replace(new, old)
    g.need(inverse == original, 'exact inverse ELF cap projection')
    ns = {'require': g.need, 'struct': struct, 'MIB': 1024**2,
          'INTERPRETER': '/lib64/ld-linux-x86-64.so.2', 'LIBRARIES': LIBRARIES}
    exec(compile(projected, 'fixed_pc1_elf_reader', 'exec', dont_inherit=True), ns)
    return ns['elf_dependencies'], {'original': g.pin(original), 'projected': g.pin(projected),
                                  'cap_only_substitutions': 2, 'inverse_exact': True}


def verify(g, observer, mount, repo, catalog):
    g.need(catalog['schema'] == 'PC1_FIXED_COMPILER_DEPENDENCIES_V1' and
           10 <= len(catalog['files']) <= 40, 'fixed finite dependency catalog')
    rows = catalog['files']
    evidence = observer.userns_evidence(g, rows)
    g.need(evidence['euid'] == 1000 and evidence['egid'] == 1000 and evidence['groups'] == [] and
           evidence['uid_map'].split() == ['1000', '0', '1'] and
           evidence['gid_map'].split() == ['1000', '0', '1'], 'fixed local namespace')
    reader, projection = elf_reader(g, repo)
    observations = {}
    for path, expected in rows.items():
        p = Path(path)
        g.need(str(p).startswith('/usr/') and str(p.resolve(strict=True)) == path, 'fixed dependency realpath')
        item = evidence['observed'][path]
        g.need({'ro', 'nosuid', 'nodev'} <= set(item['covering_mount']['options']), 'fixed readonly mount')
        for entry in item['chain'].values():
            g.need(not int(entry['mode'], 8) & 0o022 and entry['writable_by_current_process'] is False,
                   'fixed protected ancestors')
        pin = {k: expected[k] for k in ('bytes', 'sha256', 'mode')}
        observations[path] = mount.descriptor_snapshot(g, p, pin)
        if expected['kind'] == 'dynamic_elf':
            raw = g.checked(p, {k: expected[k] for k in ('bytes', 'sha256')}, 64 * g.MIB, fixed_leaf=p.name)
            meta = reader(raw)
            g.need(meta == expected['elf'], 'fixed dependency ELF changed')
            g.need(set(meta['needed']) <= set(catalog['libraries']), 'closed dependency sonames')
    for invoked, resolved in catalog['resolutions'].items():
        g.need(str(Path(invoked).resolve(strict=True)) == resolved and resolved in rows,
               'fixed compiler/library resolution')
    for name, path in catalog['libraries'].items():
        g.need(name in LIBRARIES and path in rows and rows[path]['kind'] == 'dynamic_elf',
               'fixed dynamic library mapping')
    g.need(set(catalog['programs']) == {'g++', 'cc1plus', 'collect2', 'as', 'ld'}, 'five compiler programs')
    for path in catalog['programs'].values():
        g.need(path in rows and int(rows[path]['mode'], 8) & 0o111, 'fixed executable')
    return {'files': observations, 'elf_projection': projection,
            'host_uid0_inferred': False, 'official_provenance_claimed': False}


def check_binary(g, repo, catalog, path):
    p = Path(path)
    g.need(p.is_absolute() and p.resolve(strict=True) == p and p.is_file() and
           0 < p.stat().st_size <= 16 * g.MIB, 'fixed produced binary')
    raw = p.read_bytes()
    g.need(len(raw) >= 64 and int.from_bytes(raw[16:18], 'little') == 3,
           'fixed default PIE startup-object profile')
    pin = g.pin(raw)
    g.need(g.checked(p, pin, 16 * g.MIB, fixed_leaf=p.name) == raw, 'same produced binary')
    reader, projection = elf_reader(g, repo)
    meta = reader(raw)
    g.need(meta['interpreter'] == '/lib64/ld-linux-x86-64.so.2' and
           set(meta['needed']) <= set(catalog['libraries']), 'produced ELF dependency closure')
    return {'identity': pin, 'elf': meta, 'elf_projection': projection}
