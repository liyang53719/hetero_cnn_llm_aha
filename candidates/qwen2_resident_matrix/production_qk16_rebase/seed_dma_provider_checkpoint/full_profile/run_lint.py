"""Fixed original iDMA wrapper lint qualification; no simulation or automatic retries."""
import argparse,hashlib,json,re,signal,time
from pathlib import Path
import owned_compile
P=Path(__file__).resolve().parent
TOP='ProductionQk16KernelBench'
WRAP='hetero_cnn_llm_aha/rtl/integration/idma_backend_rw_axi_flat_wrap.sv'
WRAP_SHA='a82bc50fac9b29df3f5f68527361f9dfac4792dfea3178b84eb488428d8d12c0'
PROVIDER='idma_source_export_attempt_v8_20261017/source/idma_export/'
TOOLROOT='production_qkv_native_tools_v10_20261017/usr/share/verilator/'
TOOL='production_qkv_native_tools_v10_20261017/usr/bin/verilator_bin'
TOOL_SHA='619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def waiver_text(root,rows,pins):
 rules=sorted({(r['rule'],r['file'],r['line']) for r in rows if r['rule'] in ('WIDTHEXPAND','WIDTHTRUNC')})
 need(len(rows)==24 and len(rules)==21,'fixed warning inventory')
 need(sum(r['rule']=='PINMISSING' for r in rows)==1,'warning inventory')
 for r in rows:need(pins[r['file']]==r['source_sha256'],'warning source hash binding')
 return '`verilator_config\n'+''.join(f'lint_off -rule {rule} -file "{root/path}" -lines {line}\n' for rule,path,line in rules)
HINT_TARGETS=[
 ('isolate_assignments','cc_passthrough_stream_fifo','valid_o',PROVIDER+'deps/common_cells/src/cc_passthrough_stream_fifo.sv',r'output\s+logic\s+valid_o\s*,'),
 ('isolate_assignments','idma_axi_write','first_w',PROVIDER+'idma/src/backend/idma_axi_write.sv',r'logic\s+first_w\s*;'),
 ('isolate_assignments','idma_axi_write','last_w',PROVIDER+'idma/src/backend/idma_axi_write.sv',r'logic\s+last_w\s*;'),
 ('isolate_assignments','idma_channel_coupler','aw_sent',PROVIDER+'idma/src/backend/idma_channel_coupler.sv',r'logic\s+aw_sent\s*;'),
 ('isolate_assignments','cc_passthrough_stream_fifo','ready_o',PROVIDER+'deps/common_cells/src/cc_passthrough_stream_fifo.sv',r'output\s+logic\s+ready_o\s*,'),
 ('split_var','idma_axi_write','write_req_o',PROVIDER+'idma/src/backend/idma_axi_write.sv',r'output\s+write_req_t\s+write_req_o\s*,'),
 ('split_var','idma_axi_read','read_req_o',PROVIDER+'idma/src/backend/idma_axi_read.sv',r'output\s+read_req_t\s+read_req_o\s*,'),
 ('split_var','idma_axi_read','read_rsp_i',PROVIDER+'idma/src/backend/idma_axi_read.sv',r'input\s+read_rsp_t\s+read_rsp_i\s*,'),
]
def validate_hints(root,c,text):
 expected=[f'{rule} -module "{module}" -var "{var}"' for rule,module,var,_,_ in HINT_TARGETS]
 active=[x.strip() for x in text.splitlines() if x.strip() and not x.strip().startswith('//')]
 need(active==['`verilator_config']+expected,'unmatched or extra structural rule')
 module_bodies={}
 for item in c['source_order']:
  raw=(root/item['path']).read_text();clean=re.sub(r'//[^\n]*|/\*.*?\*/',lambda m:'\n'*m[0].count('\n'),raw,flags=re.S)
  for m in re.finditer(r'\bmodule\s+([A-Za-z_$][\w$]*)\b(.*?)\bendmodule\b',clean,re.S):module_bodies.setdefault(m[1],[]).append((item['path'],m[2]))
 matches=[]
 for rule,module,var,path,decl in HINT_TARGETS:
  bodies=module_bodies.get(module,[]);need(len(bodies)==1 and bodies[0][0]==path,'hint module not unique/matched '+module)
  need(len(re.findall(decl,bodies[0][1]))==1,'hint variable not unique/matched '+module+'.'+var)
  matches.append({'rule':rule,'module':module,'variable':var,'source':path,'source_sha256':sha(root/path),'declaration_matches':1})
 return matches
