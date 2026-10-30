"""Whitelist-only saved metadata export. Never export logs/IR/SV/classes or authorize re-pin."""
import argparse,pathlib,time,math
from contract import *

def stage_row(name,path,strict=True):
 r=read(path,4<<20)
 if strict:need(completed(r),'strict actual stage result required')
 _,wall,rss=next(x for x in STAGES if x[0]==name)
 caps=r['caps'];need(caps['wall_seconds']==wall and caps['cleanup_seconds']==30 and caps['rss_bytes']==rss<<30 and caps['max_entries']==100000,'unchanged per-phase caps')
 elapsed=r['elapsed_seconds'];peak=r['observed_peak_rss'];need(type(elapsed)in(int,float) and math.isfinite(elapsed) and 0<=elapsed<=(wall+30 if strict else WHOLE) and type(peak)is int and 0<=peak<=((rss if strict else 64)<<30),'bounded actual telemetry')
 native=r.get('native_exit');need(native is None or type(native)is int and -255<=native<=255,'bounded native status')
 errors=r.get('errors');need(type(errors)is list and len(errors)<=4096,'bounded error count')
 return dict(name=name,native_exit=native,strict_complete=completed(r),cleanup_complete=r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof_observed=r.get('log_capture',{}).get('pipe_eof_observed')is True,gzip_finalized=r.get('log_capture',{}).get('gzip_finalized')is True,error_count=len(errors),elapsed_seconds=elapsed,observed_peak_rss=peak,result_sha256=sha(path))
