"""Explicit existing-install adoption; archive reading/hash only, never Torch/install.
Review binding, memory/disk/time admission externally BEFORE --execute-reviewed.
"""
import argparse,importlib.util,json,pathlib
import shared_runtime as s
P=pathlib.Path
DERIVE_SHA='e96130e044520444758b913ba38f7fe774ac752675daf85aaa95da77e136e274'
def prepare(repo,binding,binding_sha,out):
 s.need(s.sha(binding)==binding_sha,'reviewed original install/artifact input binding');b=s.read(binding)
 s.need(b['schema']=='THREE_INSTALLS_ARCHIVE_ADOPTION_V1' and set(b['entries'])==set(s.KEYS),'all three original installations')
 job=P(b['owner_root']).resolve();out=s.inside(P(out).resolve(),job)
 s.need(not out.exists(),'fresh output only')
 s.need(s.shutil.disk_usage(job).free>=8*(1<<30),'original setup 8GiB free gate')
 s.need(s.sys.version_info[:2]==(3,12) and s.platform.machine()=='x86_64','original Python/x86_64 ABI')
 s.need('avx512f' in P('/proc/cpuinfo').read_text().split(),'original P0 AVX512 gate')
 for e in b['entries'].values():
  root=s.inside(e['import_root'],job).resolve();s.need(not out.is_relative_to(root) and not root.is_relative_to(out),'metadata disjoint from imports')
  for key in ('installation','installation_run','install_binding','sample_source','sample_receipt','wrapper','python','framework_archive','torch_archive'):s.checked(e[key])
 helper=P(repo)/'candidates/ci_single_profile_runtime_20261029/derive_sidecar.py';s.need(s.sha(helper)==DERIVE_SHA,'original archive helper')
 spec=importlib.util.spec_from_file_location('locked_original_sidecar',helper);derive=importlib.util.module_from_spec(spec);spec.loader.exec_module(derive)
 out.mkdir();entries={}
 for key,original in b['entries'].items():
  side=out/(key+'_SOURCE_SIDECAR.json');derive.derive(s.CONTRACT[key][0],P(original['framework_archive']['path']),original['framework_archive']['sha256'],P(original['torch_archive']['path']),side)
  s.need(s.sha(side)==s.CONTRACT[key][1],'exact original independently locked sidecar')
  entries[key]={k:v for k,v in original.items() if k not in ('framework_archive','torch_archive')};entries[key]['sidecar']=s.pin(side)
 adopted=out/'INSTALL_BINDING.json';adopted.write_text(json.dumps(dict(schema='EXISTING_THREE_INSTALLS_BINDING_V1',owner_root=str(job),entries=entries,source_binding=s.pin(binding),derive_source=s.pin(helper)),indent=2)+'\n')
 return s.bind(adopted,s.sha(adopted),out/'owner')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=P,required=True);ap.add_argument('--binding',type=P,required=True);ap.add_argument('--binding-sha256',required=True);ap.add_argument('--output',type=P,required=True);ap.add_argument('--execute-reviewed',action='store_true');a=ap.parse_args();s.need(a.execute_reviewed,'explicit reviewed archive/tree scan only');print(json.dumps(prepare(a.repo,a.binding,a.binding_sha256,a.output)))
