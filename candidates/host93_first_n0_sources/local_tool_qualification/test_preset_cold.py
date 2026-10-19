import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import ast,copy,json,tempfile,types
from pathlib import Path
from unittest import mock
checks=[]
def check(n,f):f();checks.append(n)
def rejects(f,text):
 try:f()
 except (ValueError,OSError) as e:g.need(text in str(e),'wrong rejection '+str(e));return
 raise ValueError('missing rejection '+text)
name='candidates/host93_first_n0_sources/local_dependency_bootstrap/test_bootstrap_cold.py';raw=g.checked(REPO/name,{'bytes':23019,'sha256':'40329861443bee643cf21eafefc822b36ddcd6e75a42885cae168abc70048477'});node=[n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='Fixture'][0];lines=raw.splitlines(keepends=True);exec(compile(b''.join(lines[node.lineno-1:node.end_lineno])+b'\n','original_fixture','exec'),globals())

def preset_success():
 with Fixture() as f:
  source=f.work/'packages';f.b['work_root']=str(f.work/'new_work');f.braw=json.dumps(f.b).encode();f.bpin=g.pin(f.braw)
  evidence=p.accept(g,REPO,f.braw,f.bpin,source,f.receipt_pin);raw=json.dumps(evidence).encode()
  phase={'name':p.PHASE,'record':{'exit_code':0,'cleanup_confirmed':True}}
  result,proof=p.stage(g,a,REPO,f.braw,f.bpin,phase,f.receipt_pin,raw,g.pin(raw))
  g.need(result['files']==69 and proof['preset_phase_projection']['substitutions']==1 and proof['stage_data']['substitutions']==0,'single phase anchor original stage')
  g.need(evidence['network_acquisition_claimed'] is False and proof['original_download_cleanup_claimed'] is False,'no historical cleanup claim')
  rejects(lambda:p.accept(g,REPO,f.braw,f.bpin,source,f.receipt_pin),'fresh preset acceptance')
check('fresh_preset_six_data_and_original_stage_single_phase_anchor',preset_success)

def no_invented_cleanup():
 with Fixture() as f:
  f.b['work_root']=str(f.work/'new_work');f.braw=json.dumps(f.b).encode();f.bpin=g.pin(f.braw)
  evidence=p.accept(g,REPO,f.braw,f.bpin,f.work/'packages',f.receipt_pin);raw=json.dumps(evidence).encode()
  for phase in ({'name':'local_dependencies_acquire','record':{'exit_code':0,'cleanup_confirmed':True}}, {'name':p.PHASE,'record':{'exit_code':0,'cleanup_confirmed':False}}, {'name':p.PHASE,'record':{'exit_code':False,'cleanup_confirmed':True}}):
   rejects(lambda:p.stage(g,a,REPO,f.braw,f.bpin,phase,f.receipt_pin,raw,g.pin(raw)),'new preset phase exit0')
  g.need(not (Path(f.b['work_root'])/'stage').exists(),'no stage without current acceptance cleanup')
  phase={'name':p.PHASE,'record':{'exit_code':0,'cleanup_confirmed':True}}
  rejects(lambda:p.stage(g,a,REPO,f.braw,f.bpin,phase,f.receipt_pin,raw,{'bytes':len(raw),'sha256':'0'*64}),'same-buffer preset')
  evidence['files']={};bad=json.dumps(evidence).encode();rejects(lambda:p.stage(g,a,REPO,f.braw,f.bpin,phase,f.receipt_pin,bad,g.pin(bad)),'exact preset acceptance six')
check('download_old_name_false_cleanup_bool_exit_and_false_receipt_rejected',no_invented_cleanup)

def bad_preset():
 with Fixture() as f:
  source=f.work/'packages';f.b['work_root']=str(f.work/'new_work');f.braw=json.dumps(f.b).encode();f.bpin=g.pin(f.braw)
  (source/f.s['pins']['packages'][0]['deb_filename']).write_bytes(b'bad')
  rejects(lambda:p.accept(g,REPO,f.braw,f.bpin,source,f.receipt_pin),'artifact exact size')
  g.need(not Path(f.b['work_root']).exists(),'bad fixed package before output')
check('wrong_preset_bytes_rejected_before_output',bad_preset)
print(json.dumps({'status':'PASS_PRESET_ACCEPTANCE_SOURCE_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'real_packages_copied':False},sort_keys=True))
