"""Build an exact cold-import config using only stdlib and static ELF reads."""
from __future__ import annotations
import argparse
import base64
import csv
import email.parser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLASS_FILES, GATE_FILES, LIMITS, UPSTREAM, class_static_identity,
                         file_id, need, write_new, loopback_probe_policy, read_checked)


def inventory(root, exclude=()):
    files = {}
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in exclude)
        for name in sorted(names):
            p = Path(parent) / name
            if not p.is_file():
                continue
            canonical = p.resolve(strict=True)
            need(canonical.is_relative_to(Path(root).resolve()), 'root-escaping file symlink: ' + str(p))
            files[str(canonical)] = file_id(p)
    return files


def verify_runtime(root, baseline, manifest):
    result = []
    for pin in baseline['distributions']:
        choices = []
        for d in root.glob('*.dist-info'):
            data = email.parser.Parser().parsestr((d / 'METADATA').read_text())
            if data['Name'].lower().replace('-', '_') == pin['name'].lower().replace('-', '_') and data['Version'] == pin['version']:
                choices.append(d)
        need(len(choices) == 1, 'exact fixed distribution missing: ' + pin['name'])
        d = choices[0]
        need(file_id(d / 'METADATA') == pin['metadata'], 'fixed METADATA changed: ' + pin['name'])
        need(file_id(d / 'RECORD') == pin['record'], 'fixed RECORD changed: ' + pin['name'])
        checked = 0
        excluded_cli = []
        with (d / 'RECORD').open(newline='') as f:
            for relative, digest, size in csv.reader(f):
                p = (root / relative).resolve()
                if not p.is_relative_to(root):
                    need(relative in pin['outside_runtime'], 'new RECORD escape from fixed runtime')
                    excluded_cli.append(relative)
                    continue
                p = p.resolve(strict=True)
                need(str(p) in manifest, 'RECORD file not inventoried')
                if digest:
                    algorithm, value = digest.split('=', 1)
                    need(algorithm == 'sha256', 'non-SHA256 RECORD is not accepted')
                    hex_digest = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)).hex()
                    need(manifest[str(p)] == {'bytes': int(size), 'sha256': hex_digest}, 'runtime RECORD payload mismatch: ' + relative)
                    checked += 1
        need(sorted(excluded_cli) == sorted(pin['outside_runtime']), 'baseline excluded CLI list drift')
        result.append({'name': pin['name'], 'version': pin['version'], 'record_payloads_checked': checked,
                       'baseline_excluded_external_cli_not_imported': excluded_cli})
    for name, pin in baseline['native_pins'].items():
        p = Path(pin['path']).resolve(strict=True)
        need(file_id(p) == pin['actual'], 'fixed native pin mismatch: ' + name)
    return result


def elf_closure(paths, interpreter_library_directory):
    queue = [Path(p) for p in paths]
    nodes = {}
    missing = []
    while queue:
        p = queue.pop().resolve(strict=True)
        if str(p) in nodes:
            continue
        with p.open('rb') as f:
            if f.read(4) != b'\x7fELF':
                continue
        r = subprocess.run(['/usr/bin/readelf', '-d', str(p)], check=True, capture_output=True, text=True)
        needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]', r.stdout)
        rpaths = re.findall(r'\((?:RUNPATH|RPATH)\).*?\[(.*?)\]', r.stdout)
        search = []
        for row in rpaths:
            for x in row.split(':'):
                x = x.replace('${ORIGIN}', str(p.parent)).replace('$ORIGIN', str(p.parent))
                if x and '$' not in x:
                    search.append(Path(x))
        # Pinned interpreter DT_RPATH ($ORIGIN/../lib) is inherited for its extension closure.
        search += [Path(interpreter_library_directory), Path('/lib/x86_64-linux-gnu'), Path('/usr/lib/x86_64-linux-gnu')]
        edges = []
        for soname in needed:
            choices = [d / soname for d in search if (d / soname).is_file()]
            if not choices:
                missing.append({'from': str(p), 'needed': soname})
                continue
            target = choices[0].resolve(strict=True)
            queue.append(target)
            edges.append({'needed': soname, 'target': str(target)})
        nodes[str(p)] = {**file_id(p), 'needed': needed, 'rpaths': rpaths, 'edges': edges}
    need(not missing, 'unresolved static ELF dependencies: ' + str(missing))
    return {'nodes': nodes, 'missing': missing, 'readelf': file_id(Path('/usr/bin/readelf')),
            'scope': 'static dependency candidate set, never ldd or ELF entry execution; actual maps verified later'}


