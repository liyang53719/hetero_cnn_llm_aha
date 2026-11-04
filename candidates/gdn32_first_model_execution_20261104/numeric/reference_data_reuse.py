"""Approved readonly reference tensor hardlinks; fresh metadata, never DUT PASS."""
import hashlib,json,os,stat
from pathlib import Path
MODE='STAGE_COVERAGE_DIAGNOSTIC'
SCOPE='READONLY_REFERENCE_TENSOR_HARDLINKS_NOT_DUT_PASS'
COUNTS=(24,19,26,23,30)
BYTES=(10650624,6439936,7259136,9563136,10349568)
TREE=12037043872

def need(value,message):
 if not value:raise ValueError(message)
def digest(path):
 with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(path,directory=False):
 p=Path(path);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents)),'canonical nonalias path')
 s=p.lstat();need(stat.S_ISDIR(s.st_mode)if directory else stat.S_ISREG(s.st_mode),'regular expected type');return p

def checked(row,content=True,cap=128<<20):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact pin')
 need(type(row['bytes'])is int and 0<row['bytes']<=cap,'pin bytes')
 h=row['sha256'];need(type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'pin SHA256')
 p=canonical(row['path']);need(p.stat().st_size==row['bytes'],'size drift')
 if content:need(digest(p)==h,'hash drift')
 return p

def read(row):return json.loads(checked(row,cap=2<<20).read_text())
def pin(path):
 p=canonical(str(path));return dict(path=str(p),bytes=p.stat().st_size,sha256=digest(p))
def inventory(reference,result):
 root=Path(reference['path']).parent;files={}
 for v in result['tensor_records'].values():
  rel=Path(v['file']);need(not rel.is_absolute()and '..'not in rel.parts and len(rel.parts)>=2 and rel.parts[0]in('input_only','reference_only'),'segregated tensor path')
  row=dict(path=str(root/rel),bytes=v['bytes'],sha256=v['sha256'])
  need(str(rel)not in files or files[str(rel)]==row,'duplicate reference mismatch');files[str(rel)]=row
 return files

def verify_metadata(reuse_pin,b):
 d=read(reuse_pin)
 need(set(d)=={'schema','scope','execution_mode','context','references','tensor_files','tensor_bytes','tree_cap','numerical_pass'},'exact reference reuse schema')
 need(d['schema']=='READONLY_REFERENCE_REUSE_V1'and d['scope']==SCOPE and d['execution_mode']in(MODE,'P0_FIRST_FAULT_DIAGNOSTIC') and d['numerical_pass']is False,'explicit data-only stage reuse')
 need(set(d['context'])=={'repo','artifact_manifest','retained_materials'}and all(d['context'][k]==b[k]for k in d['context']),'current reference context')
 if d['execution_mode']=='P0_FIRST_FAULT_DIAGNOSTIC':need(b.get('execution_mode')==d['execution_mode'],'first-fault reference exact binding mode')
 if 'execution_mode'in b:need(b['execution_mode']==d['execution_mode'],'exact diagnostic reuse mode')
 canonical(b['repo'],True);read(b['artifact_manifest']);retained=read(b['retained_materials'])
 need(set(d['references'])==set(d['tensor_files'])=={str(i)for i in range(5)},'all five references')
 need(type(d['tensor_bytes'])is int and d['tensor_bytes']==sum(BYTES)and type(d['tree_cap'])is int and d['tree_cap']==TREE,'exact removed tensor bytes and tighter cap')
 roots=[]
 for i in range(5):
  key=str(i);row=d['references'][key];need(row==retained['references'][key]['result'],'exact admitted retained reference')
  r=read(row);need(type(r['profile']['profile'])is int and r['profile']['profile']==i and r['complete_block_tokens']==128 and r['hardware_executed']is False and r['exact_baseline_observer_output_equal']is True and r['router_policy']=='UNMODIFIED_OFFICIAL_TORCH_TOPK','original reference semantics')
  files=inventory(row,r);need(files==d['tensor_files'][key]and len(files)==COUNTS[i]and sum(v['bytes']for v in files.values())==BYTES[i],'exact tensor inventory')
  for v in files.values():checked(v,False)
  roots.append(str(canonical(str(Path(row['path']).parent),True)))
 need(len(set(roots))==5,'distinct five reference roots')
 return dict(scope=SCOPE,roots=roots,reference_pins=d['references'],tensor_files=d['tensor_files'],tensor_bytes=sum(BYTES),tree_cap=TREE,reuse_binding_sha256=reuse_pin['sha256'])

