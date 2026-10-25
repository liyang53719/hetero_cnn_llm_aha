"""Reconstruct symbolic ABI metadata only, never real SV/model/weights or native code."""
import argparse,hashlib,importlib.util,json
from pathlib import Path

def need(ok,why):
    if not ok:raise ValueError(why)
def checked(path,pin):
    path=Path(path)
    need(not path.is_symlink() and path.is_file() and path.resolve()==path.absolute(),'regular non-symlink source')
    data=path.read_bytes()
    need(len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],'source bytes/hash drift')
    return data

def read_json(path):return json.loads(Path(path).read_text())
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def rebuild(repository_root,output,package_root=None):
    package=Path(package_root) if package_root is not None else Path(__file__).resolve().parent
    root=Path(repository_root).resolve();output=Path(output).absolute()
    need(not output.exists() and not output.is_symlink() and output.parent.resolve()==output.parent and output.parent.is_dir(),'fresh output in existing non-symlink parent')
    pins=read_json(package/'pins/SOURCE_PINS.json');refs=read_json(package/'pins/EXISTING_PUBLIC_REFERENCES.json')['references'];data={}
    for ref in refs:
        rel=Path(ref['repo_path']);need(not rel.is_absolute() and '..' not in rel.parts,'safe reference path')
        data[ref['repo_path']]=checked(root/rel,ref)
    stem='candidates/qwen2_core_client_sv_structure/'
    previous=json.loads(data[stem+'pins/SOURCE_PINS.json'])['expectation'];types_ref=previous['top_types_public_reference']
    types_raw=data[types_ref['repo_path']]
    need(len(types_raw)==types_ref['bytes'] and hashlib.sha256(types_raw).hexdigest()==types_ref['sha256'],'top types pin')
    derive=module(root/(stem+'derive_ports.py'),'public_fixed_type_flattener')
    ports=derive.derive(json.loads(types_raw)['review'])
    expectation=json.loads(data[stem+'EXPECTATION_TEMPLATE.json']);expectation['top_ports']=ports
    topabi=json.loads(checked(package/'TOP_ABI_TEMPLATE.json',pins['top_abi_template']));topabi['ports']=ports
    sources={row['name']:checked(package/row['public_path'],row) for row in pins['source_files']}
    generator=module(package/'source/generate_abi.py','public_fixed_abi_generator')
    header,mapping=generator.generate(ports)
    blobs={'STRUCTURE_EXPECTATION.json':encoded(expectation),'TOP_ABI.json':encoded(topabi),'generated_abi.hpp':header.encode(),'ABI_MAPPING.json':encoded(mapping)}
    for name,b in blobs.items():need(len(b)==pins['reconstructed'][name]['bytes'] and hashlib.sha256(b).hexdigest()==pins['reconstructed'][name]['sha256'],'reconstruction mismatch '+name)
    # Preserve the original generators/tests' relative layout in a fresh output, not Git.
    destinations={'STRUCTURE_EXPECTATION.json':'qwen2_core_client_sv_offline_prepare_20261025T1956/STRUCTURE_EXPECTATION.json','TOP_ABI.json':'qwen2_core_client_verilator_source_review_20261025T2045/TOP_ABI.json','generated_abi.hpp':'harness/generated_abi.hpp','ABI_MAPPING.json':'harness/ABI_MAPPING.json'}
    planned={destinations[n]:b for n,b in blobs.items()}
    for name in sorted(sources):planned['harness/'+name]=sources[name]
    output.mkdir()
    for rel,b in planned.items():
        p=output/rel;p.parent.mkdir(exist_ok=True,parents=True)
        with p.open('xb') as stream:stream.write(b)
    return {'status':'PASS_SYMBOLIC_ABI_METADATA_ONLY','reconstructed':pins['reconstructed'],'copied_original_sources':7,'target_compiler_or_model_executed':False}

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repository-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();print(json.dumps(rebuild(v.repository_root,v.output)))
if __name__=='__main__':main()
