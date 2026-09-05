#!/usr/bin/env python3
"""Only structural emission admission; never pretends this is numeric/DC closure."""
import hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]); source=Path(__file__).resolve().parents[1]
required=['qwen2_shared_l2_matrix_tile16_payload','bf16_tile_transpose_stager','shared_l2_fabric','qwen2_projection_q1024_group8_controller']
files=sorted(out.glob('*.sv'))
if not files: raise RuntimeError('no emitted SystemVerilog')
text='\n'.join(p.read_text() for p in files)
for name in required:
 if len(re.findall(r'\bmodule\s+'+name+r'\b',text))!=1: raise RuntimeError('missing/duplicate root '+name)
for port in ['address_error_o','reset_required_o']:
 if port not in text: raise RuntimeError('missing diagnostic '+port)
scala=list((source/'src/main/scala').rglob('*.scala'))
blackboxes=[]
for p in scala:
 blackboxes += re.findall(r'class\s+(\w+)\s+extends\s+BlackBox',p.read_text())
if set(blackboxes)!={'RetainedDescriptor','RetainedMatrix'}: raise RuntimeError('unexpected blackboxes '+repr(blackboxes))
if any('HasBlackBoxInline' in p.read_text() for p in scala): raise RuntimeError('inline SV forbidden')
report={'status':'PASS_EMITTED_STRUCTURE_ONLY','roots':required,'sram_bytes':1572864,'clock_target_hz':800000000,
 'retained_blackboxes':blackboxes,'rtl_numeric_integration':False,'dc':False,
 'scala_sha256':{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in scala},
 'generated_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(out/'EMISSION_MANIFEST.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'roots':4,'generated_files':len(files)}))
