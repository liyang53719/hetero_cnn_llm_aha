#!/usr/bin/env python3
"""Bounded source/model checks. These are NOT retained RTL simulation evidence."""
from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import json
import re
import os
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PATCH=HERE/"retained_accumulator_seed.patch"
MANIFEST=json.loads((HERE/"source_manifest.json").read_text())
BASE=MANIFEST["base_commit"]
TEMP=None
OVERLAY=None
SV=None

def frozen(path):
    return subprocess.check_output(["git","show",f"{BASE}:{path}"],cwd=ROOT)

def setUpModule():
    global TEMP,OVERLAY,SV
    work=ROOT/"work/qwen2_transposed_seed_leaf_20261011/leaf"
    work.mkdir(parents=True,exist_ok=True)
    TEMP=tempfile.TemporaryDirectory(prefix="contract_overlay_",dir=work)
    OVERLAY=Path(TEMP.name)
    SV=OVERLAY/"rtl/matrix/candidates/rev8b_b"
    for path,pins in MANIFEST["files"].items():
        data=frozen(path)
        if hashlib.sha256(data).hexdigest()!=pins["base_sha256"]:
            raise AssertionError("Frozen source pin drift: "+path)
        target=OVERLAY/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    if hashlib.sha256(PATCH.read_bytes()).hexdigest()!=MANIFEST["patch_sha256"]:
        raise AssertionError("Patch pin drift")
    # Keep apply rooted in this isolated overlay, irrespective of enclosing git.
    env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(work.resolve()))
    subprocess.run(["git","apply","--check",str(PATCH)],cwd=OVERLAY,env=env,check=True,capture_output=True)
    subprocess.run(["git","apply",str(PATCH)],cwd=OVERLAY,env=env,check=True,capture_output=True)

def tearDownModule():
    if TEMP is not None:
        TEMP.cleanup()


@dataclass(frozen=True)
class Identity:
    context:int=0
    group_tag:int=0x12345678
    group_sequence:int=123
    source_generation:int=0x87654321

class SeedContract:
    """Independent event-level contract, with one physical five-bank lane set.

    A returned ACK is visible only to the caller's NEXT observation after
    commit. Abort preserves any previously offered ACK tuple, but poisons the
    transaction and invalidates its bank. No arithmetic is emulated here.
    """
    def __init__(self):
        self.banks=[[0xdeadbeef]*5 for _ in range(512)]
        self.valid=[True]*5
        self.reserved=None
        self.last_identity=None
        self.count=0
        self.ack=None
        self.poison=False
        self.arithmetic_busy=0
        self.arithmetic_out_valid=False
        self.arithmetic_counters=(13,13)
        self.arithmetic_fifo_pointers=(2,2,3,3)

    def bad(self):
        self.poison=True
        if self.last_identity is not None and self.last_identity.context<5:
            self.valid[self.last_identity.context]=False

    def begin(self,identity):
        if self.poison or self.reserved is not None or self.ack is not None:
            self.bad();return False
        if self.arithmetic_busy or self.arithmetic_out_valid:
            self.bad();return False
        if not 0<=identity.context<5:
            self.bad();return False
        self.reserved=identity
        self.last_identity=identity
        self.valid[identity.context]=False
        self.count=0
        return True

    def beat(self,identity,cluster,words):
        legal=(not self.poison and self.reserved==identity and self.ack is None and
            self.count<32 and cluster==self.count and len(words)==16 and
            all(0<=x<=0xffffffff and (x>>23)&255!=255 for x in words))
        if not legal:
            self.bad();return False
        for lane,word in enumerate(words):
            self.banks[cluster*16+lane][identity.context]=word
        self.count+=1
        return True

    def commit(self,identity):
        if self.poison or self.reserved is None or self.ack is not None:
            self.bad();return False
        error=self.count!=32 or identity!=self.reserved
        self.ack=(self.reserved,error)
        if error:
            self.bad()
        else:
            self.valid[identity.context]=True
        return not error

    def accept_ack(self):
        ack=self.ack
        self.ack=None
        if not self.poison:
            self.reserved=None
        return ack

    def abort(self):
        self.bad()

    @property
    def datapath_hold(self):
        return self.reserved is not None or self.ack is not None

    def drain_accepted_arithmetic(self):
        assert not self.datapath_hold
        self.arithmetic_counters=(self.arithmetic_counters[0],self.arithmetic_counters[1]+1)
        self.arithmetic_busy=0
        self.arithmetic_out_valid=False