def overlay_sources(original,delta):
 old={'path':delta['old_path'],'sha256':delta['old_sha256']};new={'path':delta['new_path'],'sha256':delta['new_sha256']}
 need(original.count(old)==1,'exact one old provider')
 need(not any(x['path']==new['path'] for x in original),'overlay already present')
 return [new if x==old else x for x in original]
def prepare(root):
 need(re.fullmatch(r'[A-Za-z0-9_./-]+',str(root)) is not None,'unsafe workspace path')
 own=json.loads((P/'ARTIFACT_HASHES.json').read_text());pins=json.loads((P/'INPUT_PINS.json').read_text());c=json.loads((P/'LINT_PLAN_REDUCED.json').read_text());rows=json.loads((P/'WARNINGS.json').read_text())['warnings']
 need(all(sha(P/n)==h for n,h in own.items()),'runner drift')
 need(c['top']==TOP and len(c['source_order'])==307 and {'path':WRAP,'sha256':WRAP_SHA} in c['source_order'],'top/wrapper/source inventory')
 need(pins[TOOL]==TOOL_SHA and pins[WRAP]==WRAP_SHA,'fixed tool/parameters')
 need(set(c['initial_defines'])=={'TARGET_ASIC','TARGET_RTL','TARGET_SYNTHESIS','TARGET_VERILATOR'} and all(v=='' for v in c['initial_defines'].values()),'macro profile')
 need(len(c['include_directory_order'])==8,'include inventory')
 for n,h in pins.items():
  f=root/n;need(f.is_file() and not f.is_symlink() and sha(f)==h,'input drift '+n)
 for prefix in (PROVIDER,TOOLROOT):
  entries=list((root/prefix).rglob('*'));need(not any(f.is_symlink() for f in entries),'provider/tool symlink')
  need({str(f.relative_to(root)) for f in entries if f.is_file()}=={n for n in pins if n.startswith(prefix)},'full inventory drift')
 for x in c['source_order']:need(pins[x['path']]==x['sha256'],'composition binding')
 for d in c['include_directory_order']:need((root/d).is_dir() and not (root/d).is_symlink(),'include boundary')
 need(sha(root/'idma_wrapper_lint_attempt_v3_20261017/receipt.json')=='409f759ac62b573219de97f65b21e3f938908f2dc4ce6faf160711f82004db00','wrapper proof binding')
 need((P/'structural_hints.vlt').read_bytes()==(root/'idma_read_packed_hints_v1_20261017/structural_hints.vlt').read_bytes(),'exact reviewed eight hints')
 need((P/'structural_hints.vlt').read_bytes().startswith((root/'idma_wrapper_lint_runner_v3_20261017/structural_hints.vlt').read_bytes()),'original six hints unchanged prefix')
 prior=json.loads((root/'production_qk16_kernel_collection_sv_attempt_v2_20261017/receipt.json').read_text())
 need(prior['status']=='PASS_COLLECTION_SV_GENERATION_INVENTORY_ONLY' and prior['sv']['sha256']==c['source_order'][-1]['sha256'],'same common SV')
 original=json.loads((root/'production_qk16_kernel_link_plan_v2_20261017/COMPOSITION.json').read_text())['sources_ordered']
 excluded={r['path'] for r in c['excluded_library_candidates_lexical_only']}
 need(excluded=={PROVIDER+'deps/axi_stream/src/axi_stream_cut.sv',PROVIDER+'deps/axi_stream/src/axi_stream_multicut.sv'},'exact excluded unused libraries')
 delta=json.loads((P/'PROVIDER_DELTA.json').read_text())
 need(c['source_order']==overlay_sources([r for r in original if r['path'] not in excluded],delta),'307 exact single provider overlay')
 need(pins[delta['old_path']]==delta['old_sha256'] and pins[delta['new_path']]==delta['new_sha256'],'provider delta binding')
 need(sha(root/delta['component_receipt'])==delta['component_receipt_sha256'],'component receipt binding')
 component=json.loads((root/delta['component_receipt']).read_text())
 need(component['status']=='PASS_ENDPOINT_COMPONENT_LINT_ONLY' and component['postflight_complete'] and component['endpoint_lane_configuration']==512,'component prerequisite')
 need(sha(root/delta['fix_manifest_path'])==delta['fix_manifest_sha256'],'source model binding')
 need(all(r['instance'] is None or r['instance'].startswith('ProductionQk16KernelBench.dma.backend.u_backend') for r in rows),'original wholeBench warning context')
 validate_hints(root,c,(P/'structural_hints.vlt').read_text())
 return c,pins,waiver_text(root,rows,pins)
