"""Cold admission/cleanup tests. Native loading and compilers are blocked."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from . import prepare, monitor
from .test_capture import fill


BOOT = """
import ctypes,subprocess,hashlib,json,sys
ctypes.CDLL=lambda *a,**k: (_ for _ in ()).throw(AssertionError('native load prohibited'))
subprocess.run=lambda *a,**k: (_ for _ in ()).throw(AssertionError('compiler prohibited'))
from candidates.qwen2_resident_matrix.attention_packed_observation import monitor
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
from candidates.qwen2_resident_matrix.dense_block_reduce.profile import QWEN2_QKV_PROFILE
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
p=json.loads((monitor.ROOT/monitor.PREFIX/'pins.json').read_text())
sources={**p['runtime'],**p['own'],monitor.PREFIX+'pins.json':monitor.digest(monitor.ROOT/monitor.PREFIX/'pins.json')}
def fixture():
 o=object.__new__(OfficialAttentionOwner)
 o.matrix=object.__new__(ProfiledMatrixService);o.scalar=object.__new__(ScalarService)
 o.matrix.profile=QWEN2_QKV_PROFILE;o.matrix.owner=None;o.matrix.poison=False;o.matrix.lib=type('SyntheticLib',(),{'matrix_state':lambda self:0})();o.scalar.client=None
 o.packed_schedule=None;o.state='idle';o.poison=False;o.scratch_pending=False;o.scratch_leased=False
 return o
"""


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=prepare.compose(Path(cls.temp.name)/'tree')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def child(self,body):
        result=subprocess.run([sys.executable,'-B','-c',BOOT+body],cwd=self.root,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)

    def test_frozen_composition_identity(self):
        pins=prepare.check()
        self.assertEqual({n:prepare.digest(self.root/n) for n in pins['runtime']},pins['runtime'])
        self.assertEqual({n:prepare.digest(self.root/n) for n in pins['own']},pins['own'])

    @unittest.skipIf(sys.flags.optimize,'production observer rejects optimized interpreter')
    def test_exact_type_code_and_empty_close(self):
        self.child("""
o=fixture();capture=monitor.PackedAttentionMonitoringObservation(o,source_sha256=sources)
assert capture.codes['op'] is AttentionOwner._op.__code__
assert capture.codes['op'] is OfficialAttentionOwner._op.__code__
with capture:pass
assert capture.report()['status']=='INCOMPLETE'
assert capture.tool_id is None
assert all(sys.monitoring.get_tool(i) is None for i in (3,4))
""")

    @unittest.skipIf(sys.flags.optimize,'production observer rejects optimized interpreter')
    def test_source_and_loaded_mutations_rejected(self):
        self.child("""
o=fixture()
bad=dict(sources);bad[monitor.SCHEDULE]='0'*64
try:monitor.PackedAttentionMonitoringObservation(o,source_sha256=bad)
except ValueError:pass
else:raise AssertionError('source mutation accepted')
o._op=lambda *a,**k:0
try:monitor.PackedAttentionMonitoringObservation(o,source_sha256=sources)
except ValueError:pass
else:raise AssertionError('instance override accepted')
""")

    @unittest.skipIf(sys.flags.optimize,'production observer rejects optimized interpreter')
    def test_partial_entry_preserves_existing_callback(self):
        self.child("""
callback=lambda *a:None
assert sys.monitoring.get_tool(3) is None
sys.monitoring.register_callback(3,sys.monitoring.events.PY_RETURN,callback)
capture=monitor.PackedAttentionMonitoringObservation(fixture(),source_sha256=sources)
try:capture.__enter__()
except ValueError:pass
else:raise AssertionError('stale callback takeover')
assert sys.monitoring.register_callback(3,sys.monitoring.events.PY_RETURN,None) is callback
assert sys.monitoring.get_tool(3) is None
""")

    @unittest.skipIf(sys.flags.optimize,'production observer rejects optimized interpreter')
    def test_replaced_callback_is_preserved_and_capture_invalid(self):
        self.child("""
capture=monitor.PackedAttentionMonitoringObservation(fixture(),source_sha256=sources)
capture.__enter__();ident=capture.tool_id
foreign=lambda *a:None
sys.monitoring.register_callback(ident,sys.monitoring.events.LINE,foreign)
capture.__exit__(None,None,None)
assert capture.report()['status']=='INCOMPLETE' and capture.error is not None
assert sys.monitoring.register_callback(ident,sys.monitoring.events.LINE,None) is foreign
sys.monitoring.free_tool_id(ident)
""")

    @unittest.skipIf(sys.flags.optimize,'production observer rejects optimized interpreter')
    def test_replaced_event_mask_is_preserved(self):
        self.child("""
