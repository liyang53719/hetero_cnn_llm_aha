"""Exact original parent + scratch successor composition; source-only."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from candidates.qwen2_resident_matrix.raw_kv_parent import compose as parent
ROOT=parent.ROOT;HERE=Path(__file__).resolve().parent;PREFIX=str(HERE.relative_to(ROOT))+'/'
OWN=tuple(PREFIX+n for n in ('scratch.patch','model.py','prepare.py','test_model.py','test_sources.py','README.md'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sources():
 pins=json.loads((parent.HERE/'source_pins.json').read_bytes())
 names=set(pins['inputs'])|set(parent.TARGETS)|set(parent.PATCHES)|set(parent.OMITTED)
 names.update('candidates/qwen2_resident_matrix/'+n for n in ('raw_kv_parent/compose.py','raw_kv_parent/source_pins.json','raw_kv_parent/integration.patch','raw_kv/raw_kv_port.patch','raw_kv/model.py','attention_bank_scratch/port.py','transposed_down/model.py'))
 return {n:sha(ROOT/n) for n in sorted(names)}
def compose(out,*,verify=True):
 if verify:check()
 out=Path(out);parent.compose(out)
 subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=(HERE/'scratch.patch').read_bytes(),cwd=out,check=True,capture_output=True,timeout=10)
 return {n:sha(out/n) for n in parent.TARGETS}
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 if p['sources']!=sources() or p['own']!={n:sha(ROOT/n) for n in OWN}:raise ValueError('source drift')
 with tempfile.TemporaryDirectory() as d:
  if compose(Path(d)/'out',verify=False)!=p['generated']:raise ValueError('generated drift')
 return p
