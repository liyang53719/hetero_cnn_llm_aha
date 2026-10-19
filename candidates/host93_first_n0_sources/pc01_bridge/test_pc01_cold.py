"""Pure SOURCE/abstract-ledger checks, never C++ compilation or RTL qualification."""
import hashlib
import json
import re
import unittest


def need(ok, code):
    if not ok:
        raise ValueError(code)


def pin(raw, record):
    need(len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256'], 'IDENTITY')
    return raw


class LedgerModel:
    """Independent finite contract model; not the production C++ or a DUT."""
    BASE = 4484322368
    SIZE = 786432

    def __init__(self, ack0=True):
        need(ack0, 'ACK0')
        self.accepted = self.done = self.published = self.poison = False
        self.aw = None
        self.queue = []
        self.staged = None
        self.written = set()
        self.payload = {}
        self.serial = 0
        self.b_count = 0

    def check(self, ok, code):
        need(not self.poison, 'POISON')
        if not ok:
            self.poison = True
            raise ValueError(code)

    def job(self, tag=458753, epoch=7):
        self.check(not self.accepted and tag == 458753 and epoch == 7, 'JOB')
        self.accepted = True

    def address(self, address, length=0, ident=0, size=6, burst=1):
        count = (length + 1) * 64
        self.check(self.accepted and not self.done and self.aw is None and self.staged is None, 'AW_OWNER')
        self.check(0 <= ident < 256 and 0 <= length < 256 and size == 6 and burst == 1 and address % 64 == 0, 'AXI')
        self.check((address & 4095) + count <= 4096 and self.BASE <= address and address + count <= self.BASE + self.SIZE, 'RANGE')
        self.check(all(x not in self.written for x in range(address, address + count, 64)), 'SSA')
        self.serial += 1
        self.aw = (address, length, ident, self.serial)
        self.stage()

    def data(self, value=7, last=True, strobe=(1 << 64) - 1):
        self.check(self.accepted and not self.done and self.staged is None and len(self.queue) < 256, 'W_OWNER')
        self.check(strobe == (1 << 64) - 1, 'STROBE')
        self.queue.append((value, last))
        self.stage()

    def stage(self):
        if self.aw and len(self.queue) >= self.aw[1] + 1:
            count = self.aw[1] + 1
            self.check(self.staged is None and all(last == (i == count - 1) for i, (_, last) in enumerate(self.queue[:count])), 'WLAST')
            self.staged = self.queue[:count]
            del self.queue[:count]

    def b(self, ident=0, resp=0, generation=1, serial=None, post_fault=False):
        self.check(self.aw is not None and self.staged is not None, 'EARLY_B')
        a, length, expected, seq = self.aw
        self.check(ident == expected and resp == 0 and generation == 1 and (serial is None or serial == seq), 'B_ID')
        self.check(not post_fault, 'POST_FAULT')
        self.check(all(a + i * 64 not in self.written for i in range(length + 1)), 'B_SSA')
        # No further checks after the first payload mutation.
        for i, (value, _) in enumerate(self.staged):
            self.written.add(a + i * 64)
            self.payload[a + i * 64] = value
        self.b_count += 1
        self.aw = self.staged = None

    def owner_done(self, bytes_=SIZE, status=0):
        self.check(self.accepted and not self.done and self.aw is None and self.staged is None and not self.queue, 'DONE_DEBT')
        self.check(status == 0 and bytes_ == self.SIZE and len(self.written) * 64 == self.SIZE, 'FULL')
        self.done = True

    def ack(self, pc=1, owner=2, status=0, signal=2, post_pc=2, jobs=2, post_fault=False):
        self.check(self.done and not self.published and not post_fault and
                   (pc, owner, status, signal, post_pc, jobs) == (1, 2, 0, 2, 2, 2), 'ACK1')
        self.published = True

    def read(self):
        self.check(self.published, 'UNPUBLISHED')
        return len(self.written) * 64


def full_model():
    m = LedgerModel()
    m.job()
    address = m.BASE
    while address < m.BASE + m.SIZE:
        count = min(4096 - (address & 4095), m.BASE + m.SIZE - address)
        beats = count // 64
        m.address(address, beats - 1)
        for i in range(beats):
            m.data(value=address + i * 64, last=i == beats - 1)
        m.b()
        address += count
    return m


def run(source, manifest):
    """All production source was read once and pinned by the cold entry."""
    text = {name: raw.decode('utf-8') for name, raw in source.items()}
    def src(name):
        return text['bridge/include/' + name]

    class SourceChecks(unittest.TestCase):
        def test_exact_twenty_eight_pinned_buffers(self):
            self.assertEqual(len(source), 28)
            self.assertEqual(set(source), set(manifest['files']))
            for name, raw in source.items():
                self.assertIs(pin(raw, manifest['files'][name]), raw)

        def test_same_length_mutation_rejected(self):
            name = 'bridge/include/pc1_model_scheduler.inc'
            raw = source[name]
            with self.assertRaises(ValueError):
                pin(bytes([raw[0] ^ 1]) + raw[1:], manifest['files'][name])

        def test_no_private_paths(self):
            for value in text.values():
                for word in ('/workspace/', '/tmp/', '/home/'):
                    self.assertNotIn(word, value)

        def test_quoted_include_closure(self):
            present = {name.rsplit('/', 1)[-1] for name in source}
            external = {'verilated.h', 'verilated_sym_props.h', 'VHostBlockTop.h', 'VHostBlockTop___024root.h', 'VHostBlockTop__Syms.h'}
            for value in text.values():
                for include in re.findall(r'^#include "([^"\n]+)"', value, re.M):
                    self.assertIn(include, present | external)

        def test_sole_host_context_and_no_offline_n0(self):
            value = src('pc01_driver.hpp')
            self.assertEqual(value.count('VHostBlockTop model{'), 1)
            self.assertEqual(value.count('VerilatedContext context;'), 1)
            self.assertLess(value.index('N0ModelScheduler<VHostBlockTop> scheduler'), value.index('Pc1ModelScheduler pc1'))
            self.assertNotIn('load_next', value)
            self.assertNotIn('model.final(', value.replace('// no model.final(), further eval, or mathematical reference', ''))

        def test_distinct_fixed_capability(self):
            value = src('runtime_ram.hpp')
            self.assertIn('pc1_outstanding_->permit==WritePermit{1,(7U<<16)|1U,1,false}', value)
            self.assertIn('p.public_pc==0&&p.tag==(7U<<16)&&p.generation==0&&!p.prefix', value)
            self.assertIn('if(a.access==Access::Qraw)require(pc1_adapter_&&qraw_published_', value)

        def test_qraw_only_new_allocation(self):
            self.assertEqual(src('runtime_policy.hpp').count('Access::Qraw}'), 1)
            self.assertIn('"qraw", 4484322368ULL, 786432ULL, 786432ULL, Access::Qraw', src('runtime_policy.hpp'))
            self.assertIn('"qr", 4485108864ULL, 786432ULL, 786432ULL, Access::Denied', src('runtime_policy.hpp'))

        def test_all_postchecks_before_commit(self):
            value = src('pc1_model_scheduler.inc').split('void rise_and_observe', 1)[1]
            order = ['model_.eval()', 'healthy(post)', 'guard_.after_rising(edge)', 'audit_.consume(pre_.axi)', 'advance_reads()', 'adapter_.retire_high(edge)']
            positions = [value.index(token) for token in order]
            self.assertEqual(positions, sorted(positions))
            commit = src('pc1_retirement_adapter.inc').split('owner_.commit_prevalidated(tx);', 1)[1].split('return;', 1)[0]
            self.assertNotIn('require(', commit)
            self.assertNotIn('check(', commit)

        def test_ack1_terminal_and_window(self):
            self.assertIn('decoded.pc!=1||decoded.owner!=2||decoded.status!=0||decoded.signal!=2', src('completion_payload.hpp'))
            value = src('pc01_driver.hpp')
            self.assertIn('if(qraw_published_)break;', value)
            self.assertIn('full.pc1_cycles=full.ack1_edge-full.pc1_accept_edge+1;', value)
            self.assertIn('model_.io_pc==2&&model_.io_issuedJobs==2&&!post.job_valid', src('pc1_model_scheduler.inc'))

        def test_transposed_counts_and_fixed_denominator(self):
            value = src('pc01_result.hpp')
            for token in ('useful_macs=301989888', 'physical_macs_per_cycle=4096', 'wide_steps=73728', 'slice_steps=589824', 'add_vectors=12288', 'total_cycle_budget=8000000'):
                self.assertIn(token, value)
            self.assertNotIn('122880', value)
            self.assertEqual(73728 * 4096, 301989888)
            self.assertEqual(589824 * 512, 301989888)

        def test_real_registered_model_and_no_new_taps(self):
            value = src('pc1_production_guard.hpp')
            for token in ('varFind(name)', 'var->datap()', '!var->isPublicRW()', 'root_->vlSymsp==syms_', '#include "n0_field_registry.inc"'):
                self.assertIn(token, value)
            self.assertNotIn('__reduction__', value)
            self.assertNotIn('fake', value)

        def test_no_bias_reference_computation(self):
            value = src('pc01_driver.hpp')
            for token in ('std::fma', 'matmul', 'numpy', 'torch', 'reference.f32le', 'bq.bin'):
                self.assertNotIn(token, value)
            main = text['bridge/source/pc01_main.cpp']
            self.assertIn('actual_qraw.f32le', main)
            self.assertIn('NOT_RUN', main)

        def test_complete_safe_code_vocabulary(self):
            codes = src('first_n0_diagnostic_codes.inc')
            for name, value in text.items():
                if name.endswith(('pc1_model_scheduler.inc', 'pc1_retirement_adapter.inc', 'pc1_production_guard.hpp', 'pc01_driver.hpp', 'runtime_ram.hpp', 'completion_payload.hpp')):
                    for phrase in re.findall(r'"(PC1[^"\n]*)"', value):
                        self.assertIn('"' + phrase + '"', codes)

    class LedgerChecks(unittest.TestCase):
        def test_requires_ack0(self):
            with self.assertRaises(ValueError): LedgerModel(False)

        def test_wrong_tag(self):
            with self.assertRaises(ValueError): LedgerModel().job(tag=458752)

        def test_wrong_epoch(self):
            with self.assertRaises(ValueError): LedgerModel().job(epoch=8)

        def test_duplicate_job(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.job()

        def test_aw_before_job(self):
            m = LedgerModel()
            with self.assertRaises(ValueError): m.address(m.BASE)

        def test_w_before_job(self):
            with self.assertRaises(ValueError): LedgerModel().data()

        def test_w_before_aw_is_staged_without_commit(self):
            m = LedgerModel(); m.job(); m.data(value=91)
            self.assertFalse(m.payload); m.address(m.BASE); self.assertFalse(m.payload); m.b()
            self.assertEqual(m.payload[m.BASE], 91)

        def test_early_b(self):
            m = LedgerModel(); m.job(); m.address(m.BASE)
            with self.assertRaises(ValueError): m.b()
            self.assertFalse(m.payload)

        def test_wrong_b_id(self):
            m = LedgerModel(); m.job(); m.address(m.BASE); m.data()
            with self.assertRaises(ValueError): m.b(ident=1)
            self.assertFalse(m.payload)

        def test_wrong_b_status(self):
            m = LedgerModel(); m.job(); m.address(m.BASE); m.data()
            with self.assertRaises(ValueError): m.b(resp=2)

        def test_wrong_generation(self):
            m = LedgerModel(); m.job(); m.address(m.BASE); m.data()
            with self.assertRaises(ValueError): m.b(generation=0)

        def test_wrong_serial(self):
            m = LedgerModel(); m.job(); m.address(m.BASE); m.data()
            with self.assertRaises(ValueError): m.b(serial=2)

        def test_same_edge_fault_prevents_mutation(self):
            m = LedgerModel(); m.job(); m.address(m.BASE); m.data()
            with self.assertRaises(ValueError): m.b(post_fault=True)
            self.assertFalse(m.payload)

        def test_duplicate_ssa_write(self):
            m = LedgerModel(); m.job(); m.address(m.BASE); m.data(); m.b()
            with self.assertRaises(ValueError): m.address(m.BASE)

        def test_n0_write_rejected(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.address(4483535872)

        def test_qr_write_rejected(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.address(4485108864)

        def test_guard_tail_rejected(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.address(m.BASE + m.SIZE)

        def test_cross_page_rejected(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.address(m.BASE, 63)

        def test_partial_strobe_rejected(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.data(strobe=1)

        def test_early_wlast_rejected(self):
            m = LedgerModel(); m.job(); m.address(m.BASE, 1); m.data(last=True)
            with self.assertRaises(ValueError): m.data(last=True)

        def test_missing_wlast_rejected(self):
            m = LedgerModel(); m.job(); m.address(m.BASE)
            with self.assertRaises(ValueError): m.data(last=False)

        def test_read_before_ack(self):
            with self.assertRaises(ValueError): LedgerModel().read()

        def test_incomplete_done_rejected(self):
            m = LedgerModel(); m.job()
            with self.assertRaises(ValueError): m.owner_done()

        def test_complete_full_qraw(self):
            m = full_model(); m.owner_done(); m.ack(); self.assertEqual(m.read(), 786432)

        def test_wrong_ack_signal(self):
            m = full_model(); m.owner_done()
            with self.assertRaises(ValueError): m.ack(signal=3)

        def test_wrong_ack_owner(self):
            m = full_model(); m.owner_done()
            with self.assertRaises(ValueError): m.ack(owner=3)

        def test_late_fault_revokes_ack(self):
            m = full_model(); m.owner_done()
            with self.assertRaises(ValueError): m.ack(post_fault=True)
            self.assertFalse(m.published)

        def test_no_pc2_accept(self):
            m = full_model(); m.owner_done(); m.ack()
            with self.assertRaises(ValueError): m.job(tag=458754)

        def test_duplicate_ack(self):
            m = full_model(); m.owner_done(); m.ack()
            with self.assertRaises(ValueError): m.ack()

    suite = unittest.TestSuite()
    for case in (SourceChecks, LedgerChecks):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
            'passed': result.wasSuccessful(), 'scope': 'STATIC_SOURCE_AND_INDEPENDENT_ABSTRACT_LEDGER_ONLY',
            'cpp_compiled': False, 'rtl_executed': False, 'numeric_comparison': 'NOT_RUN'}
