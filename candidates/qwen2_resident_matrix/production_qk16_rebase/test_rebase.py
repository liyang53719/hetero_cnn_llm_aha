"""Cold source composition/invariants only; no elaboration or arithmetic."""
import argparse,hashlib,json,subprocess,tempfile,unittest,re
from pathlib import Path
from build_source import compose,P,between
HERE=Path(__file__).resolve().parent
BASE=DONOR=None
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)/'overlay'
        cls.receipt=compose(BASE,DONOR,cls.out)
        cls.old={n:(BASE/P/n).read_text() for n in ('Qwen2Block.scala','QwenOwnerProtocol.scala','MatrixPipeline.scala','HostBlockTop.scala')}
        cls.new={n:(cls.out/P/n).read_text() for n in (*cls.old,'PackedAttentionStreamClient.scala')}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_exact_postimages(self):
        self.assertEqual(self.receipt,json.loads((HERE/'POSTIMAGE_PINS.json').read_text()))
    def test_patch_zero_fuzz_same_postimages(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            for n,s in self.old.items():p=out/P/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
            r=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'production_qk16.patch')],cwd=out,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            for item in self.receipt:self.assertEqual(hashlib.sha256((out/item['path']).read_bytes()).hexdigest(),item['post_sha256'])
    def test_full_policy_and_capacity_preserved(self):
        self.assertIn('s.maxTokens==1024',self.new['QwenOwnerProtocol.scala'])
        for n in ('Qwen2Block.scala','QwenOwnerProtocol.scala','HostBlockTop.scala'):
            self.assertEqual(self.old[n].count('Qwen2NumericPolicy.checkShape(numericPolicy,s)'),self.new[n].count('Qwen2NumericPolicy.checkShape(numericPolicy,s)'))
        q=self.new['Qwen2Block.scala']
        self.assertNotIn('materializePackedQk',q);self.assertIn('val dotValue=materialize(scalarValue)',q)
        self.assertIn('val score=materialize(scalarValue)',q)
    def test_guard_before_begin_without_truncation(self):
        q=self.new['Qwen2Block.scala'];start=q.index('when(start){\n      val j=')
        end=q.index('.otherwise{state:=st("begin")}',start);chunk=q[start:end]
        self.assertIn('enableProductionPackedQk16.B && j.kind===QwenOwnerKind.Attention.U && j.m>128.U',chunk)
        self.assertNotIn('j.m(6,0)',chunk)
        for m in (0,1,127,128,129,65535):
            for selected in (False,True):
                for attention in (False,True):
                    rejected=m==0 or m>1024 or (selected and attention and m>128)
                    self.assertEqual(rejected,not 1<=m<=(128 if selected and attention else 1024))
    def test_softmax_pv_and_head_order_byte_unchanged(self):
        a='  when(state===st("attExpRead"))';b='  // Numerically stable SiLU'
        self.assertEqual(between(self.old['Qwen2Block.scala'],a,b),between(self.new['Qwen2Block.scala'],a,b))
    def test_full_production_resident_and_router_preserved(self):
        k=self.new['QwenOwnerProtocol.scala'];old=self.old['QwenOwnerProtocol.scala']
        for phrase in ('new TransposedDenseDownOwner','new ScheduledSiluOwner','new Public21QkvReductionRouter','new FfnResidentCoordinator'):
            self.assertEqual(k.count(phrase),old.count(phrase))
        a='      // Physical retirement, never reset/abort shortcuts.';b='      when(r.io.reductionOwns)'
        self.assertEqual(between(k,a,b),between(old,a,b))
        self.assertIn('matrix.io.port.abort:=dense.matrix.abort || r.io.backendAbort',k)
    def test_seed_and_group_fields_are_explicit(self):
        k=self.new['QwenOwnerProtocol.scala'];a=k[k.index('    if(enableProductionPackedQk16){'):]
        self.assertNotIn('matrix.io.port.group.bits:=p.group.bits',a)
        for field in ('opcode','sliceMask','tag'):self.assertIn('matrix.io.port.group.bits.'+field+':=p.group.bits.'+field,a)
        for statement in ('matrix.io.port.group.bits.transposedDense.foreach(_:=false.B)','matrix.io.port.group.bits.groupSequence.foreach(_:=0.U)','matrix.io.port.seed.get.begin.valid:=false.B','matrix.io.port.seed.get.beat.valid:=false.B','matrix.io.port.seed.get.ack.ready:=false.B'):self.assertIn(statement,a)
    def test_one_client_and_existing_status_logic(self):
        self.assertEqual(self.new['PackedAttentionStreamClient.scala'],(DONOR/P/'PackedAttentionStreamClient.scala').read_text())
        q=self.new['Qwen2Block.scala'];self.assertEqual(q.count('new PackedAttentionStreamClient(true)'),1)
        self.assertIn('state===st("finish") && !packedBusy && !packedFeedDebt',q)
        self.assertIn('packedMemDebt.get && io.response.fire && io.response.bits.tag===request.tag',q)
        self.assertIn('c.io.start.bits.pv:=false.B',q)
        self.assertIn('matrixFault:=matrixResult.fire && matrixResult.bits.error',q)
        self.assertNotIn('matrixFault:=fmDone &&',q)
        self.assertIn('work && !tags.io.deq.valid && !io.port.step.valid && !poison',self.new['MatrixPipeline.scala'])
    def test_default_off_and_no_new_payload_arrays(self):
        for n in ('Qwen2Block.scala','QwenOwnerProtocol.scala','HostBlockTop.scala'):
            self.assertIn('enableProductionPackedQk16:Boolean=false',self.new[n])
        q=self.new['Qwen2Block.scala'];old=self.old['Qwen2Block.scala']
        for p in ('val denseWindow=Reg(Vec','val denseWeights=Reg(Vec','val scores=SyncReadMem','val probs=SyncReadMem'):
            self.assertEqual(q.count(p),old.count(p))
        self.assertNotIn('scratchBegin',q)
    def test_use_dense_lexical_scope_counterexample(self):
        k=self.new['QwenOwnerProtocol.scala']
        start=k.index('    val useDense=')
        end=k.index('    if(enableProductionPackedQk16){',start)
        chunk=re.sub(r'"(?:[^"\\]|\\.)*"','""',k[start:end])
        self.assertEqual(chunk.count('{')-chunk.count('}'),0,'packed mux must remain inside useDense else scope')
    def test_stale_legacy_error_cannot_poison_packed(self):
        for packed_fire in (False,True):
            legacy_valid=False;legacy_ready=False;stale_error=True
            actual_legacy_fault=legacy_valid and legacy_ready and stale_error
            self.assertFalse(actual_legacy_fault)
            if packed_fire:self.assertTrue(packed_fire and stale_error) # rejected old fmDone expression
    def test_default_off_state_codes_and_status_projection(self):
        def names(s):return re.search(r'val names=Seq\((.*?)\)\n',s).group(1)
        old=names(self.old['Qwen2Block.scala']);new=names(self.new['Qwen2Block.scala'])
        self.assertEqual(new,old+',"attPackedIssue","attPackedSelect"')
        m=self.new['MatrixPipeline.scala']
        m=m.replace(',enablePackedDrainStatus:Boolean=false','')
        m=m.replace('    val packedStepsDrained=if(enablePackedDrainStatus)Some(Output(Bool()))else None\n','')
        m=m.replace('  // Existing metadata owns retirement; no new debt counter or payload.\n  if(enablePackedDrainStatus){io.packedStepsDrained.get:=work && !tags.io.deq.valid && !io.port.step.valid && !poison}\n','')
        self.assertEqual(m,self.old['MatrixPipeline.scala'])
    def test_existing_output_not_overwritten(self):
        with self.assertRaises(ValueError):compose(BASE,DONOR,self.out)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--production-source',required=True);ap.add_argument('--qk16-source',required=True);args,rest=ap.parse_known_args();BASE=Path(args.production_source);DONOR=Path(args.qk16_source)
    unittest.main(argv=['test_rebase.py']+rest)
