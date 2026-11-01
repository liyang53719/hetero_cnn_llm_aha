"""Actual reuse-core negative gates; small fresh copies only, never DUT/data writes."""
import argparse,hashlib,importlib.util,json,pathlib,shutil,sys
P=pathlib.Path
ap=argparse.ArgumentParser()
for n in ('core','binding','provider','output'):ap.add_argument('--'+n,type=P,required=True)
ap.add_argument('--core-sha256',required=True);ap.add_argument('--binding-sha256',required=True)
a=ap.parse_args()
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
need(a.core.is_file() and sha(a.core)==a.core_sha256,'actual core pin');need(sha(a.binding)==a.binding_sha256,'binding pin')
need(a.output.is_absolute() and not a.output.exists() and not a.output.is_symlink(),'fresh negative root')
a.output.mkdir()
spec=importlib.util.spec_from_file_location('actual_negative_reuse_core',a.core);core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
# No test is allowed to read a large input file, start processes, or use network.
def audit(event,args):
 if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn') or event.startswith('socket.'):raise RuntimeError('negative process/network forbidden')
 if event=='open' and isinstance(args[0],(str,bytes)):
  p=P(args[0])
  if p.is_file() and p.stat().st_size>2<<20:raise RuntimeError('negative large-file read forbidden')
sys.addaudithook(audit)
results=[]
def rejected(name,fn,message):
 try:fn()
 except ValueError as e:need(str(e)==message,'unexpected rejection '+str(e));results.append(dict(case=name,rejected=True,reason=str(e)))
 else:raise ValueError('negative accepted '+name)
badout=a.output/'wrong_digest_destination'
rejected('wrong_binding_digest_before_write',lambda:core.materialize(a.binding,'0'*64,badout),'pin hash')
need(not badout.exists(),'bad binding wrote destination')
for name in ('input_root','program_hash'):
 dest=a.output/name;shutil.copytree(a.provider,dest)
 need(sum(p.stat().st_size for p in dest.rglob('*') if p.is_file())<128<<10,'small provider metadata only')
 rp=dest/'RESULT.json';r=json.loads(rp.read_text())
 for group in ('program_pins','metadata_pins'):
  for row in r[group].values():row['path']=str(dest/P(row['path']).relative_to(a.provider))
 if name=='input_root':r['input_root']=str(a.output/'unapproved_input_root')
 else:r['program_pins']['commands']['sha256']='0'*64
 rp.write_text(json.dumps(r,indent=2)+'\n')
 rejected(name,lambda:core.verify_materialized(a.binding,a.binding_sha256,dest),'same admitted data binding' if name=='input_root' else 'pin hash')
safe=dict(scope='ACTUAL_CORE_SMALL_NEGATIVE_GATES_ONLY',core_sha256=a.core_sha256,binding_sha256=a.binding_sha256,cases=results,large_input_read_allowed=False,positive_provider_modified=False,dut_executed=False,numerical_pass=False)
with (a.output/'SAFE_NEGATIVE_RESULT.json').open('x')as f:json.dump(safe,f,indent=2);f.write('\n')
print(json.dumps(safe))
