"""Offline metadata/default/namespace replay. No real DUT import or service."""
from pathlib import Path
import sys,tempfile,types,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cold_policy as policy
if Path(policy.__file__).resolve()!=HERE/'cold_policy.py':raise RuntimeError('foreign policy')

SOURCE='''from dataclasses import dataclass
@dataclass(frozen=True)
class Services:
    busy: bool = False
class Coordinator:
    def ports(self, services=Services()):
        pass
    def tick(self, services=Services()):
        pass
'''
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.p=self.root/'fixture.py';self.p.write_text(SOURCE);self.files={str(self.p):{}};self.sites=policy.metadata_sites(self.root,self.files)
    def tearDown(self):self.tmp.cleanup()
    def collect(self,text=SOURCE,sites=None):
        namespace={'__file__':str(self.p),'__name__':'cold_policy_fixture'};mod=types.ModuleType('cold_policy_fixture');mod.__dict__.update(namespace);sys.modules[mod.__name__]=mod
        result=[]
        def callback(frame,event,arg):
            if event=='call' and frame.f_code.co_name=='__init__' and frame.f_code.co_filename=='<string>' and frame.f_globals is mod.__dict__:
                result.append(policy.metadata_default(frame,self.sites if sites is None else sites,self.files))
        old=sys.getprofile();sys.setprofile(callback)
        try:exec(compile(text,str(self.p),'exec'),mod.__dict__)
        finally:sys.setprofile(old);sys.modules.pop(mod.__name__,None)
        return result
    def test_all_definition_defaults_found(self):
        self.assertEqual([(x['caller'],x['line'],x['constructor']) for x in self.sites],[('Coordinator',6,'Services'),('Coordinator',8,'Services')])
    def test_exact_frozen_defaults_allowed(self):self.assertEqual(self.collect(),[True,True])
    def test_nonfrozen_rejected(self):self.assertEqual(self.collect(SOURCE.replace('frozen=True','frozen=False')),[False,False])
    def test_wrong_caller_rejected(self):self.assertEqual(self.collect(sites=[dict(s,caller='Other') for s in self.sites]),[False,False])
    def test_wrong_line_rejected(self):self.assertEqual(self.collect(sites=[dict(s,line=999) for s in self.sites]),[False,False])
    def test_wrong_class_rejected(self):self.assertEqual(self.collect(sites=[dict(s,constructor='MatrixService') for s in self.sites]),[False,False])
    def test_runtime_constructor_not_definition(self):
        self.assertEqual(self.collect(SOURCE+'\ndef task():\n    return Services()\ntask()\n'),[True,True,False])
    def test_module_constant_found(self):
        self.p.write_text(SOURCE+'CONSTANT = Services()\n');sites=policy.metadata_sites(self.root,self.files)
        self.assertEqual(sites[-1]['kind'],'module_constant')
        self.assertEqual(self.collect(self.p.read_text(),sites),[True,True,True])
    def test_task_entries_explicit(self):
        for n in ('configure_library','tick','acquire','run','execute_public_suffix','load_inputs','__new__'):self.assertIn(n,policy.TASK_CALLS)
        self.assertNotIn('load_module',policy.TASK_CALLS)
    def test_namespace_repetitions_retained(self):
        m=types.ModuleType('candidates');m.__path__=[str(self.root),str(self.root)]
        out,notes=policy.namespace_registration({'candidates':m},{'candidates':{'paths':[str(self.root)]}})
        self.assertEqual(out['candidates']['paths'],m.__path__);self.assertEqual(len(notes),1)
        self.assertFalse(notes[0]['paths_deduplicated'])
    def test_foreign_namespace_not_admitted(self):
        m=types.ModuleType('candidates');m.__path__=[str(self.root),'/foreign']
        expected={'candidates':{'paths':[str(self.root)]}}
        out,notes=policy.namespace_registration({'candidates':m},expected)
        self.assertEqual(out,expected);self.assertEqual(notes,[])
    def test_noncanonical_alias_not_admitted(self):
        m=types.ModuleType('candidates');m.__path__=[str(self.root)+'/../'+self.root.name]
        expected={'candidates':{'paths':[str(self.root)]}}
        self.assertEqual(policy.namespace_registration({'candidates':m},expected),(expected,[]))
    def test_namespace_object_untouched(self):
        m=types.ModuleType('candidates');paths=[str(self.root),str(self.root)];m.__path__=paths
        policy.namespace_registration({'candidates':m},{'candidates':{'paths':[str(self.root)]}})
        self.assertIs(m.__path__,paths)
    def test_no_default_call_in_body_inventory(self):
        self.p.write_text('def task():\n    Services()\n')
        self.assertEqual(policy.metadata_sites(self.root,self.files),[])

class QualificationTests(unittest.TestCase):
    def test_empty_report_rejected(self):
        self.assertTrue(policy.qualify_namespace_repetitions({},[])['remaining_failures'])
    def test_other_failure_retained(self):
        e={'code':'foreign_module','detail':'x'}
        row={'name':'x','errors':[e]}
        report={'schema':1,'entry_count':1,'modules':[row], 'failures':[dict(name='x',**e)],'status':'FAIL_MODULE_IDENTITY'}
        self.assertEqual(policy.qualify_namespace_repetitions(report,[])['remaining_failures'],report['failures'])
    def test_clean_report_is_not_runtime_execution(self):
        report={'schema':1,'entry_count':0,'modules':[],'failures':[],'status':'PASS_MODULE_IDENTITY'}
        decision=policy.qualify_namespace_repetitions(report,[])
        self.assertFalse(decision['live_snapshot_checked'])
        self.assertFalse(decision['original_audit_modified'])

if __name__=='__main__':unittest.main()