def words(cluster):
    # Includes both zero signs, both subnormal signs, min normal, max finite.
    special=[0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,
             0x00800000,0x80800000,0x7f7fffff,0xff7fffff]
    return [special[(cluster+lane)%len(special)] if lane<10 else
            (0x3f000000+cluster*16+lane) for lane in range(16)]

def complete(model,identity):
    assert model.begin(identity)
    for cluster in range(32):
        assert model.beat(identity,cluster,words(cluster))
    assert model.ack is None
    assert model.commit(identity)

class TokenDrainContract:
    """Cycle-level consistency oracle, not an FMA or clock-gate simulator.

    Four accepted-token stages correspond to input, pre, mul, and post;
    post/round writes the result FIFO on the next edge. Metadata and payload
    move independently so an erroneous raw-begin data freeze is detectable.
    """
    def __init__(self,unsafe_raw_begin_freeze=False):
        self.seed=SeedContract()
        self.tokens=[None]*4
        self.data=[None]*4
        self.flags=[None]*4
        self.result_tokens=[]
        self.results=[]
        self.result_flags=[]
        self.accepted=0
        self.completed=0
        self.result_write=0
        self.result_read=0
        self.flags_write=0
        self.flags_read=0
        self.seed_writes=0
        self.observed=[]
        self.unsafe_raw_begin_freeze=unsafe_raw_begin_freeze

    @staticmethod
    def payload(token):
        return 0x3f800000+token,token&31

    @property
    def busy(self):
        return any(x is not None for x in self.tokens) or bool(self.result_tokens)

    def tick(self,*,begin=False,new_token=None,out_ready=False):
        self.seed.arithmetic_busy=int(self.busy)
        self.seed.arithmetic_out_valid=bool(self.result_tokens)
        if begin:
            self.seed.begin(Identity())
        hold=self.seed.datapath_hold or (begin and self.unsafe_raw_begin_freeze)
        admit=new_token is not None and not(begin or self.seed.poison or self.seed.datapath_hold)
        # Scheduler consumes its existing token irrespective of seed admission.
        if self.result_tokens and out_ready:
            token=self.result_tokens.pop(0)
            data=self.results[0] if self.results else None
            flags=self.result_flags[0] if self.result_flags else None
            self.observed.append((token,data,flags))
            self.completed+=1
            if not hold:
                if self.results:self.results.pop(0)
                if self.result_flags:self.result_flags.pop(0)
                self.result_read=(self.result_read+1)%5
                self.flags_read=(self.flags_read+1)%5
        if self.tokens[-1] is not None:
            self.result_tokens.append(self.tokens[-1])
            if not hold:
                self.results.append(self.data[-1])
                self.result_flags.append(self.flags[-1])
                self.result_write=(self.result_write+1)%5
                self.flags_write=(self.flags_write+1)%5
        if not hold:
            self.data=[self.payload(new_token)[0] if admit else None]+self.data[:-1]
            self.flags=[self.payload(new_token)[1] if admit else None]+self.flags[:-1]
        self.tokens=[new_token if admit else None]+self.tokens[:-1]
        self.accepted+=int(admit)
        # No reserve succeeded in the busy-begin rejection scenarios.
        assert self.seed.reserved is None
        return admit

