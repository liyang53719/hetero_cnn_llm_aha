"""Bounded synthetic and source-contract tests. NOT Chisel/native/fullblock QA."""
import ast
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from synthetic_services import (ROOT, SOURCE, ScalarDouble, ArithmeticFault,
                                binary, finite, fma_bf16, rational, rne,
                                run_owner, word)
from pv_reuse_test_config import SCALA_BASELINE

SCALA = ROOT / 'delta/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala'
PYTHON = ROOT / 'delta/candidates/qwen2_fixed93_attention/owner.py'
RESULTS = []

class OwnerDifferentialTests(unittest.TestCase):
    def check_case(self, m):
        baseline, candidate = (run_owner(v, m, seed=3) for v in ('baseline', 'candidate'))
        old, new = baseline['owner'], candidate['owner']
        self.assertEqual(baseline['requests'], candidate['requests'])
        self.assertEqual(baseline['writes'], candidate['writes'])
        self.assertEqual(baseline['matrix'].trace, candidate['matrix'].trace)
        self.assertEqual(old.pv_inputs, new.pv_inputs)
        self.assertEqual(old.pv_intermediates, new.pv_intermediates)
        # Includes actual scalar exp recipe, denominator, inverse, QK score
        # reductions, per-use BF16 conversion, and output materialization.
        self.assertEqual([x for x in baseline['scalar'].trace if not x[0]],
                         [x for x in candidate['scalar'].trace if not x[0]])
        pairs = 12 * m * (m + 1) // 2
        self.assertEqual(len(baseline['scalar'].normalizations), 8 * pairs)
        self.assertEqual(len(candidate['scalar'].normalizations), pairs)
        self.assertEqual(len(new.pv_inputs), 8 * pairs)
        self.assertTrue(all(x[0][3] == 0 for x in candidate['scalar'].normalizations))
        self.assertEqual([x for x in baseline['scalar'].normalizations if x[0][3] == 0],
                         candidate['scalar'].normalizations)
        uses = defaultdict(list)
        for (t, h, k, col), fp32, bf in new.pv_inputs:
            self.assertLessEqual(k, t)
            uses[t, h, k].append((col, fp32, bf))
        for row in uses.values():
            self.assertEqual([x[0] for x in row], list(range(0, 128, 16)))
            self.assertEqual(len({x[1:] for x in row}), 1)
        self.assertEqual(new.peak_probability_words, m)
        self.assertEqual(new.peak_score_words, m)
        self.assertEqual(baseline['terminal'], candidate['terminal'])
        self.assertEqual(baseline['ticks'], candidate['ticks']) # scalar timing is collapsed, not an improvement measurement
        RESULTS.append(dict(m=m, heads=12, variant='SYNTHETIC_EXACT_RNE_SURROGATE',
                            causal_keys=pairs, old_normalize=8*pairs, new_normalize=pairs,
                            actual_pv_uses=8*pairs, output_acks=len(candidate['writes']),
                            owner_model_ticks=candidate['ticks'], hardware_cycles=None,
                            fullblock_executed=False, native_executed=False))
    def test_m1_real_owner_equal_bits_and_transactions(self): self.check_case(1)
    def test_m2_real_owner_equal_bits_and_transactions(self): self.check_case(2)
    def test_m16_real_owner_equal_bits_and_transactions(self): self.check_case(16)

    def check_fault(self, fault, m=1):
        old, new = (run_owner(v, m, fault=fault) for v in ('baseline', 'candidate'))
        self.assertEqual(old['terminal'].status, new['terminal'].status)
        self.assertEqual(old['requests'], new['requests'])
        self.assertEqual(old['writes'], new['writes'])
        self.assertEqual(old['owner'].pv_inputs, new['owner'].pv_inputs)
        self.assertEqual(old['owner'].pv_intermediates, new['owner'].pv_intermediates)
        self.assertEqual(old['matrix'].trace, new['matrix'].trace)
        self.assertLess(len(new['writes']), m * 12 * 8)
        return new
    def test_first_normalize_fault_has_no_vread_or_store(self):
        run = self.check_fault(('normalize', (0, 0, 0, 0)))
        self.assertFalse(run['owner'].pv_inputs)
        self.assertFalse(run['writes'])
        self.assertFalse(any(0x300000 <= a < 0x400000 for a, _, _ in run['requests']))
        failed = run['scalar'].normalizations[-1]
        self.assertEqual(run['scalar'].fault_probability_storage[0], failed[1])
    def test_new_query_normalize_fault_does_not_use_previous_head_cache(self):
        self.check_fault(('normalize', (1, 0, 0, 0)), m=2)
    def test_vread_fault_preserves_fail_closed_prefix(self): self.check_fault('vread')
    def test_write_fault_preserves_fail_closed_prefix(self): self.check_fault('write')
    def test_nonfinite_pv_result_still_fails_before_store(self):
        run = self.check_fault(('nonfinite_pv', 1))
        self.assertEqual(run['terminal'].status, 'Numerical')
        self.assertFalse(run['writes'])
    def test_new_jobs_recreate_probability_lifetime(self):
        first = run_owner('candidate', 2, seed=1)
        shared = first['matrix'], first['scalar']
        second = run_owner('candidate', 1, seed=11, shared=shared)
        fresh = run_owner('candidate', 1, seed=11)
        self.assertEqual(second['owner'].pv_inputs, fresh['owner'].pv_inputs)
        self.assertEqual(second['writes'], fresh['writes'])
        self.assertNotEqual(first['writes'][:96], second['writes'])

