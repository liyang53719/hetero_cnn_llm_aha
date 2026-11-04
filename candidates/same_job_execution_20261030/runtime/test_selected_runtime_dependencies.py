"""Dependency metadata and tiny mocked receipts only: never install or native import."""
import ast,copy,hashlib,importlib.util,itertools,json,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(D))
import runtime_dependencies as d
import runtime_phase as phase
import runtime_reuse as reuse
import runtime_reuse_phase as reuse_phase

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
locked=load('selected_original_metadata',D/'source/prepare_runtimes.py')
def b(profiles):
 return dict(execution_policy=d.policy.selected_policy(profiles),pins={str(D/'runtime_dependencies.py'):d.sha(D/'runtime_dependencies.py'),str(D.parent/'profile_policy.py'):d.sha(D.parent/'profile_policy.py')})
def rows(value):return [dict(path='/metadata-only/'+x['filename'],bytes=x['bytes'],sha256=x['sha256'])for x in d.union(value,locked).values()]
class DependencyTests(unittest.TestCase):
 def test_all31_nonempty_selections_exact_original_union(self):
  items,specs,_=locked.artifacts()
  for n in range(1,6):
   for ids in itertools.combinations(range(5),n):
    with self.subTest(ids=ids):
     expected={x['filename']:(x['sha256'],x['bytes'])for i in ids for x in locked.selected_artifacts(i,items,specs)}
     actual=d.union(b(list(ids)),locked)
     self.assertEqual({k:(v['sha256'],v['bytes'])for k,v in actual.items()},expected)
     d.archive_rows(b(list(ids)),rows(b(list(ids))),locked,lambda x:pathlib.Path(x['path']),check_metadata=False)
 def test_recorded_original_counts_and_legacy53(self):
  expected={ (0,):(26,238463458),(1,):(39,259895288),(2,):(39,259895288),(3,):(39,259161043),(4,):(39,259161043),(1,2,3,4):(40,287899273),(0,1,2,3,4):(53,305867713)}
  for ids,want in expected.items():
   union=d.union(b(list(ids)),locked);self.assertEqual((len(union),sum(x['bytes']for x in union.values())),want)
  for value in ({},{'execution_policy':d.policy.policy()},{'execution_policy':d.policy.policy(d.policy.DEFER)}):
   union=d.union(value,locked);self.assertEqual((len(union),sum(x['bytes']for x in union.values())),(53,305867713));self.assertEqual(d.archive_fields(value),{})
 def test_selected_archive_missing_extra_duplicate_and_changed_metadata(self):
  value=b([2]);good=rows(value);all_rows=rows(b([0,1,2,3,4]));extra=next(x for x in all_rows if x not in good)
  for kind in ('missing','extra','duplicate','sha','bytes','bool','pin-extra'):
   bad=copy.deepcopy(good)
   if kind=='missing':bad.pop()
   if kind=='extra':bad.append(extra)
   if kind=='duplicate':bad[-1]=bad[0]
   if kind=='sha':bad[-1]['sha256']='f'*64
   if kind=='bytes':bad[-1]['bytes']+=1
   if kind=='bool':bad[-1]['bytes']=True
   if kind=='pin-extra':bad[-1]['historical_pass']=True
   with self.subTest(kind=kind),self.assertRaises(ValueError):d.archive_rows(value,bad,locked,lambda x:pathlib.Path(x['path']),check_metadata=False)
 def test_permitted_runtime_before_phase_native_or_path_access(self):
  for ids,key in (([2],'qwen2'),([2],'qwen35_35b'),([3],'qwen35_08b')):
   with self.subTest(ids=ids,key=key),patch.object(phase,'module',side_effect=AssertionError('installer called')),patch.object(pathlib.Path,'read_text',side_effect=AssertionError('CPU or source read')):
    with self.assertRaisesRegex(ValueError,'not permitted'):phase.install(b(ids),key)
 def test_selected_p0_preserves_exact_avx512_guard(self):
  for flags in ('avx2','avx512fp16','notavx512f'):
   with self.subTest(flags=flags),patch.object(phase.sys,'version_info',(3,12)),patch.object(phase.platform,'machine',return_value='x86_64'),patch.object(pathlib.Path,'read_text',return_value=flags),patch.object(phase,'module',side_effect=AssertionError('installer called')):
    with self.assertRaisesRegex(ValueError,'P0 AVX512'):phase.install(b([0]),'qwen2')
 def test_selected_source_pin_missing_rejects_before_install(self):
  for path in (D/'runtime_dependencies.py',D.parent/'profile_policy.py'):
   value=b([2]);value['pins'].pop(str(path))
   with self.assertRaisesRegex(ValueError,'source pin'):phase.install(value,'qwen35_08b')
 def test_versioned_archive_output_and_policy_drift(self):
  value=b([2]);result=dict(scope=d.archive_scope(value,True),**d.archive_fields(value));d.check_archive_fields(value,result,True)
  for bad in (dict(result,schema='ORIGINAL53'),dict(result,scope='READ_EXISTING_PINNED_ARCHIVES_NO_INSTALL'),dict(result,execution_policy=d.policy.selected_policy([1]))):
   with self.assertRaises(ValueError):d.check_archive_fields(value,bad,True)

class InventoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.b=b([2]);self.b.update(identity={'source_commit':'a'*40},source_dir=str(D/'source'))
  self.b['pins'][str(D/'source/prepare_runtimes.py')]=d.sha(D/'source/prepare_runtimes.py')
  self.python=self.write(self.root/'python','original synthetic interpreter');self.b['python']=self.python['path']
  self.b['helper']=str(self.root/'helper.py');self.write(pathlib.Path(self.b['helper']),'# synthetic helper');self.b['pins'][self.b['helper']]=d.sha(self.b['helper'])
  root=self.root/'only-qwen35-08b';home=root/'work/runtime';site=home/'site-packages';site.mkdir(parents=True);self.write(site/'native.so','tiny original bytes')
  entry=dict(runtime='qwen35_08b',revision='original-test-revision',import_root=str(root),home=str(home),site=str(site),wrapper=self.write(home/'python.sh','original wrapper'),installation=self.write(home/'runtime_install.json',{'status':'HISTORICAL_NOT_CURRENT'}),sidecar=self.write(home/'SOURCE_SIDECAR.json',{}))
  def tree(*args):return {str(p.relative_to(root)):reuse.pin(p)for p in root.rglob('*')if p.is_file()}
  entry['whole_tree']=self.write(self.root/'whole-tree.json',tree());self.entry=entry
  self.helper=types.SimpleNamespace(CONTRACT={'qwen35_08b':('original-test-revision',entry['sidecar']['sha256'])},tree=tree,wrapper_policy=lambda *a:None,sidecar=lambda *a:None)
  self.m=dict(schema=d.SELECTED_INVENTORY,scope='EXISTING_BYTES_ONLY_REVALIDATE_EVERY_EXECUTOR',execution_policy=self.b['execution_policy'],source_commit='a'*40,python=self.python,entries={'qwen35_08b':entry},archives=rows(self.b),reference_qualified=False,numerical_qualified=False)
  self.mp=self.root/'manifest.json';self.refresh()
  original=reuse.module
  self.addCleanup(patch.stopall);patch.object(reuse,'HELPER_SHA',d.sha(self.b['helper'])).start();patch.object(reuse,'module',side_effect=lambda name,path,pins:self.helper if name=='reuse_original_helpers'else original(name,path,pins)).start()
 def write(self,path,value):
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value if isinstance(value,str)else json.dumps(value));return reuse.pin(path)
 def refresh(self):self.b['runtime_reuse_manifest']=self.write(self.mp,self.m)
 def test_selected_inventory_and_tree_do_not_need_p0(self):
  m,h=reuse.manifest(self.b);self.assertEqual(set(m['entries']),{'qwen35_08b'});self.assertEqual(reuse.verify_entry(self.b,'qwen35_08b',m,h),self.entry)
  for key in ('qwen2','qwen35_35b'):
   with self.assertRaisesRegex(ValueError,'not permitted'):reuse.verify_entry(self.b,key,m,h)
  (pathlib.Path(self.entry['site'])/'native.so').write_text('changed')
  with self.assertRaisesRegex(ValueError,'entire runtime'):reuse.verify_entry(self.b,'qwen35_08b',m,h)
 def test_exact_schema_profile_and_inventory_scope(self):
  good=copy.deepcopy(self.m)
  for case in ('missing-runtime','extra-runtime','missing-archive','extra-archive','legacy-schema','extra-field','sibling-policy'):
   self.m=copy.deepcopy(good)
   if case=='missing-runtime':self.m['entries']={}
   if case=='extra-runtime':self.m['entries']['qwen2']=copy.deepcopy(self.entry)
   if case=='missing-archive':self.m['archives'].pop()
   if case=='extra-archive':self.m['archives'].append(rows(b([0]))[0])
   if case=='legacy-schema':self.m['schema']='PINNED_EXISTING_THREE_RUNTIME_BYTES_V1'
   if case=='extra-field':self.m['historical_pass']=True
   if case=='sibling-policy':self.m['execution_policy']=d.policy.selected_policy([1])
   self.refresh()
   with self.subTest(case=case),self.assertRaises(ValueError):reuse.manifest(self.b)
 def test_reuse_phase_rejects_excluded_runtime_before_import(self):
  self.b.update(owner_root=str(self.root),result_root=str(self.root/'results'))
  path=self.root/'binding.json';pin=self.write(path,self.b)
  with patch.object(reuse,'admit'),patch.object(reuse_phase.subprocess,'run')as native:
   with self.assertRaisesRegex(ValueError,'not permitted'):reuse_phase.run(path,pin['sha256'],'qwen2')
   native.assert_not_called();self.assertFalse((self.root/'results').exists())


