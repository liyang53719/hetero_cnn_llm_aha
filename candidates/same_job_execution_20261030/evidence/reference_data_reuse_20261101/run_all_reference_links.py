"""Actual five-profile readonly hardlink checks only; parent-supervised, no DUT."""
import argparse,hashlib,importlib.util,json,pathlib,sys
P=pathlib.Path
p=argparse.ArgumentParser()
for n in ('repo','binding','output'):p.add_argument('--'+n,type=P,required=True)
for n in ('source-pins-sha256','binding-sha256'):p.add_argument('--'+n,required=True)
a=p.parse_args()
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def checked(p,h):
 need(p.is_absolute()and p==p.resolve()and p.is_file()and all(not x.is_symlink()for x in(p,*p.parents)),'canonical pinned file');need(sha(p)==h,'pin drift');return p
sys.addaudithook(lambda event,args:(_ for _ in()).throw(RuntimeError('NO_PROCESS_OR_NETWORK'))if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn')or event.startswith('socket.')else None)
repo=a.repo.absolute();catalog=repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json';rows=json.loads(checked(catalog,a.source_pins_sha256).read_text())['files'];seen=set()
for row in rows:
 rel=P(row['path']);need(not rel.is_absolute()and '..'not in rel.parts and str(rel)not in seen,'unique source role');seen.add(str(rel));f=checked(repo/rel,row['sha256']);need(f.stat().st_size==row['bytes'],'source bytes')
binding=checked(a.binding,a.binding_sha256);b=json.loads(binding.read_text());context=b['context'];need(context['repo']==str(repo),'same actual source')
corepath=repo/'candidates/same_job_execution_20261030/numeric/reference_data_reuse.py';need(str(corepath.relative_to(repo))in seen,'core source role')
s=importlib.util.spec_from_file_location('actual_reference_reuse',corepath);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
verified=m.verify_metadata(pin(binding),context)
out=a.output.absolute();need(out==out.resolve()and not out.exists()and all(not x.is_symlink()for x in(out,*out.parents)),'fresh output');out.mkdir()
results=[];total=0;count=0
for i in range(5):
 root=out/f'profile{i}';root.mkdir();row=verified['reference_pins'][str(i)];ref=m.link_reference(row,root,i,pin(binding),context);m.verify_materialized(row,root,i,pin(binding),context)
 old=P(row['path']);doc=json.loads(old.read_text());unique={v['file']:v for v in doc['tensor_records'].values()};n=0
 for rel,v in unique.items():
  before=(old.parent/rel).stat();after=(ref/rel).stat();need((before.st_dev,before.st_ino)==(after.st_dev,after.st_ino),'same inode');n+=after.st_size
 x=old.stat();y=(ref/'RESULT.json').stat();need((x.st_dev,x.st_ino)!=(y.st_dev,y.st_ino)and sha(ref/'RESULT.json')==row['sha256'],'fresh exact reference metadata')
 total+=n;count+=len(unique);results.append(dict(profile=i,tensor_files=len(unique),tensor_bytes=n,same_inode=True,fresh_result=True))
for i in range(5):m.verify_materialized(verified['reference_pins'][str(i)],out/f'profile{i}',i,pin(binding),context)
need(count==122 and total==44262400,'exact actual five tensor domain')
safe=dict(scope='ACTUAL_FIVE_REFERENCE_HARDLINKS_ONLY_NO_DUT',source_catalog_sha256=a.source_pins_sha256,source_catalog_count=len(rows),binding_sha256=a.binding_sha256,core_sha256=sha(corepath),profiles=results,tensor_files=count,tensor_bytes=total,pre_and_post_full_hash_inode_checks=True,numerical_pass=False,dut_executed=False,execution_admitted=False)
with (out/'SAFE_RESULT.json').open('x')as f:json.dump(safe,f,indent=2);f.write('\n')
print(json.dumps(safe))
