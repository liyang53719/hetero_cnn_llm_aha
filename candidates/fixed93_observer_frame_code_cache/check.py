"""Static package checker. Never import or execute candidate/model/test code."""
import argparse
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parent

def need(ok, message):
    if not ok:
        raise ValueError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def dump(node):
    return ast.dump(node, include_attributes=False)

def method(tree, cls, name):
    c = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return next(n for n in c.body if isinstance(n, ast.FunctionDef) and n.name == name)

def resolve_input(key, baseline, old_observer):
    if key == 'old_observer':
        return old_observer
    kind, relative = key.split('/', 1)
    rel = PurePosixPath(relative)
    need(not rel.is_absolute() and '..' not in rel.parts, 'unsafe input reference')
    base = {'package': ROOT, 'baseline': baseline,
            'old_observer_parent': None if old_observer is None else old_observer.parent}[kind]
    return None if base is None else base / relative

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--old-observer', type=Path)
    args = parser.parse_args()
    need((args.baseline is None) == (args.old_observer is None), 'supply both external roots or neither')
    baseline = None if args.baseline is None else args.baseline.resolve()
    old_observer = None if args.old_observer is None else args.old_observer.resolve()
    manifest = json.loads((ROOT / 'PORTABLE_MANIFEST.json').read_bytes())
    need(manifest['schema'] == 'attention-frame-code-cache-portable-source-v1', 'schema')
    paths = list(ROOT.rglob('*'))
    need(not any(p.is_symlink() for p in paths), 'package symlink')
    actual = {p.relative_to(ROOT).as_posix() for p in paths if p.is_file()}
    need(actual == set(manifest['publish_whitelist']), 'publication whitelist mismatch')
    need(actual == set(manifest['files']) | {'PORTABLE_MANIFEST.json'}, 'manifest file closure')
    private_path = re.compile(r'(?<![A-Za-z0-9_:])/(?:workspace|home|Users|mnt|tmp|var)/[^\s\"\'<>]*')
    for name in sorted(actual):
        rel = PurePosixPath(name)
        need(not rel.is_absolute() and '..' not in rel.parts, 'unsafe package path')
        raw = (ROOT / name).read_bytes()
        if name != 'PORTABLE_MANIFEST.json':
            pin = manifest['files'][name]
            need(len(raw) == pin['bytes'] and digest(raw) == pin['sha256'], 'package pin: ' + name)
        text = raw.decode('utf-8')
        need(private_path.search(text) is None, 'private absolute path: ' + name)
        if name.endswith('.py'):
            ast.parse(text)
    for name, pin in manifest['unchanged_original_files'].items():
        need(manifest['files'][name] == pin, 'original source changed: ' + name)
    verified, omitted = [], []
    for key, pin in manifest['test_inputs'].items():
        p = resolve_input(key, baseline, old_observer)
        if p is None:
            omitted.append(key)
            continue
        raw = p.read_bytes()
        need(len(raw) == pin['bytes'] and digest(raw) == pin['sha256'], 'input pin: ' + key)
        verified.append(key)
    proofs = []
    if baseline is not None:
        specs = [('wholeblock.py', baseline / 'capture/wholeblock.py', 'TraceDispatcher', '_dispatch', 6),
                 ('narrow_fullblock_attention.py', old_observer, 'Fixed93FullblockAttentionObservation', '_trace', 15)]
        for filename, original_path, cls, name, count in specs:
            before = original_path.read_text()
            after = (ROOT / 'overlay' / filename).read_text()
            a, b = ast.parse(before), ast.parse(after)
            old, new = method(a, cls, name), method(b, cls, name)
            need(not any(isinstance(n, ast.Name) and n.id == 'code' for n in ast.walk(old)), 'preexisting code name')
            need(dump(new.body[0]) == dump(ast.parse('code = frame.f_code').body[0]), 'initial assignment')
            direct = lambda n: isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'frame' and n.attr == 'f_code'
            need(sum(direct(n) for n in ast.walk(old)) == count and sum(direct(n) for n in ast.walk(new)) == 1, 'direct read count')
            reconstructed = copy.deepcopy(b)
            restored = method(reconstructed, cls, name)
            restored.body.pop(0)
            class Restore(ast.NodeTransformer):
                def visit_Name(self, node):
                    if node.id == 'code':
                        need(isinstance(node.ctx, ast.Load), 'unexpected code store')
                        return ast.Attribute(value=ast.Name(id='frame', ctx=ast.Load()), attr='f_code', ctx=ast.Load())
                    return node
            Restore().visit(restored)
            need(dump(a) == dump(reconstructed), 'inverse module AST: ' + filename)
            x, y = before.splitlines(keepends=True), after.splitlines(keepends=True)
            need(x[:old.lineno] == y[:new.lineno] and x[old.end_lineno:] == y[new.end_lineno:], 'outside-target source')
            expected_patch = ''.join(difflib.unified_diff(x, y, fromfile='a/' + filename, tofile='b/' + filename))
            need(expected_patch == (ROOT / 'patches' / (Path(filename).stem + '.patch')).read_text(), 'exact relative patch')
            proofs.append(cls + '.' + name)
    print(json.dumps({'status': 'PASS_PORTABLE_STATIC_CHECK', 'file_count': len(actual),
                      'verified_inputs': verified, 'external_inputs_not_checked': omitted,
                      'inverse_module_ast_proofs': proofs, 'tests_executed': False,
                      'model_or_native_executed': False}, sort_keys=True))

if __name__ == '__main__':
    main()