class FreshOwnerTests(unittest.TestCase):
 def selected_fixture(self,ids):
  import test_owner_fresh as old
  case=old.Tests();case.setUp();self.addCleanup(case.doCleanups)
  m=old.m;value=case.b;policy=d.policy.selected_policy(ids);value.update(execution_policy=policy,schema=d.SELECTED_BINDING)
  value['pins'].update(b(ids)['pins']);keys=d.policy.runtimes(value)
  value['runtimes']={k:v for k,v in value['runtimes'].items()if k in keys};case.entries={k:v for k,v in case.entries.items()if k in keys}
  originals=copy.deepcopy(value['archives']);items=[dict(filename=pathlib.Path(x['path']).name,bytes=x['bytes'],sha256=x['sha256'])for x in originals]
  specs={'qwen35_08b':{'artifacts':[items[0],items[4]],'transformers':items[5]},'qwen35_35b':{'artifacts':[items[0],items[6]],'transformers':items[7]}}
  fake=types.SimpleNamespace(artifacts=lambda:(items[:4],specs,None));wanted=d.union(value,fake)
  value['archives']=[x for x in originals if pathlib.Path(x['path']).name in wanted]
  source=case.root/'locked';source.mkdir();file=source/'prepare_runtimes.py';file.write_text('def artifacts():return '+repr((items[:4],specs,None))+'\ndef check_wheel_metadata(item,path):pass\n');value['source_dir']=str(source);value['pins'][str(file)]=d.sha(file)
  phase=pathlib.Path(value['phase_binding']['path']);value['phase_binding']=old.write(phase,dict(execution_policy=policy));value['pins'][str(phase)]=d.sha(phase)
  for key,entry in case.entries.items():
   value['runtimes'][key]['argv'][-3]=d.sha(phase)
   native=pathlib.Path(entry['native']['path']);doc=json.loads(native.read_text());doc['argv']=value['runtimes'][key]['argv'];entry['native']=old.write(native,doc)
   result=pathlib.Path(entry['phase_result']['path']);doc=json.loads(result.read_text());doc.update(schema=d.SELECTED_PHASE,execution_policy=policy);entry['phase_result']=old.write(result,doc)
  old.write(case.bp,value);old.write(case.index,dict(execution_policy=policy,schema=d.SELECTED_RECEIPTS,identity=case.identity,binding=old.pin(case.bp),entries=case.entries))
  return case,old
 def test_selected_owner_full_provenance_and_sibling_lease_denial(self):
  for ids in ([2],[4],[1,2,3,4],[0],[0,2,4],list(range(5))):
   with self.subTest(ids=ids):
    case,old=self.selected_fixture(ids);m=old.m;row=m.bind(case.bp,old.pin(case.bp)['sha256'],case.index,old.pin(case.index)['sha256'],case.root/'owner');owner,helper=m.verify(row['path'],row['sha256'],case.root)
    self.assertEqual(owner['schema'],d.SELECTED_OWNER);self.assertEqual(set(owner['entries']),set(d.policy.runtimes(case.b)));self.assertEqual(owner['execution_policy'],case.b['execution_policy'])
    out=case.root/'consumer';out.mkdir()
    with patch.object(m.sys,'version_info',(3,12)),patch.object(m.platform,'machine',return_value='x86_64'),patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=20<<30)):
     for profile in set(range(5))-set(ids):
      with self.assertRaises(ValueError):
       with m.lease(row['path'],row['sha256'],case.root,profile,out):self.fail('unselected sibling lease granted')
     if 0 not in ids:
      with m.lease(row['path'],row['sha256'],case.root,ids[0],out)as leased:self.assertEqual(set(leased),{d.policy.MAP[ids[0]]})
    for entry in owner['entries'].values():m.validate_tree(helper,entry)
 def test_selected_owner_rejects_missing_extra_archives_and_phase_policy(self):
  for mode in ('missing','extra','phase-policy','legacy-schema','fabricated-entry'):
   case,old=self.selected_fixture([2]);m=old.m
   if mode=='missing':case.b['archives'].pop()
   if mode=='extra':case.b['archives'].append(old.pin(case.root/'archives'/'1'))
   if mode=='legacy-schema':case.b['schema']='FRESH_JOB_THREE_RUNTIME_INSTALL_BINDING_V1'
   if mode=='fabricated-entry':case.b['runtimes']['qwen2']=copy.deepcopy(case.b['runtimes']['qwen35_08b'])
   if mode=='phase-policy':
    path=pathlib.Path(case.b['phase_binding']['path']);case.b['phase_binding']=old.write(path,dict(execution_policy=d.policy.selected_policy([1])));case.b['pins'][str(path)]=d.sha(path)
   old.write(case.bp,case.b)
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.binding(case.bp,old.pin(case.bp)['sha256'])