def project_runtime(path,expected,identity):
 need(sha(path)==expected,'runtime inventory completion pin')
 r=read(path,2<<20);need(r['schema']=='SV_ONLY_JDK_PYTHON_IDENTITY_V1' and r['old_pass_transfer']is False and r['scope']=='IDENTITY_ONLY_NO_RUNTIME_CPU_OR_NUMERICAL_QUALIFICATION','runtime scope')
 need(r['contract']==dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k]for k in ('run_id','source_commit','launch_commit')}),'runtime owning identity')
 j=r['jdk'];need(j['status']=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION' and j['old_pass_transfer']is False,'JDK identity only')
 release=j['version'];props=j['actual_runtime_properties']
 need(release['JAVA_VERSION']=='21.0.13' and release['IMPLEMENTOR']=='Eclipse Adoptium' and release['JAVA_RUNTIME_VERSION']in ('21.0.13+9','21.0.13+9-LTS'),'fixed JDK release')
 need(props['java.vendor']=='Eclipse Adoptium' and props['java.runtime.version']in ('21.0.13+9','21.0.13+9-LTS') and props['os.arch']in ('amd64','x86_64'),'fixed actual runtime properties')
 rows=[x for x in j['files']if x['path']=='bin/java'];need(len(rows)==1 and type(rows[0].get('sha256'))is str and re.fullmatch('[0-9a-f]{64}',rows[0]['sha256']),'actual JDK java file pin')
 paths=[p for p,h in r['pins'].items()if p.endswith('/bin/java') and h==rows[0]['sha256']];need(len(paths)==1 and sha(paths[0])==rows[0]['sha256'],'actual java binary still same')
 return dict(scope='IDENTITY_ONLY_NOT_RUNTIME_OR_NUMERICAL_QUALIFICATION',inventory_sha256=expected,java_sha256=rows[0]['sha256'],version='21.0.13',vendor='Eclipse Adoptium',runtime_version=props['java.runtime.version'])

def project(repo,work,identity):
 closure(repo);need(read(work/'IDENTITY.json',4096)==identity,'same owning identity')
 c=read(work/'COMPLETE.json',65536)
 need(set(c)=={'schema','identity','source_pins_sha256','runtime_inventory_sha256','proof_sha256','canonical_sha256','normalized_sha256','sv_inputs','stage_count','numerical_pass','sv_repin_authorized'},'exact completion receipt')
 need(c['schema']=='SV_ONLY_RECONSTRUCTION_COMPLETE_V1' and c['identity']==identity and c['source_pins_sha256']==sha(D/'SOURCE_PINS.json') and c['canonical_sha256']==CANONICAL and c['normalized_sha256']==NORMALIZED and c['stage_count']==15 and c['numerical_pass']is False and c['sv_repin_authorized']is False,'completion exact scope binding')
 stages=[stage_row(n,work/n/'RESULT.json')for n,_,_ in STAGES]
 saved=read(work/'STAGES.json',65536);need(len(saved)==15,'parent complete15')
 for a,b in zip(saved,stages):need(a=={k:b[k]for k in a},'parent/actual stage receipt agreement')
 for side in ('old','new'):
  sv=work/(side+'_emit_sv')/'compiled-host/HostBlockTopV4.sv';canonical=work/(side+'_canonical')/'canonical.tsv';scan=read(work/(side+'_svscan')/'sv-identity.json',512<<10)
  need(sha(canonical)==CANONICAL[side] and scan['normalized_sha256']==NORMALIZED[side] and scan['raw_sha256']==sha(sv) and scan['bytes']==sv.stat().st_size and c['sv_inputs'][side]==dict(sha256=sha(sv),bytes=sv.stat().st_size),'generated canonical/SV drift')
 proof_path=work/'projection/proof.json';need(sha(proof_path)==c['proof_sha256'],'proof terminal digest')
 from sv_difference_projection import project_proof
 proof=project_proof(read(proof_path,65536))
 for side in ('old','new'):
  scan_path=work/(side+'_svscan')/'sv-identity.json';receipt=scan_path.parent/'RESULT.json'
  expected=dict(bytes=c['sv_inputs'][side]['bytes'],raw_sha256=c['sv_inputs'][side]['sha256'],normalized_sha256=NORMALIZED[side],metadata_sha256=sha(scan_path),scan_receipt_sha256=sha(receipt))
  need(proof['full_sv'][side]==expected,'proof bound actual full SV/scanner receipts')
 runtime=project_runtime(work/'jdk-runtime.json',c['runtime_inventory_sha256'],identity)
 return stages,proof,c,runtime

def main():
 ap=argparse.ArgumentParser()
 for n in ('repo','work','identity','job-start','output'):ap.add_argument('--'+n,type=pathlib.Path,required=True)
 a=ap.parse_args();identity=validate_identity(read(a.identity,4096));clock=read(a.job_start,4096)
 need(clock['schema']=='SAME_JOB_START_V1' and clock['job_budget_seconds']==WHOLE and clock['run_id']==identity['run_id'] and clock['launch_commit']==identity['launch_commit'] and 0<=time.monotonic()-clock['started_monotonic']<WHOLE,'whole-job export clock')
 need(a.output.is_absolute() and not a.output.exists() and not any(p.is_symlink()for p in (a.output,*a.output.parents)),'fresh export directory')
 # Failure reasons are closed vocabulary; arbitrary exception text/raw logs never exported.
 status='OBSERVATION_UNAVAILABLE_OR_INCOMPLETE';stages=[];c=None;runtime=None
 # Useful bounded terminal phase diagnostics survive a missing completion proof.
 try:
  for n,_,_ in STAGES:
   p=a.work/n/'RESULT.json'
   if not p.exists():break
   stages.append(stage_row(n,p,False))
 except (OSError,ValueError,KeyError,TypeError):stages=[]
 proof=dict(schema='SV_ONLY_PROOF_UNAVAILABLE_V1',status=status,numerical_pass=False,sv_repin_authorized=False)
 try:stages,proof,c,runtime=project(a.repo.resolve(),a.work.resolve(),identity);status='TWO_MODULE_PROJECTION_OBSERVED_NOT_PRODUCTION_ACCEPTANCE'
 except (OSError,ValueError,KeyError,TypeError,ImportError):pass
 need(time.monotonic()-clock['started_monotonic']<WHOLE-300,'retain artifact publication deadline')
 a.output.mkdir();write(a.output/'sv-only-proof.json',proof,65536)
 summary=dict(schema='SV_ONLY_SAVED_SAFE_SUMMARY_V1',status=status,artifact_identity=identity,source_pins_sha256=sha(D/'SOURCE_PINS.json'),runtime_provenance=runtime,stages=stages,proof_file=dict(name='sv-only-proof.json',bytes=(a.output/'sv-only-proof.json').stat().st_size,sha256=sha(a.output/'sv-only-proof.json')),canonical_sha256=CANONICAL,normalized_sha256=NORMALIZED,numerical_pass=False,sv_repin_authorized=False,full_m128_pass_count=0,final_rtl_replay=False,archive_link_executed=False,verilator_gcc_executed=False)
 write(a.output/'sv-only-summary.json',summary,65536);need(sum(p.stat().st_size for p in a.output.iterdir())<=131072,'two metadata files aggregate128KiB')
if __name__=='__main__':main()
