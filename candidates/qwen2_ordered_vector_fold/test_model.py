"""Bounded stdlib-only regression; no imports of production module preludes."""
import argparse
import ast
from collections import Counter
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest
# Isolated Python intentionally omits the script directory from sys.path.
# Add only this resolved candidate directory, never the production source root.
HERE = Path(__file__).resolve(strict=True).parent
sys.path.insert(0, str(HERE))
import model as _candidate_model
if Path(_candidate_model.__file__).resolve(strict=True) != HERE / 'model.py':
    raise ImportError('ordered fold model resolved outside its candidate directory')
OrderedVectorFold = _candidate_model.OrderedVectorFold
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root', type=Path, required=True)
options, rest = parser.parse_known_args()
sys.argv[:] = [sys.argv[0], *rest]
root = options.source_root.resolve(strict=True)
pins = json.loads((HERE / 'SOURCE_PINS.json').read_text())
ns = {'Counter': Counter, 'Fraction': Fraction, 'lru_cache': lru_cache}
for relative, pin in pins['sources'].items():
    data = (root / relative).read_bytes()
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('source pin mismatch: ' + relative)

def load(relative, names):
    data = (root / relative).read_bytes()
    if hashlib.sha256(data).hexdigest() != pins['sources'][relative]['sha256']:
        raise ValueError('source pin mismatch: ' + relative)
    tree = ast.parse(data, filename=relative)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    if {n.name for n in nodes} != set(names):
        raise ValueError('missing pinned definition')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, 'exec'), ns)

