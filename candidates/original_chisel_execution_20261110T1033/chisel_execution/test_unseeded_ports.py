from pathlib import Path
import json,re,hashlib
R=Path(__file__).resolve().parent;W=R.parents[1];c=json.loads((R/'unseeded_v2/CONTRACT.json').read_text());ir=W/'round_20261110T0733/qwen2_execution/v4_legacy_pipeline/HostBlockTopV4.fir'
expected={(p['direction'],p['name'],p['width']) for p in c['ports']};matched=0
s=ir.read_text()
for b in re.split(r'\n  (?=extmodule|module)',s):
 if not b.startswith('extmodule qwen2_matrix_command_endpoint'):continue
 rows=re.findall(r'    (input|output) (\w+) : (Clock|UInt<(\d+)>)',b)
 actual={(('IN' if d=='input' else 'OUT'),n,1 if t=='Clock' else int(w)) for d,n,t,w in rows}
 if actual!=expected or len(rows)!=22 or 'parameter ' in b:raise ValueError('IR/transport mismatch')
 matched+=1
if matched!=8:raise ValueError('not eight independent endpoints')
def validate(actual):
 if actual!=expected:raise ValueError('binding direction/name/width mismatch')
validate(expected)
# Wrong direction/width/extra seed are explicitly rejected by the same comparison.
for changed in [expected|{('IN','seed_begin_valid_i',1)},(expected-{('IN','cmd_i',128)})|{('IN','cmd_i',64)},(expected-{('IN','rst_ni',1)})|{('OUT','rst_ni',1)}]:
 try:validate(changed)
 except ValueError:pass
 else:raise RuntimeError('accepted incompatible binding')
result={'status':'PASS_PORT_MAP_ONLY','matrix_instances':matched,'ports_each':22,'ir_sha256':hashlib.sha256(ir.read_bytes()).hexdigest(),'contract_sha256':c['contract_sha256'],'negative_cases':3,'hardware_or_timing_pass':False}
(R/'unseeded_v2/PORT_TEST.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
