#!/usr/bin/env python3
"""Reproduce pinned source composition only. No compilation or simulation."""
from pathlib import Path
import argparse,hashlib,json,importlib.util,subprocess,re
HERE=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def run(repo,out):
 repo=repo.resolve(strict=True);out=out.absolute()
 require(not out.exists(),'fresh output required')
 m=json.loads((HERE/'MANIFEST.json').read_text());prov=HERE/'provenance'
 for n,h in m['provenance_sha256'].items():require(sha((prov/n).read_bytes())==h,'provenance drift '+n)
 patch=(HERE/'production_qkv_reduction.patch').read_bytes();require(sha(patch)==m['patch_sha256'],'patch identity')
 targets=re.findall(rb'^\+\+\+ b/(.+)$',patch,re.M)
 require([x.decode() for x in targets]==m['changed_paths'],'patch target mismatch')
 require(all(not Path(x.decode()).is_absolute() and '..' not in Path(x.decode()).parts for x in targets),'unsafe path')
 spec=importlib.util.spec_from_file_location('pinned_parent_compose',prov/'compose.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 overlay=json.loads((prov/'evidence/overlay_manifest.json').read_text());parent=json.loads((prov/'pinned_source_manifest.json').read_text())
 require(parent['final_post_sha256']==m['baseline']['composed'],'baseline identity')
 source={}
 for n,h in m['baseline']['inputs'].items():
  p=repo/n;require(p.is_file() and not p.is_symlink(),'missing/linked source '+n)
  b=p.read_bytes();require(sha(b)==h,'source drift '+n);source[n]=b
 source=c.strict_patch(source,(prov/'current_overlay.patch').read_bytes(),overlay['changed_sources']);c.verify_map(source,overlay['post_sha256'],'overlay')
 source=c.strict_patch(source,(prov/'attention_preflight.patch').read_bytes(),[c.HOST]);c.verify_map(source,parent['attention_post_sha256'],'attention')
 source=c.strict_patch(source,(prov/'dispatch_abort.patch').read_bytes(),[c.HOST]);c.verify_map(source,parent['final_post_sha256'],'parent')
 out.mkdir(parents=True)
 for tree in ['baseline','source']:
  for n,b in source.items():
   p=out/tree/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 result=subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=patch,cwd=out/'source',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (out/'patch.log').write_bytes(result.stdout);require(result.returncode==0,'patch failed')
 actual={str(p.relative_to(out/'source')):sha(p.read_bytes()) for p in (out/'source').rglob('*') if p.is_file()}
 require(actual==m['post_sha256'],'postimage or inventory mismatch')
 report={'status':'PASS_PINNED_SOURCE_REPLAY_ONLY','post_sha256':actual,'compiled':False,'elaborated':False,'rtl_generated':False,'hardware_arithmetic_executed':False}
 (out/'REPLAY.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo','--source-root',dest='repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(run(a.repo,a.out)['status'])
