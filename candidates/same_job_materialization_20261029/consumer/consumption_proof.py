"""Cross-check existing producer ledgers and actual pinned process receipts.
Missing retained evidence fails closed. No compiler/DUT/process execution.
"""
import hashlib,json,pathlib
P=pathlib.Path
OVERLAY_SHA='f8cb8f64819e7f2dd4f3778cc6066e18d062ec1102832f53ef6eabfbcace4b39'
SCALA={'helper':'DiagnoseOriginalHostMoePhaseV5.scala','host_top':'HostBlockTopV4.scala','host_commands':'HostBlockCommandsV4.scala','owner_kernel':'QwenOwnerProtocol.scala','qkv_router':'Public21QkvReductionRouter.scala','resident':'FfnResidentCoordinator.scala','bridge':'FfnTileSiluBridge.scala'}
ROLES={**{k:'FIXED155_SCALA_INPUT' for k in SCALA},'driver':'FRONTEND_EXE_DRIVER','sparse_memory':'DRIVER_INCLUDE_HEADER','program_manifest':'RUNTIME_PROGRAM_METADATA','commands':'RUNTIME_COMMAND_BYTES','descriptors':'RUNTIME_DESCRIPTOR_BYTES'}
def need(v,s):
 if not v:raise ValueError(s)
