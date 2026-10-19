"""Three finite synthetic cases projected from the independent v2 counterexample.
No phase argv is executed; generated fixture contents are deliberately tiny.
"""
import sys
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('flags')
from pathlib import Path
import argparse,hashlib,json,tempfile,types
parser=argparse.ArgumentParser();parser.add_argument('--repo',required=True,type=Path);args=parser.parse_args()
CAND=Path(__file__).absolute().parent;BASE=args.repo.absolute()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def identity(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def load():
 raw=(CAND/'host_emission.py').read_bytes()
 need(identity(raw)=={'bytes':26517,'sha256':'f1cb8595247b2c991c77e4fa7404fc1cd618bb28f9e173eb43d7e00a58c49b50'},'module identity before compile')
 m=types.ModuleType('fixed_emission_finalization');m.__file__=str(CAND/'host_emission.py')
 exec(compile(raw,m.__file__,'exec',dont_inherit=True),m.__dict__)
 return m
m=load();pins=m.source_pins()
for name,pin in pins.items():need(identity((BASE/name).read_bytes())==pin,'fixed published source')
replay=json.loads((BASE/m.REPLAY).read_bytes())
actual_helpers={n:(BASE/n).read_bytes() for n in (m.ASSEMBLER,m.ACQUIRER,m.CLASS_HELPER,m.CHIRRTL_HELPER,m.SV_HELPER,m.MEMBER_HELPER)}
actual_plans={group:json.loads((BASE/(m.BASE+'acquisition/plans/'+group+'.json')).read_bytes()) for group in ('jar87','hardfloat20','firtool')}

def full_mock(case):
 # Each mock uses 111 tiny project inputs, 93 tiny sources and full 87/20/1
 # destination names. Published helper source is loaded but command argv is ONLY inspected.
 m=load()
 with tempfile.TemporaryDirectory(prefix='review-emission-mock-') as td:
  root=Path(td);repo=root/'repo';repo.mkdir();(repo/'.git').mkdir();work=root/'work'
  java_home=root/'jdk';(java_home/'bin').mkdir(parents=True);java=java_home/'bin/java'
  java.write_bytes(b'not executable mock Java');(java_home/'release').write_bytes(b'JAVA_VERSION="21.0.0"\n')
  def fake_java():return java_home,java,{'environment_key':'PURE_MOCK','java':identity(java.read_bytes()),'release':identity((java_home/'release').read_bytes())}
  m._java21=fake_java
  m.FIR_PIN=identity(b'tiny mock FIR\n');m.SV_PIN=identity(b'tiny mock SV\n');m.FIRTOOL_PIN=identity(b'tiny mock firtool never executed\n')
  source=b'// tiny synthetic Scala fixture only\n'
  expected={n:hashlib.sha256(source).hexdigest() for n in replay['expected93']}
  raws={'fixture/input%03d.txt'%i:b'tiny\n' for i in range(111)}
  plan={'input_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in raws.items()},'expected93':expected}
  raws[m.REPLAY]=json.dumps(plan).encode()
  plans={}
  for group,actual in actual_plans.items():
   d=json.loads(json.dumps(actual))
   for a in d['artifacts']:
    a.update(sha256=hashlib.sha256(b'tiny acquired\n').hexdigest(),known_size_bytes=len(b'tiny acquired\n'),max_transfer_bytes=len(b'tiny acquired\n')+1)
   plans[group]=d;raws[m.BASE+'acquisition/plans/'+group+'.json']=json.dumps(d).encode()
  raws.update(actual_helpers)
  need(len(raws)==121,'mock pin count')
  for n,v in raws.items():p=repo/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
  mock_pins={n:identity(v) for n,v in raws.items()};m.source_pins=lambda:mock_pins
  calls=[]
  def callback(name,argv,cwd,environment,limits):
   calls.append((name,argv,cwd,environment,limits))
   need(cwd==work/'phases'/name.removeprefix('host93_'),'unique phase cwd')
   need(limits==m.LIMITS[name.removeprefix('host93_')],'exact forwarded limits')
   need(environment['HOME']==str(work/'home'),'isolated home')
   log=b'ok\n'
   if case=='callback_failure' and name=='host93_acquire_hardfloat20':raise RuntimeError('injected callback failure')
   if name=='host93_java_version':
    need(argv==[str(java),'-Xmx64m','-XX:ActiveProcessorCount=1','-version'],'version argv');log=b'openjdk version "21.0.0"\n'
   elif name in ('host93_acquire_jar87','host93_acquire_hardfloat20'):
    group=name.removeprefix('host93_acquire_');dest=work/'acquired'/group
    need(argv[1:5]==['-I','-S','-B','-c'] and argv[5]==m.BOOTSTRAP,'same buffer bootstrap argv')
    need(argv[9:]==['fetch',group,'--repository',str(repo),'--output-root',str(dest),'--execute-acquisition'],'actual acquirer argv')
    for a in plans[group]['artifacts']:p=dest/a['relative_destination'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'tiny acquired\n')
    (dest/'ACQUISITION.json').write_text('{}')
   elif name=='host93_assemble':
    dest=work/'assembled'
    need(argv[9:]==['--repo',str(work/'frozen_repo'),'--assemble-reviewed-source','--hardfloat-scala',str(work/'acquired/hardfloat20/hardfloat/src/main/scala'),'--output',str(dest)],'actual assembler argv')
    for n in expected:p=dest/'scala'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source)
    (dest/'SOURCE_RECEIPT.json').write_text('{}')
   elif name=='host93_class':
    need('scala.tools.nsc.Main' in argv and len([x for x in argv if x.endswith('.scala')])==93,'real class builder exact93')
    need(len(argv[argv.index('-cp')+1].split(':'))==87,'real class cp87')
    p=work/'classes/heteronpu/continuous/EmitCanonicalHost93.class';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'mock class')
   elif name=='host93_chirrtl':
    need(argv[-2]=='heteronpu.continuous.EmitCanonicalHost93','real CHIRRTL entry')
    dest=work/'structure';dest.mkdir();(dest/'HostBlockCollection.fir').write_bytes(b'tiny mock FIR\n')
    log=b'CANONICAL_HOST93_CHIRRTL_BEGIN x\nCANONICAL_HOST93_CHIRRTL_WRITTEN x\n'
   elif name=='host93_acquire_firtool':
    dest=work/'acquired/firtool';dest.mkdir()
    need(argv[9:]==['--acquisition-source',str(work/'frozen_repo'/m.BASE/'acquisition'),'--repository',str(repo),'--output-root',str(dest),'--execute-reviewed-acquisition'],'actual member helper argv')
    for a in plans['firtool']['artifacts']:(dest/a['relative_destination']).write_bytes(b'tiny acquired\n')
    (dest/'ACQUISITION.json').write_text('{}')
    (dest/'MEMBER.json').write_text(json.dumps({'extracted_member_count':1,'binary_executed':False,'member_name':'org.chipsalliance/llvm-firtool/linux-x64/bin/firtool'}))
    (dest/'firtool').write_bytes(b'tiny mock firtool never executed\n');(dest/'firtool').chmod(0o600)
   elif name=='host93_sv':
    need(argv[1:]==['-format=fir',str(work/'structure/HostBlockCollection.fir'),'-o',str(work/'rtl/HostBlockCollection.sv'),'-warn-on-unprocessed-annotations','-output-annotation-file',str(work/'rtl/circt.anno.json'),'--preserve-values=all','-disable-all-randomization','--verbose-pass-executions'],'real SV command')
    (work/'rtl/HostBlockCollection.sv').write_bytes(b'tiny mock SV\n')
   else:raise ValueError('unexpected mock phase')
   return {'record':{'exit_code':0,'cleanup_confirmed':True,'synthetic':True},'raw_log':log,'usage':{'synthetic':True},'evidence_root':str(root/'synthetic_evidence'/name)}
  original_save=m.save
  def fail_save(path,value):
   if path.name=='HOST_EMISSION_RESULT.json':raise OSError('injected terminal receipt failure')
   return original_save(path,value)
  if case=='terminal_receipt_failure':m.save=fail_save
  try:
   result=m.run(repo,work,callback)
   need(case=='success','failure case unexpectedly returned')
   need(result['status']=='PASS_HOST93_FRESH_EMISSION_ONLY' and len(calls)==8,'success phases')
   need(result['full_block_rtl_passes']==0 and result['host_executed'] is False and result['numerical_qualification'] is False,'scope')
   need(result['fir']['sha256']==m.FIR_PIN['sha256'] and result['sv']['path']==str(work/'rtl/HostBlockCollection.sv'),'return aliases')
   need((work/'HOST_EMISSION_RESULT.json').exists() and not (work/'HOST_EMISSION_FAILED.json').exists(),'success receipt')
   return {'case':case,'phase_count':len(calls),'status':result['status'],'phase_argv_never_executed':True}
  except (RuntimeError,OSError) as exc:
   need(case!='success','unexpected success fixture failure')
   failed=json.loads((work/'HOST_EMISSION_FAILED.json').read_bytes())
   need(not(work/'HOST_EMISSION_RESULT.json').exists(),'no success receipt')
   need(failed['error']==str(exc) and failed['inventories']['failure_work_before_receipt']['complete'],'failure details retained')
   need(failed['status']=='INCOMPLETE_HOST93_FRESH_EMISSION','every failure receipt status must be incomplete')
   if case=='callback_failure':need(len(calls)==3,'early failure stage count')
   return {'case':case,'phase_count':len(calls),'failure_receipt_status':failed['status'],'error':failed['error'],'raises':type(exc).__name__,'phase_argv_never_executed':True}

cases=[full_mock(n) for n in ('success','callback_failure','terminal_receipt_failure')]
print(json.dumps({'scope':'PURE_MOCK_ONLY','cases':cases,'native_or_network_executed':False},sort_keys=True))
