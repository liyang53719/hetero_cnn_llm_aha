"""Exact source-only M3 assembly from pinned public M2 sources and a strict delta.
No compiler, model, native executable, real SV, actual log, or execution grant.
"""
import argparse,hashlib,importlib.util,json,re,sys
from pathlib import Path

def need(ok,why):
 if not ok:raise ValueError(why)
def read(path,pin):
 p=Path(path);need(p.is_file() and not p.is_symlink() and p.resolve()==p.absolute(),'regular non-symlink source')
 b=p.read_bytes();need(len(b)==pin['bytes'] and hashlib.sha256(b).hexdigest()==pin['sha256'],'bytes/hash drift');return b

def apply_delta(original,patch):
 lines=original.decode().splitlines(True);p=patch.decode().splitlines(True)
 need(p[:2]==['--- a/m2_main.cpp\n','+++ b/m2_main.cpp\n'],'exact one-file delta headers')
 out=[];cursor=0;i=2
 while i<len(p):
  m=re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n',p[i]);need(m is not None,'strict hunk header');start=int(m[1])-1;count=int(m[2] or 1);newstart=int(m[3])-1;newcount=int(m[4] or 1)
  need(cursor<=start<=len(lines),'ordered hunk');out+=lines[cursor:start];cursor=start;need(len(out)==newstart,'new hunk position');i+=1;oldn=newn=0
  while i<len(p) and not p[i].startswith('@@ '):
   row=p[i];need(row[:1] in [' ','-','+'],'delta line');kind=row[0];body=row[1:]
   if kind in [' ','-']:need(cursor<len(lines) and lines[cursor]==body,'exact original hunk');cursor+=1;oldn+=1
   if kind in [' ','+']:out.append(body);newn+=1
   i+=1
  need((oldn,newn)==(count,newcount),'exact hunk lengths')
 out+=lines[cursor:];return ''.join(out).encode()

def rebuild(root,abi,output,package=None):
 root=Path(root).resolve();out=Path(output).absolute();package=Path(package or Path(__file__).resolve().parent)
 need(not out.exists() and not out.is_symlink() and out.parent.is_dir() and out.parent.resolve()==out.parent,'fresh output under regular existing parent')
 pins=json.loads((package/'pins/SOURCE_PINS.json').read_text());refs=json.loads((package/'pins/EXISTING_PUBLIC_REFERENCES.json').read_text())['references'];rb={}
 for row in refs:
  p=Path(row['repo_path']);need(not p.is_absolute() and '..' not in p.parts,'safe reference');rb[str(p)]=read(root/p,row)
 blobs={}
 for row in pins['source_files']:
  p=Path(row['public_path']);need(not p.is_absolute() and '..' not in p.parts and Path(row['name']).name==row['name'],'safe source');blobs['m3_source/'+row['name']]=read(package/p,row)
 for row in pins['referenced_source_files']:
  need(Path(row['name']).name==row['name'],'safe referenced output');b=rb[row['repo_path']];need(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'referenced source identity');blobs['m3_source/'+row['name']]=b
 delta=pins['cpp_delta'];need(delta['patch']=='M2_TO_M3_SOURCE.patch' and delta['output_name']=='m3_main.cpp','fixed delta target');b=apply_delta(rb[delta['baseline_repo_path']],read(package/delta['patch'],delta['patch_identity']));need(len(b)==delta['bytes'] and hashlib.sha256(b).hexdigest()==delta['sha256'],'exact reconstructed C++');blobs['m3_source/m3_main.cpp']=b
 ab=read(abi,pins['reconstructed']['generated_abi.hpp']);blobs['m3_source/generated_abi.hpp']=ab
 old='qwen2_core_client_verilator_m2_prepare_20261025T2307/'
 blobs[old+'generated_abi.hpp']=ab
 for name in ['m2_main.cpp','reference_events.py']:blobs[old+name]=rb['candidates/qwen2_core_client_m2_build/source/'+name]
 blobs['qwen2_core_client_verilator_build_prepare_20261025T2143/check_build.py']=rb['candidates/qwen2_core_client_build/source/check_build.py']
 out.mkdir()
 for rel,b in blobs.items():
  p=out/rel;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(b)
 # Only verified closed-form source is imported. Failure leaves a fresh partial output, never modifies inputs.
 sp=importlib.util.spec_from_file_location('frozen_M3_reference_source',out/'m3_source/generate_reference.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);b=m.render().encode();want=pins['reconstructed']['expected_m3.hpp'];need(len(b)==want['bytes'] and hashlib.sha256(b).hexdigest()==want['sha256'],'exact scalar/scripted header reconstruction')
 with (out/'m3_source/expected_m3.hpp').open('xb') as f:f.write(b)
 return {'status':'PASS_ORIGINAL_SOURCE_AND_SYNTHETIC_HEADER_ASSEMBLY_ONLY','files':len(blobs)+1,'bytes':sum(map(len,blobs.values()))+len(b),'target_compiled_or_run':False}
if __name__=='__main__':
 sys.dont_write_bytecode=True;a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repository-root',type=Path,required=True);a.add_argument('--abi-header',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args();print(json.dumps(rebuild(x.repository_root,x.abi_header,x.output)))
