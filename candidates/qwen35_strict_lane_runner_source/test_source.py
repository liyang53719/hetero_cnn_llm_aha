"""Self-contained pure Python mocks. Never starts a process or uses the network."""
import hashlib,json,pathlib,tempfile,types,unittest.mock as mock
PUBLIC=pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='strict_lane_source_mock_') as outer:
    HERE=pathlib.Path(outer)
    (HERE/'run_lane.py').write_bytes((PUBLIC/'run_lane.py').read_bytes())
    synthetic={'scope':'singlelane_spec_only','execution_authorized':False,'backend_reviewed':False,'backend_evidence_sha256':None,'backend_evidence_path':None,'output':str(HERE/'never_created_actual_output'),'inputs':{str(HERE/'missing_dependency.jar'):{'bytes':1,'sha256':'0'*64}},'original_classes':str(HERE/'original_classes'),'original_class_paths':[],'compile_argv':['not-executed'],'test_argv':['not-executed'],'environment':{}}
    (HERE/'PLAN.json').write_text(json.dumps(synthetic))
    pins={name:{'bytes':(HERE/name).stat().st_size,'sha256':hashlib.sha256((HERE/name).read_bytes()).hexdigest()} for name in ['run_lane.py','PLAN.json']}
    (HERE/'REVIEW_PINS.json').write_text(json.dumps(pins))
    no_launch=mock.patch("subprocess.Popen",side_effect=AssertionError("Real process launch forbidden in source tests"))
    no_launch.start()
    ns={'__name__':'source_test','__file__':str(HERE/'run_lane.py')};exec(compile((HERE/'run_lane.py').read_text(),str(HERE/'run_lane.py'),'exec'),ns)
    plan=json.loads((HERE/'PLAN.json').read_text());checks=[]
    def rejects(fn,text):
        try:fn();raise AssertionError('Expected rejection')
        except RuntimeError as e:assert text in str(e)
    rejects(ns['admission'],'Execution not authorized');checks.append('execution false blocks admission')
    with mock.patch.object(ns['json'],'loads',side_effect=[json.loads((HERE/'REVIEW_PINS.json').read_text()),dict(plan,execution_authorized=True)]):
        rejects(ns['admission'],'Backend review missing')
    checks.append('unreviewed backend blocks authorized plan')
    try:ns['verify'](plan);raise AssertionError('Expected absent jar')
    except FileNotFoundError:checks.append('missing dependency rejected')
    with tempfile.TemporaryDirectory(prefix='lane_r2_pure_test_') as d:
        root=pathlib.Path(d);log=root/'fast.log';log.write_bytes(b'x'*(2*1024**2+1))
        rejects(lambda:ns['terminal_caps'](root,log,1),'Terminal log cap');checks.append('fast-exit oversized log rejected')
        log.write_bytes(b'');rejects(lambda:ns['terminal_caps'](root,log,181),'Terminal phase wall cap');checks.append('terminal timeout rejected')
    with mock.patch.object(ns['os'],'killpg',side_effect=ProcessLookupError):assert ns['group_absent'](999999)
    with mock.patch.object(ns['os'],'killpg',return_value=None):assert not ns['group_absent'](999999)
    checks.append('group existence checks distinguish absent/present')
    rejects(lambda:ns['terminated'](15,None),'termination signal');checks.append('termination raises into cleanup')
    # Force final inventory failure in main, without admitting or launching JVM.
    with tempfile.TemporaryDirectory(prefix='lane_r2_receipt_') as d:
        root=pathlib.Path(d)/'output';fake=dict(plan,output=str(root));phase_calls=[]
        originals={k:ns[k] for k in ['admission','verify','phase','inventory']}
        ns['admission']=lambda:fake;ns['verify']=lambda p:{}
        def fakephase(p,name,argv):
            phase_calls.append(name)
            if name=='test':(root/'test.log').write_text('All tests passed. Tests: succeeded 5, failed 0')
        ns['phase']=fakephase
        def fail_inventory(root):raise RuntimeError('forced cap failure')
        ns['inventory']=fail_inventory
        with mock.patch.object(ns['sys'],'argv',['run_lane.py']):assert ns['main']()==1
        result=json.loads((root/'RESULT.json').read_text());assert result['status']=='FAILED' and 'inventory_error' in result and result['RTL_generated'] is None
        ns.update(originals)
    checks.append('inventory failure still emits FAILED RESULT')
    assert not pathlib.Path(plan['output']).exists()
    result={'status':'PASS_PURE_PYTHON','checks':checks,'JVM_executed':False,'network_attempted':False,'actual_output_absent':True}
    (PUBLIC/'PURE_TEST_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    no_launch.stop()
