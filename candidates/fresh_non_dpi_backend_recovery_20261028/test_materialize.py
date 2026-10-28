#!/usr/bin/env python3
"""Small file-only materializer checks; never compiles or simulates."""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--original-high',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);a=p.parse_args()
checks=[]
with tempfile.TemporaryDirectory(prefix='backend-path-rebind-') as t:
 d=Path(t)
 def call(name,h,ann,out,want,optimized=False):
  cmd=[sys.executable]+(['-O'] if optimized else [])+[str(P/'materialize_emitter.py'),'--original-high',str(h),'--annotations',str(ann),'--output',str(out)]
  r=subprocess.run(cmd,capture_output=True,text=True)
  if (r.returncode==0)!=want:raise RuntimeError(name+': '+r.stderr)
  checks.append(name)
 call('verified_materialization',a.original_high,a.annotations,d/'good',True)
 call('refuse_overwrite',a.original_high,a.annotations,d/'good',False)
 bad=d/'bad';bad.write_text('not the reviewed high')
 call('wrong_high_rejected',bad,a.annotations,d/'wrong',False)
 call('wrong_high_rejected_under_O',bad,a.annotations,d/'wrongO',False,True)
 link=d/'link';link.symlink_to(a.annotations.resolve())
 call('symlink_annotation_rejected',a.original_high,link,d/'linkout',False)
 call('verified_materialization_under_O',a.original_high,a.annotations,d/'goodO',True,True)
 receipt=json.loads((d/'good/REBIND_RECEIPT.json').read_text())
 print(json.dumps({'status':'PASS_PATH_MATERIALIZER_ONLY','checks':checks,'rebound_source_sha256':receipt['sha256'],'matches_original_compiled_source':receipt['matches_historical_compiled_source_bytes']}))