class SeedModelTests(unittest.TestCase):
    def test_busy_begin_at_every_pipeline_stage_drains_tokens_and_data(self):
        for age,stage in enumerate(["input","pre","mul","post_round","stalled_result"]):
            for stall in [0,5]:
                with self.subTest(stage=stage,stall=stall):
                    m=TokenDrainContract();token=17+age
                    self.assertTrue(m.tick(new_token=token))
                    for _ in range(age):m.tick()
                    self.assertTrue(m.busy)
                    self.assertFalse(m.tick(begin=True,new_token=99,out_ready=stall==0))
                    self.assertTrue(m.seed.poison)
                    self.assertFalse(m.seed.datapath_hold)
                    for _ in range(stall):
                        old_fifo=(tuple(m.results),tuple(m.result_flags),m.result_read,m.flags_read)
                        had_result=bool(m.result_tokens)
                        self.assertFalse(m.tick(new_token=99))
                        if had_result:
                            self.assertEqual((tuple(m.results),tuple(m.result_flags),m.result_read,m.flags_read),old_fifo)
                    for _ in range(8):
                        self.assertFalse(m.tick(new_token=99,out_ready=True))
                    expected_data,expected_flags=m.payload(token)
                    self.assertEqual(m.observed,[(token,expected_data,expected_flags)])
                    self.assertEqual((m.accepted,m.completed),(1,1))
                    self.assertEqual((m.result_write,m.result_read,m.flags_write,m.flags_read),(1,1,1,1))
                    self.assertFalse(m.busy)
                    self.assertEqual(m.seed_writes,0)
                    self.assertTrue(m.seed.poison)
        # Mutation sensitivity: reproducing the rejected raw-begin hold must
        # break either payload alignment or a result/flags pointer.
        for age in range(5):
            broken=TokenDrainContract(unsafe_raw_begin_freeze=True)
            broken.tick(new_token=17)
            for _ in range(age):broken.tick()
            broken.tick(begin=True,out_ready=True)
            for _ in range(8):broken.tick(out_ready=True)
            consistent=(broken.observed==[(17,*broken.payload(17))] and
                (broken.result_write,broken.result_read,broken.flags_write,broken.flags_read)==(1,1,1,1))
            self.assertFalse(consistent)

    def test_all_five_banks_raw_finite_and_geometry(self):
        m=SeedContract()
        baseline=(m.arithmetic_counters,m.arithmetic_fifo_pointers)
        for context in range(5):
            identity=Identity(context=context,group_sequence=context+1)
            self.assertTrue(m.begin(identity))
            self.assertFalse(m.valid[context])
            self.assertEqual(m.arithmetic_busy,0)
            for cluster in range(32):
                self.assertTrue(m.beat(identity,cluster,words(cluster)))
                self.assertFalse(m.valid[context])
            self.assertIsNone(m.ack)
            self.assertTrue(m.commit(identity))
            self.assertTrue(m.valid[context])
            self.assertEqual(m.ack,(identity,False))
            for cluster in range(32):
                for lane in range(16):
                    self.assertEqual(m.banks[cluster*16+lane][context],words(cluster)[lane])
            self.assertEqual((m.arithmetic_counters,m.arithmetic_fifo_pointers),baseline)
            self.assertEqual(m.accept_ack(),(identity,False))
        self.assertFalse(m.poison)

    def test_missing_duplicate_skipped_and_extra_beats(self):
        for count in [0,1,15,31]:
            with self.subTest(short=count):
                m=SeedContract();identity=Identity();self.assertTrue(m.begin(identity))
                for cluster in range(count): self.assertTrue(m.beat(identity,cluster,words(cluster)))
                self.assertFalse(m.commit(identity));self.assertTrue(m.poison)
                self.assertFalse(m.valid[0]);self.assertEqual(m.ack,(identity,True))
        for sequence in [[1],[0,0],list(range(32))+[0]]:
            with self.subTest(sequence=sequence):
                m=SeedContract();identity=Identity();m.begin(identity)
                for cluster in sequence: m.beat(identity,cluster,words(cluster))
                self.assertTrue(m.poison);self.assertFalse(m.valid[0])

    def test_wrong_identity_each_field(self):
        for field in Identity.__dataclass_fields__:
            for stage in ["beat","commit"]:
                with self.subTest(field=field,stage=stage):
                    m=SeedContract();identity=Identity();m.begin(identity)
                    wrong=replace(identity,**{field:getattr(identity,field)+1})
                    if stage=="beat": self.assertFalse(m.beat(wrong,0,words(0)))
                    else:
                        for cluster in range(32):m.beat(identity,cluster,words(cluster))
                        self.assertFalse(m.commit(wrong))
                        self.assertEqual(m.ack,(identity,True))
                    self.assertTrue(m.poison);self.assertFalse(m.valid[0])

    def test_nonfinite_never_writes(self):
        for nonfinite in [0x7f800000,0xff800000,0x7fc00001,0x7f800001]:
            m=SeedContract();identity=Identity();m.begin(identity)
            bad_words=words(0);bad_words[7]=nonfinite
            self.assertFalse(m.beat(identity,0,bad_words))
            self.assertEqual([lane[0] for lane in m.banks[:16]],[0xdeadbeef]*16)
            self.assertTrue(m.poison)

    def test_abort_partial_and_ack_backpressure(self):
        for count in [0,1,16,32]:
            m=SeedContract();identity=Identity();m.begin(identity)
            for cluster in range(count):m.beat(identity,cluster,words(cluster))
            m.abort();self.assertTrue(m.poison);self.assertFalse(m.valid[0])
            self.assertFalse(m.begin(Identity(context=1)))
        m=SeedContract();identity=Identity();complete(m,identity)
        held=m.ack
        m.abort()
        self.assertEqual(m.ack,held);self.assertFalse(m.valid[0])
        self.assertEqual(m.accept_ack(),held);self.assertTrue(m.poison)

    def test_late_transport_and_coordinated_reset(self):
        m=SeedContract();identity=Identity();complete(m,identity);m.accept_ack()
        self.assertFalse(m.beat(identity,0,words(0)));self.assertTrue(m.poison)
        self.assertFalse(m.valid[identity.context])
        self.assertFalse(m.begin(Identity(context=1)))
        m=SeedContract();self.assertTrue(m.begin(Identity(context=1)))

    def test_reservation_requires_arithmetic_quiescence(self):
        for busy,out_valid in [(1,False),(0,True),(16,True)]:
            m=SeedContract();m.arithmetic_busy=busy;m.arithmetic_out_valid=out_valid
            self.assertFalse(m.begin(Identity()));self.assertIsNone(m.reserved)
            self.assertTrue(m.poison);self.assertFalse(m.datapath_hold)
            old_completed=m.arithmetic_counters[1]
            m.drain_accepted_arithmetic()
            self.assertEqual(m.arithmetic_counters[1],old_completed+1)
        for context in [5,6,7]:
            m=SeedContract();self.assertFalse(m.begin(Identity(context=context)))
            self.assertTrue(m.poison)

