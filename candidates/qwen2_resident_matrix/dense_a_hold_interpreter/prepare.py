"""Prepare private copies of the frozen real-owner sources; never run EDA."""
import json
from pathlib import Path
import shutil
import subprocess

from candidates.qwen2_resident_matrix.dense_a_hold_chisel.prepare import prepare as owner_prepare, sha, require

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=ROOT/'candidates/qwen2_resident_matrix/dense_a_hold_chisel'


def prepare(out, *, verify=True):
    pins=json.loads((HERE/'source_pins.json').read_text()) if verify else None
    if verify:
        for path,digest in pins['inputs'].items():
            require(sha(ROOT/path)==digest,'interpreter source drift: '+path)
    out=Path(out)
    receipt=owner_prepare(out)
    shutil.copyfile(ORIGINAL/'AHoldUnit.scala',out/'AHoldUnit.scala')
    subprocess.run(['patch','--batch','--fuzz=0','-p1'],
        input=(HERE/'harness.patch').read_text(),text=True,cwd=out,
        capture_output=True,check=True,timeout=10)
    shutil.copyfile(HERE/'ProbeElaborate.scala',out/'ProbeElaborate.scala')
    generated={p.name:sha(p) for p in sorted(out.glob('*.scala'))}
    require(len(generated)==15,'exact real owner plus harness/emitter closure')
    require(all(generated[p]==h for p,h in receipt['generated_sha256'].items()),'frozen owner changed')
    if verify:require(generated==pins['generated_sha256'],'prepared interpreter source drift')
    return generated