class ArithmeticBoundaryTests(unittest.TestCase):
    def test_rational_rne_surrogate_known_ties_and_signed_zero(self):
        self.assertEqual(binary('add', 0x4b800000, word(1.0)), 0x4b800000)
        self.assertEqual(binary('add', 0x4b800001, word(1.0)), 0x4b800002)
        self.assertEqual(binary('mul', 0x80000000, word(0.5)), 0x80000000)
        self.assertEqual(binary('mul', 1, word(1.0)), 1)
        self.assertEqual(binary('mul', 1, word(0.5)), 0)
        self.assertEqual(fma_bf16(0x8000, 0x3f80, 0x80000000), 0x80000000)
        self.assertEqual(fma_bf16(0x8000, 0x3f80, 0), 0)
    def test_fp32_cache_is_not_bf16_early_materialization(self):
        for x in (0, 0x80000000, 1, 0x00800001, 0x3eaaaaab, 0x3f7fffff, 0x7f7fffff):
            cache = binary('mul', x, word(1.0))
            self.assertEqual(cache, x)
            self.assertEqual([cache] * 8, [binary('mul', x, word(1.0)) for _ in range(8)])
        self.assertNotEqual(binary('bf', 0x3eaaaaab), 0x3eaaaaab)
        self.assertEqual(binary('bf', 0x7f7fffff), 0x7f800000) # unchanged BF16 overflow, not a legal successful PV value
    def test_subnormal_policy_is_not_changed_to_mul_ieee_rne(self):
        c = type('Client', (), {'program': None})()
        scalar = ScalarDouble(); scalar.acquire(c)
        self.assertEqual(scalar.op(c, 'mul', 1, word(1.0)), 1)
        with self.assertRaises(ArithmeticFault): scalar.op(c, 'mul', 1, word(0.5))
        self.assertEqual(scalar.op(c, 'mul', 1, word(0.5), policy='vector'), 0)