def prepare(target, runtime, baseline_path, install_path):
    target, runtime = Path(target).resolve(strict=True), Path(runtime).resolve(strict=True)
    here = Path(__file__).resolve().parent
    baseline = json.loads(Path(baseline_path).read_text())
    install = json.loads(Path(install_path).read_text())
    need(install['status'] == 'BYTE_VERIFIED_NOT_IMPORTED', 'unverified dependency installation')
    manifest = inventory(runtime)
    runtime_check = verify_runtime(runtime, baseline, manifest)
    new_files = inventory(target)
    expected_new = {str((target / rel).resolve(strict=True)): pin for rel, pin in install['files'].items()}
    need(new_files == expected_new, 'installed target inventory differs from pinned installation receipt')
    manifest.update(new_files)
    stdlib = Path(sysconfig.get_path('stdlib')).resolve(strict=True)
    manifest.update(inventory(stdlib, exclude=('site-packages',)))
    interpreter = Path(sys.executable).resolve(strict=True)
    manifest[str(interpreter)] = file_id(interpreter)
    expected_python = baseline['native_pins']['python']
    need(interpreter == Path(expected_python['path']).resolve(strict=True), 'wrong Python executable')
    need(manifest[str(interpreter)] == expected_python['actual'], 'wrong Python executable bytes')
    for name in GATE_FILES:
        manifest[str(here / name)] = file_id(here / name)
    upstream = {}
    for relative, digest in UPSTREAM.items():
        p = target / relative
        actual = file_id(p)
        need(actual['sha256'] == digest, 'official upstream source mismatch: ' + relative)
        upstream[relative] = actual
    classes = {name: class_static_identity((target / relative).read_bytes(), name, str(target / relative))
               for name, relative in CLASS_FILES.items()}
    excluded_native_roots = [p for p in manifest if Path(p).name.startswith('_tkinter.') and '.so' in Path(p).name]
    native_roots = [p for p in manifest if ('.so' in Path(p).name or p == str(interpreter)) and p not in excluded_native_roots]
    elf = elf_closure(native_roots, interpreter.parent.parent / 'lib')
    mapped_manifest = {}
    for path, info in elf['nodes'].items():
        manifest[path] = {k: info[k] for k in ('bytes', 'sha256')}
        mapped_manifest[path] = manifest[path]
    # Retain every current mapped file of this stdlib-only preparer as a candidate too.
    # These are pinned bytes, not a claim they will be imported by the worker.
    from gate_common import parse_maps
    for row in parse_maps(Path('/proc/self/maps').read_text()):
        if row['kind'] == 'file':
            p = Path(row['decoded_pathname']).resolve(strict=True)
            manifest[str(p)] = file_id(p)
            mapped_manifest[str(p)] = manifest[str(p)]
    return {'schema': 1, 'status': 'PREPARED_NOT_EXECUTED_NOT_APPROVED',
            'action': 'single_official_normal_import_only',
            'target': str(target), 'runtime': str(runtime), 'stdlib': str(stdlib),
            'interpreter': str(interpreter), 'gate_directory': str(here),
            'expected_versions': {'transformers': '4.40.1', 'torch': '2.10.0+cpu', 'numpy': '2.3.5'},
            'python_major_minor': [3, 12], 'python_optimization': 0,
            'upstream': upstream, 'selected_classes': classes,
            'file_manifest': manifest, 'mapped_file_manifest': mapped_manifest,
            'excluded_native_roots': excluded_native_roots,
            'excluded_module_prefixes': ['tkinter', '_tkinter'],
            'runtime_record_verification': runtime_check,
            'baseline_receipt': {'path': str(Path(baseline_path).resolve()), **file_id(baseline_path)},
            'installation_receipt': {'path': str(Path(install_path).resolve()), **file_id(install_path)},
            'static_native_closure': elf, 'limits': LIMITS,
            'loopback_probe': loopback_probe_policy(target),
            'scope': {'normal_import_only': True, 'instantiate_config': False, 'instantiate_layer': False,
                      'model_forward': False, 'user_tensors': False, 'raw_inputs': False,
                      'matrix_or_dut': False, 'network': False,
                      'single_exact_dependency_loopback_probe': True,
                      'ordinary_torch_numpy_initialization_allowed': True,
                      'full_live_code_identity_claimed': False},
            'execution_started': False}