class FreshControllerTests(unittest.TestCase):
 def exercise(self,ids,reject_archive=False,early=0):
  import install_job as installer
  import time
  with tempfile.TemporaryDirectory()as temp:
   root=pathlib.Path(temp);repo=root/'repo';(repo/'src').mkdir(parents=True);(repo/'src/tiny.py').write_text('# synthetic source, never executed\n')
   supervisor=root/'supervisor';supervisor.mkdir()
   for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):(supervisor/name).write_text('# synthetic supervisor closure\n')
   helper=root/'helper.py';helper.write_text('# synthetic owner helper, no imports\n')
   value=b(ids);identity=dict(started_monotonic=time.monotonic());python=str(pathlib.Path(sys.executable).resolve())
   value.update(schema='FRESH_JOB_RUNTIME_CONTROLLER_V1',execution_context='CLOUD_EXECUTOR_V1',identity=identity,job_started_monotonic=identity['started_monotonic'],job_budget_seconds=43200,reserved_other_owner_bytes=5<<30,stage_resources={'install':{'rss_bytes':2<<30,'as_bytes':2<<30},'reference':{'rss_bytes':2<<30,'as_bytes':2<<30}},early_build_seconds=early,install_wall_seconds=60,metadata_wall_seconds=60,remaining_job_reservation_seconds=500,owner_root=str(root/'new-owner'),owned_roots=[str(root)],repo=str(repo),python=python,helper=str(helper),supervisor_dir=str(supervisor),lock=str(root/'lock'))
   allsource=[p for q in (D/'source',repo/'src')for p in q.rglob('*')if p.is_file()and p.suffix in('.py','.json')and '__pycache__'not in p.parts]
   for path in [*allsource,D/'install_job.py',D/'runtime_phase.py',D/'owner_fresh.py',D/'bind_phase.py',D.parent/'numeric/live_budget.py',pathlib.Path(python),helper,*supervisor.iterdir()]:value['pins'][str(path)]=d.sha(path)
   cache=root/'synthetic-cache';cache.mkdir();items=[]
   for i in range(8):
    path=cache/('tiny-'+str(i));path.write_text('synthetic original archive '+str(i));pin=reuse.pin(path);items.append(dict(filename=path.name,bytes=pin['bytes'],sha256=pin['sha256']));value['pins'][str(path)]=pin['sha256']
   specs={'qwen35_08b':{'artifacts':[items[0],items[4]],'transformers':items[5]},'qwen35_35b':{'artifacts':[items[0],items[6]],'transformers':items[7]}}
   metadata=types.SimpleNamespace(artifacts=lambda:(items[:4],specs,None),check_wheel_metadata=lambda *a:None)
   selected=d.union(value,metadata);value['archives']=[reuse.pin(cache/name)for name in selected]
   binding=root/'controller.json';binding.write_text(json.dumps(value));calls=[];original_read=pathlib.Path.read_text
   def read(path,*args,**kwargs):
    if str(path)=='/proc/cpuinfo':
     self.assertIn(0,ids,'non-P0 fresh controller must not inspect P0 CPU flags');return 'avx512f'
    return original_read(path,*args,**kwargs)
   def write(path,doc):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(doc));return reuse.pin(path)
   def execute(argv,out,lock,caps,env,pins,resource_gate):
    self.assertEqual(resource_gate['min_disk_free'],8<<30);out=pathlib.Path(out);out.mkdir(parents=True)
    result=dict(native_exit=0,errors=[],status='PASS_PROCESS_ONLY',argv=argv,caps=caps,cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
    if argv[2]==str(D/'bind_phase.py'):
     config=json.loads(pathlib.Path(argv[4]).read_text());self.assertEqual(config['execution_policy'],value['execution_policy'])
     admission=json.loads(pathlib.Path(config['owner_binding']).read_text());self.assertEqual(admission['schema'],d.SELECTED_BINDING);self.assertEqual(set(admission['runtimes']),set(d.policy.runtimes(value)))
     index=json.loads(pathlib.Path(config['receipt_index']).read_text());self.assertEqual(index['schema'],d.SELECTED_RECEIPTS);self.assertEqual(index['execution_policy'],value['execution_policy'])
     write(pathlib.Path(config['output'])/'SHARED_RUNTIMES_FRESH_JOB_V3.json',dict(schema=d.SELECTED_OWNER,execution_policy=value['execution_policy'],identity=identity,**installer.context_fields(value)))
    else:
     key=argv[-1];calls.append(key);self.assertIn(key,d.policy.runtimes(value));self.assertEqual(caps['rss_bytes'],2<<30);self.assertEqual(caps['per_process_as_bytes'],2<<30)
     phase=json.loads(pathlib.Path(argv[5]).read_text());self.assertEqual(phase['execution_policy'],value['execution_policy'])
     installed=write(root/'new-owner/installs'/key/'runtime_install.json',{'synthetic':True});sidecar=write(root/'new-owner/installs'/key/'SOURCE_SIDECAR.json',{'synthetic':True})
     write(pathlib.Path(phase['result_root'])/(key+'_RESULT.json'),dict(installation=installed,sidecar=sidecar))
    write(out/'RESULT.json',result);return result
   archive_rows=installer.deps.archive_rows
   def check_archives(binding,archives,original,checked):
    if reject_archive:raise ValueError('synthetic rejected archive before filesystem mutations')
    return archive_rows(binding,archives,metadata,checked)
   with patch.object(installer,'verify_controller_identity',return_value=43200),patch.object(installer,'snapshot'),patch.object(installer.deps,'archive_rows',side_effect=check_archives),patch.dict(sys.modules,{'supervise_multiroot':types.SimpleNamespace(execute=execute)}),patch.object(pathlib.Path,'read_text',read):
    if reject_archive:
     with self.assertRaisesRegex(ValueError,'rejected archive'):installer.run(value,binding,d.sha(binding))
     self.assertFalse((root/'new-owner').exists());self.assertEqual(calls,[]);return
    _,index,owner=installer.run(value,binding,d.sha(binding))
   self.assertEqual(calls,list(d.policy.runtimes(value)));self.assertEqual(set(json.loads(index.read_text())['entries']),set(d.policy.runtimes(value)));self.assertTrue(owner.is_file())
   if 0 not in ids:self.assertFalse((root/'new-owner/installs/qwen2').exists())
 def test_selected_fresh_controller_only_chosen_runtime_and_policy_chain(self):
  for ids in ([1],[2],[3],[4],[1,2,3,4],[0],[0,2,4],list(range(5))):
   with self.subTest(ids=ids):self.exercise(ids)
 def test_bad_selected_archive_rejected_before_new_root_or_native(self):self.exercise([2],reject_archive=True)
 def test_earlybuild_35b_guard_is_only_for_explicit_earlybuild(self):
  import install_job as installer
  self.assertEqual(installer.install_order(('qwen35_08b','qwen35_35b')),['qwen35_35b','qwen35_08b'])
  with self.assertRaisesRegex(ValueError,'include35B'):installer.install_order(('qwen35_08b',))
  self.exercise([2])

if __name__=='__main__':unittest.main()
