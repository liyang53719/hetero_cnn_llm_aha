"""Read-only bounded emitted-IR evidence checks, not canonical/RTL/numeric acceptance."""
from pathlib import Path
import hashlib,json,gzip,re
NAMES=['original-high.fir','official-low.fir','SCOPE.txt']+[p+s for p in ('high','low') for s in ('-annotations.json','-hierarchy.tsv','-top-ports.fir','-extmodules.fir','-summary.txt')]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def small(p,limit):
 if p.stat().st_size>limit:raise ValueError('metadata cap '+p.name)
 return p.read_text()
def inspect(root):
 root=Path(root);out=root/'host-diagnostic';rows={};total=0
 for name in NAMES:
  p=out/name
  if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=384*1024**2:raise ValueError('missing/invalid IR evidence '+name)
  total+=p.stat().st_size;rows[name]=dict(bytes=p.stat().st_size,sha256=sha(p))
 if total>1024**3:raise ValueError('IR tree budget')
 for suffix in ('*.sv','*.v','*.cpp'):
  if next(root.rglob(suffix),None) is not None:raise ValueError('unexpected backend output')
 for name in ('original-high.fir','official-low.fir'):
  with (out/name).open('rb') as f:prefix=f.read(8192)
  if b'circuit HostBlockTopV4' not in prefix:raise ValueError('original top circuit identity')
 for label in ('high','low'):
  summary=small(out/(label+'-summary.txt'),65536)
  for line in ('top=HostBlockTopV4','endpoints=8','matrix_logical_macs=4096','fixed_element_lanes=32','launch_bits=844'):
   if line not in summary.splitlines():raise ValueError('helper inventory '+line)
  ports=small(out/(label+'-top-ports.fir'),1024*1024)
  if 'residentObservation' not in ports or 'rawScoreObservation' not in ports:raise ValueError('combined sidebands absent from emitted top')
 if 'HIGH_AND_OFFICIAL_LOW_FIRRTL_ONLY' not in small(out/'SCOPE.txt',65536):raise ValueError('unexpected scope')
 with gzip.open(root/'frontend.log.gz','rb') as f:raw=f.read(16*1024**2+1)
 if len(raw)>16*1024**2:raise ValueError('raw log cap')
 text=raw.decode('utf-8','replace')
 if text.count('HOST_PHASE PASS_HIGH_AND_LOW_DIAGNOSTIC_ONLY ')!=1:raise ValueError('missing helper terminal marker')
 for name,r in rows.items():
  marker='HOST_ARTIFACT '+name+' bytes='+str(r['bytes'])+' sha256='+r['sha256']
  if text.count(marker)!=1:raise ValueError('artifact/log pin mismatch '+name)
 measured_ports={label:len(re.findall(r'^\s*(?:input|output)\s+',small(out/(label+'-top-ports.fir'),1024*1024),re.M)) for label in ('high','low')}
 if measured_ports['low'] != 122:raise ValueError('fresh R2 flattened ABI count differs from reviewed122')
 for field in ('kind','rank','last'):
  if 'rawScoreObservation_bits_'+field not in small(out/'low-top-ports.fir',1024*1024):raise ValueError('selector output observation field missing '+field)
 result=dict(status='COMPLETE_ORIGINAL_HIGH_AND_OFFICIAL_LOW_DIAGNOSTIC_ONLY',measured_top_port_counts=measured_ports,expected_top_ports_unverified_before_run=122,artifacts=rows,artifact_bytes=total,old_canonical_identity_compared=False,new_ir_identity=True,sv_generated=False,generated_abi_qualification=False,physical_resource_or_qor_qualification=False,block_numerical_pass=False)
 (root/'IR_ARTIFACT_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
