"""Prepare one fixed suffix plan from explicit private paths. Never launch or run Git.

--inputs and --references are JSON objects mapping fixed names to local file paths.
The exact saved words/weights/references are hash-pinned; no new arithmetic is done.
"""
import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_chunk import HERE, CHECKPOINT, checked, create, need
from suffix_case import NAMES, case, plan_case


def transpose_words(raw, n=1024, k=2048):
    need(type(n) is int and type(k) is int and n > 0 and k > 0 and len(raw) == n*k*2, 'NK weight extent')
    words = array('H'); words.frombytes(raw)
    if sys.byteorder != 'little':
        words.byteswap()
    packed = array('H', [0]) * len(words)
    for row in range(n):
        packed[row::n] = words[row*k:(row+1)*k]
    restored = array('H', [0]) * len(words)
    for row in range(n):
        restored[row*k:(row+1)*k] = packed[row::n]
    need(restored == words, 'uint16 transpose roundtrip')
    if sys.byteorder != 'little':
        packed.byteswap()
    return packed.tobytes()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=NAMES, required=True)
    for option in ('repository', 'runtime-site', 'python', 'compiler', 'inputs', 'references', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    for option in ('matrix-library', 'matrix-receipt'):
        parser.add_argument('--' + option, type=Path)
    parser.add_argument('--cpu', type=int, required=True)
    args = parser.parse_args(argv)
    if (args.case == 'o') != bool(args.matrix_library and args.matrix_receipt):
        parser.error('ordinary O requires both Matrix library and receipt; other cases reject them')
    if args.case != 'o' and (args.matrix_library or args.matrix_receipt):
        parser.error('Scalar cases cannot load a Matrix library')
    return args


def main():
    args = parse_args(); selected = case(args.case)
    root = args.repository.resolve(strict=True); runtime = args.runtime_site.resolve(strict=True)
    out = args.output.resolve()
    need(not os.path.lexists(out), 'fresh output directory required')
    for protected in (root, runtime, CHECKPOINT):
        need(out != protected and protected not in out.parents, 'output inside protected tree')
    need(args.cpu in os.sched_getaffinity(0), 'CPU not allowed')
    base = json.loads((HERE / 'pins.json').read_text()); spec = json.loads((HERE / 'suffix_pins.json').read_text())
    inputs = {}

    def admit(path, expected=None, capture=False):
        path = Path(path).resolve(strict=True)
        recorded, raw = checked(path, expected, capture)
        inputs[str(path)] = recorded
        return raw

    sources = dict(base['sources'], **base['m128']['sources'])
    for relative, expected in sources.items():
        admit(root / relative, expected)
    rows = []
    for name in base['runtime']['site_tree']['roots']:
        directory = runtime / name
        need(directory.is_dir() and not directory.is_symlink(), 'runtime subtree')
        for path in sorted(directory.rglob('*')):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            need(not path.is_symlink(), 'runtime symlink')
            if path.is_file():
                admit(path); pin = inputs[str(path.resolve())]
                rows.append([path.relative_to(runtime).as_posix(), pin['bytes'], pin['sha256']])
    tree = base['runtime']['site_tree']
    need(len(rows) == tree['files'] and hashlib.sha256(json.dumps(sorted(rows), separators=(',', ':')).encode()).hexdigest()
         == tree['canonical_sha256'], 'selected runtime tree identity')
    admit(args.python, base['runtime']['python']); admit(args.compiler, base['runtime']['compiler'])
    environment = dict(base['environment']); git = dict(expected_calls=selected['git_calls'], execution_pins={})
    if selected['git_calls']:
        # Fresh source identity, not a copied historical Git receipt. A detached
        # exact HEAD is deliberately required; no preparation-time Git calls.
        head = admit(root / '.git/HEAD', capture=True)
        need(head.decode().strip() == base['source_commit'], 'detached exact source commit required')
        for path in (root / '.git/HEAD', root / '.git/config', Path('/usr/bin/git')):
            admit(path); git['execution_pins'][str(path)] = inputs[str(path.resolve())]['sha256']
        need(git['execution_pins']['/usr/bin/git'] == spec['git_binary_sha256'], 'Git executable identity')
        need(not (root / '.git/objects/info/alternates').exists() and not (root / '.git/refs/replace').exists(),
             'Git alternates/replacements not admitted')
    if args.case == 'o':
        library = args.matrix_library.resolve(strict=True); receipt_path = args.matrix_receipt.resolve(strict=True)
        admit(library, spec['matrix_library']); receipt = json.loads(admit(receipt_path, capture=True))
        need(receipt['status'] == 'PASS_HOST_BUILD_ONLY' and receipt['returncode'] == 0 and
             receipt['repo'] == str(root) and receipt['library'] == str(library), 'existing exact Matrix build receipt')
        need(receipt['sources_before'] == receipt['sources_after'] and receipt['library_sha256'] == spec['matrix_library']['sha256'] and
             receipt['compiler_sha256'] == base['runtime']['compiler']['sha256'], 'Matrix build source/compiler/library identity')
        expected_sources = ('candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
                            'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp')
        for relative in expected_sources:
            need(receipt['sources_before'][relative] == sources[relative]['sha256'], 'Matrix source hash')
        need(receipt['argv'] == [str(args.compiler.resolve()), '-shared', '-fPIC', '-O2', '-ffp-contract=off',
             '-fno-fast-math', *(str(root / relative) for relative in expected_sources), '-o', str(library)], 'Matrix build recipe')
        environment.update(MATRIX_SERVICE_LIBRARY=str(library), MATRIX_SERVICE_COMPILE_RECEIPT=str(receipt_path))
    data = {}; records = {}
    for section, mapping_path in (('stage_inputs', args.inputs), ('references', args.references)):
        paths = json.loads(admit(mapping_path, capture=True)); expected = selected[section]
        required = set(expected) - ({'weight_kn'} if section == 'stage_inputs' and args.case == 'o' else set())
        need(set(paths) == required, 'exact explicit input path map: ' + section)
        records[section] = {}
        for name in required:
            digest = {key: expected[name][key] for key in ('bytes', 'sha256')}
            data[section, name] = admit(paths[name], digest, True)
        if section == 'stage_inputs' and args.case == 'o':
            data[section, 'weight_kn'] = transpose_words(data[section, 'weight_nk'])
        for name in expected:
            raw = data[section, name]
            need(len(raw) == expected[name]['bytes'] and hashlib.sha256(raw).hexdigest() == expected[name]['sha256'], 'fixed mapped words')
            target = out / ('inputs' if section == 'stage_inputs' else 'reference') / expected[name]['filename']
            records[section][name] = dict(path=str(target), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    for path in HERE.glob('*.py'):
        admit(path)
    admit(HERE / 'pins.json'); admit(HERE / 'suffix_pins.json')
    os.umask(0o077); out.mkdir(mode=0o700)
    for (section, name), raw in data.items():
        path = Path(records[section][name]['path']); create(path, raw); admit(path)
    plan = dict(schema=selected['schema'], case=args.case, stages=selected['stages'], policy=selected['policy'],
        limits=selected['limits'], addresses=selected['addresses'], **records, inputs=inputs, environment=environment,
        source_commit=base['source_commit'], repository=str(root), numpy_site=str(runtime),
        python=str(args.python.resolve()), cpu=args.cpu, cleanup_helper=str(root / 'scripts/idma_source_export_20261017/strict_cleanup.py'),
        run_directory=str(out / 'run'), git_source_identity=git,
        reference_paths=[str(Path(p).resolve()) for p in json.loads(args.references.read_text()).values()] +
                        [entry['path'] for entry in records['references'].values()],
        note='Fresh explicit saved-boundary diagnostic only; native adaptation TEMP_NOT_EXECUTED.')
    if args.case == 'o':
        plan['matrix_library'] = str(library)
    plan['child_argv'] = [plan['python'], '-I', '-S', '-B', str(HERE / 'suffix_child.py'), str(out / 'PLAN.json')]
    plan_case(plan)
    for path, expected in inputs.items():
        current, _ = checked(path); need(current == expected, 'post-preparation input drift')
    raw = (json.dumps(plan, indent=2, sort_keys=True) + '\n').encode(); create(out / 'PLAN.json', raw)
    print(json.dumps(dict(status='PREPARED_NOT_EXECUTED', plan_sha256=hashlib.sha256(raw).hexdigest(), input_pins=len(inputs))))


if __name__ == '__main__':
    main()