class SourceContractTests(unittest.TestCase):
    def test_baseline_sources_and_originals_stay_pinned(self):
        entries = [
            (ROOT/'baseline/Qwen2Block.scala', SCALA_BASELINE, 'a6e7f781dd46063a7373c712f7d8eda289038e0be51e0f9184f382fe26805491'),
            (ROOT/'baseline/owner.py', SOURCE/'candidates/qwen2_fixed93_attention/owner.py', '1e90ecb2e5cf26755c7fe5b7cc201d563afde23af6c27105daeb2387cb5cf443')]
        for snapshot, original, sha in entries:
            for path in (snapshot, original): self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)
    def test_python_only_loop_and_report_change(self):
        old, new = (ast.parse(p.read_text()) for p in (ROOT/'baseline/owner.py', PYTHON))
        old_cls = next(x for x in old.body if isinstance(x, ast.ClassDef))
        new_cls = next(x for x in new.body if isinstance(x, ast.ClassDef))
        for om, nm in zip(old_cls.body, new_cls.body):
            if isinstance(om, ast.FunctionDef) and om.name in ('_attention', 'report'): continue
            self.assertEqual(ast.dump(om), ast.dump(nm))
        attention = next(x for x in old_cls.body if isinstance(x, ast.FunctionDef) and x.name == '_attention')
        new_attention = next(x for x in new_cls.body if isinstance(x, ast.FunctionDef) and x.name == '_attention')
        loop = next(n for n in ast.walk(attention) if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == 'col')
        inner = loop.body[0]
        original_mul = inner.body.pop(0)
        cache_write = ast.parse('probabilities[key] = probability').body[0]
        inner.body.insert(0, ast.If(test=ast.Compare(left=ast.Name(id='col',ctx=ast.Load()), ops=[ast.Eq()], comparators=[ast.Constant(value=0)]), body=[original_mul, cache_write], orelse=[]))
        self.assertEqual(ast.dump(attention), ast.dump(new_attention))
    def test_scala_one_read_one_write_site_and_no_new_resource_declaration(self):
        old, new = (p.read_text() for p in (ROOT/'baseline/Qwen2Block.scala', SCALA))
        self.assertEqual(new.count('probs.write('), 1)
        self.assertEqual(new.count('probs.read('), 1)
        self.assertIn('when(state===st("attExpResult") || (enableProductionPackedQk16.B && state===st("attProbScale") && col===0.U)){probs.write(key,scalarValue)}', new)
        pattern = r'.*(?:=Reg|=SyncReadMem|=Module\(|val names=|case class QwenBlockShape).*'
        self.assertEqual(re.findall(pattern, old), re.findall(pattern, new))
        self.assertIn('val probs=SyncReadMem(s.maxTokens,UInt(32.W))', new)
    def test_scala_original_tail_checks_and_legacy_branch_preserved(self):
        old, new = (p.read_text() for p in (ROOT/'baseline/Qwen2Block.scala', SCALA))
        start, end = '  when(state===st("attPVCompute"))', '  // Numerically stable SiLU'
        self.assertEqual(old[old.index(start):old.index(end)], new[new.index(start):new.index(end)])
        self.assertEqual(old[old.index('  // Last-connect safety checks'):], new[new.index('  // Last-connect safety checks'):])
        scalar = '  when(state===st("scalarRsp")&&scalar.io.result.fire)'
        self.assertEqual(next(x for x in old.splitlines() if x.startswith(scalar)), next(x for x in new.splitlines() if x.startswith(scalar)))
        legacy = '  }else{\n    when(state===st("attProbWait")){calc(ScalarOp.Mul,probOut,scale,"attProbScale")}\n    when(state===st("attProbScale")){probability:=scalarValue;read(ptr("v",key.pad(32)*s.kv.U+kvHead*s.headDim.U+col),"attPVCompute")}\n  }'
        self.assertIn(legacy, new)
        self.assertNotIn('MulIeeeRne', new[new.index('  when(state===st("attInv"))'):new.index(end)])
    def test_m128_formula_only_no_m128_execution(self):
        keys = 12 * 128 * 129 // 2
        self.assertEqual((keys, 8*keys, 7*keys, 4*7*keys), (99072, 792576, 693504, 2774016))

