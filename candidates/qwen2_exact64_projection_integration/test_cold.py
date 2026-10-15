"""No compilation, tensor inputs or native arithmetic: protocol rejection gates."""
import ctypes as C
from dataclasses import replace
import inspect
import unittest
from .kernel import Exact64Kernel,source_check
from .owner import Exact64ProjectionOwner,MemoryResponse,MemoryRequest
from .driver import Exact64PublicDriver
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job

def cold_kernel():
    # Exact class shell for metadata/protocol-only tests. No numerical PASS.
    k=Exact64Kernel.__new__(Exact64Kernel);k.state='idle';k.fmas=C.c_uint64();k.adds=C.c_uint64()
    k.partial=(C.c_float*4096)();k.next_k=k.serial=0;k.tile=k.output=None
    return k

def job():return Job('Dense',0x110001,0x100000,0x200000,0x900000,1,256,1536,1024,weight_bf16=True)

class Cold(unittest.TestCase):
    def owner(self):return Exact64ProjectionOwner(cold_kernel())
    def test_small_service_scope(self):
        from . import check_small
        from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService
        self.assertIs(check_small.MatrixService,MatrixService)
    def test_source_pins(self):self.assertEqual(len(source_check()),3)
    def test_capacities(self):
        o=self.owner();self.assertEqual(len(o.row),6144);self.assertEqual(len(o.weights),128)
        self.assertEqual(o.report()['payload_capacity']['conservative_total'],23552)
    def test_real_public_dense_job_without_third_operand(self):
        from candidates.qwen2_resident_matrix.ffn_group.model import Job as PublicJob,PrefixJob
        from dataclasses import asdict
        j=PublicJob('Dense',0x110001,0x100000,0x200000,0x900000,16,1536,1536,98304,weight_bf16=True)
        self.assertFalse(hasattr(j,'c'));o=self.owner();o.validate(j)
        self.assertTrue(o.tick(job=j)['job_fire']);self.assertIs(o.job,j)
        self.assertEqual(o.ports()['memory'].address,j.a)
        for bad in (1,True,None,'private/path',0.0):
            with self.assertRaises(ValueError):self.owner().validate(PrefixJob(**asdict(j),c=bad))
        self.owner().validate(PrefixJob(**asdict(j),c=0))
    def test_all_direct_job_fields_exist_on_public_job(self):
        import ast
        from dataclasses import fields
        from candidates.qwen2_resident_matrix.ffn_group.model import Job as PublicJob
        allowed={f.name for f in fields(PublicJob)}
        for cls in (Exact64ProjectionOwner,Exact64PublicDriver):
            for node in ast.walk(ast.parse(inspect.getsource(cls))):
                if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id in ('j','job'):
                    self.assertIn(node.attr,allowed)
    def test_geometry(self):
        o=self.owner();o.validate(job())
        for kw in ({'m':True},{'n':True},{'k':1535},{'m':129},{'a':True},{'a':0x100001},
                   {'dst':0x100000},{'write_bytes':True},{'weight_bf16':1},{'c':True},{'tag':True}):
            with self.assertRaises(ValueError):o.validate(replace(job(),**kw))
    def test_request_stable(self):
        o=self.owner();self.assertTrue(o.tick(job=job())['job_fire']);q=o.ports()['memory']
        for _ in range(4):
            e=o.tick();self.assertEqual(e['memory'],q);self.assertFalse(e['memory_fire'])
        self.assertEqual(o.report()['kernel_delta']['fmas'],0)
    def test_abort_unaccepted(self):
        o=self.owner();o.tick(job=job());e=o.tick(memory_ready=True,abort=True)
        self.assertFalse(e['memory_fire']);self.assertEqual(o.ports()['response'].status,'Protocol')
    def test_abort_accepted_debt(self):
        o=self.owner();o.tick(job=job());q=o.ports()['memory'];o.tick(memory_ready=True)
        o.tick(abort=True);self.assertIsNone(o.ports()['response']);self.assertTrue(o.ports()['memory_response_ready'])
        o.tick(memory_response=MemoryResponse(q.tag,b'\0'*64));self.assertEqual(o.ports()['response'].status,'Protocol')
        self.assertEqual(o.kernel.report()['fmas'],0)
    def test_bad_response(self):
        for change in ({'nbytes':True},{'nbytes':32},{'error':1},{'data':b''},{'data':(0,)*16}):
            o=self.owner();o.tick(job=job());q=o.ports()['memory'];o.tick(memory_ready=True)
            o.tick(memory_response=replace(MemoryResponse(q.tag,b'\0'*64),**change))
            self.assertEqual(o.ports()['response'].status,'Protocol');self.assertEqual(o.ack_bytes,0)
    def test_bad_response_type(self):
        o=self.owner();o.tick(job=job());o.tick(memory_ready=True);o.tick(memory_response=object())
        self.assertIsNone(o.ports()['response']);self.assertEqual(o.state,'drain')
    def test_foreign_tag_keeps_debt(self):
        for abort in (False,True):
            for wrong in (False,1):
                o=self.owner();o.tick(job=job());q=o.ports()['memory'];o.tick(memory_ready=True)
                e=o.tick(abort=abort,memory_response=MemoryResponse(wrong,b'\0'*64))
                self.assertFalse(e['memory_response_fire']);self.assertIs(o.request,q);self.assertIsNone(o.ports()['response'])
                e=o.tick(memory_response=MemoryResponse(q.tag,b'\0'*64));self.assertTrue(e['memory_response_fire'])
                self.assertEqual(o.ports()['response'].status,'Protocol')
    def test_foreign_write_ack_keeps_debt(self):
        o=self.owner();o.tick(job=job());q=MemoryRequest(job().dst,123,True,b'\0'*64,(1<<64)-1)
        o.request=q;o.state='wait'  # cold accepted-write obligation fixture only
        e=o.tick(abort=True,memory_response=MemoryResponse(124))
        self.assertFalse(e['memory_response_fire']);self.assertIs(o.request,q);self.assertEqual(o.ack_bytes,0)
        self.assertIsNone(o.ports()['response'])
        e=o.tick(memory_response=MemoryResponse(123));self.assertTrue(e['memory_response_fire'])
        self.assertEqual(o.ack_bytes,64);self.assertEqual(o.ports()['response'].status,'Protocol')
    def test_driver_preaccept_abort(self):
        from types import SimpleNamespace
        d=Exact64PublicDriver.__new__(Exact64PublicDriver)
        d.cancelled=False;d.started=False;d.terminal=None;d.x=SimpleNamespace(exact64_projection=d)
        with self.assertRaises(ValueError):d.tick(abort=1)
        self.assertIs(d.x.exact64_projection,d)
        self.assertTrue(d.tick(abort=True)['cancelled']);self.assertIsNone(d.x.exact64_projection)
    def test_native_handshake_bits(self):
        o=self.owner()
        for field in ('abort','memory_ready','response_ready'):
            with self.assertRaises(ValueError):o.tick(**{field:1})
        self.assertEqual(o.clock,0)
    def test_failed_terminal_held(self):
        o=self.owner();o.tick(job=replace(job(),k=1));r=o.ports()['response']
        for _ in range(3):o.tick();self.assertEqual(o.ports()['response'],r)
        self.assertTrue(o.tick(response_ready=True)['response_fire']);self.assertEqual(o.state,'locked')
        self.assertFalse(o.tick(job=job())['job_fire'])
    def test_driver_rejects_detached(self):
        with self.assertRaises(ValueError):Exact64PublicDriver(object(),object(),job(),self.owner())
    def test_no_matrix_arithmetic(self):
        text=inspect.getsource(Exact64PublicDriver)
        self.assertNotIn('.td_step(',text);self.assertNotIn('.normal(',text)
        self.assertIn('self.memory.write_event',text);self.assertIn('self.service.retire_owner_response',text)
if __name__=='__main__':unittest.main()
