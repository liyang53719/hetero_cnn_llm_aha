from pathlib import Path
import sys,types,importlib.util,json,unittest,collections,time
D=Path(__file__).resolve().parent
INPUTS=json.loads(Path(__import__('os').environ['QWEN2_LINE_INPUTS']).read_text())
OLD=Path(INPUTS['observer_root'])
OWNER=Path(INPUTS['owner_root'])
BUFFER=Path(INPUTS['buffer_source'])
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def pkg(n,p):
 m=types.ModuleType(n);m.__path__=[str(p)];sys.modules[n]=m
argv=sys.argv[:]
sys.argv=[argv[0],'--source-root',str(OWNER/'replay_source'),'--owner-root',str(OWNER/'overlay/candidates/qwen2_ordered_owner'),'--buffer-source',str(BUFFER)]
f=load('_select_fixture',OLD/'test_observer.py');sys.argv=argv
pkg('_select',D/'postimage');new=load('_select.monitor',D/'postimage/monitor.py');bridge=load('_select.bridge',D/'postimage/bridge.py');service=load('_select.service_trace',D/'postimage/service_trace.py')
OLD_FG=Path(INPUTS['fullgraph_root'])
pkg('_select_oldfg',OLD_FG);oldbridge=load('_select_oldfg.bridge',OLD_FG/'bridge.py')
active=None
measurements=[]
timings=[]
instrumented={}
def audit(event,args):
 if active is not None and event=='sys._getframe':active['getframe']+=1
# No global audit/profiler instrumentation in timed exact-callback runs.
def make(m=1,selective=True,words=None,old=False,measured=False):
 o,s,sc,j,prior=f.setup(m,words)
 module=f.mon if old else new
 if measured:module=instrumented[old]
 class FixtureObservation(module.Observation):
  def __init__(self,*a,**kw):super().__init__(*a,**kw,ast_definition_test=True)
 proxy=types.SimpleNamespace(Observation=FixtureObservation)
 obs=(oldbridge.make_observation(proxy,o,m,f.b.PackedFields,prior.specs) if old else bridge.make_observation(proxy,o,m,f.b.PackedFields,prior.specs,selective_lines=selective))
 return o,s,sc,j,obs

def run(m=1,selective=True,old=False,broken=False,measured=False):
 global active
 o,s,sc,j,obs=make(m,selective,old=old,measured=measured)
 if broken:obs.data.fields['dot_parts']['observed'][0]=1
 counts=collections.Counter()
 def profiler(frame,event,arg):
  if event=='call' and frame.f_code is obs._line.__func__.__code__:counts['line_callbacks']+=1
 active=None
 if measured:instrumented[old].COUNTS.clear()
 start=time.perf_counter();cpu=time.process_time()
 try:
  with obs:
   d=f.f.Driver(o,j);d.until(lambda:o.state=='finish');d.step(response_ready=True)
 finally:active=None
 elapsed=time.perf_counter()-start;used=time.process_time()-cpu
 if not measured and not broken:timings.append(dict(rows=m,old=old,selective=selective,wall=elapsed,cpu=used,scope='uninstrumented_exact_callbacks_driver_only_fixture'))
 if measured:counts.update(instrumented[old].COUNTS)
 fields={k:{n:(list(v) if n in ('words','observed','frequency') else v) for n,v in data.items()} for k,data in obs.data.fields.items()}
 controls=(d.writes,o.clock,dict(sc.calls),dict(s.counts),s.events,o.ordered_adapter.events)
 return obs,fields,controls,dict(counts)

