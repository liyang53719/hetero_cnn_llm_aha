"""Initialized transposed_seed base owner + PhysicalMemory, synthetic 128B.

This base owner is not the public runner's FfnDrainOwnerModel inheritance chain.
The held-terminal test initializes finish/ack directly. The separate
test_ffn_drain_debts module covers the actual owner's final-ACK transitions.
"""
import copy
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from candidates.qwen2_resident_matrix.transposed_seed import model
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory, execution
wire = execution.numeric.model.down
from .debts import retained_write_evidence, corrected_debts


def fixture():
    allocation=NS(address=4096,storage_bytes=128,reserved_bytes=128,dtype=7,readonly=False,virtual=False)
    table1,table2=NS(base=8192),NS(base=8256)
    f=NS(validate_spans=lambda:None,allocations={'down':allocation},
         config=NS(command=table1,descriptor=table2),memory=NS(mappings={8192:bytes(64),8256:bytes(64)}))
    physical=PhysicalMemory(f,{})
    owner=model.DenseOwnerModel()
    command=model.WriteCommand(4096,2,123)
    owner.accepted_write=command
    physical.write_event('command',command)
    physical.write_event('data',wire.WriteBeat((0,)*16,False))
    physical.write_event('data',wire.WriteBeat((0,)*16,True))
    physical.write_event('ack',model.WriteAck(123,nbytes=128))
    return owner,physical

class RetainedWriteTests(unittest.TestCase):
    def test_real_writer_ack_retired_and_nonmutating(self):
        owner,p=fixture(); descriptor=owner.accepted_write
        before=copy.deepcopy(p.regions);ports=owner.ports()
        debts,e=corrected_debts({'accepted_write':True,'other':True},owner,p)
        self.assertTrue(e['retired']);self.assertFalse(debts['accepted_write']);self.assertTrue(debts['other'])
        self.assertIs(owner.accepted_write,descriptor);self.assertEqual(p.regions,before);self.assertEqual(owner.ports(),ports)

    def test_real_owner_ack_then_held_terminal_retirement(self):
        o,p=fixture()
        # Synthetic base-owner finish/ack boundary, not a production lifecycle.
        o.state='finish';o.write_state='ack'
        o.write_row_beat=0;o.write_row=0;o.job=NS(tag=123,output_bf16=False,m=1)
        ack=p.regions['down']['records'][0][1]
        self.assertFalse(retained_write_evidence(o,p)['retired'])
        edge=o.tick(write_ack=ack,response_ready=False)
        self.assertTrue(edge['write_ack_fire']);self.assertEqual(o.write_state,'idle')
        self.assertFalse(retained_write_evidence(o,p)['retired'])
        for _ in range(3):
            self.assertFalse(o.tick(response_ready=False)['response_fire'])
            self.assertFalse(retained_write_evidence(o,p)['retired'])
        descriptor=o.accepted_write
        self.assertTrue(o.tick(response_ready=True)['response_fire'])
        self.assertEqual(o.state,'idle');self.assertIs(o.accepted_write,descriptor)
        self.assertTrue(retained_write_evidence(o,p)['retired'])

    def test_live_writer_and_pending_rejected(self):
        for attr,value in [('state','finish'),('write_state','ack'),('error','fault'),('pending',object())]:
            with self.subTest(attr=attr):
                o,p=fixture();setattr(o,attr,value);self.assertFalse(retained_write_evidence(o,p)['retired'])
        o,p=fixture();p.pending=['outstanding'];self.assertFalse(retained_write_evidence(o,p)['retired'])

    def test_live_ports_rejected(self):
        for field,value in [('write_command',object()),('write_data',object()),('write_ack_ready',True),('reset_required',True)]:
            with self.subTest(field=field):
                o,p=fixture();ports=o.ports();ports[field]=value
                with patch.object(o,'ports',return_value=ports):self.assertFalse(retained_write_evidence(o,p)['retired'])

    def test_coverage_and_duplicate_record_rejected(self):
        for field in ('written','acked'):
            o,p=fixture();p.regions['down'][field].remove(4160);self.assertFalse(retained_write_evidence(o,p)['retired'])
        for count in (0,2):
            o,p=fixture();p.regions['down']['records']*=count;self.assertFalse(retained_write_evidence(o,p)['retired'])

    def test_ack_mismatch_error_and_optional_bytes_rejected(self):
        for changes in ({'tag':124},{'error':True},{'nbytes':64},{'nbytes':None}):
            o,p=fixture();cmd,ack=p.regions['down']['records'][0];p.regions['down']['records']=[(cmd,replace(ack,**changes))]
            self.assertFalse(retained_write_evidence(o,p)['retired'])

    def test_wrong_or_ambiguous_region_rejected(self):
        o,p=fixture();p.regions['other']=p.regions.pop('down');self.assertFalse(retained_write_evidence(o,p)['retired'])
        o,p=fixture();p.regions['alias']=p.regions['down'];self.assertFalse(retained_write_evidence(o,p)['retired'])

    def test_no_descriptor_and_missing_fields(self):
        o,p=fixture();o.accepted_write=None;self.assertFalse(corrected_debts({'accepted_write':False},o,p)[0]['accepted_write'])
        o,p=fixture();del p.regions['down']['records'];self.assertFalse(retained_write_evidence(o,p)['retired'])

if __name__=='__main__':unittest.main()