# This explicit FSM is a source-contract surrogate, not evaluated Chisel RTL.
# It makes SRAM ownership/read latency and reset/fault boundaries inspectable.
class ProbabilitySramModel:
    def __init__(self, reuse=True):
        self.mem = [0x7fc01234] * 1024; self.reuse = reuse; self.trace = []; self.time = 0
    def edge(self, state, key, *, write=None, read=False):
        assert not (write is not None and read), 'same-edge SRAM read/write'
        self.trace.append((self.time, state, key, write, read)); self.time += 1
        if write is not None: self.mem[key] = write
        return self.mem[key] if read else None
    def row(self, token, seed=0, fail_key=None):
        raw = [word((key + seed + 1) / 256) for key in range(token + 1)]
        for key, value in enumerate(raw): self.edge('attExpResult', key, write=value)
        inverse = word(2.0 ** (-1 - seed % 4)); uses = []; muls = 0
        for col in range(0, 128, 16):
            for key in range(token + 1):
                out = self.edge('attProbRead', key, read=True)
                self.edge('attProbWait', key)
                if not self.reuse or col == 0:
                    self.edge('scalarReq', key); self.edge('scalarRsp_wait', key); self.edge('scalarRsp_fire', key)
                    muls += 1
                    if fail_key == key: return uses, muls, False
                    out = binary('mul', out, inverse)
                    self.edge('attProbScale', key, write=out if self.reuse else None)
                uses.append((col, key, out))
        return uses, muls, True

class SramStateContractTests(unittest.TestCase):
    def test_causal_boundaries_0_15_16_127_and_poison_future(self):
        for token in (0, 15, 16, 127):
            old, new = ProbabilitySramModel(False), ProbabilitySramModel(True)
            a, an, ok1 = old.row(token); b, bn, ok2 = new.row(token)
            self.assertTrue(ok1 and ok2); self.assertEqual(a, b)
            self.assertEqual((an, bn), (8*(token+1), token+1))
            self.assertEqual(old.time-new.time, 4*7*(token+1))
            self.assertTrue(all(key <= token for _, _, key, _, read in new.trace if read))
            self.assertTrue(all(w == 0x7fc01234 for w in new.mem[token+1:]))
            for i, (_, state, key, write, read) in enumerate(new.trace):
                if state == 'attProbWait': self.assertEqual(new.trace[i-1][1:3], ('attProbRead', key))
    def test_head_query_and_smaller_next_job_overwrite_only_causal_prefix(self):
        model = ProbabilitySramModel()
        model.row(127, seed=1)
        for token, seed in ((16, 4), (0, 9), (15, 23), (16, 37)):
            actual = model.row(token, seed=seed)
            self.assertEqual(actual, ProbabilitySramModel().row(token, seed=seed))
    def test_first_column_failure_never_writes_failed_or_uses_future_key(self):
        model = ProbabilitySramModel()
        uses, muls, ok = model.row(16, fail_key=7)
        self.assertFalse(ok); self.assertEqual(muls, 8)
        self.assertEqual([key for _, key, _ in uses], list(range(7)))
        self.assertFalse(any(state == 'attProbScale' and key == 7 for _, state, key, _, _ in model.trace))
        self.assertFalse(any(col != 0 for col, _, _ in uses))
        self.assertEqual(model.mem[7], word(8/256))

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(status='PASS' if result.wasSuccessful() else 'FAIL', tests_run=result.testsRun,
                  failures=len(result.failures), errors=len(result.errors), cases=RESULTS,
                  evidence_scope='real Python owner/shared-client control plus rational-RNE test doubles and source/FSM contracts only',
                  native_executed=False, chisel_compiled=False, rtl_executed=False, eda_executed=False,
                  fullblock_executed=False, m128_executed=False)
    assert not any(name in sys.modules for name in ('numpy', 'torch'))
    report['imported_readonly_source_dependencies'] = {
        str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for module in sys.modules.values()
        if (name := getattr(module, '__file__', None)) and (path := Path(name)).is_file() and SOURCE in path.parents
    }
    (ROOT/'reports/test_result.json').write_text(json.dumps(report, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
