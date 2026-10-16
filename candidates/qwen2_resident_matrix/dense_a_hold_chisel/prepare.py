"""Prepare a fresh actual-owner Chisel overlay; never compile or emit RTL."""
import hashlib
import json
from pathlib import Path
import subprocess

from candidates.qwen2_resident_matrix.raw_kv_parent.prepare_unit import prepare as parent_prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGETS = ('TransposedDenseBanks.scala', 'TransposedDenseOwner.scala')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(out, *, verify=True):
    out = Path(out)
    require(not out.exists(), 'fresh A-hold source directory required')
    pins = json.loads((HERE / 'source_pins.json').read_text()) if verify else None
    if verify:
        for path, digest in pins['inputs'].items():
            require(sha(ROOT / path) == digest, 'A-hold source drift: ' + path)
    parent = parent_prepare(out)
    before = {p.name: sha(p) for p in out.glob('*.scala')}
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'],
                   input=(HERE / 'a_hold.patch').read_text(), text=True,
                   cwd=out, capture_output=True, check=True, timeout=10)
    after = {p.name: sha(p) for p in sorted(out.glob('*.scala'))}
    require(set(after) == set(before), 'overlay must not add a replacement module')
    require({p for p in before if before[p] != after[p]} == set(TARGETS),
            'overlay must affect only actual Down owner and banks')
    if verify:
        require(after == pins['generated_sha256'], 'A-hold generated source drift')
    return {'parent_generated_sha256': before, 'generated_sha256': after,
            'parent_inputs': parent['inputs'], 'rtl_generated': False,
            'scala_compiled': False, 'chisel_elaborated': False}
