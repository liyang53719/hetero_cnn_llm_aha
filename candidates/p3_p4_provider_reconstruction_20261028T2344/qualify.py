"""Unchanged C++ Config/affine loader admission and raw-source boundary tests only."""
import argparse,json,subprocess,hashlib,resource
from pathlib import Path

def limits():
 resource.setrlimit(resource.RLIMIT_AS,(2560*1024*1024,2560*1024*1024))
 resource.setrlimit(resource.RLIMIT_CPU,(60,60))
 resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024))
def main(a):
 a.output.mkdir(exist_ok=False);rows=[];d=a.profile.resolve();cfg=(d/'runtime.tsv').read_text();views=(d/'views.tsv').read_text();probes=(d/'PRIVATE_PROBES.tsv').read_text()
 # Truncate expert dimension without changing allocated bytes: final expert must be rejected.
 truncated=[]
 for line in views.splitlines():
  fields=line.split('\t')
  if len(fields)==16 and fields[1]=='moe_weight_1':fields[6]='255,2048,512'
  truncated.append('\t'.join(fields))
 # Point gate at up half: source extent remains valid, raw boundary probes must disagree.
 swapped=[]
 for line in views.splitlines():
  fields=line.split('\t')
  if len(fields)==16 and fields[1]=='moe_weight_1':fields[9]=str(512*2048*2)
  swapped.append('\t'.join(fields))
 corrupt_probe=probes.split('\t',1)[0]+'\t'+('00' if probes.split('\t',1)[1][:2]!='00' else '01')+probes.split('\t',1)[1][2:]
 cases=[('actual',views,probes,True),('source_sha_corrupt',views.replace(views.splitlines()[1].split('\t')[-1],'0'*64,1),probes,False),('independent_probe_corrupt',views,corrupt_probe,False),('missing_input_view','\n'.join([views.splitlines()[0]]+[s for s in views.splitlines()[1:] if s.split('\t')[1]!='input'])+'\n',probes,False),('missing_last_expert','\n'.join(truncated)+'\n',probes,False),('gate_up_half_swap','\n'.join(swapped)+'\n',probes,False)]
 for name,v,pr,accept in cases:
  t=(a.output/name).resolve();t.mkdir();(t/'views.tsv').write_text(v);(t/'PRIVATE_PROBES.tsv').write_text(pr);(t/'runtime.tsv').write_text(cfg.replace(str(d/'views.tsv'),str(t/'views.tsv')))
  r=subprocess.run([str(a.probe.resolve()),str(t/'runtime.tsv'),str(t/'PRIVATE_PROBES.tsv')],capture_output=True,text=True,timeout=90,preexec_fn=limits)
  if (r.returncode==0)!=accept:raise RuntimeError((name,r.returncode,r.stdout,r.stderr))
  rows.append({'case':name,'expected_accept':accept,'exit_code':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr.strip()});print(rows[-1],flush=True)
 result={'status':'PASS_INPUT_ONLY_CPP_BOUNDARIES_AND_NEGATIVE_ADMISSION','dut_executed':False,'complete_block_numeric_pass':False,'cases':rows,'probe_binary_sha256':hashlib.sha256(a.probe.read_bytes()).hexdigest()};(a.output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for flag in ('profile','output','probe'):p.add_argument('--'+flag,type=Path,required=True)
 main(p.parse_args())
