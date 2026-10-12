"""Source/assembly contracts only. These tests never compile or simulate Chisel."""
from pathlib import Path
import re
import tempfile
import unittest

from candidates.qwen2_resident_matrix.official_bf16 import chisel_policy as policy


class ChiselPolicySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='qwen_bf16_source_test_')
        cls.out = Path(cls.temporary.name) / 'sources'
        cls.paths, cls.report, cls.before, cls.after = policy.compose(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def reject_change(self, path, before, after):
        sources = dict(self.after)
        self.assertIn(before, sources[path])
        sources[path] = sources[path].replace(before, after, 1)
        with self.assertRaises(ValueError):
            policy.audit_sources(self.before, sources)

    def test_actual_parent_assembly_and_scope(self):
        self.assertEqual(len(self.paths), 72)
        self.assertEqual(set(self.report['changed_production_sources']), set(policy.TOUCHED))
        self.assertEqual(self.report['status'], 'PASS_SOURCE_STRUCTURE_ONLY')
        for key in ('scala_compiled', 'chisel_elaborated', 'rtl_generated',
                    'hardware_arithmetic_executed', 'qor_measured', 'numerical_acceptance'):
            self.assertIs(self.report[key], False)

    def test_no_new_arithmetic_or_memory_constructor(self):
        for path in self.paths:
            self.assertEqual(policy.source_inventory(self.before[path]),
                             policy.source_inventory(self.after[path]), path)

    def test_legacy_default_at_every_changed_constructor(self):
        expected = {
            'HostBlockTop.scala': 2, 'HostBlockCommands.scala': 1,
            'QwenOwnerProtocol.scala': 1, 'Qwen2Block.scala': 1,
            'VectorSilu.scala': 2, 'OverlappedSilu.scala': 2,
            'ElementwiseMemoryEngine.scala': 1,
        }
        for file, count in expected.items():
            self.assertEqual(self.after[policy.PREFIX + file].count(
                'numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0'), count)
        self.assertEqual(self.after[policy.OWNER].count(
            'numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0'), 1)

    def test_public21_contract_matches_existing_unchanged_metadata(self):
        from candidates.qwen2_resident_matrix.ffn_public.fixture import make_qwen2_21_fixture
        producer_a = {1: 0, 2: 1, 3: 2, 4: 0, 5: 4, 6: 5, 7: 0,
                      8: 7, 9: 6, 10: 3, 11: 10, 12: 11, 13: 12,
                      15: 14, 16: 15, 17: 15, 18: 16, 19: 18, 20: 14}
        producer_b = {9: 8, 14: 13, 18: 17, 20: 19}
        for rows, relocation in ((16, 0), (128, 0x100000000)):
            fixture = make_qwen2_21_fixture(rows=rows, relocate=relocation)
            schedule = fixture.manifest['schedule']
            tensors = fixture.manifest['tensors']
            self.assertEqual(tuple(int(c.opcode) for c in fixture.commands), policy.PUBLIC21_OPCODES)
            for pc, prior in producer_a.items():
                self.assertEqual(tensors[schedule[pc]['a']]['address'],
                                 tensors[schedule[prior]['dst']]['address'])
            for pc, prior in producer_b.items():
                self.assertEqual(tensors[schedule[pc]['b']]['address'],
                                 tensors[schedule[prior]['dst']]['address'])
            self.assertEqual(tensors[schedule[14]['a']]['address'], tensors[schedule[0]['a']]['address'])
            self.assertEqual(tensors[schedule[10]['b']]['address'], tensors[schedule[9]['dst']]['address'])
            self.assertEqual(tensors[schedule[12]['b']]['address'],
                             tensors[schedule[9]['dst']]['address'] + rows * 256 * 4)
            for pc in policy.MATERIALIZED_DENSE_PCS + policy.RAW_QKV_PCS:
                self.assertEqual(int(fixture.commands[pc].opcode), 0x20)
                output = tensors[schedule[pc]['dst']]
                self.assertEqual(output.get('storage_dtype', 7), 7)
                self.assertEqual(output['words'] * 4, rows * output['dims'][1] * 4)

    def test_frozen_reduction_index_covers_one_existing_row(self):
        # Address-order model only: no claim about hardware floating-point values.
        indexes = [block * 512 + term * 32 + residue * 8 + lane
                   for lane in range(8) for residue in range(4)
                   for block in range(3) for term in range(16)]
        self.assertEqual(sorted(indexes), list(range(1536)))
        self.assertEqual(indexes[:16], list(range(0, 512, 32)))
        self.assertEqual(indexes[16:32], list(range(512, 1024, 32)))
        self.assertEqual(indexes[48:64], list(range(8, 520, 32)))
        self.assertEqual(self.report['rms_added_fp32_partial_registers'],
                         ['rmsPartial', 'rmsResidueSum', 'rmsLaneSum'])
        core = self.after[policy.PREFIX + 'Qwen2Block.scala']
        state_names = re.search(r'val names=Seq\((.*?)\)\n', core, re.S)[1]
        self.assertLess(len(re.findall(r'"[^"]+"', state_names)), 128)

    def test_reject_reciprocal_multiply_in_official_rms(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'calc(ScalarOp.Div,sum,F32.lit(1536.0),"normEps")',
            'calc(ScalarOp.Mul,sum,F32.lit(1.0/1536.0),"normEps")')

    def test_reject_missing_normalized_input_rounding(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'val normalized=VecInit(vout.map(materialize))',
            'val normalized=vout')

    def test_tiny_bf16_square_ieee_underflow_contract(self):
        # Exact arithmetic witness and a source-selected error-mask check only;
        # this is not Chisel simulation or primitive arithmetic signoff.
        from fractions import Fraction
        import struct
        bits = 0x1c810000  # BF16 129/128 * 2^-70, stored in FP32.
        x = struct.unpack('<f', struct.pack('<I', bits))[0]
        exact = Fraction(129, 128) ** 2 / (1 << 140)
        rounded = struct.unpack('<I', struct.pack('<f', x * x))[0]
        self.assertEqual(bits & 0xffff, 0)
        self.assertEqual(rounded, 0x00000208)
        self.assertNotEqual(exact, Fraction(rounded, 1 << 149))
        self.assertLess(exact, Fraction(1, 1 << 126))
        # HardFloat flags: underflow=bit1, inexact=bit0; other bits clear.
        flags = 0b00011
        fatal = lambda op: bool((flags & 0b11100) or ((flags & 0b00010) and op != 6))
        self.assertTrue(fatal(1))  # preserved legacy ScalarOp.Mul
        self.assertFalse(fatal(6))  # selected only for official RMS square
        self.assertIn('calc(ScalarOp.MulIeeeRne,av(rmsIndex(3,0)),av(rmsIndex(3,0)),"normOfficialAdd")',
                      self.after[policy.PREFIX + 'Qwen2Block.scala'])
        self.assertEqual(self.before[policy.PREFIX + 'BlockFloat.scala'],
                         self.after[policy.PREFIX + 'BlockFloat.scala'])

    def test_reject_legacy_square_underflow_policy(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'calc(ScalarOp.MulIeeeRne,av(rmsIndex(3,0)),av(rmsIndex(3,0)),"normOfficialAdd")',
            'calc(ScalarOp.Mul,av(rmsIndex(3,0)),av(rmsIndex(3,0)),"normOfficialAdd")')

    def test_reject_missing_normalized_bf16_finite_check(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'when(officialBf16.B && normalized.map(x=> !TensorMath.finite(x)).reduce(_||_)){fail(Status.Numerical.U)}',
            'when(false.B){fail(Status.Numerical.U)}')

    def test_reject_missing_final_bf16_store_finite_check(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'val bad=(0 until 16).map(i=> !TensorMath.finite(data(32*i+31,32*i))).reduce(_||_)',
            'val bad=false.B')

    def test_reject_missing_rope_product_rounding(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'vectorA:=bv;vectorB:=dv;tmp2:=VecInit(vout.map(materialize))',
            'vectorA:=bv;vectorB:=dv;tmp2:=vout')

    def test_reject_missing_post_reduction_qk_rounding(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'calc(ScalarOp.Mul,materialize(scalarValue),F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")',
            'calc(ScalarOp.Mul,scalarValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")')

    def test_reject_materializing_raw_qkv(self):
        self.reject_change(policy.PREFIX + 'HostBlockCommands.scala',
            'pc===13.U || pc===16.U || pc===17.U || pc===19.U',
            'pc===1.U || pc===13.U || pc===16.U || pc===17.U || pc===19.U')

    def test_reject_shape_only_dense_role(self):
        self.reject_change(policy.PREFIX + 'HostBlockCommands.scala',
            '13.U->(dense && inputA(12) && readonly(b))',
            '13.U->(dense && n===1536.U && readonly(b))')

    def test_reject_missing_policy_forwarding(self):
        self.reject_change(policy.PREFIX + 'HostBlockTop.scala',
            'enableResidentFfn=enableResidentFfn,numericPolicy=numericPolicy',
            'enableResidentFfn=enableResidentFfn')

    def test_reject_materializing_split_k_prefix(self):
        before = 'val prefix=VecInit((0 until 16).map(i=>finalValue(prefixWriteIndex(7,4))(Cat(prefixWriteIndex(3,0),i.U(4.W))))).asUInt'
        sources = dict(self.after)
        start, down = sources[policy.OWNER].split('class TransposedDenseDownOwner', 1)
        self.assertIn(before, down)
        down = down.replace(before, before.replace('=>finalValue(', '=>F32.bf(finalValue(').replace('))).asUInt', ')))).asUInt'))
        sources[policy.OWNER] = start + 'class TransposedDenseDownOwner' + down
        with self.assertRaises(ValueError):
            policy.audit_sources(self.before, sources)

    def test_reject_storage_flag_repurposing(self):
        self.reject_change(policy.PREFIX + 'HostBlockCommands.scala',
            'bound.weightBf16:=nativeWeight', 'bound.weightBf16:=nativeWeight;bound.outputBf16:=officialMaterializeDense')

    def test_reject_second_scalar(self):
        self.reject_change(policy.PREFIX + 'Qwen2Block.scala',
            'val rmsPartial=RegInit(0.U(32.W))',
            'val extra=Module(new BlockScalarFloat);val rmsPartial=RegInit(0.U(32.W))')

    def test_reject_missing_silu_phase4_rounding(self):
        self.reject_change(policy.PREFIX + 'VectorSilu.scala',
            'Mux(phase===4.U || phase===5.U,F32.bf(cores(i).io.result.bits),cores(i).io.result.bits)',
            'Mux(phase===5.U,F32.bf(cores(i).io.result.bits),cores(i).io.result.bits)')

    def test_reject_copy_value_changes(self):
        self.reject_change(policy.PREFIX + 'ElementwiseMemoryEngine.scala',
            'Mux(binary,arithmeticValue,a(32*i+31,32*i))',
            'Mux(binary,arithmeticValue,F32.bf(a(32*i+31,32*i)))')

    def test_refuses_existing_output_directory(self):
        with self.assertRaisesRegex(ValueError, 'new source assembly'):
            policy.compose(self.out)


if __name__ == '__main__':
    unittest.main()