def run(a):
 start=time.monotonic();stop=start+210
 need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
 def alarm(s,f):raise TimeoutError('absolute deadline')
 old=signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,15)
 try:
  need(a.execute,'explicit execute required');need(not a.out.exists() and not a.out.is_symlink(),'fresh out')
  root=a.workspace.resolve(strict=True);out=a.out.resolve();need(out.is_relative_to(root),'output workspace boundary')
  available=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));need(available>=8*1024**3,'need at least8GiB available for6GiB AS trial');c,pins,waivers=prepare(root);hints=(P/'structural_hints.vlt').read_text();matches=validate_hints(root,c,hints);out.mkdir();(out/'fixed_width.vlt').write_text(waivers);(out/'structural_hints.vlt').write_text(hints)
  cmd=[str(root/TOOL),'--lint-only','-fno-inline','-fno-dfg','--top-module',TOP,'--threads','1','--no-std','--relative-includes','--timescale','1ns/1ps','--Mdir',str(out/'obj_dir'),str(out/'fixed_width.vlt'),str(out/'structural_hints.vlt')]
  cmd+=['+define+'+n for n in c['initial_defines']]+['+incdir+'+str(root/n) for n in c['include_directory_order']]+[str(root/x['path']) for x in c['source_order']]
  r=dict(resource_preflight=dict(initial_mem_available_bytes=available,minimum_available_bytes=8*1024**3,scope='HOST_AVAILABLE_SNAPSHOT_NOT_RESERVATION_OR_TREE_HARD_LIMIT'),status='NOT_COMPLETED',scope='FULL_FIXED_4096MAC_BENCH_PROVIDER_LINT_ONLY',tool_optimization_delta=['-fno-inline','-fno-dfg'],provider_delta=json.loads((P/'PROVIDER_DELTA.json').read_text()),top=TOP,total_budget_seconds=210,tool_budget_seconds=180,source_count=307,waiver_rules=21,structural_hint_targets=matches,structural_hint_semantics='assignment_isolation_and_packed_field_splitting_not_warning_suppression',target_match_scope='unique_pinned_source_declarations_not_internal_tool_telemetry',whole_bench=True,simulation=False,numerical=False,stages=[])
  signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));(out/'argv.json').write_text(json.dumps(cmd,indent=2)+'\n');(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
  spawn_available=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));r['resource_preflight']['before_spawn_mem_available_bytes']=spawn_available;(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');need(spawn_available>=8*1024**3,'available memory changed before spawn')
  with (out/'lint.log').open('xb') as log:
   signal.setitimer(signal.ITIMER_REAL,0)
   try:result=owned_compile.execute(cmd,cwd=out,log=log,cleanup_helper=P/'strict_cleanup.py',absolute_stop=stop,stage_stop=min(stop-10,time.monotonic()+180),cleanup_seconds=10)
   finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
  r['stages'].append(result);(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
  prepare(root);need((out/'fixed_width.vlt').read_text()==waivers,'waiver postflight');need((out/'structural_hints.vlt').read_text()==hints,'hint postflight');r['postflight_complete']=True
  limits=json.loads((out/'native_limits.json').read_text());need(limits==dict(as_limit=[6442450944,6442450944],file_limit=[16777216,16777216],affinity_count=1),'limits drift');r['native_limits']=limits
  need(not any(f.suffix in ['.cpp','.o','.so','.a'] for f in out.rglob('*')),'native build forbidden')
  r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name!='receipt.json'}
  r['elapsed_seconds']=time.monotonic()-start;r['status']='PASS_FULL_BENCH_PROVIDER_LINT_ONLY' if result['exit_code']==0 and result['error'] is None and result['cleanup_complete'] else 'FAIL_FULL_BENCH_PROVIDER_LINT'
  temp=out/'receipt.pending.json';temp.write_text(json.dumps(r,indent=2)+'\n');need(time.monotonic()<stop,'absolute deadline');temp.replace(out/'receipt.json')
  need(r['status']=='PASS_FULL_BENCH_PROVIDER_LINT_ONLY','lint failed; preserve original diagnostics')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true');run(p.parse_args())