class SourceContractTests(unittest.TestCase):
    def test_frozen_sources_and_patch_application(self):
        manifest=json.loads((HERE/"source_manifest.json").read_text())
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(),manifest["patch_sha256"])
        for path,entry in manifest["files"].items():
            self.assertEqual(hashlib.sha256(frozen(path)).hexdigest(),entry["base_sha256"])
            self.assertEqual(hashlib.sha256((OVERLAY/path).read_bytes()).hexdigest(),entry["patched_sha256"])
        dependencies=json.loads((HERE/"dependency_manifest.json").read_text())
        self.assertEqual(dependencies["base_commit"],BASE)
        for entry in dependencies["source_entries"]:
            self.assertEqual(hashlib.sha256(frozen(entry["path"])).hexdigest(),entry["base_sha256"])
            if entry["changed"]:
                self.assertEqual(hashlib.sha256((OVERLAY/entry["path"]).read_bytes()).hexdigest(),entry["patched_sha256"])
            else:
                self.assertEqual(entry["base_sha256"],entry["patched_sha256"])

    def test_single_existing_accumulator_write_port(self):
        s=(SV/"bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv").read_text()
        self.assertEqual(re.findall(r"logic\s+\[31:0\]\s+accumulator_bank\[0:4\]",s),["logic [31:0] accumulator_bank[0:4]"])
        self.assertEqual(re.findall(r"accumulator_bank\[[^\]]+\]\s*<=",s),["accumulator_bank[bank_write_context]<="])
        self.assertIn("bank_write_data=bank_seed_write?seed_data_i:round_out",s)
        self.assertIn("bank_write_context=bank_seed_write?seed_context_i:early_commit_context_i",s)
        for helper in ["Pre","Mul","Post","Round"]:
            self.assertEqual(len(re.findall("HeteroBF16Fma"+helper+r"\s+u_",s)),1)
        self.assertNotRegex(s,r"(?i)(seed.*\[[^\]]+:[^\]]+\].*\[0:|sram|bf16rne|outputbf16)")
        self.assertIn("if(!(ENABLE_ACCUMULATOR_SEED && seed_block_i))begin",s)

    def test_physical_cluster_lane_order_and_valid_wiring(self):
        outer=(SV/"bf16_outer_product_context_array_rev8b_b_candidate.sv").read_text()
        cluster=(SV/"bf16_context_lane_cluster16_rev8b_b_candidate.sv").read_text()
        self.assertIn("cluster<32",outer);self.assertIn("lane<16",cluster)
        self.assertIn("seed_write&&seed_cluster_i==cluster",outer)
        self.assertIn("seed_data_i(seed_data_i[lane*32+:32])",cluster)
        self.assertIn("lane_result[cluster*16*32+:16*32]",outer)
        self.assertIn("CONTROL_WIDTH=ENABLE_ACCUMULATOR_SEED?20:13",outer)
        self.assertIn(".BUNDLE_WIDTH(CONTROL_WIDTH)",outer)
        self.assertIn("front_control_bundle[13]=seed_hold",outer)
        self.assertNotIn("front_control_bundle[13]=seed_block",outer)
        self.assertIn("end else if(!(ENABLE_ACCUMULATOR_SEED && seed_block_i))begin",cluster)
        for scope in ["bf16_context_scheduler5","bf16_context_fma_pipeline_lane5"]:
            s=(SV/(scope+"_rev8b_b_candidate.sv")).read_text()
            self.assertIn("(seed_reserve_i||seed_invalidate_i)",s)
            self.assertIn("seed_commit_i && seed_context_i<5",s)

    def test_registered_ack_separate_busy_and_full_commit(self):
        front=(SV/"bf16_context_front_control5_rev8b_b_candidate.sv").read_text()
        scheduler=(SV/"bf16_context_scheduler5_rev8b_b_candidate.sv").read_text()
        self.assertIn("seed_ack_valid_o=ack_valid_q",front)
        self.assertIn("if(commit_fire)begin ack_valid_q<=1'b1",front)
        self.assertIn("legal_commit=identity_matches&&beat_count_q==32",front)
        self.assertIn("seed_write_o=beat_fire&&legal_beat&&!fault",front)
        self.assertIn("seed_commit_o=commit_fire&&legal_commit&&!fault",front)
        self.assertIn("assign busy_o=busy_q",scheduler)
        self.assertNotRegex(scheduler,r"busy_q[^;\n]*seed")
        self.assertIn("seed_invalidate_o=fault||poison_q",front)
        self.assertIn("seed_hold_o=reserved_q||ack_valid_q",front)
        self.assertIn("(seed_begin_valid_i&&!quiescent)",front)

    def test_optional_blackbox_abi_matches_actual_endpoint(self):
        scala=(OVERLAY/"chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedMatrix.scala").read_text()
        endpoint=(OVERLAY/"rtl/integration/qwen2_matrix_command_endpoint.sv").read_text()
        options=re.findall(r"val ((?:seed_|arithmetic_)\w+)=if\(enableAccumulatorSeed\)Some\((Input|Output)\((Bool\(\)|UInt\((\d+)\.W\))\)\)else None",scala)
        self.assertEqual(len(options),23)
        for name,direction,kind,width in options:
            self.assertRegex(endpoint,r"\b"+name+r"\b")
        self.assertIn("enableAccumulatorSeed:Boolean=false",scala)
        self.assertIn("else Map.empty[String,Param]",scala)
        self.assertIn("arithmetic_busy_o=mbusy",endpoint)
        self.assertIn("arithmetic_out_valid_o=moutv",endpoint)
        self.assertIn("parameter bit ENABLE_ACCUMULATOR_SEED=1'b0",endpoint)

if __name__=="__main__":
    unittest.main(verbosity=2)
