"""Concrete FRONTEND_ONLY binding from already materialized job-local tools/sources.
No EDA/download. NEW observed tools must pass actual version/identity qualifications;
source selection is pinned by the checked-out commit and fixed R2/canonical gates.
"""
import stat,argparse,hashlib,json,pathlib,subprocess,os
from provider_root_gate import validate_provider_roots,WRAPPER_SHA
D=pathlib.Path(__file__).parent.resolve()
def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser()
 for k in ['repo','pipeline','jdk_inventory','java','tools','idma','matrix','canonical','binding','output']:a.add_argument('--'+k.replace('_','-'),type=pathlib.Path,required=True)
 a.add_argument('--expected-repo-sha',required=True)
 v=a.parse_args();R=v.repo.resolve();C=v.pipeline.resolve();I=v.idma.resolve();T=v.tools.resolve();M=v.matrix.resolve()
 head=subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()
 need(head==v.expected_repo_sha and len(head)==40,'independently reviewed checkout commit')
 need(C.is_relative_to(R) and D.is_relative_to(R),'published source candidates must be in reviewed checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True)
 tracked=subprocess.check_output(['git','-C',str(R),'ls-files'],text=True).splitlines()
 for folder in (C,D):
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
 need(sha(v.canonical)=='90464ff45917c1b853c7d1b36e67dd5e43b5503b7fa0583704ee615c08919533','approved fixed canonical')
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
 helpers=[C/n for n in ['CanonicalHighGate.scala','CanonicalInfoMicroTest.scala','PortableHostDenseAccMemoryLowering.scala','PortableHostMatrixResultFifoMemoryLowering.scala','PortableHostHighSimulationEmitter.scala','NewToolchainTransformGate.scala']]+[backend/n for n in ['PhysicalFmaStageLibrary.scala','RetainedBackendCircuitGate.scala','RetainedEndpointPortContract.scala','RetainedServicePhaseObserver.scala']]
 driver=R/'candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'
 need(sha(driver)=='f4f00dffd348e1822e7fcb5ac59602579d693d7a8d04e221cdd3f0255b56b04c','V3 driver')
 paths=[str(p) for folder in (C,D) for p in folder.iterdir() if p.is_file() and p.suffix in ('.py','.json','.scala','.vlt','.tsv')]+providers+list(map(str,helpers))+[str(java),str(T/'verilator'),str(pathlib.Path('/usr/bin/make').resolve()),str(pathlib.Path('/usr/bin/python3').resolve()),str(D/'hierarchy_r7.vlt'),str(driver),str(v.canonical.resolve()),str(D/'FIXED_SOURCE_OVERLAY_R2.json'),str(D/'fixed_sources.py'),str(C/'prepare_fma_subset.py'),str(R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json')]
 paths += [str(R/'candidates/same_job_execution_20261030/numeric/LOCKED_SOURCE_CONTRACT.json'),str(R/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json')]
 paths += [str(driver.parent/n) for n in ('resident_observation.hpp','moe_raw_score_observation.hpp')]
 paths += [str(I/n) for n in im]+[str(driver_headers/n) for n in ['affine_readonly_memory.hpp','affine_tsv_loader.hpp','sparse_write_memory.hpp']]
 vm=json.loads((D/'VERILATOR_MANIFEST.json').read_text())
 for x in vm['files']:
  if not x['path'].startswith(('usr/bin/','usr/share/verilator/')):continue
  p=T/'verilator-package'/x['path'];need(sha(p)==x['sha256'],'Verilator closure');paths.append(str(p))
 original=R/'candidates/fresh_original_top_recovery_20261028'
 om=json.loads((original/'SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
 from fixed_sources import checked_paths
 paths+=checked_paths(R,D/'FIXED_SOURCE_OVERLAY_R2.json',om)
 for x in om['jars']:
  p=original/'cache'/x['maven_path'];need(sha(p)==x['sha256'],'exact JAR/toolchain pin');paths.append(str(p))
 paths += [str((jh/x['path']).resolve(strict=True)) for x in j['files'] if 'sha256' in x]
 pins={p:sha(p) for p in dict.fromkeys(paths)};pins.update(external_pins)
 b=dict(provider_root_receipt=provider_root_receipt,schema='FRESH155_SINGLE_BINARY_M128_V1',mode='FRONTEND_ONLY',jdk_aliases=jdk_aliases,repo=str(R),repo_sha=v.expected_repo_sha,java=str(java),verilator=str(T/'verilator'),make=str(pathlib.Path('/usr/bin/make').resolve()),python=str(pathlib.Path('/usr/bin/python3').resolve()),pins=pins,canonical_manifest=str(v.canonical.resolve()),canonical_manifest_sha256=sha(v.canonical),provider_sources=providers,idma_include_dirs=inc,idma_defines=defs,hierarchy=str(D/'hierarchy_r7.vlt'),driver=str(driver),driver_include=str(driver_headers),helper_sources=list(map(str,helpers)),output=str(v.output.resolve()),fixed_source_overlay=str(D/'FIXED_SOURCE_OVERLAY_R2.json'),fixed_source_validator=str(D/'fixed_sources.py'),sv_identity_script=str(D/'check_fresh_sv.py'),materialized_roots=[str(T),str(I.parent.parent),str(M),str(C),str(D)])
 v.binding.write_text(json.dumps(b,indent=2)+'\n');v.binding.with_suffix('.sha256').write_text(sha(v.binding)+'\n')
 print('FRONTEND_BINDING_PREPARED_NOT_EXECUTED '+sha(v.binding))
if __name__=='__main__':main()
