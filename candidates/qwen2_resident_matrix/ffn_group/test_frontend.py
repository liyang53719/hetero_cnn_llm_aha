#!/usr/bin/env python3
"""Bounded composition/source integration guards; no arithmetic/RTL claims."""
from pathlib import Path
import importlib.util,json,tempfile,unittest
TASK=Path(__file__).resolve().parent
ROOT=TASK.parents[2]
spec=importlib.util.spec_from_file_location('resident_frontend',TASK/'check_frontend.py')
front=importlib.util.module_from_spec(spec);spec.loader.exec_module(front)

class ProductionComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='ffn_group_composition_',dir=ROOT/'work')
        cls.source=Path(cls.tmp.name)
        cls.paths,cls.pins=front.compose(cls.source)
        cls.host=(cls.source/(front.PREFIX+'HostBlockCommands.scala')).read_text()
        cls.kernel=(cls.source/(front.PREFIX+'QwenOwnerProtocol.scala')).read_text()
        cls.top=(cls.source/(front.PREFIX+'HostBlockTop.scala')).read_text()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_exact_parent_postimages_and_pins(self):
        self.assertEqual(self.pins,json.loads((TASK/'source_pins.json').read_text()))
        self.assertEqual(len(self.paths),len(set(self.paths)))
    def test_actual_kernel_instantiates_the_coordinator(self):
        self.assertIn('Some(Module(new FfnResidentCoordinator))',self.kernel)
        self.assertIn('!resident.get.io.group.busy && !io.resident.get.request.valid',self.kernel)
        for port in ('tiles','window','drain','tileSilu'):
            self.assertRegex(self.kernel,r'val '+port+r'=if\([^\n]* && !enableResidentFfn\)')
        self.assertIn('owner.io.resident.get<>cmd.io.resident.get',self.top)
    def test_no_harness_bridge_duplicate(self):
        definitions=[]
        for path in self.paths:
            if path.endswith('.scala'):
                if 'class FfnTileSiluBridge(' in (self.source/path).read_text():definitions.append(path)
        self.assertEqual(definitions,['candidates/qwen2_resident_matrix/ffn_group/FfnTileSiluBridge.scala'])
    def test_no_private_public_opcode_or_bias_convention(self):
        original=(self.source/'baseline/HostBlockCommandsGroupBaseline.scala').read_text()
        old_kind=(self.source/(front.PREFIX+'QwenOwnerProtocol.scala')).read_text().split('object QwenOwnerKind {',1)[1].split('}',1)[0]
        self.assertNotIn('Ffn',old_kind)
        self.assertNotIn('bias_index',self.host)
        self.assertEqual(original.count('opcode===0x20.U'),self.host.count('opcode===0x20.U')-1)
        self.assertIn('sameAllocation(a,score)&&sameAllocation(b,probability)',self.host)
    def test_preflight_uses_real_typed_reader_and_full_spans(self):
        self.assertIn('state===scanTensorIssue||state===scanTensorGet',self.host)
        self.assertIn('val response=tensor.io.result.bits;val t=response.tensor',self.host)
        self.assertIn('overlap(t.address,t.paddedEnd,score.address,score.paddedEnd)',self.host)
        self.assertIn('overlap(t.address,t.paddedEnd,probability.address,probability.paddedEnd)',self.host)
        self.assertIn('virtualCount+&2.U>maxCommands.U',self.host)
        self.assertIn('sameAllocation(t,score)',self.host)
        self.assertIn('sameAllocation(t,probability)',self.host)
    def test_flush_reaches_existing_adapter(self):
        self.assertIn('owner.io.residentHandoff.get.valid',self.top)
        self.assertIn('dma.io.flush:=io.launch.fire||owner.io.job.fire||owner.io.done.fire||owner.io.residentHandoff.get.valid',self.top)
        adapter=next(self.source/p for p in self.paths if p.endswith('WeightBurstIdma.scala')) if any(p.endswith('WeightBurstIdma.scala') for p in self.paths) else None
        if adapter is None:
            adapter=next(self.source/p for p in self.paths if p.endswith('.scala') and 'class RetainedIdmaWeightBurstAdapter' in (self.source/p).read_text())
        text=adapter.read_text()
        self.assertRegex(text,r'io\.request\.ready\s*:=.*!io.flush')
        self.assertRegex(text,r'io\.streamRequest.get.ready\s*:=.*!io.flush')
    def test_poison_fences_every_public_success(self):
        self.assertIn('io.resident.get.resetRequired && (resident.get.pending || r.status===0.U)){fail(Status.Protocol.U)}',self.host)
        self.assertIn('status=/=0.U || !io.resident.get.resetRequired',self.host)
        self.assertIn('state===complete && status===0.U && io.resident.get.resetRequired',self.host)
        self.assertIn("owner.io.resident.get.resetRequired || owner.io.resetRequired || hub.io.resetRequired || dmaPoison",self.top)
        self.assertNotIn("state===finish &&",self.host)
    def test_numeric_acceptance_not_claimed(self):
        profile=(TASK/'FfnResidentProfile.scala').read_text()
        self.assertIn('"numeric_policy_approved":false',profile)
        self.assertIn('"native_arithmetic_accepted":false',profile)
        self.assertIn('"fp32_final_accepted":false',profile)

if __name__=='__main__':unittest.main()
