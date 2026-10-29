"""INCOMPLETE until actual Host admission/build/link. Never invokes a tool on import.
The injected stage MUST be the reviewed bounded multiroot supervisor adapter.
No make -n, frontend, downloader or automatic publication is implemented here.
"""
from pathlib import Path
import hashlib,json,re,shlex,struct,os
TOP='VHostBlockTopV4'
CHILDREN=('bf16_context_lane_cluster16_rev8b_b_candidate_d','qwen2_matrix_command_endpoint_0','TransposedDenseDownOwner')
DRIVER_SHA='20df2692d41693491f0da03fa17f21886b9375ca599c83b5b75c0994841dc45e'
O0=['OPT_FAST=-O0','OPT_SLOW=-O0','OPT_GLOBAL=-O0','CXXFLAGS=-O0']
def need(x,m):
 if not x: raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def pin(p):
 p=Path(p);need(p.is_file() and not p.is_symlink(),'regular file required: '+str(p))
 return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=sha(p))
def check_pins(pins):
 need(bool(pins),'empty pins')
 for p,h in pins.items():need(sha(p)==h,'pin drift: '+p)
def logical(text):return re.sub(r'\\\n',' ',text)
def assignment(text,name):
 rows=re.findall(r'^'+re.escape(name)+r'\s*(?::=|=)\s*(.*)$',logical(text),re.M)
 need(len(rows)==1,'exact single assignment required: '+name)
 return shlex.split(rows[0])
def target(text,name):return re.search(r'^'+re.escape(name)+r'\s*:',text,re.M) is not None

def check_aliases(b):
 for p,target in b.get('compile_aliases',{}).items():need(str(Path(p).resolve(strict=True))==target,'compile alias drift: '+p)

def prepare(b):
 """Source-only inspection; reviewed exact actual make closure is REQUIRED.
 This is not a general make evaluator/security proof. Admission must additionally
 review expanded flags/includes/recipes and all tool/header/driver identities.
 """
 need(b['schema']=='FIXED_BINARY_BUILD_BINDING_V1','binding schema')
 need(b['source_commit']==b['admission']['source_commit'],'source mismatch')
 need(b['admission']['status']=='ACTUAL_MAKE_CLOSURE_REVIEWED','actual Host make review missing')
 check_aliases(b);check_pins(b['pins']); a=b['admission'];check_pins(a['make_closure_pins'])
 need(a['no_implicit_frontend'] is True and a['uniform_O0_no_fast_math'] is True,'make review incomplete')
 need(a['header_85_ports_and_driver_ABI_reviewed'] is True,'actual header/driver ABI review missing')
 need(sha(b['driver'])==DRIVER_SHA,'real V3 driver required')
 obj=Path(b['obj']).resolve();need(obj.is_dir(),'actual generated object tree absent')
 # Reject stale compiled products: candidate requires a NEW uncompiled copy tree.
 need(not any(p.suffix in ('.o','.a','.gch') for p in obj.rglob('*')),'fresh uncompiled tree required')
 need(not (obj/TOP).exists(),'stale binary')
 for p in obj.rglob('*'):
  if p.is_file() and p.suffix in ('.cpp','.h','.v','.sv','.dat'):
   need(str(p.resolve()) in b['pins'],'unbound generated input: '+str(p))
 for p in obj.rglob('*.mk'):
  need(str(p.resolve()) in a['make_closure_pins'],'unreviewed generated makefile: '+str(p))
 for p in [b['make'],b['cxx'],b['ar'],b['driver'],b['sv'],b['source_manifest'],b['tool_manifest']]:
  need(str(Path(p).resolve()) in b['pins'],'unbound input/tool: '+p)
 host=(obj/(TOP+'.mk')).read_text();hier=(obj/(TOP+'_hier.mk')).read_text()
 need(target(host,TOP) and target(host,'default'),'actual --exe target missing')
 need(assignment(host,'VM_USER_CLASSES')==[Path(b['driver']).stem],'unique real driver class required')
 need(str(Path(b['driver']).parent) in {str((obj/d).resolve()) for d in assignment(host,'VM_USER_DIR')},'driver source dir mismatch')
 need('-lcrypto' in assignment(host,'VM_USER_LDLIBS'),'crypto link missing')
 need('include '+TOP+'_hier.mk' in host,'unexpected hierarchy inclusion')
 need('ifndef VM_HIER_VERILATION_INCLUDED' in hier,'unsupported hierarchy guard')
 libs=assignment(hier,'VM_HIER_LIBS')
 expected=['V'+n+'/lib'+n+'.a' for n in CHILDREN]
 need(len(libs)==3 and set(libs)==set(expected),'unexpected child topology')
 # Never forward unreviewed custom/compiler wrappers or environment flags.
 flags_text=' '.join(assignment(host,'VM_USER_CFLAGS'))
 need(not re.search(r'HOST_DRIVER_CONFIG_ONLY|fast-math|Ofast|ffp-contract=fast|flto|(?:^|\s)-O[^0\s]',flags_text),'unsafe flags')
 phases=[]
 common=['-j1','VM_HIER_VERILATION_INCLUDED=1',*O0,'CXX='+b['cxx'],'LINK='+b['cxx'],'AR='+b['ar'],'RANLIB='+b['compile_tools']['ranlib'],'PERL='+b['compile_tools']['perl'],'PYTHON3='+b['compile_tools']['python'],'OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=']
 for n in CHILDREN:
  d=obj/('V'+n);mk=d/('V'+n+'.mk');txt=mk.read_text()
  need(target(txt,'lib'+n+'.a'),'missing actual child archive target')
  need(not re.search(r'^VM_HIER_LIBS\s*[:?+]?=',txt,re.M),'unexpected nested child dependency')
  phases.append(dict(name='archive_'+n,cwd=str(d),argv=[b['make'],'-C',str(d),'-f',mk.name,*common,'VM_HIER_LIBS=','lib'+n+'.a'],output=str(d/('lib'+n+'.a'))))
 for name,t in [('host_archive',TOP+'__ALL.a'),('host_link',TOP)]:
  phases.append(dict(name=name,cwd=str(obj),argv=[b['make'],'-C',str(obj),'-f',TOP+'.mk',*common,'VM_HIER_LIBS='+' '.join(libs),t],output=str(obj/t)))
 for p in phases:
  budget=b['budgets'][p['name']]
  need(0<budget['seconds']<=3600 and 0<budget['rss_gib']<=8 and 0<budget['tree_bytes']<=b['shared_tree_cap'],'budget admission required')
  p['budget']=budget
 return dict(schema='SERIAL_REAL_BINARY_PLAN_V1',scope='BUILD_LINK_ONLY_NOT_NUMERICAL',phases=phases,VM_HIER_LIBS=libs,pins=b['pins'],make_closure_pins=a['make_closure_pins'])

