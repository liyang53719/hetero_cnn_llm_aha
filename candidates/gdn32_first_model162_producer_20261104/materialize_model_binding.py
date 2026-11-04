"""Concrete FRONTEND_ONLY binding from already materialized job-local tools/sources.
No EDA/download. NEW observed tools must pass actual version/identity qualifications;
source selection is pinned by the checked-out commit and fixed R2/canonical gates.
"""
import stat,argparse,hashlib,json,pathlib,subprocess,os
import sys
K=pathlib.Path(__file__).resolve().parent
D=K.parent/'ci_frontend_materialization_r2_20261029'
sys.path.insert(0,str(D));sys.path.insert(0,str(K))
from provider_root_gate import validate_provider_roots,WRAPPER_SHA
from candidate_generation_gate import selected_inputs,checked_paths
def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser()
 for k in ['repo','pipeline','jdk_inventory','java','tools','idma','matrix','binding','output']:a.add_argument('--'+k.replace('_','-'),type=pathlib.Path,required=True)
 a.add_argument('--expected-repo-sha',required=True)
 a.add_argument('--hardware-source',choices=('legacy','transposed-tile-address-v1','prefill-supply-overlap-v1','gdn-chunk32-abort-v2'),default='legacy')
 flags=a.add_mutually_exclusive_group()
 flags.add_argument('--first-fault-readonly',action='store_true')
 flags.add_argument('--terminal-finite-readonly',action='store_true')
 flags.add_argument('--finite-full-watchdog',action='store_true')
 flags.add_argument('--profiled-host-diagnostic',action='store_true')
 v=a.parse_args();R=v.repo.resolve();C=v.pipeline.resolve();I=v.idma.resolve();T=v.tools.resolve();M=v.matrix.resolve()
 if v.hardware_source!='gdn-chunk32-abort-v2':
  old=v.repo.resolve()/'candidates/model_candidate_build_20261101'/pathlib.Path(__file__).name
  os.execve(sys.executable,[sys.executable,'-B',str(old),*sys.argv[1:]],dict(os.environ))
 sys.path.insert(0,str(C))
 selection=selected_inputs(R,v.hardware_source,v.first_fault_readonly,v.terminal_finite_readonly);contract=selection['contract']
 source_contract=R/'candidates/same_job_execution_20261030/numeric/MODEL_P0_SOURCE_CONTRACT.json'
 if selection['name']=='gdn-chunk32-abort-v2':
  from candidate_generation_gate import MODEL162_SOURCE_CONTRACT_REL,MODEL162_SOURCE_CONTRACT_SHA
  source_contract=R/MODEL162_SOURCE_CONTRACT_REL;need(sha(source_contract)==MODEL162_SOURCE_CONTRACT_SHA,'exact actual162 P0 source roles')
 if selection['name']=='prefill-supply-overlap-v1':
  from model_source_evidence import PREFILL_CONTRACT_REL,PREFILL_CONTRACT_SHA
  source_contract=R/PREFILL_CONTRACT_REL;need(sha(source_contract)==PREFILL_CONTRACT_SHA,'exact prefill P0 source contract')
 head=subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()
 need(head==v.expected_repo_sha and len(head)==40,'independently reviewed checkout commit')
 need(C.is_relative_to(R) and D.is_relative_to(R),'published source candidates must be in reviewed checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True)
 tracked=subprocess.check_output(['git','-C',str(R),'ls-files'],text=True).splitlines()
 for folder in (C,D,K):
  for sourcefile in folder.glob('*.py'):
   need(str(sourcefile.relative_to(R)) in tracked,'untracked executable candidate source')
 need(not v.binding.exists() and not v.output.exists(),'fresh binding/output')
 j=json.loads(v.jdk_inventory.read_text());need(j['status']=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION' and not j['old_pass_transfer'],'new JDK receipt')
 java=v.java.resolve();jh=java.parent.parent;jdk_aliases=[];external_pins={}
 for x in j['files']:
  p=jh/x['path']
  if 'symlink' in x:
   need(p.is_symlink() and os.readlink(p)==x['symlink'] and str(p.resolve(strict=True))==x['resolved_target'],'JDK symlink drift')
   jdk_aliases.append(dict(path=str(p),link=x['symlink'],target=x['resolved_target']))
   if 'external_dependency' in x:
    e=x['external_dependency'];target=pathlib.Path(e['resolved_target'])
    need(x['path']=='lib/security/cacerts' and str(target)=='/etc/ssl/certs/adoptium/cacerts','only public JDK truststore alias')
    need(stat.S_ISREG(target.stat().st_mode) and not target.is_symlink() and target.stat().st_size==e['bytes'] and 0<=e['bytes']<=4*1024**2 and sha(target)==e['sha256'],'external JDK dependency drift')
    external_pins[str(target)]=e['sha256']
  else:need(p.is_file() and p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],'JDK file drift')
 need(sha(I/'SHA256SUMS.json')=='a699b8074b8099e00859d5174c0a5fb6b5a171a28cad30bab8dd96226dc67b19','exact original idma manifest')
 im=json.loads((I/'SHA256SUMS.json').read_text())
 for n,h in im.items():need(sha(I/n)==h,'iDMA source drift '+n)
 source=[];inc=[];defs=[]
 for line in (I/'idma.f.in').read_text().splitlines():
  if not line.strip():continue
  if line.startswith('+incdir+'):target=inc;value=str(I/line[len('+incdir+@ROOT@/'):])
  elif line.startswith('+define+'):target=defs;value=line[len('+define+'):]
  elif line.startswith('@ROOT@/'):target=source;value=str(I/line[len('@ROOT@/'):])
  else:raise ValueError('unreviewed filelist syntax '+line)
  if value not in target:target.append(value)
 need(len(source)==294 and len(inc)==8 and len(defs)==4,'exact iDMA filelist closure')
 matrix=json.loads((D/'MATRIX_REPO_SOURCE_MAP.json').read_text())['files']
 for row in matrix:need(sha(M/row['name'])==row['sha256'],'matrix source drift')
 # Original iDMA filelist excludes tc_clk; Matrix closure supplies it exactly once.
 wrapper=R/'rtl/integration/idma_backend_rw_axi_flat_wrap.sv'
 need(str(wrapper.relative_to(R)) in tracked and wrapper.is_file() and not wrapper.is_symlink() and sha(wrapper)==WRAPPER_SHA,'exact tracked original iDMA wrapper required')
 providers=source+[str(M/r['name']) for r in matrix]+[str(wrapper)]
 provider_root_receipt=validate_provider_roots(providers)
 need(len(providers)==308,'294 iDMA +13 matrix/clock +1 wrapper required')
 need(sum(pathlib.Path(p).name=='tc_clk.sv' for p in providers)==1,'single tc_clk definition')
 backend=R/'candidates/fresh_non_dpi_backend_recovery_20261028/source'
 driver_headers=R/'candidates/host_runtime_non_dpi_backend/source'
 helpers=[C/n for n in ['CanonicalHighGate.scala','CanonicalInfoMicroTest.scala','PortableHostDenseAccMemoryLowering.scala','PortableHostMatrixResultFifoMemoryLowering.scala']]+[K/n for n in ['CandidateDenseAccMemoryLoweringV2.scala','ModelCandidateHighDescriptorV1.scala','ModelCandidateHostSimulationEmitterV1.scala','ModelCandidateTransformGateV1.scala']]+[backend/n for n in ['PhysicalFmaStageLibrary.scala','RetainedBackendCircuitGate.scala','RetainedEndpointPortContract.scala','RetainedServicePhaseObserver.scala']]
 driver=R/'candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'
 need(sha(driver)=='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61','V3 driver')
 if selection['name']=='gdn-chunk32-abort-v2':
  from model162_driver_policy import OLD_REL,NEW_REL,inverse
  original_driver=driver;driver=R/NEW_REL;inverse(original_driver.read_bytes(),driver.read_bytes())
 finite=None
 if v.finite_full_watchdog:
  from finite_watchdog_policy import RELATION,OLD_REL,NEW_REL,SOURCE_REL,SELF_REL,inverse
  need(v.hardware_source=='transposed-tile-address-v1','finite ordinary watchdog only corrected159')
  inverse((R/OLD_REL).read_bytes(),(R/NEW_REL).read_bytes());finite=dict(RELATION);driver=R/NEW_REL
 host_profile=None
 if v.profiled_host_diagnostic:
  from host_profile_policy import load as load_profile,REL as PROFILE_REL,REL_SHA as PROFILE_REL_SHA,DRIVER_REL as PROFILE_DRIVER_REL,CONTRACT_REL as PROFILE_CONTRACT_REL,HARDWARE as PROFILE_HARDWARE
  need(v.hardware_source==PROFILE_HARDWARE,'profiled mapper requires explicit supply159')
  host_profile=load_profile(R);driver=R/PROFILE_DRIVER_REL;source_contract=R/PROFILE_CONTRACT_REL
 diagnostic=None
 if v.first_fault_readonly or v.terminal_finite_readonly:
  from first_fault_policy import load_source_contract,contract_path,contract_sha,contract_roles,SOURCE_CONTRACT_REPO_PATH,SOURCE_CONTRACT_SHA
  diagnostic=load_source_contract(R,terminal=v.terminal_finite_readonly);driver=R/diagnostic['diagnostic_driver']['repo_path']
  CONTRACT_REPO_PATH=contract_path(diagnostic);CONTRACT_SHA=contract_sha(diagnostic);ROLES=contract_roles(diagnostic)
 paths=[str(p) for folder in (C,D,K) for p in folder.iterdir() if p.is_file() and p.suffix in ('.py','.json','.scala','.vlt','.tsv')]+providers+list(map(str,helpers))+[str(java),str(T/'verilator'),str(pathlib.Path('/usr/bin/make').resolve()),str(pathlib.Path('/usr/bin/python3').resolve()),str(D/'hierarchy_r7.vlt'),str(driver),str(selection['overlay']),str(K/'candidate_generation_gate.py'),str(selection['contract_path']),str(K/'MODEL_CANDIDATE_PRECONDITIONS.json'),str(C/'prepare_fma_subset.py'),str(R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json')]
 paths += [str(R/'candidates/same_job_execution_20261030/SOURCE_PINS.json'),str(source_contract),str(R/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json')]
 paths += [str(driver.parent/n) for n in ('resident_observation.hpp','moe_raw_score_observation.hpp')]
 paths += [str(I/n) for n in im]+[str(driver_headers/n) for n in ['affine_readonly_memory.hpp','affine_tsv_loader.hpp','sparse_write_memory.hpp']]
 vm=json.loads((D/'VERILATOR_MANIFEST.json').read_text())
 for x in vm['files']:
  if not x['path'].startswith(('usr/bin/','usr/share/verilator/')):continue
  p=T/'verilator-package'/x['path'];need(sha(p)==x['sha256'],'Verilator closure');paths.append(str(p))
 original=R/'candidates/fresh_original_top_recovery_20261028'
 om=json.loads((original/'SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
 paths+=checked_paths(R,selection['overlay'],om,contract)
 need(all(str(pathlib.Path(p).relative_to(R))in tracked for p in checked_paths(R,selection['overlay'],om,contract))and all(str(selection[k].relative_to(R))in tracked for k in ('overlay','contract_path')),'tracked selected model source closure')
 for x in om['jars']:
  p=original/'cache'/x['maven_path'];need(sha(p)==x['sha256'],'exact JAR/toolchain pin');paths.append(str(p))
 paths += [str((jh/x['path']).resolve(strict=True)) for x in j['files'] if 'sha256' in x]
 if finite is not None:
  paths += [str(R/rel)for rel in(OLD_REL,NEW_REL,SOURCE_REL,SELF_REL)]
  need(all(rel in tracked for rel in(OLD_REL,NEW_REL,SOURCE_REL,SELF_REL)),'tracked finite ordinary watchdog inputs')
 if diagnostic is not None:
  paths += [str(R/diagnostic[n]['repo_path']) for n in ROLES]+[str(R/CONTRACT_REPO_PATH),str(R/SOURCE_CONTRACT_REPO_PATH)]
  need(sha(R/SOURCE_CONTRACT_REPO_PATH)==SOURCE_CONTRACT_SHA,'first-fault P0 source contract')
  need(all(str(Path.relative_to(R))in tracked for Path in [R/diagnostic[n]['repo_path'] for n in ROLES]+[R/CONTRACT_REPO_PATH,R/SOURCE_CONTRACT_REPO_PATH]),'tracked first-fault inputs')
 if host_profile is not None:
  profile_paths=[R/PROFILE_REL,R/PROFILE_CONTRACT_REL]+[R/x['repo_path']for x in host_profile['sources'].values()]
  need(all(str(p.relative_to(R))in tracked for p in profile_paths),'tracked profiled host source closure')
  paths+=list(map(str,profile_paths))
 if selection['name']=='gdn-chunk32-abort-v2':
  from candidate_generation_gate import UPSTREAM_DIR,LEGACY_DIR,MODEL162_CATALOG_REL,MODEL162_NUMERIC_REL
  paths.append(str(R/MODEL162_CATALOG_REL))
  paths.append(str(R/MODEL162_NUMERIC_REL))
  need(MODEL162_NUMERIC_REL in tracked,'tracked actual162 numeric runner source')
  paths += [str(R/UPSTREAM_DIR/n)for n in ('GENERATION_CONTRACT.json','MODEL_SOURCE_OVERLAY.json')]
  paths.append(str(R/'candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'))
  paths += [str(R/LEGACY_DIR/n)for n in ('candidate_generation_gate.py','MODEL_SOURCE_OVERLAY.json','GENERATION_CONTRACT.json','MODEL_CANDIDATE_PRECONDITIONS.json')]
 pins={p:sha(p) for p in dict.fromkeys(paths)};pins.update(external_pins)
 b=dict(provider_root_receipt=provider_root_receipt,schema='MODEL_CANDIDATE_BUILD_BINDING_V1',mode='BUILD_ONLY',candidate_status='UNREVIEWED_MODEL_BUILD',numeric_execution_authorized=False,generation_contract=str(selection['contract_path']),generation_contract_sha256=selection['contract_sha256'],hardware_source=selection['name'],unchanged_module_contract=str(K/'MODEL_CANDIDATE_PRECONDITIONS.json'),host_port_contract=str(C/'OBSERVER_HOST_PORTS_122.json'),model_source_contract=str(source_contract),jdk_aliases=jdk_aliases,repo=str(R),repo_sha=v.expected_repo_sha,java=str(java),verilator=str(T/'verilator'),make=str(pathlib.Path('/usr/bin/make').resolve()),python=str(pathlib.Path('/usr/bin/python3').resolve()),pins=pins,provider_sources=providers,idma_include_dirs=inc,idma_defines=defs,hierarchy=str(D/'hierarchy_r7.vlt'),driver=str(driver),driver_include=str(driver_headers),helper_sources=list(map(str,helpers)),output=str(v.output.resolve()),fixed_source_overlay=str(selection['overlay']),fixed_source_validator=str(K/'candidate_generation_gate.py'),sv_identity_script=str(K/'observe_model_sv.py'),materialized_roots=[str(T),str(I.parent.parent),str(M),str(C),str(D),str(K)])
 if host_profile is not None:
  b['host_profile_driver']={'path':str(R/PROFILE_REL),'sha256':PROFILE_REL_SHA}
  from host_profile_policy import binding_policy as profile_binding
  profile_binding(b)
 if finite is not None:
  b['finite_watchdog_driver']=finite;b['model_source_contract']=str(R/SOURCE_REL)
  from finite_watchdog_policy import binding_policy as finite_binding
  finite_binding(b)
 if diagnostic is not None:
  b['first_fault_driver_contract']={'path':str(R/CONTRACT_REPO_PATH),'sha256':CONTRACT_SHA}
  b['model_source_contract']=str(R/SOURCE_CONTRACT_REPO_PATH)
  from first_fault_policy import binding_policy
  binding_policy(b)
 v.binding.write_text(json.dumps(b,indent=2)+'\n');v.binding.with_suffix('.sha256').write_text(sha(v.binding)+'\n')
 print('MODEL_CANDIDATE_BINDING_NOT_ACCEPTED_NOT_EXECUTED '+sha(v.binding))
if __name__=='__main__':main()
