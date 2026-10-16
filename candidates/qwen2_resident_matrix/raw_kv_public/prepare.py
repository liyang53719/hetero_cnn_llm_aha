"""Compose the exact default-off public KV hook; never execute a numerical job."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from candidates.qwen2_resident_matrix.raw_kv_attention import numeric_prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'candidates/qwen2_resident_matrix/'
TARGETS = (PREFIX + 'ffn_public/execute_numeric.py', PREFIX + 'ffn_public/fullgraph_execution.py')
RECEIPT = 'reports/execution/QWEN2_DENSE_BLOCK_REDUCTION_20261012/M128_RESULT.json'
PINNED_INPUTS = (*TARGETS, RECEIPT, *(PREFIX + name for name in (
    'ffn_public/fullgraph_memory.py', 'official_bf16/execution.py',
    'official_bf16/dense_silu.py', 'dense_block_reduce/public_execution.py',
    'dense_block_reduce/matrix_binding.py', 'dense_block_reduce/check_public_numeric.py',
    'raw_kv_attention/numeric_prepare.py', 'raw_kv_attention/numeric_pins.json')))
OWN_INPUTS = ('model.py', 'test_model.py', 'public_execution.patch', 'prepare.py', 'pins.json', 'README.md')


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def _ast(text):
    return ast.parse(text)


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _one(nodes, kind, name):
    found = [n for n in nodes if isinstance(n, kind) and n.name == name]
    need(len(found) == 1, 'unique original declaration required')
    return found[0]


def check_scope(originals, generated):
    """Existing policy, arithmetic and physical IO statements remain identical."""
    old, new = (_ast(v[TARGETS[0]]) for v in (originals, generated))
    old_class = _one(old.body, ast.ClassDef, 'PublicExecution')
    new_class = _one(new.body, ast.ClassDef, 'PublicExecution')
    changed = {'__init__', 'reset_required', 'attention_edge'}
    added = {'_checked_attention_transport', 'bind_attention_transport'}
    need({n.name for n in new_class.body if isinstance(n, ast.FunctionDef)} ==
         {n.name for n in old_class.body if isinstance(n, ast.FunctionDef)} | added,
         'public hook method scope')
    for cls in (old_class, new_class):
        cls.body = [n for n in cls.body if not isinstance(n, ast.FunctionDef) or n.name not in changed | added]
    need(_dump(old) == _dump(new), 'unrelated public execution changed')
    old, new = (_ast(v[TARGETS[1]]) for v in (originals, generated))
    for name in ('execute_attention_owner', 'execute_public_suffix'):
        before = _one(old.body, ast.FunctionDef, name)
        after = _one(new.body, ast.FunctionDef, name)
        need(len(after.args.kwonlyargs) == len(before.args.kwonlyargs) + 1 and
             after.args.kwonlyargs[-1].arg == 'enable_raw_kv' and
             isinstance(after.args.kw_defaults[-1], ast.Constant) and
             after.args.kw_defaults[-1].value is False, 'default-off public flag')
        if name == 'execute_attention_owner':
            a = [n for n in before.body if isinstance(n, ast.While)]
            b = [n for n in after.body if isinstance(n, ast.While)]
            need(len(a) == len(b) == 1 and _dump(a[0]) == _dump(b[0]),
                 'original physical memory loop changed')
            # Its accepted terminal and report are also untouched.
            need([_dump(n) for n in before.body[before.body.index(a[0]) + 1:]] ==
                 [_dump(n) for n in after.body[after.body.index(b[0]) + 1:]],
                 'original physical terminal/report changed')
        old.body.remove(before); new.body.remove(after)
    need(_dump(old) == _dump(new), 'Dense/MLP/fullgraph helper changed')


def prepare(out):
    """Return source hashes and two composed real files in a fresh tree."""
    out = Path(out)
    need(not out.exists() and not out.is_symlink(), 'fresh source directory required')
    pins = json.loads((HERE / 'pins.json').read_text())
    need(set(pins['inputs']) == set(PINNED_INPUTS), 'exact public source pin closure')
    for name, expected in pins['inputs'].items():
        need(blob((ROOT / name).read_bytes()) == expected, 'public source drift: ' + name)
    historical = json.loads((ROOT / RECEIPT).read_text())
    need(historical['published_matching_source_commit'] == pins['lineage']['historical_source_commit'] and
         historical['status'] == pins['lineage']['historical_status'] and
         historical['official_comparison']['failed_stages'] == [] and
         pins['lineage']['historical_receipt_applies_to_this_extension'] is False and
         pins['lineage']['prepared_pv32_selected'] is False, 'historical PV16 lineage drift')
    for name in PINNED_INPUTS:
        if name != RECEIPT and '/raw_kv_attention/' not in name:
            need(historical['source_sha256'].get(name) == sha((ROOT / name).read_bytes()),
                 'original executed PV16 source identity drift: ' + name)
    numeric_prepare.check()
    patch = (HERE / 'public_execution.patch').read_bytes()
    need(sha(patch) == pins['patch_sha256'], 'public hook patch drift')
    headers = [line[6:] for line in patch.decode().splitlines() if line.startswith('--- a/')]
    need(tuple(headers) == TARGETS, 'exact two source patch targets')
    originals = {name: (ROOT / name).read_text() for name in TARGETS}
    out.mkdir(parents=True)
    for name, source in originals.items():
        target = out / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(source)
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], input=patch, cwd=out,
                   check=True, capture_output=True, timeout=10)
    generated = {name: (out / name).read_text() for name in TARGETS}
    check_scope(originals, generated)
    generated_hashes = {name: sha(source.encode()) for name, source in generated.items()}
    need(generated_hashes == pins['generated_sha256'], 'composed public hook drift')
    need({str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()} == set(TARGETS),
         'unexpected generated source file')
    numeric = json.loads((numeric_prepare.HERE / 'numeric_pins.json').read_text())['inputs']
    names = set(numeric) | set(PINNED_INPUTS) | {str((HERE / name).relative_to(ROOT)) for name in OWN_INPUTS}
    return dict(status='PASS_PREPARATION_ONLY', inputs={name: sha((ROOT / name).read_bytes()) for name in sorted(names)},
        generated=generated_hashes, lineage=pins['lineage'], arithmetic_executed=False,
        public_fullgraph_executed=False, hardware_simulation=False, old_pass_inherited=False)


def check():
    with tempfile.TemporaryDirectory(prefix='public-kv-source-') as directory:
        return prepare(Path(directory) / 'source')


if __name__ == '__main__':
    result = check()
    print('PASS: two pinned public source hooks prepared; numerical/RTL execution NOT RUN')
