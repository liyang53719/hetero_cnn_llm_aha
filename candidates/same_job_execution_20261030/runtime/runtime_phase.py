"""Fresh owning-job installation from the unchanged locked lifecycle overlay.
No archive acquisition, model import/forward or DUT. Original installer selfchecks
remain exactly those of the admitted source; not numerical qualification.
"""
import argparse,hashlib,importlib.util,json,pathlib,platform,sys
P=pathlib.Path

def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def install(b,key):
 need(key in ('qwen2','qwen35_08b','qwen35_35b'),'selected runtime')
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64'and 'avx512f'in P('/proc/cpuinfo').read_text().split(),'original installation ABI/P0 capability')
 for p,h in b['pins'].items():need(sha(p)==h,'source/archive/tool drift')
 need(str(P(sys.executable).resolve())==b['python'],'exact owning interpreter')
 source=P(b['source_dir']);m=module('locked_runtime_install',source/'prepare_runtimes.py');items,specs,torch=m.artifacts();cache=P(b['cache']);out=P(b['install_root'])
 if key=='qwen2':home,site,wrapper,receipt=m.qwen2_install(out,cache,items)
 else:home,site,wrapper,receipt=m.qwen35_install(key,out,P(b['repo']),cache,specs[key],[])
 contract=json.loads((source/'RUNTIME_CONTRACT.json').read_text());framework=next(x for x in items if x['name']=='transformers')if key=='qwen2'else specs[key]['transformers']
 derive=module('original_archive_sidecar',source/'derive_sidecar.py');side=home/'SOURCE_SIDECAR.json'
 derive.derive(contract['entries'][key]['revision'],cache/framework['filename'],framework['sha256'],cache/torch['filename'],side)
 need(m.digest(side)==contract['entries'][key]['expected_sidecar_sha256'],'independent original sidecar');m.verify_sidecar(site,side)
 result=dict(scope='FRESH_INSTALL_ARCHIVE_SOURCE_BOUND_NOT_REFERENCE_TESTED',runtime=key,wrapper=m.record(wrapper),installation=m.record(receipt),sidecar=m.record(side),site=str(site),python=m.record(P(sys.executable).resolve()))
 with (P(b['result_root'])/(key+'_RESULT.json')).open('x')as f:json.dump(result,f,indent=2);f.write('\n')
 for p,h in b['pins'].items():need(sha(p)==h,'post-install source/archive/tool drift')
 return result

def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);a.add_argument('--runtime',required=True);v=a.parse_args()
 need(sha(v.binding)==v.binding_sha256,'independently admitted phase binding');install(json.loads(v.binding.read_text()),v.runtime)
if __name__=='__main__':main()