def prepare_reusing_closure(config_path, config_sha256):
    """Reuse the exact frozen closure without importing targets or copying dependencies.

    The launcher still rehashes every reused file before and after the sole run.
    Preparation rehashes the new gate and exact probe source only.
    """
    config = read_checked(config_path, config_sha256)
    need(config['status'] == 'PREPARED_NOT_EXECUTED_NOT_APPROVED' and config['execution_started'] is False,
         'invalid frozen predecessor configuration')
    need(config['limits'] == LIMITS, 'predecessor limit mismatch')
    here = Path(__file__).resolve().parent
    previous = Path(config['gate_directory'])
    need(previous != here and not (here / 'COLD_IMPORT_CLAIM.json').exists(), 'fresh independent gate directory required')
    for name in GATE_FILES:
        old_path = previous / name
        need(file_id(old_path) == config['file_manifest'][str(old_path)], 'frozen predecessor gate drift')
        del config['file_manifest'][str(old_path)]
        config['file_manifest'][str(here / name)] = file_id(here / name)
    config['gate_directory'] = str(here)
    config['loopback_probe'] = loopback_probe_policy(config['target'])
    fp = config['loopback_probe']['function']
    need(config['file_manifest'][fp['filename']] == {'bytes': fp['file_bytes'], 'sha256': fp['file_sha256']},
         'probe source absent from reused pinned closure')
    config['scope']['single_exact_dependency_loopback_probe'] = True
    config['predecessor_config'] = {'path': str(Path(config_path).resolve()), **file_id(config_path)}
    config['preparation_scope'] = 'Original dependency/source/runtime/ELF closure reused unchanged; four gate file identities replaced, exact loopback policy added. Full preflight and postflight remain mandatory.'
    return config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target')
    p.add_argument('--reuse-config')
    p.add_argument('--reuse-config-sha256')
    p.add_argument('--runtime')
    p.add_argument('--runtime-baseline')
    p.add_argument('--installation-receipt')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    if a.reuse_config:
        need(a.reuse_config_sha256 is not None, 'exact predecessor config SHA required')
        result = prepare_reusing_closure(a.reuse_config, a.reuse_config_sha256)
    else:
        need(all((a.target, a.runtime, a.runtime_baseline, a.installation_receipt)), 'all preparation paths required')
        result = prepare(a.target, a.runtime, a.runtime_baseline, a.installation_receipt)
    identity = write_new(a.output, result)
    print(json.dumps({'status': result['status'], 'config': str(Path(a.output).resolve()),
                      'identity': identity, 'files': len(result['file_manifest']),
                      'bytes_pinned': sum(x['bytes'] for x in result['file_manifest'].values())}, sort_keys=True))

if __name__ == '__main__':
    main()