base = 'candidates/qwen2_resident_matrix/'
load(base+'ffn_public/test_prefix_owners.py', ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'))
load(base+'attention_matrix_batch/test_model.py', ('finite', 'ArithmeticFault', 'ExactScalar'))
Scalar, Fault, finite = ns['ExactScalar'], ns['ArithmeticFault'], ns['finite']

class LiveTile:
    """Only selected diagonal cells exist. Any tail/unselected read fails."""
    def __init__(self, keys):
        self.keys, self.reads = keys, []
        self.value = self
    def __getitem__(self, row):
        outer = self
        class Row:
            def __getitem__(self, col):
                key, offset = divmod(col, 16)
                if key >= len(outer.keys) or offset != row:
                    raise AssertionError('read tail/unselected cell')
                outer.reads.append((row, col))
                return outer.keys[key][row]
        return Row()

def baseline(keys):
    s = Scalar()
    scores, maximum = [], 0xff800000
    for j, values in enumerate(keys):
        try:
            if any(not finite(x) for x in values):
                raise Fault('nonfinite selected lane')
            a = 0
            for x in values:
                a = s('add', a, x)
            dot = s('bf', a)
            if not finite(dot):
                raise Fault('nonfinite dot')
            score = s('bf', s('mul', dot, 0x3db504f3))
            if not finite(score):
                raise Fault('nonfinite score')
            scores.append(score)
            if maximum == 0xff800000 or ns['exact'](maximum) < ns['exact'](score):
                maximum = score
        except Fault:
            return scores, maximum, j
    return scores, maximum, None

class Tests(unittest.TestCase):
    def new(self, keys):
        tile = LiveTile(keys)
        m = OrderedVectorFold(Scalar(), finite, Fault, enabled=True)
        self.assertTrue(m.accept(tile, len(keys)))
        return m, tile
    def run_case(self, keys, stalls=False):
        m, tile = self.new(keys)
        for t in range(400):
            if m.state == 'drain':
                break
            m.step(retire_ready=not stalls or t % 3 == 0, ack_ready=not stalls or t % 5 == 0)
            self.assertIs(m.result, tile)
            self.assertFalse(m.ready)
        else:
            self.fail('bounded model did not retire')
        expected = baseline(keys)
        self.assertEqual((m.committed, m.maximum, m.fault_key), expected)
        self.assertEqual(m.ack, expected[2] is None)
        return m, tile
    def test_default_disabled_and_input_backpressure(self):
        m = OrderedVectorFold(Scalar(), finite, Fault)
        self.assertFalse(m.ready)
        self.assertFalse(m.accept(LiveTile([[0]*16]), 1))
        m.enabled = True
        self.assertFalse(m.accept(None, 1, valid=False))
        self.assertTrue(m.accept(LiveTile([[0]*16]), 1))
        self.assertFalse(m.accept(None, 1))
    def test_all_tails_rounding_cancellation_zero_subnormal(self):
        patterns = [
            [0]*16, [0x80000000]*16,
            [0x3f800000, 0xbf800000]+[0]*14,
            [0x3f800000, 0x33800000, 0x33800000]+[0]*13,
            [0x3f800001, 0x33800000]+[0]*14,
            [1, 0x80000001]+[0]*14,
            [0x00800000]*16,
            [0x3f808000]+[0]*15,
            [0x3f818000]+[0]*15,
        ]
        for count in range(1,17):
            for shift in range(len(patterns)):
                with self.subTest(count=count, shift=shift):
                    self.run_case([patterns[(j+shift)%len(patterns)] for j in range(count)], True)
    def test_random_finite_exact_words(self):
        rng = random.Random(0x514b16)
        for n in range(96):
            count = 1+n%16
            keys = [[(rng.getrandbits(1)<<31)|(rng.randrange(1,254)<<23)|rng.getrandbits(23) for _ in range(16)] for _ in range(count)]
            self.run_case(keys, True)
    def test_later_fault_preserves_every_score_prefix(self):
        good = [0x3f800000]*16
        bads = [[0x7fc00000]+[0]*15, [0x7f800000]+[0]*15,
                [0x7f7fffff,0x7f7fffff]+[0]*14,
                [0x7f7fffff]+[0]*15, [0x00800000]+[0]*15]
        for bad in bads:
            for fault_key in range(16):
                keys = [good[:] for _ in range(16)]
                keys[fault_key] = bad
                m, _ = self.run_case(keys, True)
                self.assertEqual(m.fault_key, fault_key)
                self.assertEqual(len(m.committed), fault_key)
    def test_computation_fault_order_is_not_retirement_order(self):
        good = [0x3f800000]*16
        # Key 2 scan fault is discovered before key 1's late fold overflow.
        self.run_case([good, [0x7f7fffff]+[0]*14+[0x7f7fffff], [0x7fc00000]+[0]*15])
        # Key 2 fold overflow is discovered before key 1's scale underflow.
        m, _ = self.run_case([good, [0x00800000]+[0]*15, [0x7f7fffff]*16])
        self.assertEqual(m.fault_key, 1)
        self.assertEqual(len(m.committed), 1)

    def test_early_fault_has_no_commit_or_ack(self):
        m, _ = self.run_case([[0x7fc00000]*16]+[[0x3f800000]*16]*15)
        self.assertEqual(m.committed, [])
        self.assertFalse(m.ack)
    def test_strict_exception_policy(self):
        s = Scalar()
        # NX-only allowed; exact subnormal allowed; UF+NX/OF/NV-input rejected.
        self.assertEqual(s('add',0x3f800000,0x33800000),0x3f800000)
        self.assertEqual(s('mul',0x00800000,0x3f000000),0x00400000)
        self.assertEqual(s('mul',0x80000000,0x3f800000),0x80000000)
        for op,a,b in [('mul',0x00800000,0x3db504f3),('add',0x7f7fffff,0x7f7fffff),('mul',0x7fc00000,0),('add',0x7f800000,0xff800000)]:
            with self.assertRaises(Fault): s(op,a,b)
        # DZ is unreachable for finite Add/Mul. No division is issued here.
    def test_order_not_tree(self):
        values=[0x4b800000,0x3f800000,0xcb800000]+[0]*13
        m,_=self.run_case([values])
        self.assertEqual(m.committed,[0])
    def test_no_early_release_and_debts(self):
        m,tile=self.new([[0x3f800000]*16]*3)
        for _ in range(33): m.step()
        self.assertEqual(m.state,'retire')
        for _ in range(12): m.step(retire_ready=False)
        self.assertEqual(m.committed,[])
        with self.assertRaises(ValueError): m.drain('result')
        for _ in range(3): m.step()
        self.assertEqual(m.state,'ack')
        for _ in range(12): m.step(ack_ready=False)
        self.assertIs(m.result,tile)
        self.assertFalse(m.ack)
        m.step()
        m.drain('done'); m.drain('result')
        self.assertFalse(m.ready)
        self.assertIsNone(m.result)
        m.drain('response')
        self.assertTrue(m.ready)
        with self.assertRaises(ValueError): m.drain('response')
    def test_maximum_fixed_mixed_sign_and_zero(self):
        m, _ = self.run_case([[0xbf800000]*16, [0]*16, [0x3f800000]*16])
        self.assertEqual(m.maximum, 0x3fb50000)
        for a, b, expected in [(0x80000000,0,False),(0,0x80000000,False),
                               (0xbf800000,0,True),(0,0xbf800000,False),
                               (0xff800000,0xbf800000,True)]:
            self.assertEqual(OrderedVectorFold.less(a,b), expected)
        m = OrderedVectorFold(Scalar(), finite, Fault, enabled=True)
        m.accept(LiveTile([[0]*16]),1,initial_max=0x80000000)
        while m.state != 'drain': m.step()
        self.assertEqual(m.maximum,0x80000000)

    def test_carry_maximum_between_groups(self):
        m = OrderedVectorFold(Scalar(), finite, Fault, enabled=True)
        self.assertTrue(m.accept(LiveTile([[0]*16]), 1, initial_max=0x41200000))
        while m.state != 'drain': m.step()
        self.assertEqual(m.maximum, 0x41200000)
        self.assertEqual(m.committed, [0])
        for debt in ['result','done','response']: m.drain(debt)
        self.assertTrue(m.accept(LiveTile([[0x3f800000]*16]), 1, initial_max=m.maximum))
        while m.state != 'drain': m.step()
        self.assertEqual(m.maximum, 0x41200000)

    def test_abort_every_phase_no_extra_commit(self):
        for steps in [0,1,15,16,17,31,32,33,34,35,36]:
            m,tile=self.new([[0x3f800000]*16]*3)
            for _ in range(steps): m.step()
            before=m.committed[:]
            m.step(abort=True)
            self.assertEqual(m.state,'drain')
            self.assertFalse(m.ack)
            for _ in range(10): m.step()
            self.assertEqual(m.committed,before)
            self.assertIs(m.result,tile)
            for debt in ['response','done','result']: m.drain(debt)
            self.assertTrue(m.ready)

if __name__=='__main__': unittest.main()
