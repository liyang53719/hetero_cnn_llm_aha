"""Exercise actual C++ transport only. Negative fixtures never touch live runtime files."""
from pathlib import Path
import hashlib,json,subprocess,argparse
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
for flag in ('actual','probe','output'):parser.add_argument('--'+flag,type=Path,required=True)
a=parser.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False);rows=[]
for p in (1,2):
 d=a.actual.resolve()/f'profile{p}';original=(d/'runtime.tsv').read_text();views=(d/'views.tsv').read_text();probes=(d/'PRIVATE_PROBES.tsv').read_text()
 cases=[('actual',original,views,probes,True),('source_sha_corrupt',original,views.replace(views.splitlines()[1].split('\t')[-1],'0'*64,1),probes,False),('independent_probe_corrupt',original,views,probes.split('\t',1)[0]+'\t'+('00' if probes.split('\t',1)[1][:2]!='00' else '01')+probes.split('\t',1)[1][2:],False),('missing_allocation_view',original,'\n'.join([views.splitlines()[0]]+[x for x in views.splitlines()[1:] if x.split('\t')[1]!='input'])+'\n',probes,False)]
 for name,c,v,pr,ok in cases:
  t=out/f'p{p}_{name}';t.mkdir();(t/'views.tsv').write_text(v);(t/'PRIVATE_PROBES.tsv').write_text(pr);(t/'runtime.tsv').write_text(c.replace(str(d/'views.tsv'),str(t/'views.tsv')))
  r=subprocess.run([str(a.probe.resolve()),str(t/'runtime.tsv'),str(t/'PRIVATE_PROBES.tsv')],text=True,capture_output=True)
  if (r.returncode==0)!=ok:raise RuntimeError((p,name,r.returncode,r.stdout,r.stderr))
  rows.append({'profile':p,'case':name,'expected_accept':ok,'exit_code':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr.strip()})
(out/'RESULT.json').write_text(json.dumps({'status':'PASS_BYTE_PROVIDER_BOUNDARIES_AND_NEGATIVE_ADMISSION_ONLY','cases':rows,'dut_executed':False,'numeric_pass':False},indent=2)+'\n');print(json.dumps(rows))
