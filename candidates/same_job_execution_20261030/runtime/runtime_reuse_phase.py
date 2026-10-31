"""Strict-supervised byte revalidation and actual import smoke; never model forward."""
import argparse,json,pathlib,subprocess,sys
import runtime_reuse as r
P=pathlib.Path

def run(binding,digest,key):
 b=r.read(dict(path=str(binding),bytes=P(binding).stat().st_size,sha256=digest));r.admit(b)
 for p,h in b['pins'].items():r.need(r.sha(p)==h,'pre-import original source pin')
 r.need(str(P(sys.executable).resolve())==b['python'],'current pinned original interpreter')
 if key=='qwen2':r.need('avx512f'in P('/proc/cpuinfo').read_text().split(),'original P0 AVX512')
 m,helper=r.manifest(b);e=r.verify_entry(b,key,m,helper)
 # Original pinned wrapper retains its original CPU/thread/import policy. Every
 # writable cache path was created under this job by the strict owning controller.
 code="import json,pathlib,torch,transformers; site=pathlib.Path("+repr(e['site'])+").resolve(); paths=[pathlib.Path(torch.__file__).resolve(),pathlib.Path(transformers.__file__).resolve()];\nif not all(p.is_relative_to(site) for p in paths): raise ValueError('original runtime module origins')\nprint('RUNTIME_IMPORT_SMOKE_V1 '+json.dumps({'torch':torch.__version__,'transformers':transformers.__version__},sort_keys=True))"
 subprocess.run([e['wrapper']['path'],'-c',code],check=True)
 r.verify_entry(b,key,m,helper)
 for p,h in b['pins'].items():r.need(r.sha(p)==h,'post-import original source pin')
 target=P(b['result_root'])/(key+'_IMPORT_VALIDATED.json');r.need(target.parent.is_relative_to(P(b['owner_root'])),'new job-only validation result')
 r.save(target,dict(schema='FRESH_RUNTIME_IMPORT_VALIDATION_V1',scope=r.SCOPE,identity=b['identity'],runtime=key,runtime_reuse_manifest=b['runtime_reuse_manifest'],whole_tree=e['whole_tree'],smoke_import_exit=0,reference_qualified=False,numerical_qualified=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--binding',type=P,required=True);p.add_argument('--binding-sha256',required=True);p.add_argument('--runtime',choices=r.KEYS,required=True);a=p.parse_args();run(a.binding,a.binding_sha256,a.runtime)
