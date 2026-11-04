"""Selected162 source gate plus unchanged official model JAR inventory/acquisition.
No production generation allowlist changes, compiler, elaboration or DUT.
"""
import argparse,hashlib,importlib.util,json,pathlib,urllib.error,socket,ssl
P=pathlib.Path
HERE=P(__file__).resolve().parent
MODEL_RESTORE='candidates/model_candidate_build_20261101/restore_model_inputs.py'
MODEL_RESTORE_SHA256='52cf08821a982a4e0cadc8661d0d7e6c9877a4541b5389a79231410b2e10f15d'
TOOLCHAIN='candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json'
TOOLCHAIN_SHA256='7c8d4bd1f7a0a080f06161e70361a3c3676ede483703a90986fe9dfcf091d85b'
CANDIDATE_REL='candidates/gdn_chunk32_actual_v2_20261104'
GENERATION='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(v,s):
 if not v:raise ValueError(s)
def load_helper(repo):
 p=repo/MODEL_RESTORE;need(sha(p)==MODEL_RESTORE_SHA256,'reviewed model JAR helper pin')
 spec=importlib.util.spec_from_file_location('compile_only_pinned_model_jar_io',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def selected(repo,candidate):
 toolpins=json.loads((HERE/'TOOL_PINS.json').read_text())
 for n in ('select_sources.py','MODEL_SOURCE_OVERLAY.json','GENERATION_CONTRACT.json','PUBLICATION_MANIFEST.json'):
  p=candidate/n;rel=CANDIDATE_REL+'/'+n;need(sha(p)==toolpins['repo'][rel],'selected source gate pin')
 spec=importlib.util.spec_from_file_location('compile_only_selected162',candidate/'select_sources.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 s=module.select(repo,'gdn-chunk32-abort-v2');need(s['generation_identity']==GENERATION and len(s['source_paths'])==162 and not s['numeric_execution_authorized'],'exact new source generation')
 need(sha(repo/TOOLCHAIN)==TOOLCHAIN_SHA256,'unchanged official JAR manifest');original=json.loads((repo/TOOLCHAIN).read_text());return s,original
def source_closure(repo,candidate):
 repo=P(repo).resolve();candidate=P(candidate).resolve();s,original=selected(repo,candidate);helper=load_helper(repo)
 fresh,legacy_original,legacy_paths,legacy_contract=helper.source_inputs('legacy')
 need(fresh==repo/'candidates/fresh_original_top_recovery_20261028' and legacy_original==original and len(legacy_paths)==159,'exact compatible model159 gate')
 helper.inventory(original)
 toolpins=json.loads((HERE/'TOOL_PINS.json').read_text());pins={}
 def add(path,digest):
  path=str(path);need(path not in pins or pins[path]==digest,'conflicting shared source pin');pins[path]=digest
 metadata=[TOOLCHAIN,MODEL_RESTORE,'candidates/model_candidate_build_20261101/candidate_generation_gate.py','candidates/model_candidate_build_20261101/GENERATION_CONTRACT.json','candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json','candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json']
 for rel in metadata:
  p=repo/rel;h=toolpins['repo'][rel];need(sha(p)==h,'immutable model gate input');add(p,h)
 model=json.loads((repo/'candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json').read_text())
 for row,path in zip(model['files'],legacy_paths):add(path,row['sha256'])
 for n in ('select_sources.py','MODEL_SOURCE_OVERLAY.json','GENERATION_CONTRACT.json','PUBLICATION_MANIFEST.json'):add(candidate/n,toolpins['repo'][CANDIDATE_REL+'/'+n])
 overlay=json.loads((candidate/'MODEL_SOURCE_OVERLAY.json').read_text())
 for row,path in zip(overlay['files'],s['source_paths']):add(path,row['sha256'])
 for path,h in pins.items():need(sha(path)==h,'immutable complete source closure')
 return pins,s,helper

def run(repo,candidate,download=False,verify_only=False):
 result=dict(schema='GDN32_COMPILE_INPUT_STATUS_V1',status='INCOMPLETE',reason=None,source_count=None,legacy_gate_source_count=159,verified_jar_count=0,required_jar_count=107,jar_index=None,compiler_executed=False,numerical_pass=False)
 try:
  pins,s,helper=source_closure(repo,candidate);result['source_count']=len(s['source_paths'])
  # Original complete model-aware gate+download path is preserved. Independently
  # verified actual162 selection coexists; no old generation allowlist is widened.
  old=helper.run(download,verify_only,'legacy')
  for key in ('reason','verified_jar_count','jar_index','http_status'):
   if key in old:result[key]=old[key]
  need(old['source_count']==159,'legacy gate remains exact159')
  if old['status']=='INCOMPLETE':return result
  result['status']='SOURCE162_AND_MODEL159_JAR_INVENTORY_VERIFIED_ONLY' if verify_only else 'SOURCE162_AND_MODEL159_ALL_JAR_BYTES_VERIFIED'
  for path,h in pins.items():need(sha(path)==h,'post-acquisition source pin drift')
  return result
 except urllib.error.HTTPError as e:result.update(reason='JAR_HTTP_ERROR',http_status=e.code if type(e.code)is int and 100<=e.code<=599 else None)
 except (TimeoutError,socket.timeout):result['reason']='JAR_TIMEOUT'
 except (urllib.error.URLError,ssl.SSLError):result['reason']='JAR_NETWORK_ERROR'
 except OSError:result['reason']='JAR_IO_ERROR'
 except Exception as e:
  reason=getattr(e,'reason',None);result['reason']=reason if reason in {'JAR_INVENTORY_REJECTED','JAR_CACHE_REJECTED','JAR_MISSING','JAR_CONTENT_REJECTED'}else 'SOURCE_OR_CONTRACT_REJECTED'
 return result
def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=P,required=True);p.add_argument('--candidate',type=P,required=True);g=p.add_mutually_exclusive_group();g.add_argument('--download-jars',action='store_true');g.add_argument('--verify-only',action='store_true');a=p.parse_args();r=run(a.repo,a.candidate,a.download_jars,a.verify_only);print(json.dumps(r,sort_keys=True));return 1 if r['status']=='INCOMPLETE'else 0
if __name__=='__main__':raise SystemExit(main())
