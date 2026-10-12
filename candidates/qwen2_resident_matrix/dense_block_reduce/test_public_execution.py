"""Original public metadata -> Norm -> complete Q Dense -> Bias, synthetic M16.

The original full21 image is scanned; only its first three commands execute.
No weights, reference tensors, new compilation, RTL or block acceptance here.
"""
import os
import struct
import time
import unittest
from .public_execution import ReducedPublicExecution,ReductionDriver
from .matrix_binding import ProfiledMatrixService
from .profile import QWEN2_QKV_PROFILE
from .dense_drain import DenseReductionOwner,drain
from ..official_bf16.owners import OfficialPrefixOwner,OfficialAttentionOwner
from ..official_bf16.test_owners import verified_library
from ..ffn_public.fixture import make_qwen2_21_fixture
from ..ffn_public import model as public,prefix_execution as prefix
from ..ffn_public.execute_numeric import numeric
from ..ffn_public.prefix_arithmetic import ScalarService


class PublicExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('MATRIX_SERVICE_LIBRARY'):
            raise AssertionError('explicit receipt-verified Matrix library required')
        cls.library=verified_library()

    def make_reduction(self,*,q_weight=0x3f00):
        f=make_qwen2_21_fixture(16)
        providers={name:(lambda offset:struct.pack('<32H',*([0x3f00]*32))) if a.dtype==5 else
            (lambda offset:struct.pack('<16I',*([0x3f800000]*16)))
            for name,a in f.allocations.items() if a.readonly}
        providers['wq']=lambda offset:struct.pack('<32H',*([q_weight]*32))
        physical=prefix.PhysicalMemory(f,providers);r=f.config.regions[3]
        o=DenseReductionOwner(drain.PrefixWorkspace(r.base,r.limit-r.base,f.config.epoch+1,2560),
            enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,
            enable_ffn_window=True,enable_ffn_tiles=True)
        lib=self.library;self.assertEqual(lib.td_reset(),0)
        service=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE);scalar=ScalarService()
        x=ReducedPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),o,
            numeric.CappedTrace(),time.monotonic()+90,fixture=f,
            host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
            prefix_owner=OfficialPrefixOwner(scalar),attention_owner=OfficialAttentionOwner(service,scalar),
            matrix_service=service)
        norm=x.advance_to_request()['ordinary_request'];self.assertEqual(norm.tag&0xffff,0)
        prefix.execute_prefix_owner(x,physical,norm)
        x.publish_completions((0,));physical.publish(norm,x.host)
        job=x.advance_to_request()['ordinary_request'];self.assertEqual(job.tag&0xffff,1)
        return x,physical,ReductionDriver(x,physical,job)

    def test_actual_public_norm_complete_q_and_bias_share_memory_and_publication(self):
        x,physical,driver=self.make_reduction()
        o,service,job=x.owner,x.matrix_service,driver.public_job
        while driver.terminal is None:
            driver.tick()
            self.assertFalse(physical.regions['qraw']['published'])
        # All physical output writes/ACKs happened; completion is still held.
        self.assertEqual(x.host.completed,1);self.assertEqual(x.host.state,'complete')
        raw=physical.raw(job.dst,job.write_bytes)
        self.assertEqual(raw,struct.pack('<f',768.0)*(16*1536))
        self.assertEqual(len(driver.partials),20);self.assertEqual(len(driver.drains),10)
        self.assertEqual(driver.terminal.useful_macs,16*1536*1536)
        self.assertEqual(driver.terminal.executed_macs,driver.counts['backend_step_fire']*4096)
        self.assertGreater(driver.counts['matrix_result_capacity_stall'],0)
        self.assertEqual(driver.terminal.write_bytes,job.write_bytes)
        self.assertEqual(driver.counts['final_ack_stall'],5)
        self.assertEqual(o.k_a_fences,1);self.assertIsNone(o.lease)
        self.assertFalse(o.tiles.leased);self.assertIsNone(service.owner)
        x.reduction=None
        x.publish_completions((1,));physical.publish(job,x.host);x.retire_ordinary_bookkeeping()
        bias=x.advance_to_request()['ordinary_request'];self.assertEqual(bias.tag&0xffff,2)
        self.assertEqual(bias.a,job.dst)
        prefix.execute_prefix_owner(x,physical,bias)
        self.assertFalse(physical.regions['qr']['published'])
        x.publish_completions((2,));physical.publish(bias,x.host)
        # BF16 spacing at 768 is four, so 768 + 1 rounds back to 768.
        self.assertEqual(physical.raw(bias.dst,bias.write_bytes),raw)
        self.assertEqual((x.host.pc,x.host.completed),(3,3))
        self.assertIsNone(x.launch_result)
        physical.check_coexistence(unpublished_pristine=True)


    def until(self,driver,predicate,limit=100000):
        for _ in range(limit):
            if predicate():return
            driver.tick()
        self.fail(('bounded public reduction watchdog',driver.c.state,driver.owner.state,
                   driver.owner.error,driver.service.lib.matrix_state()))

    def assert_failed_retired(self,x,physical,driver):
        self.until(driver,lambda:driver.terminal is not None)
        self.assertIsNotNone(driver.terminal.status)
        self.assertEqual(x.counts['owner_result_fire'],2)  # completed Norm, failed Dense
        self.assertEqual(driver.counts['result_fire'],1)
        self.assertEqual(x.host.state,'complete')
        self.assertIsNotNone(x.host.status)
        self.assertEqual(x.host.completed,1)
        self.assertEqual(x.host.events,{0,1})
        self.assertNotIn((driver.public_job.dst,driver.public_job.dst+driver.public_job.write_bytes),x.host.published)
        self.assertFalse(physical.regions['qraw']['terminal'])
        self.assertFalse(physical.regions['qraw']['published'])
        self.assertIsNone(driver.read);self.assertIsNone(driver.write);self.assertIsNone(driver.ack)
        self.assertFalse(driver.results);self.assertIsNone(driver.adapter)
        self.assertIsNone(driver.service.owner);self.assertEqual(driver.service.lib.matrix_state()&255,0)
        self.assertIsNone(physical.pending)
        self.assertTrue(driver.owner.tiles.idle)
        self.assertTrue(driver.loan.ports()['drained']);self.assertFalse(driver.sum.busy)
        self.assertFalse(driver.loan.pending)
        self.assertIsNone(driver.owner.read_active);self.assertIsNone(driver.owner.a_rmw_pending)
        self.assertIsNone(driver.owner.pending);self.assertFalse(driver.owner.fifo)
        self.assertIsNone(driver.owner.accepted_write)
        self.assertTrue(driver.c.poison);self.assertEqual(driver.c.state,'locked')
        self.assertFalse(driver.c.ports(driver.services())['request_ready'])
        # Failure completion and launch result each backpressure normally and
        # must not promote the Dense allocation or erase poison/live tile tags.
        held=x.ports()['completion'];tags=tuple(t.live for t in driver.owner.tiles.tags)
        self.assertIsNotNone(held.status)
        for _ in range(4):
            driver.tick()
            self.assertEqual(x.ports()['completion'],held)
            self.assertEqual(tuple(t.live for t in driver.owner.tiles.tags),tags)
        x.completion_ready=True;driver.tick();x.completion_ready=False
        self.assertEqual(x.host.state,'finish')
        self.assertIsNotNone(x.ports()['launch_result']['status'])
        x.result_ready=True;driver.tick();x.result_ready=False
        self.assertEqual(x.host.state,'locked')
        self.assertIsNotNone(x.launch_result['status'])
        self.assertEqual(driver.counts['result_fire'],1)
        self.assertFalse(physical.regions['qraw']['published'])
        self.assertEqual(tuple(t.live for t in driver.owner.tiles.tags),tags)
        physical.check_coexistence()

    def test_real_finite_input_overflow_drains_without_fake_result_or_later_steps(self):
        # Max finite BF16 weights and actual Norm output 1.0 overflow FP32
        # accumulation. No FPU result, return code, or owner method is patched.
        x,physical,driver=self.make_reduction(q_weight=0x7f7f)
        self.assertNotEqual(0x7f7f&0x7f80,0x7f80)
        self.until(driver,lambda:driver.matrix_fault is not None)
        failure=dict(driver.matrix_fault)
        self.assertEqual(failure['rc'],-3)
        self.assertEqual(driver.counts['matrix_step_errors'],1)
        self.assertFalse(driver.results)
        self.assertFalse(driver.adapter.pending)
        self.assertTrue(driver.service.reset_required)
        self.assertTrue(driver.service.lib.matrix_done_ready())
        stopped=driver.counts['backend_step_fire']
        self.assertEqual(failure['accepted_steps'],stopped)
        report=driver.run()
        self.assertEqual(driver.counts['backend_step_fire'],stopped)
        self.assertEqual(driver.counts['backend_result_fire'],0)
        self.assertEqual(driver.counts['backend_matrix_done_fire'],1)
        self.assertEqual(driver.counts['matrix_abort_fire'],1)
        self.assertEqual(driver.terminal.write_bytes,0)
        self.assertEqual(report['matrix_step_failure'],failure)
        actual=report['actual_dense_fma_calls_delta']
        self.assertEqual(actual,(stopped-1)*4096+1)
        self.assertEqual(driver.terminal.executed_macs,stopped*4096)
        self.assertLess(actual,driver.terminal.executed_macs)
        self.assertIn('stop mid-step',report['failed_step_counter_note'])
        self.assertIs(x.reduction,driver)
        self.assert_failed_retired(x,physical,driver)
        self.assertTrue(driver.owner.tiles.tags[0].live)

    def test_abort_after_accepted_read_drains_without_inventing_matrix_done(self):
        x,physical,driver=self.make_reduction()
        self.until(driver,lambda:driver.read is not None)
        self.assertFalse(driver.owner.group_started)
        self.assertEqual(driver.counts['backend_read_command_fire'],1)
        driver.tick(abort=True)
        report=driver.run()
        self.assertIsNotNone(report['terminal']['status'])
        self.assertIs(x.reduction,driver)  # failed run does not drop its lock
        self.assert_failed_retired(x,physical,driver)
        self.assertEqual(driver.counts['matrix_abort_fire'],1)
        self.assertEqual(driver.counts['backend_read_fire'],1)
        self.assertEqual(driver.counts['backend_matrix_done_fire'],0)
        self.assertEqual(driver.service.report()['counters'].get('dense_groups',0),0)
        self.assertEqual(driver.terminal.write_bytes,0)

    def test_abort_after_actual_matrix_steps_retires_real_done_once(self):
        x,physical,driver=self.make_reduction()
        self.until(driver,lambda:driver.counts['backend_step_fire']>=7)
        self.assertIs(driver.service.owner,driver.owner)
        self.assertTrue(driver.owner.group_started)
        self.assertFalse(driver.service.lib.matrix_done_ready())
        driver.tick(abort=True)
        self.assertEqual(driver.counts['matrix_abort_fire'],1)
        self.assert_failed_retired(x,physical,driver)
        self.assertEqual(driver.service.report()['counters']['aborts'],1)
        self.assertEqual(driver.counts['backend_matrix_done_fire'],1)
        self.assertTrue(driver.service.reset_required)
        self.assertTrue(driver.owner.tiles.tags[0].live)
        self.assertEqual(driver.terminal.write_bytes,0)

    def test_abort_with_actual_matrix_result_queued_drains_before_done(self):
        x,physical,driver=self.make_reduction()
        self.until(driver,lambda:bool(driver.results))
        self.assertFalse(driver.service.lib.matrix_done_ready())
        done_before=driver.counts['backend_matrix_done_fire']
        driver.tick(abort=True)
        self.assertEqual(driver.counts['backend_matrix_done_fire'],done_before)
        self.assert_failed_retired(x,physical,driver)
        counts=driver.service.report()['counters']
        self.assertEqual(counts['aborts'],1)
        self.assertEqual(counts['dense_done'],1)
        self.assertEqual(driver.counts['backend_result_fire'],counts['dense_results'])
        self.assertGreater(counts['dense_results'],0)

    def test_abort_after_accepted_write_descriptor_drains_data_ack_without_publish(self):
        x,physical,driver=self.make_reduction()
        self.until(driver,lambda:driver.write is not None and driver.write_index==0)
        accepted=driver.write
        self.assertIsNotNone(physical.pending)
        self.assertIsNone(driver.service.owner)
        driver.tick(abort=True)
        self.assertIsNone(driver.terminal)
        self.assert_failed_retired(x,physical,driver)
        self.assertEqual(driver.counts['matrix_abort_fire'],0)
        self.assertEqual(driver.counts['backend_write_command_fire'],1)
        self.assertEqual(driver.counts['backend_write_data_fire'],accepted.beats)
        self.assertEqual(driver.counts['backend_write_ack_fire'],1)
        self.assertEqual(driver.terminal.write_bytes,accepted.beats*64)
        self.assertTrue(driver.owner.tiles.tags[2].live)

    def test_abort_after_accepted_add_drains_actual_lanes_without_publish(self):
        x,physical,driver=self.make_reduction()
        self.until(driver,lambda:driver.loan.active and driver.loan.state=='wait')
        self.assertTrue(driver.loan.pending)
        self.assertIsNone(driver.service.owner)
        driver.tick(abort=True)
        self.assertFalse(driver.loan.ports()['drained'])
        self.assertIsNone(driver.terminal)
        self.assert_failed_retired(x,physical,driver)
        self.assertEqual(driver.counts['matrix_abort_fire'],0)
        self.assertEqual(driver.loan.published,[])
        self.assertEqual(driver.counts['backend_write_command_fire'],0)
        self.assertEqual(driver.terminal.write_bytes,0)
        self.assertTrue(driver.owner.tiles.leased)


if __name__=='__main__':unittest.main()