def selected(row,out,profile,reuse_pin,context):
 need(type(profile)is int and profile in range(5),'selected profile')
 v=verify_metadata(reuse_pin,context);need(row==v['reference_pins'][str(profile)],'selected approved reference')
 out=canonical(str(out),True)
 need(all(not out.is_relative_to(Path(r))and not Path(r).is_relative_to(out)for r in v['roots']),'fresh output separate from retained reference')
 return v,out

def link_one(row,dest):
 src=checked(row);before=src.stat();need(not dest.exists()and not dest.is_symlink(),'fresh link only')
 canonical(str(dest.parent),True)
 os.link(src,dest,follow_symlinks=False) # EXDEV and all errors propagate; never copy fallback.
 s=canonical(str(dest)).stat();after=src.stat()
 need((s.st_dev,s.st_ino,s.st_size)==(before.st_dev,before.st_ino,before.st_size)==(after.st_dev,after.st_ino,after.st_size),'same original inode')
 need(digest(dest)==row['sha256']and digest(src)==row['sha256'],'linked tensor hash')

def receipt_doc(row,profile,reuse_pin,context,files):
 return dict(schema='READONLY_REFERENCE_LINK_RECEIPT_V1',scope=SCOPE,profile=profile,reuse_binding=reuse_pin,context=context,reference_result=row,tensor_files=files,tensor_bytes=sum(v['bytes']for v in files.values()),numerical_pass=False,hardware_executed=False)

def link_reference(row,out,profile,reuse_pin,context):
 v,out=selected(row,out,profile,reuse_pin,context);target=out/'reference';need(not target.exists()and not target.is_symlink(),'fresh reference directory');target.mkdir()
 files=v['tensor_files'][str(profile)]
 for rel,entry in files.items():
  dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);link_one(entry,dest)
 with (target/'RESULT.json').open('xb')as f:f.write(checked(row).read_bytes())
 need(digest(target/'RESULT.json')==row['sha256'],'fresh RESULT exact copy')
 with (out/'REFERENCE_REUSE_RECEIPT.json').open('x')as f:json.dump(receipt_doc(row,profile,reuse_pin,context,files),f,indent=2);f.write('\n')
 verify_materialized(row,out,profile,reuse_pin,context);return target

def verify_materialized(row,out,profile,reuse_pin,context):
 v,out=selected(row,out,profile,reuse_pin,context);target=canonical(str(out/'reference'),True);rp=canonical(str(out/'REFERENCE_REUSE_RECEIPT.json'));need(rp.stat().st_size<=2<<20,'bounded link receipt')
 files=v['tensor_files'][str(profile)];need(json.loads(rp.read_text())==receipt_doc(row,profile,reuse_pin,context,files),'exact fresh link evidence')
 actual=set()
 for parent,dirs,names in os.walk(target,followlinks=False):
  for name in dirs:canonical(str(Path(parent)/name),True)
  for name in names:actual.add(str(canonical(str(Path(parent)/name)).relative_to(target)))
 need(actual==set(files)|{'RESULT.json'},'exact fresh reference inventory')
 need(digest(target/'RESULT.json')==row['sha256'],'fresh reference RESULT pin')
 need((target/'RESULT.json').stat().st_ino!=Path(row['path']).stat().st_ino or (target/'RESULT.json').stat().st_dev!=Path(row['path']).stat().st_dev,'RESULT not shared inode')
 for rel,entry in files.items():
  src=checked(entry);dst=canonical(str(target/rel));s=src.stat();t=dst.stat()
  need((s.st_dev,s.st_ino,s.st_size)==(t.st_dev,t.st_ino,t.st_size),'same retained tensor inode');need(digest(dst)==entry['sha256'],'materialized tensor hash')
 return target
