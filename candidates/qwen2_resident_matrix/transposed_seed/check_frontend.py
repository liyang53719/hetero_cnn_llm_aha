#!/usr/bin/env python3
"""Frozen source composition and full-main Scala typecheck, then bounded CHIRRTL.

The full actual QwenOwnerKernel source is typechecked with pinned HardFloat.
It is NOT elaborated. Only seed/disabled owners, banks and service are emitted
as CHIRRTL. Exact retained SV endpoint declarations are BlackBoxes; no fake
arithmetic, SystemVerilog generation, simulator, downloads or heavyweight RTL.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,subprocess,sys,time
sys.dont_write_bytecode=True
TASK=Path(__file__).resolve().parent;ROOT=TASK.parents[2]
COMMIT='825caff3a6c618419c49c7da452e009ce86ae8b5'
PREFIX='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
PATCHES=['candidates/qwen2_resident_matrix/transposed_route/combined_service.patch',
         'candidates/qwen2_resident_matrix/transposed_owner/owner_selection.patch',
         'candidates/qwen2_resident_matrix/transposed_seed/service_seed.patch',
         'candidates/qwen2_resident_matrix/transposed_seed/owner_prefix.patch',
         'candidates/qwen2_resident_matrix/transposed_seed/leaf/retained_accumulator_seed.patch']

def sha(x):return hashlib.sha256(x).hexdigest()
def frozen(path):return subprocess.check_output(['git','show',COMMIT+':'+path],cwd=ROOT)
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def compose(out):
 paths=subprocess.check_output(['git','ls-tree','-r','--name-only',COMMIT,'--',
  'chisel/continuous_prefill/src/main/scala','chisel/p0_safety/src/main/scala',
  'integration/gemmini/EmitHeteroFP32Alu.scala','integration/gemmini/EmitHeteroBF16Fma.scala'],cwd=ROOT,text=True).splitlines()
 paths=[p for p in paths if p.endswith('.scala')]
 paths+=['candidates/qwen2_resident_matrix/transposed_owner/'+n for n in ('DenseOwnerIO.scala','TransposedDenseBanks.scala','TransposedDenseOwner.scala')]
 paths+=['candidates/qwen2_resident_matrix/'+n for n in ('MatrixAccumulatorSeedProtocol.scala','MatrixAccumulatorSeedController.scala')]
 leaf=json.loads((TASK/'leaf/source_manifest.json').read_text())
 paths+=list(p for p in leaf['files'] if p not in paths)
 before={}
 for p in paths:
  data=frozen(p);dest=out/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);before[p]=sha(data)
 patch_ids={}
 for patch in PATCHES:
  data=frozen(patch) if '/transposed_seed/' not in patch else (ROOT/patch).read_bytes()
  path=out/('patch_'+str(len(patch_ids))+'.patch');path.write_bytes(data);patch_ids[patch]=sha(data)
  subprocess.run(['git','apply','--check',str(path)],cwd=out,check=True)
  subprocess.run(['git','apply',str(path)],cwd=out,check=True)
 return paths,{'frozen_sources':before,'patches':patch_ids,'patched_sources':{p:sha((out/p).read_bytes()) for p in paths}}

def audit(fir):
 memories=re.findall(r'^\s*smem (\w+) : UInt<256>\s*\[(\d+)\]',fir,re.M)
 if len(memories)!=32 or sorted(int(n) for _,n in memories)!=[160]*16+[1376]*16:raise ValueError('fixed 32 SRAM geometry drift')
 ports={}
 for name,depth in memories:
  counts={k:len(re.findall(r'^\s*'+k+r' mport \w+ = '+name+r'\[',fir,re.M)) for k in ('read','write')}
  if counts!={'read':1,'write':1}:raise ValueError('physical bank port drift '+name)
  ports[name]={'depth':int(depth),**counts}
 if len(re.findall(r'inst leaves_\d+ of qwen2_matrix_command_endpoint',fir))!=8:raise ValueError('retained endpoint count drift')
 for token in ('reg finalValue : UInt<32>[256][16]', 'reg storage : {','cmem ram : {'):
  if token not in fir:raise ValueError('expected bounded buffer missing '+token)
 if len(re.findall(r'reg finalValue :',fir))!=1:raise ValueError('duplicated owner finalValue')
 queues=re.findall(r'^\s*cmem ram : (.*) \[(\d+)\]',fir,re.M)
 if len(queues)!=2 or sorted(int(n) for _,n in queues)!=[4,8]:raise ValueError('fixed operand/metadata queue depth drift')
 if not re.search(r'reg storage : .*\}\[2\], clock',fir):raise ValueError('result buffer depth drift')
 return {'memories':ports,'total_sram_bytes':786432,'final_value_bytes':16384,
  'operand_fifo_entries':4,'metadata_fifo_entries':8,'result_buffers':2,'retained_endpoints':8,
  'new_accumulator_or_sram_arrays':0,'area_timing_measured':False}

def ir_modules(fir):
 return {m.group(1):m.group(0) for m in re.finditer(r'^  (?:extmodule|module) (\w+) :.*?(?=^  (?:extmodule|module) |\Z)',fir,re.M|re.S)}

def register_widths(body):
 def width(typ):
  total=0
  for bits,vec in re.findall(r'UInt<(\d+)>((?:\[\d+\])*)',typ):
   n=int(bits)
   for size in re.findall(r'\[(\d+)\]',vec):n*=int(size)
   total+=n
  if typ.startswith('{'):
   for size in re.findall(r'\[(\d+)\]',typ[typ.rfind('}')+1:]):total*=int(size)
  return total
 return {name:width(typ) for name,typ in re.findall(r'^\s*reg(?:reset)? (\w+) : (.*?), clock',body,re.M)}

def audit_all(directory,helper):
 result={'resource_audit':{},'default_off_ir':{},'endpoint_abi':{}}
 baseline=json.loads((TASK/'baseline_ir.json').read_text())
 abi=json.loads((TASK/'leaf/abi.json').read_text())
 original=frozen(PREFIX+'RetainedMatrix.scala').decode()
 declaration=helper.declaration(original,'RetainedMatrixEndpoint')
 base=[]
 for name,direction,typ,width in re.findall(r'val (\w+)=(Input|Output)\((Clock\(\)|Bool\(\)|UInt\((\d+)\.W\))\)',declaration):
  wire='Clock' if typ=='Clock()' else 'UInt<'+(width or '1')+'>'
  base.append(direction.lower()+' '+name+' : '+wire)
 if len(base)!=22:raise ValueError('original retained ABI incomplete')
 for file in directory.glob('*.fir'):
  fir=helper.normalized_chirrtl(file.read_text());modules=ir_modules(fir)
  enabled=('enabled' in file.name)
  if file.name.startswith('seed_owner'):
   result['resource_audit'][file.name]=audit(fir)
   if not enabled:
    mode='burst' if 'burst' in file.name else 'single'
    for name in ('TransposedDenseOwner','TransposedDenseBanks','MatrixPipelineService','MatrixResultFifo','Queue4_MatrixStreamStep','Queue8_Meta'):
     actual=sha(modules[name].encode());expected=baseline['modules'][mode+'/'+name]
     result['default_off_ir'][mode+'/'+name]={'sha256':actual,'equal':actual==expected}
     if actual!=expected:raise ValueError('default-off normalized IR drift '+name)
  endpoints={n:b for n,b in modules.items() if n.startswith('qwen2_matrix_command_endpoint')}
  if len(endpoints)!=8:raise ValueError('eight endpoint declarations required')
  expected=set(base)
  if enabled:
   expected|={direction+' '+name+' : UInt<'+str(width)+'>' for key,direction in [('inputs','input'),('outputs','output')] for name,width in abi[key].items()}
  for name,block in endpoints.items():
   actual={line.strip() for line in block.splitlines() if line.strip().startswith(('input ','output '))}
   if actual!=expected:raise ValueError('exact endpoint ABI drift '+file.name+'/'+name)
   if ('parameter ENABLE_ACCUMULATOR_SEED = 1' in block)!=enabled:raise ValueError('default-off seed parameter drift')
  result['endpoint_abi'][file.name]={'ports_per_endpoint':len(expected),'seed_enabled':enabled,'endpoints':8}
 disabled=ir_modules(helper.normalized_chirrtl((directory/'seed_owner_disabled_burst.fir').read_text()))
 enabled=ir_modules(helper.normalized_chirrtl((directory/'seed_owner_enabled_burst.fir').read_text()))
 result['added_registers']={}
 for old_name,new_name in [('TransposedDenseOwner','TransposedDenseSeedOwner'),('MatrixPipelineService','MatrixPipelineService')]:
  before=register_widths(disabled[old_name]);after=register_widths(enabled[new_name])
  removed=set(before)-set(after)
  if removed:raise ValueError('existing register removed '+str(removed))
  delta={name:bits-before.get(name,0) for name,bits in after.items() if bits!=before.get(name,0)}
  result['added_registers'][new_name]={'bits':sum(delta.values()),'by_register':delta}
 controller=register_widths(enabled['MatrixAccumulatorSeedController'])
 result['added_registers']['MatrixAccumulatorSeedController']={'bits':sum(controller.values()),'by_register':controller}
 result['added_registers']['retained_leaf_source_estimate']={'bits':8*109,'per_endpoint':109,'method':'source count; not synthesis'}
 result['total_added_register_bits_source_and_chirrtl']=sum(x['bits'] for x in result['added_registers'].values())
 result['new_selection_logic']={'lanes':4096,'per_lane_bank_data_mux_bits':32,'per_lane_bank_context_mux_bits':3,
  'existing_bank_write_ports_per_lane':1,'cluster_selector_comparisons_per_endpoint':32,
  'added_sram_or_accumulator_banks':0,'added_fma':0,'area_timing_measured':False}
 result['generated_chirrtl']={p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in directory.glob('*.fir')}
 return result

def audit_existing(previous,out):
 if out.exists():raise ValueError('use a new audit evidence directory')
 report=json.loads((previous/'summary.json').read_text())
 if len(report['commands'])!=2 or any(c['exit_code']!=0 for c in report['commands']):raise ValueError('both compile/emission commands must have succeeded')
 if not report['full_qwen_owner_kernel_typechecked']:raise ValueError('full typecheck was not completed')
 for path,digest in report['source_sha256'].items():
  if sha((ROOT/path).read_bytes())!=digest:raise ValueError('compiled source changed '+path)
 for path,digest in report['source_pins']['patches'].items():
  if sha((ROOT/path).read_bytes())!=digest:raise ValueError('patch changed after emission '+path)
 helper=module('seed_audit_helper',ROOT/'scripts/check_matrix_interface_candidate.py')
 result=audit_all(previous/'chirrtl',helper)
 result.update(status='PASS_REAUDIT_EXISTING_SEED_FRONTEND',original_summary_sha256=sha((previous/'summary.json').read_bytes()),
  original_status=report['status'],original_error=report.get('error'),original_evidence=str(previous.relative_to(ROOT)),
  original_compiled_source_sha256=report['source_sha256'],source_pins=report['source_pins'],
  auditor_sha256=sha(Path(__file__).read_bytes()),baseline_ir_sha256=sha((TASK/'baseline_ir.json').read_bytes()),
  retained_leaf_abi_sha256=sha((TASK/'leaf/abi.json').read_bytes()),
  commands_reexecuted=[],full_qwen_owner_kernel_typechecked=True,full_qwen_owner_kernel_elaborated=False,
  rtl_generated=False,hardware_arithmetic_executed=False)
 out.mkdir(parents=True);(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return result

def run(out,cache,hardfloat,validate_only=False):
 if out.exists():raise ValueError('use a new evidence directory')
 out.mkdir(parents=True);start=time.monotonic()
 report={'status':'STARTED','source_commit':COMMIT,'rtl_generated':False,'hardware_arithmetic_executed':False,
  'full_qwen_owner_kernel_typechecked':False,'full_qwen_owner_kernel_elaborated':False,'commands':[],
  'native_m128_and_fp32_final_acceptance':'UNCHANGED_FAIL_POLICY_PENDING',
  'java_budget':{'active_processors':1,'heap_mib':1024,'timeout_seconds_per_command':180}}
 def save():(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
 def command(argv,name):
  t=time.monotonic()
  record={'argv':argv,'log':name,'exit_code':None,'status':'RUNNING'};report['commands'].append(record);save()
  with (out/name).open('w') as log:p=subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  record.update(exit_code=p.returncode,wall_seconds=time.monotonic()-t,status='FINISHED');save()
  if p.returncode:raise RuntimeError('command failed: '+name)
 try:
  source=out/'source';source.mkdir();paths,pins=compose(source)
  expected=json.loads((TASK/'source_pins.json').read_text())
  if pins!=expected:raise ValueError('frozen source/patch/postimage identity drift')
  report['source_pins']=pins
  route=json.loads(frozen('candidates/qwen2_resident_matrix/transposed_route/manifest.json'))
  helper=module('seed_frontend_helper',ROOT/'scripts/check_matrix_interface_candidate.py')
  if sha((ROOT/'scripts/check_matrix_interface_candidate.py').read_bytes())!=route['dependencies']['scripts/check_matrix_interface_candidate.py']:raise ValueError('helper drift')
  lock_path=ROOT/'chisel/rope_hardware_oracle/maven-lock.json'
  if sha(lock_path.read_bytes())!=route['maven_lock_sha256']:raise ValueError('Maven lock drift')
  dependencies=helper.dependency_paths(json.loads(lock_path.read_text())['artifacts'])
  if len(dependencies)!=87:raise ValueError('dependency count drift')
  for path,digest in dependencies.items():
   if sha((cache/path).read_bytes())!=digest:raise ValueError('cache dependency identity drift '+str(path))
  cp,plugin,receipt=helper.prepare_dependencies(ROOT,cache,route)
  (out/'dependency_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');report['dependency_receipt_sha256']=sha((out/'dependency_receipt.json').read_bytes())
  hf='c1105e6ac6a0dd90fc80893efc4830ab609005d3'
  if subprocess.check_output(['git','-C',str(hardfloat),'rev-parse','HEAD'],text=True).strip()!=hf:raise ValueError('HardFloat head drift')
  hpaths=subprocess.check_output(['git','-C',str(hardfloat),'ls-tree','-r','--name-only',hf,'--','hardfloat/src/main/scala'],text=True).splitlines()
  hpaths=[p for p in hpaths if p.endswith('.scala')]
  if len(hpaths)!=20:raise ValueError('HardFloat source count drift')
  sources=[source/p for p in paths if p.endswith('.scala')]
  for p in hpaths:
   dest=source/'pinned_hardfloat'/p;dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(subprocess.check_output(['git','-C',str(hardfloat),'show',hf+':'+p]));sources.append(dest)
  sources.append(TASK/'SeedOwnerElaboration.scala')
  report['source_sha256']={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sources}
  report['task_source_sha256']={str(p.relative_to(TASK)):sha(p.read_bytes()) for p in TASK.rglob('*') if p.is_file()}
  report['hardfloat_commit']=hf;report['typechecked_source_count']=len(sources)
  if validate_only:report['status']='PASS_SOURCE_AND_CACHE_VALIDATION_ONLY';save();return report
  java=['java','-Xmx1024m','-XX:ActiveProcessorCount=1'];classes=out/'classes';classes.mkdir()
  command(java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(plugin),'-d',str(classes)]+list(map(str,sources)),'compile.log')
  report['full_qwen_owner_kernel_typechecked']=True
  command(java+['-cp',str(classes)+':'+cp,'heteronpu.continuous.SeedOwnerElaboration',str(out/'chirrtl')],'elaboration.log')
  report.update(audit_all(out/'chirrtl',helper))
  for p in sources:
   if sha(p.read_bytes())!=report['source_sha256'][str(p.relative_to(ROOT))]:raise ValueError('source changed during compile')
  report['status']='PASS_SEED_OWNER_FULL_TYPECHECK_AND_FRONTEND_ONLY';report['wall_seconds']=time.monotonic()-start;save();return report
 except Exception as e:
  report['status']='FAILED';report['error']=str(e);report['wall_seconds']=time.monotonic()-start;save();raise

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--hardfloat',type=Path);p.add_argument('--validate-only',action='store_true');p.add_argument('--audit-existing',type=Path)
 a=p.parse_args()
 if a.audit_existing:result=audit_existing(a.audit_existing.resolve(),a.out.resolve())
 else:
  if a.cache is None or a.hardfloat is None:p.error('--cache and --hardfloat required for source/typecheck mode')
  result=run(a.out.resolve(),a.cache.resolve(),a.hardfloat.resolve(),a.validate_only)
 print(json.dumps({'status':result['status']}))
