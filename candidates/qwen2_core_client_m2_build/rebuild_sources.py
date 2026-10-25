"""Rebuild original source/test layout + closed-form synthetic expectations only.
No compiler, target model, native binary, raw input, or runtime permission.
"""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path

def need(ok,why):
 if not ok:raise ValueError(why)
def read(path,pin):
 p=Path(path);need(p.is_file() and not p.is_symlink() and p.resolve()==p.absolute(),'regular non-symlink source')
 b=p.read_bytes();need(len(b)==pin['bytes'] and hashlib.sha256(b).hexdigest()==pin['sha256'],'bytes/hash drift');return b

def rebuild(root,abi,output,package=None):
 root=Path(root).resolve();out=Path(output).absolute();package=Path(package or Path(__file__).resolve().parent)
 need(not out.exists() and not out.is_symlink() and out.parent.is_dir() and out.parent.resolve()==out.parent,'fresh output under regular existing parent')
 pins=json.loads((package/'pins/SOURCE_PINS.json').read_text());refs=json.loads((package/'pins/EXISTING_PUBLIC_REFERENCES.json').read_text())['references'];refbytes={}
 for row in refs:
  p=Path(row['repo_path']);need(not p.is_absolute() and '..' not in p.parts,'safe reference');refbytes[str(p)]=read(root/p,row)
 blobs={'m2_source/'+r['name']:read(package/r['public_path'],r) for r in pins['source_files']}
 ab=read(abi,pins['reconstructed']['generated_abi.hpp']);blobs['m2_source/generated_abi.hpp']=ab
 blobs['qwen2_core_client_verilator_m1_prepare_20261025T2044/generated_abi.hpp']=ab
 blobs['qwen2_core_client_verilator_m1_prepare_20261025T2044/m1_main.cpp']=refbytes['candidates/qwen2_core_client_codegen/source/m1_main.cpp']
 blobs['qwen2_core_client_verilator_build_prepare_20261025T2143/check_build.py']=refbytes['candidates/qwen2_core_client_build/source/check_build.py']
 # Generator and imported closed-form reference bytes were verified above; import has no target actions.
 sp=importlib.util.spec_from_file_location('frozen_M2_reference_source',package/'source/generate_reference.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);b=m.render().encode();want=pins['reconstructed']['expected_m2.hpp'];need(len(b)==want['bytes'] and hashlib.sha256(b).hexdigest()==want['sha256'],'expected header exact reconstruction');blobs['m2_source/expected_m2.hpp']=b
 out.mkdir()
 for rel,b in blobs.items():
  p=out/rel;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(b)
 return {'status':'PASS_ORIGINAL_SOURCE_AND_SYNTHETIC_HEADER_ASSEMBLY_ONLY','files':len(blobs),'bytes':sum(map(len,blobs.values())),'target_compiled_or_run':False}
if __name__=='__main__':
 sys.dont_write_bytecode=True;a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repository-root',type=Path,required=True);a.add_argument('--abi-header',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args();print(json.dumps(rebuild(x.repository_root,x.abi_header,x.output)))