class Tests(unittest.TestCase):
 def test_pair_m1_m2(self):
  for m in (1,2):
   a,af,ac,an=run(m,old=True);b,bf,bc,bn=run(m)
   self.assertEqual(a.seal(),b.seal());self.assertEqual(af,bf);self.assertEqual(ac,bc)
 def test_interleaved_uninstrumented_timing(self):
  for m in (1,2):
   for repeat in range(3):
    arms={}
    for old in ((True,False) if repeat%2==0 else (False,True)):
     obs,fields,control,count=run(m,old=old);arms[old]=(obs.seal(),fields,control)
     timings[-1]['sample']=repeat;timings[-1]['series']='interleaved_pair'
    self.assertEqual(arms[True],arms[False])
 def test_points_mapping_frozen(self):
  *_,o=make()
  with self.assertRaises(TypeError):o.selected_lines[o.codes['run']]=frozenset()
 def test_callback_measurement_copies(self):
  for old,path in ((True,OLD/'monitor.py'),(False,D/'postimage/monitor.py')):
   raw=path.read_text();raw=raw.replace('    def _line(self,code,line):','    def _line(self,code,line):\n        COUNTS["line_callbacks"]+=1')
   raw=raw.replace('f=sys._getframe(1)','COUNTS["getframe"]+=1;f=sys._getframe(1)')
   # The callback stays the executing function, no wrapper changes its frame.
   module=types.ModuleType('_select._instrumented_'+str(old));module.__file__=str(D/'postimage/monitor.py');module.__package__='_select'
   module.COUNTS=collections.Counter();exec(compile(raw,module.__file__,'exec'),module.__dict__);instrumented[old]=module
  for m in (1,2):
   a,af,ac,an=run(m,old=True,measured=True);b,bf,bc,bn=run(m,measured=True)
   self.assertEqual(a.seal(),b.seal());self.assertEqual(af,bf);self.assertEqual(ac,bc)
   self.assertLess(bn['line_callbacks'],an['line_callbacks']);self.assertLess(bn['getframe'],an['getframe'])
   measurements.append({'scope':'TEST_INSTRUMENTED_CALLBACK_COPIES','rows':m,'baseline':an,'selective':bn})
 def test_default_off(self):
  a,af,ac,an=run(old=True);b,bf,bc,bn=run(selective=False)
  self.assertEqual(a.seal(),b.seal());self.assertEqual((af,ac,an),(bf,bc,bn))
 def test_capture_failure_control_unchanged(self):
  _,_,control,_=run();a,_,other,_=run(broken=True);self.assertEqual(control,other)
  self.assertIsNotNone(a.error)
  with self.assertRaises(ValueError):a.seal()
 def test_only_three_roles_drop_lines(self):
  *_,o=make();m=o.monitor_masks()
  for role,code in o.codes.items():self.assertEqual(m[code],sys.monitoring.events.PY_RETURN|(0 if role in ('op','consume','tick') else sys.monitoring.events.LINE))
 def test_missing_point(self):
  *_,o=make();del o.points['store']
  with self.assertRaises(ValueError):o.monitor_masks()
 def test_duplicate_point(self):
  *_,o=make();o.points['store']=o.points['commit']
  with self.assertRaises(ValueError):o.monitor_masks()
 def test_foreign_code(self):
  *_,o=make();o._line((lambda:None).__code__,1);self.assertIn('foreign code',o.error)
 def test_duplicate_code(self):
  *_,o=make();o.codes['op']=o.codes['run']
  with self.assertRaises(ValueError):o.monitor_masks()
 def test_point_drift(self):
  *_,o=make();o.points['store']+=1
  with self.assertRaises(ValueError):o.monitor_masks()
 def test_invalid_optin(self):
  with self.assertRaises(ValueError):make(selective=1)
 def test_direct_enter_drift_no_slot_mutation(self):
  *_,o=make();o.points['store']+=1
  before=[(sys.monitoring.get_tool(i),sys.monitoring.get_events(i)) for i in (3,4)]
  # Direct observer path, unlike bridge, does not wrap enter with cleanup.
  with self.assertRaises(ValueError):new.Observation.__enter__(o)
  self.assertEqual(before,[(sys.monitoring.get_tool(i),sys.monitoring.get_events(i)) for i in (3,4)]);self.assertIsNone(o.tool)
 def test_no_disable(self):
  self.assertNotIn('monitoring.DISABLE',(D/'postimage/monitor.py').read_text())
 def test_uniform_and_mapping_lifetime(self):
  def target():return 1
  c=target.__code__;ev=sys.monitoring.events.PY_RETURN;callback=lambda *a:None
  for mask in (ev,{c:ev}):
   o=types.SimpleNamespace(closed=False,tool=None)
   service.monitoring_enter(o,'fixture',(3,4),((ev,callback),),(c,),mask)
   self.assertEqual(sys.monitoring.get_local_events(o.tool,c),ev)
   service.monitoring_stop(o,(ev,),(c,));self.assertIsNone(o.tool)
 def test_bad_mapping_reject_before_slot(self):
  def target():return 1
  c=target.__code__;ev=sys.monitoring.events.PY_RETURN
  for mask in ({},{c:0},{c:True},{c:sys.monitoring.events.LINE},{(lambda:0).__code__:ev}):
   o=types.SimpleNamespace(closed=False,tool=None)
   with self.assertRaises(ValueError):service.monitoring_enter(o,'fixture',(3,4),((ev,lambda *a:None),),(c,),mask)
   self.assertIsNone(o.tool)
 def test_foreign_slot_not_changed(self):
  mon=sys.monitoring;mon.use_tool_id(3,'foreign fixture')
  try:
   c=(lambda:0).__code__;ev=mon.events.PY_RETURN;o=types.SimpleNamespace(closed=False,tool=None)
   service.monitoring_enter(o,'fixture',(3,4),((ev,lambda *a:None),),(c,),{c:ev});self.assertEqual(o.tool,4)
   service.monitoring_stop(o,(ev,),(c,));self.assertEqual(mon.get_tool(3),'foreign fixture')
  finally:mon.free_tool_id(3)
 def test_old_negative_suite_with_selective(self):
  # Reuse original 26 owner control/negative cases with only constructor opt-in.
  old=f.mon;original=old.Observation
  class Selected(new.Observation):
   def __init__(self,*a,**kw):super().__init__(*a,**kw,selective_lines=True)
  f.mon=types.SimpleNamespace(Observation=Selected,Fields=new.Fields,bind=new.bind)
  try:
   result=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromTestCase(f.Tests).run(result)
   self.assertEqual(result.testsRun,26);self.assertFalse(result.errors,result.errors);self.assertFalse(result.failures,result.failures)
  finally:f.mon=old

if __name__=='__main__':
 result=unittest.main(verbosity=2,exit=False).result
 print('MEASUREMENTS='+json.dumps(measurements,sort_keys=True))
 print('TIMINGS='+json.dumps(timings,sort_keys=True))
 raise SystemExit(not result.wasSuccessful())
