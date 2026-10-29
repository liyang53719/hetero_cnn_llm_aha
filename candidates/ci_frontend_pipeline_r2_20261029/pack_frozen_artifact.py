"""Flat seven-file frozen binary artifact; no weights, inputs, references or DUT run."""
import pathlib,json,shutil,hashlib
from build_producer import need,check_pins,artifact_manifest,DRIVER_SHA

def sha(p):
 with pathlib.Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return dict(path=str(pathlib.Path(p).resolve()),bytes=pathlib.Path(p).stat().st_size,sha256=sha(p))
def pack(original,b,built,host,overlay,out,budget_check):
 need(built['status']=='BUILT_UNQUALIFIED','actual build result required')
 need(built['scope']=='ARCHIVE_LINK_ONLY_NOT_DUT_PASS','build-only scope')
 check_pins(b['pins']);check_pins(b['admission']['make_closure_pins'])
 need(original['artifact_identity']['source_commit']==original['repo_sha'],'source commit identity')
 phases=built['phases'];plan=built['plan']['phases']
 need(len(phases)==len(plan)>0,'complete planned build phases')
 summaries=[]
 for actual,planned in zip(phases,plan):
  need(actual['phase']==planned['name']and actual['argv']==planned['argv'],'actual phase identity')
  r=actual['supervisor'];need(r['native_exit']==0 and not r['errors']and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','native success and cleanup required')
  q=actual['output'];need(pin(q['path'])==q,'archive/binary stable after build')
  summaries.append(dict(phase=actual['phase'],output_sha256=q['sha256'],native_exit=0,observed_cpu_seconds=r.get('observed_cpu_seconds'),elapsed_seconds=r.get('elapsed_seconds'),observed_peak_rss=r.get('observed_peak_rss'),supervisor_receipt_sha256=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
 need(built['binary']==phases[-1]['output'],'final planned binary')
 source=pathlib.Path(built['binary']['path'])
 with source.open('rb')as f:need(f.read(6)==b'\x7fELF\x02\x01','actual ELF64 LE binary')
 need(sha(original['driver'])==DRIVER_SHA,'exact original V3 driver')
 root=pathlib.Path(out)/'frozen_artifact';need(not root.exists(),'fresh immutable artifact root')
 copies=[('binary',source,'dut.bin'),('sv',pathlib.Path(host),'hardware.sv'),('driver',pathlib.Path(original['driver']),'driver.cpp'),('tool_manifest',pathlib.Path(b['tool_manifest']),'tool_manifest.json'),('source_manifest',pathlib.Path(b['source_manifest']),'source_manifest.json')]
 projected=sum(path.stat().st_size for _,path,_ in copies)+131072
 budget_check(projected);root.mkdir();files={}
 for key,path,name in copies:
  before=pin(path);target=root/name;shutil.copyfile(path,target);need(sha(target)==before['sha256']and pin(path)==before,'stable copy '+key);files[key]=target
 files['binary'].chmod(0o700)
 need(sum(p.stat().st_size for p in root.iterdir())<=4*1024**3,'artifact expanded bound')
 receipt=dict(status='BINARY_BUILD_ONLY_NO_NUMERICS',config_only=False,software_arithmetic_substitution=False,source_commit=original['artifact_identity']['source_commit'],launch_commit=original['artifact_identity']['launch_commit'],tool_manifest_sha256=sha(files['tool_manifest']),**{k+'_sha256':sha(files[k])for k in ('binary','sv','source_manifest','driver')},phases=summaries,admission_method=b['admission']['method'],scope='CHISEL_TEST_BACKEND_NOT_FINAL_RTL_REPLAY')
 receipt_raw=json.dumps(receipt,indent=2)+'\n';need(len(receipt_raw.encode())<=65536,'build receipt64KiB')
 files['build_receipt']=root/'build_receipt.json';files['build_receipt'].write_text(receipt_raw)
 manifest=artifact_manifest(root,original['artifact_identity'],files,built)
 mf=root/'frozen_artifact.json';mf.write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
 need(mf.stat().st_size<=65536 and len(list(root.iterdir()))==7 and sum(p.stat().st_size for p in root.iterdir())<=4*1024**3,'seven-file whitelist and bounded manifest/expanded artifact')
 check_pins(b['pins']);check_pins(b['admission']['make_closure_pins'])
 budget_check(0)
 return dict(manifest=pin(mf),files=7,expanded_bytes=sum(p.stat().st_size for p in root.iterdir()),scope='ONE_SHARED_BINARY_FROZEN_NOT_UPLOADED_NOT_EXECUTED')