def run(b,stage):
 """Call only after exact binding review. Adapter must enforce existing shared
 wall/disk/log/root/lock caps and clean environment; no implicit retries.
 """
 plan=prepare(b);receipts=[]
 for p in plan['phases']:
  check_aliases(b);check_pins(plan['pins']);check_pins(plan['make_closure_pins'])
  for row in receipts:need(pin(row['output']['path'])==row['output'],'completed archive drift')
  budget=p['budget']
  r=stage(p['name'],p['argv'],seconds=budget['seconds'],rss=budget['rss_gib'],tree=budget['tree_bytes'],env_override={'MAKEFLAGS':'','MFLAGS':'','CXXFLAGS':'','CPPFLAGS':'','LDFLAGS':'','LDLIBS':'','OBJCACHE':'','MAKEFILES':'','MAKEOVERRIDES':'','USER_CPPFLAGS':'','USER_LDLIBS':'','COMPILER_PATH':'','LIBRARY_PATH':'','CPATH':'','CPLUS_INCLUDE_PATH':'','C_INCLUDE_PATH':'','LD_PRELOAD':'','LD_LIBRARY_PATH':'','PATH':'/usr/bin:/bin','LC_ALL':'C'},extra_watch_roots=[b['obj']],extra_pins={**plan['pins'],**plan['make_closure_pins']})
  need(r.get('native_exit')==0 and not r.get('errors') and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','build stage incomplete: '+p['name'])
  output=pin(p['output'])
  with open(p['output'],'rb') as f:raw=f.read(20)
  need(raw[:8]==b'!<arch>\n' if p['name']!='host_link' else raw[:6]==b'\x7fELF\x02\x01' and len(raw)==20 and struct.unpack('<H',raw[16:18])[0] in (2,3),'wrong archive/ELF output')
  receipts.append(dict(phase=p['name'],argv=p['argv'],output=output,supervisor=r))
  (Path(b['build_evidence_dir'])/'completed_build_phases.json').write_text(json.dumps(receipts,indent=2)+'\n')
  check_aliases(b);check_pins(plan['pins']);check_pins(plan['make_closure_pins'])
 return dict(status='BUILT_UNQUALIFIED',scope='ARCHIVE_LINK_ONLY_NOT_DUT_PASS',phases=receipts,binary=receipts[-1]['output'],plan=plan)

def validate_identity(identity):
 need(set(identity)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'V2 identity fields')
 need(identity['run_id']>0 and all(re.fullmatch('[0-9a-f]{40}',identity[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')),'artifact identity')
 need(identity['source_commit']!=identity['launch_commit'],'launch/source must be distinct')

def artifact_manifest(root,identity,files,build_receipt):
 """Packaging contract ONLY; does not assert artifact upload/API/download proof.
 Copies must already be frozen beneath NEW root; caller preserves receipts.
 """
 root=Path(root).resolve();need(set(files)=={'binary','sv','source_manifest','driver','build_receipt','tool_manifest'},'artifact file set')
 need(build_receipt['status']=='BUILT_UNQUALIFIED','not actually built')
 validate_identity(identity)
 entries={}
 for k,v in files.items():
  p=Path(v).resolve();rel=p.relative_to(root);q=pin(p);q['path']=str(rel);entries[k]=q
 need(entries['driver']['sha256']==DRIVER_SHA,'driver mismatch')
 receipt=json.loads(Path(files['build_receipt']).read_text())
 for k in ('binary','sv','source_manifest','driver'):
  need(receipt[k+'_sha256']==entries[k]['sha256'],'receipt identity mismatch '+k)
 need(receipt['tool_manifest_sha256']==entries['tool_manifest']['sha256'] and receipt['source_commit']==identity['source_commit'] and receipt['launch_commit']==identity['launch_commit'],'receipt tools/source/launch mismatch')
 need(receipt['config_only'] is False and receipt['software_arithmetic_substitution'] is False,'invalid execution layer')
 need(entries['binary']['sha256']==build_receipt['binary']['sha256'],'actual binary mismatch')
 return dict(schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2',profiles=list(range(5)),layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',artifact_identity=identity,common={k:entries[k] for k in ('binary','sv','source_manifest','driver','build_receipt')},tool_manifest=entries['tool_manifest'])