def h(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read_pin(pin,cap=2*1024**2):
 p=P(pin['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink() and p.stat().st_size==pin['bytes'] and p.stat().st_size<=cap and h(p)==pin['sha256'],'retained consumption evidence pin');return p.read_bytes()
def absolute(s):
 need(isinstance(s,str) and P(s).is_absolute() and '..' not in P(s).parts,'canonical producer absolute path');return s

def validate(m,policy,identity,common,evidence):
 need(m['schema']=='FIXED_COMMON_SOURCE_IDENTITY_V1','actual producer source manifest schema')
 need(m['source_commit']==identity['source_commit'] and m['matrix_macs']==4096 and m['vector_lanes']==32,'actual producer source/resources')
 need(m['sv_sha256']==common['sv']['sha256'] and m['driver_sha256']==common['driver']['sha256']==policy['source_pins']['driver']['sha256'],'actual common SV/driver identity')
 generation=m['generation_input_pins'];sources=m['source_pins'];gates=m['verified_gate_pins'];physical=m['physical_closure']
 need(type(generation)is dict and type(sources)is dict and type(gates)is dict and generation and sources and gates,'existing producer ledgers required')
 need(physical['top_raw_sha256']==common['sv']['sha256'],'physical raw SV identity')
 need(evidence['schema']=='P0_RETAINED_PRODUCER_EVIDENCE_V2','retained evidence schema')
 embedded=m['p0_retained_evidence'];need(embedded['schema']=='P0_EMBEDDED_ACTUAL_BUILD_EVIDENCE_V1','actual producer embedded evidence')
 import importlib.util
 dep_path=P(__file__).with_name('driver_dependency_proof.py')
 need(h(dep_path)=='2990680766c3780f41241e48445e173b042a0a6371dd018edda4f92d26c04f07','reviewed actual dependency verifier')
 spec=importlib.util.spec_from_file_location('actual_driver_dep',dep_path);dep=importlib.util.module_from_spec(spec);spec.loader.exec_module(dep)
 original=json.loads(dep.check_text(embedded['original_source_manifest'],16*1024**2))
 need(original=={k:v for k,v in m.items()if k not in ('files','observation_policy_bindings','p0_retained_evidence')},'original prebuild source fields preserved exactly')
 driver_dependency=json.loads(read_pin(evidence['driver_dependency']))
 need(driver_dependency==embedded['driver_dependency'],'actual embedded driver dependency record')
 local=evidence['files'];need(type(local)is dict and set(local)==set(embedded['files']),'exact embedded retained evidence file pins')
 for original_path,v in local.items():need(v['sha256']==embedded['files'][original_path]['sha256'] and v['bytes']==embedded['files'][original_path]['bytes'],'embedded original receipt/overlay pin')
 overlay_path=absolute(m['fixed_source_overlay'])
 need(generation[overlay_path]==OVERLAY_SHA and local[overlay_path]['sha256']==OVERLAY_SHA,'existing fixed overlay ledger')
 overlay=json.loads(read_pin(local[overlay_path]));rows=overlay['files'];need(overlay['source_count']==len(rows)==155,'exact fixed155')
 byname={r['name']:r for r in rows};need(len(byname)==155,'unique fixed155 names')
 row=byname[SCALA['host_commands']];suffix='/'+row['repo_path']
 matches=[p for p,v in sources.items() if p.endswith(suffix) and v==row['sha256']]
 need(len(matches)==1,'unique actual fixed HostCommands source path')
 repo=absolute(matches[0][:-len(suffix)])
 paths=[]
 for r in rows:
  rel=P(r['repo_path']);need(not rel.is_absolute() and '..' not in rel.parts,'overlay relative path')
  path=str(P(repo)/rel);paths.append(path)
  need(generation[path]==sources[path]==r['sha256'],'all155 existing generation/source hashes')
 for name,filename in SCALA.items():
  row=byname[filename];p=str(P(repo)/row['repo_path']);anchor=policy['source_pins'][name]
  need(row['bytes']==anchor['bytes'] and row['sha256']==anchor['sha256'],'fixed155 actual role anchor '+name)
 required={overlay_path}
 def receipt(key,stage):
  paths=[p for p in gates if P(p).name=='RESULT.json' and P(p).parent.name==stage];need(len(paths)==1,'unique actual stage receipt path')
  path=absolute(paths[0]);required.add(path);item=local[path]
  need(item['sha256']==gates[path],'retained receipt bound by existing verified_gate_pins')
  r=json.loads(read_pin(item))
  need(r['native_exit']==0 and r['errors']==[] and r['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','actual completed source stage')
  need(type(r['argv'])is list and all(isinstance(x,str) for x in r['argv']),'actual stage argv')
  return r['argv'],str(P(path).parent)
 compile_args,compiled_dir=receipt('compile155','compile155')
 need(len(compile_args)==15+len(paths),'exact actual compiler argv length')
 java=absolute(compile_args[0]);cp=compile_args[7];plugin=compile_args[11].removeprefix('-Xplugin:')
 need(java in generation and all(p in generation and p.endswith('.jar') for p in cp.split(':')) and plugin in generation and plugin.endswith('.jar'),'existing Java/jar/plugin generation pins')
 common_java=[java,'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m']
 expected_compile=common_java+['-Xmx2g','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.']+paths
 need(compile_args==expected_compile,'exact original Java/scalac entry/options/output/source order')
 constructor,_=receipt('original_high','original_high')
 need(constructor==common_java+['-Xmx4g','-cp',compiled_dir+':'+cp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'],'exact original resident constructor entry/classpath order')
 need(set(local)==required,'only exactly retained overlay/compile/constructor evidence')
 argv=physical['initial_frontend_argv'];need(type(argv)is list and '--cc' in argv and '--exe' in argv and '--build' not in argv and argv.count('--top-module')==1 and argv[argv.index('--top-module')+1]=='HostBlockTopV4','actual frontend role argv')
 drivers=[p for p,v in sources.items() if v==policy['source_pins']['driver']['sha256'] and p in argv]
 need(len(drivers)==1,'unique actual driver source role')
 driver=absolute(drivers[0])
 need(argv.count(driver)==1 and generation[driver]==sources[driver]==common['driver']['sha256'],'actual --exe driver consumed')
 # Actual GCC dependency selection replaces the unsupported same-directory shortcut.
 build=json.loads(P(common['build_receipt']['path']).read_text())
 sparse=dep.verify(driver_dependency,m,policy,common,build,repo)
 need(driver_dependency['driver']==driver,'actual --exe dependency role')
 driver_local=P(policy['source_pins']['driver']['path']).read_text()
 need('#include "sparse_write_memory.hpp"' in driver_local,'actual direct quoted include')
 # Program anchors are not Scala compilation inputs. Bind only exact runtime
 # program files already independently decoded by the corrector and view pins.
 for name in ('program_manifest','commands','descriptors'):
  need(policy['source_pins'][name]['path'] not in compile_args,'runtime program cannot be Scala compile source')
 sv_paths=[p for p in argv if p.endswith('/HostBlockTopV4.sv')];need(len(sv_paths)==1 and gates[sv_paths[0]]==common['sv']['sha256'],'actual frontend SV bound by existing gate ledger')
 return {'status':'CHECKED_EXISTING_PRODUCER_LEDGERS_AND_PINNED_STAGE_ARGV_NOT_NUMERICAL','fixed155_count':155,'roles':ROLES,'header_resolution_scope':'ACTUAL_FRESH_GCC_NON_SYSTEM_DEPENDENCY_RULE_BOUND_TO_HOST_LINK'}