capture=monitor.PackedAttentionMonitoringObservation(fixture(),source_sha256=sources)
capture.__enter__();ident=capture.tool_id;code=capture.codes['run']
foreign=sys.monitoring.events.PY_RETURN
sys.monitoring.set_local_events(ident,code,foreign)
capture.__exit__(None,None,None)
assert capture.error is not None
assert sys.monitoring.get_local_events(ident,code)==foreign
sys.monitoring.set_local_events(ident,code,0);sys.monitoring.free_tool_id(ident)
""")

    @unittest.skipIf(sys.flags.optimize,'production observer rejects optimized interpreter')
    def test_interruption_rejects_and_cleans(self):
        self.child("""
capture=monitor.PackedAttentionMonitoringObservation(fixture(),source_sha256=sources)
try:
 with capture:raise RuntimeError('synthetic interruption')
except RuntimeError:pass
assert capture.report()['status']=='INCOMPLETE' and capture.error is not None
assert all(sys.monitoring.get_tool(i) is None for i in (3,4))
""")

    @unittest.skipIf(sys.flags.optimize,'live monitoring requires original CPython mode')
    def test_real_installed_m16_schedule_with_synthetic_services(self):
        self.child("""
from candidates.qwen2_resident_matrix.attention_packed_observation.test_capture import LiveScheduleTests
capture=LiveScheduleTests().execute(16)
assert capture.coverage()
assert capture.fields['softmax_fp32']['writes']==12*16*17//2
""")

    def test_optimized_runtime_explicitly_rejected(self):
        result=subprocess.run([sys.executable,'-B','-O','-c',BOOT+"""
try:monitor.PackedAttentionMonitoringObservation(fixture(),source_sha256=sources)
except ValueError as error:assert 'without -O' in str(error)
else:raise RuntimeError('optimized runtime admitted')
"""],cwd=self.root,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_full_numeric_admission_closed(self):
        for rows in (16,128):
            with self.assertRaises(ValueError):prepare.authorize_full_numeric(rows=rows)


class SealTests(unittest.TestCase):
    def fixture(self):
        o=object.__new__(monitor.PackedAttentionMonitoringObservation)
        o.active=False;o.closed=True;o.error=None;o.started=1;o.capture=fill(1);o.fields=o.capture.fields
        o.sources={};o.job=dict(m=1,tag=7,write_bytes=6144)
        o.terminal=dict(status=None,tag=7,write_bytes=6144)
        o.retirement=dict(state='idle',poison=False,same_services=True,same_job=True,matrix_released=True,
            matrix_reset_required=False,client_retired=True,memory_pending=False,scalar_released=True,
            scratch_pending=False,scratch_leased=False,scratch_request=False,scratch_write_tag=False,packed_memory_tag=False)
        return o
    def test_complete_capture_never_inherits_numerical_or_hardware_pass(self):
        o=self.fixture();r=o.report()
        self.assertEqual(r['status'],'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        for flag in ('prior_observation_results_inherited','full_29_node_gate','whole_block_terminal_observed',
                     'physical_publication_observed','hardware_simulation','future_scores_observed',
                     'matrix_binary_provenance_verified_by_observer'):self.assertIs(r[flag],False)
        self.assertEqual(r['native_acceptance'],'NOT_EVALUATED_BY_OBSERVER')
        self.assertEqual(set(r['fields']),set(o.fields))
        self.assertNotIn('words',[key for f in r['fields'].values() for key,value in f.items() if isinstance(value,list)])
    def test_every_retirement_gate(self):
        for name,value in self.fixture().retirement.items():
            o=self.fixture();o.retirement[name]='finish' if name=='state' else not value
            self.assertEqual(o.report()['status'],'INCOMPLETE',name)
    def test_error_terminal_tag_and_write_bounds(self):
        for name,value in (('status','Numerical'),('tag',8),('write_bytes',6143)):
            o=self.fixture();o.terminal[name]=value;self.assertEqual(o.report()['status'],'INCOMPLETE')
        for attr,value in (('error','failed'),('started',0),('terminal',None)):
            o=self.fixture();setattr(o,attr,value);self.assertEqual(o.report()['status'],'INCOMPLETE')
    def test_missing_field_after_terminal(self):
        o=self.fixture();o.capture.fields.pop('softmax_fp32');self.assertEqual(o.report()['status'],'INCOMPLETE')
    def test_shape_or_count_mutation(self):
        for name in self.fixture().fields:
            o=self.fixture();o.fields[name]['shape']=(1,);self.assertEqual(o.report()['status'],'INCOMPLETE')
            o=self.fixture();o.fields[name]['writes']=True;self.assertEqual(o.report()['status'],'INCOMPLETE')


if __name__=='__main__':unittest.main()
