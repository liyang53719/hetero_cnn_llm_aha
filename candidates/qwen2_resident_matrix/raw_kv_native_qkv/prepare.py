"""Source-only explicit QKV gate variant; no replacement of published sources."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_native_qkv/'
ORIGINAL = 'scripts/qwen2_layer0_model_gate.py'
ORIGINAL_SHA256 = '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'
PROFILE = 'qwen2-independent-qkv-block-pair-v1'


def need(ok):
    if not ok:
        raise ValueError('independent QKV source contract')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(name):
    path = Path(name)
    need(type(name) is str and not path.is_absolute() and '..' not in path.parts and str(path) == name)
    target = ROOT / path
    need(all(not p.is_symlink() for p in (target, *target.parents)) and target.is_file())
    need(target.stat().st_size <= 4 * 1024 * 1024)
    return target.read_bytes()


def snapshot():
    raw = read(PREFIX + 'pins.json')
    pins = json.loads(raw)
    need(type(pins) is dict and set(pins) == {'schema', 'profile', 'source_sha256', 'generated_module_sha256', 'cpp_sha256'})
    need(type(pins['schema']) is int and pins['schema'] == 1 and pins['profile'] == PROFILE)
    expected = {PREFIX + n for n in ('kernel.py', 'adapter.py', 'prepare.py', 'variant.patch', 'test_recipe.py', 'README.md')}
    expected |= {ORIGINAL, 'candidates/qwen2_resident_matrix/dense_block_reduce/reference/dot16.inc',
                 'candidates/qwen2_resident_matrix/dense_block_reduce/reference/profile.json', 'spec/numerical_contract.md'}
    need(type(pins['source_sha256']) is dict and set(pins['source_sha256']) == expected)
    need(all(type(h) is str and len(h) == 64 and all(c in '0123456789abcdef' for c in h)
             for h in (*pins['source_sha256'].values(), pins['generated_module_sha256'], pins['cpp_sha256'])))
    need(pins['source_sha256'][ORIGINAL] == ORIGINAL_SHA256)
    need(all(sha(read(n)) == h for n, h in pins['source_sha256'].items()))
    from . import kernel
    need(sha(kernel.source_bytes()) == pins['cpp_sha256'])
    return dict(pins, pins_sha256=sha(raw))


def check_scope(original, generated):
    """Prove the disabled AST projection is identical, including every verdict."""
    before, after = ast.parse(original), ast.parse(generated)
    old = {n.name: n for n in before.body if isinstance(n, ast.FunctionDef)}
    new = {n.name: n for n in after.body if isinstance(n, ast.FunctionDef)}
    need(old.keys() == new.keys())
    independent = new['independent_forward']
    need([a.arg for a in independent.args.kwonlyargs] == ['qkv_recipe'])
    independent.args.kwonlyargs = []; independent.args.kw_defaults = []
    linear = next(n for n in independent.body if isinstance(n, ast.FunctionDef) and n.name == 'linear')
    need(isinstance(linear.body[0], ast.If) and 'qkv_recipe' in ast.unparse(linear.body[0].test))
    linear.body.pop(0)
    gate = new['run_gate']
    need([a.arg for a in gate.args.kwonlyargs] == ['qkv_recipe'])
    gate.args.kwonlyargs = []; gate.args.kw_defaults = []
    need(ast.unparse(gate.body[0]) == 'qkv_identity = None')
    gate.body.pop(0)
    tests = {'qkv_recipe is not None', 'qkv_identity is not None'}
    gate.body = [n for n in gate.body if not (isinstance(n, ast.If) and ast.unparse(n.test) in tests)]
    calls = [n for n in ast.walk(gate) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == 'independent_forward']
    need(len(calls) == 1 and len(calls[0].keywords) == 1 and calls[0].keywords[0].arg == 'qkv_recipe')
    calls[0].keywords = []
    need(ast.dump(before) == ast.dump(after))


def prepare(out):
    frozen = snapshot()
    out = Path(out)
    need(not out.exists() and not out.is_symlink() and all(not p.is_symlink() for p in out.parents))
    target = out / ORIGINAL
    target.parent.mkdir(parents=True)
    original = read(ORIGINAL)
    target.write_bytes(original)
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=out,
                   input=read(PREFIX + 'variant.patch'), check=True, capture_output=True, timeout=10)
    generated = target.read_bytes()
    need(sha(generated) == frozen['generated_module_sha256'])
    check_scope(original, generated)
    need(snapshot() == frozen)
    return dict(status='PASS_SOURCE_PREPARATION_ONLY', profile=PROFILE,
                source_sha256=frozen['source_sha256'], pins_sha256=frozen['pins_sha256'],
                generated_module_sha256=sha(generated), numerical_execution=False)
