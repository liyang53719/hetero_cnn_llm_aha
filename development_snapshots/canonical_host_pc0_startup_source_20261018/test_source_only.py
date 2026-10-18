"""Isolated source-text checks only. No compiler, EDA, model, raw log or input loading."""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {'startup/startup_main.cpp': {'bytes': 2421, 'sha256': 'ae01ddc1fa47f4c4fecd7e93acea1b1f1d1a86cdaaa2b2a1eacbd4ac86c4e038'}, 'startup/startup_inputs.hpp': {'bytes': 4810, 'sha256': '8ac9cc45e53730423a5ea02e1db5192d7243605d590c211fb721424c10af82bb'}, 'startup/startup_ledger.hpp': {'bytes': 10337, 'sha256': '5bd16ec45d9d8295e381412db0e43a56f9d17bc46e8c1c134845692334b0367d'}, 'startup/dpi_forwarders.hpp': {'bytes': 10536, 'sha256': '26cdffd5c206337d0970aa772ff666e9fc9569d600ce42e5e4478072fd4b37f6'}, 'pc0/pc0_main.cpp': {'bytes': 9813, 'sha256': 'af85c334db985bb9bb4c4c9d24961772b3c2240996560253ebd06be9d8e29323'}, 'pc0/startup_inputs.hpp': {'bytes': 4810, 'sha256': '8ac9cc45e53730423a5ea02e1db5192d7243605d590c211fb721424c10af82bb'}, 'pc0/startup_ledger.hpp': {'bytes': 15802, 'sha256': '7e12150fabd9f611137165cd2ba3ee4f2274184b48283dff46e101271070983b'}, 'pc0/dpi_forwarders.hpp': {'bytes': 10536, 'sha256': '26cdffd5c206337d0970aa772ff666e9fc9569d600ce42e5e4478072fd4b37f6'}, 'pc0/n0_participant.hpp': {'bytes': 18855, 'sha256': 'bfa982b3e404960d6c85f433131350fa5d32c60a040da31cc36334720faf5b5f'}, 'pc0/resident_participant.hpp': {'bytes': 9464, 'sha256': '95945ff9e344bd11d86cc2a46af6e4af1630d36ff88a211169057752b00f2ca7'}, 'pc0/shared_edge_runtime.hpp': {'bytes': 4996, 'sha256': '6c906bff9c327abd873218a6f81499a29723209a85b53c1baf31857deb7b8a7d'}}
OTHER_FILES = {'README_CN.md', 'failure_summary.json', 'test_source_only.py'}
EXTERNAL_INCLUDES = {
    'VHostBlockTop.h', 'VHostBlockTop___024root.h', 'VHostBlockTop__Dpi.h',
    'svdpi.h', 'n0_fields.hpp', 'axi_service.hpp', 'sink_stream_bridge.hpp', 'host_fields.hpp',
}

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read(name):
    path = ROOT / name
    need(path.is_file() and not path.is_symlink(), 'regular payload file required')
    return path.read_bytes()

def source(name):
    return read(name).decode('utf-8')

def pinned(name, raw):
    pin = EXPECTED[name]
    need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'source bytes/hash mismatch')

def method(text, name):
    match = re.search(r'\b(?:void|unsigned) ' + re.escape(name) + r'\(', text)
    need(match is not None, 'method missing')
    opening = text.index('{', match.end())
    depth = 1
    for i in range(opening + 1, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if depth == 0:
            return text[match.start():i + 1]
    raise ValueError('method unclosed')

def validate_summary(s):
    need(s['kind'] == 'CURATED_SOURCE_CHECKPOINT_FAILURE_SUMMARY_NOT_RUNTIME_RECEIPT', 'summary scope')
    need(s['status'] == 'NOT_COMPLETED', 'preserve actual failure')
    o = s['observed_prior_attempt']
    for key, value in [('work_budget_seconds', 300), ('last_saved_completed_cycles', 598016),
                       ('last_saved_pc', 0), ('last_saved_issued_jobs', 1), ('last_saved_owner_result_write_bytes', 0)]:
        need(type(o[key]) is int and o[key] == value, 'fixed observation')
    need(o['terminated_at_work_budget_boundary'] is True, 'work-bound termination')
    need(o['write_bytes_semantics'] == 'SUM_OF_COMPLETED_OWNER_RESULT_BYTES_NOT_PER_B_TRANSACTION_COUNT', 'owner aggregate semantics')
    for key in ('last_saved_cycle_is_exact_final', 'actual_B_count_known', 'internal_final_state_known',
                'actual_n0_output_available', 'numerical_comparison_available', 'continuation_checkpoint_available'):
        need(o[key] is False, 'unknown or unavailable cannot become proof')
    a = s['read_only_source_analysis']
    row = 1536 * (3 + 4 + 4 + 1) + (96 + 32 + 8) * 4
    need(row == a['normal_successful_row_reduction_lower_bound'] == 18976, 'row lower-bound arithmetic')
    need(128 * row == a['M128_reduction_only_lower_bound'] == 2428928, 'M128 lower-bound arithmetic')
    need(a['weaker_independent_M128_lower_bound'] == 2018304 > a['source_cycle_cap'] == 2000000, 'legacy cap insufficient')
    need(a['source_cycle_cap_insufficient_for_normal_successful_M128'] is True, 'insufficient cap qualification')
    need(a['is_actual_measurement_or_upper_bound'] is False and a['determines_state_at_last_saved_sample'] is False, 'source bounds are not trace')
    c = s['candidate_work']
    for key in ('original_assets_modified', 'cycle_cap_or_budget_changed', 'native_model_eda_or_cpp_executed',
                'full_block_pass', 'independently_compilable_model'):
        need(c[key] is False, 'source-only candidate qualification')
    need(c['new_run_requires_separate_review_and_authorization'] is True, 'new run gate')

class SourceOnly(unittest.TestCase):
    def test_01_exact_payload_set(self):
        paths = list(ROOT.rglob('*'))
        self.assertFalse(any(p.is_symlink() for p in paths))
        self.assertEqual({p.relative_to(ROOT).as_posix() for p in paths if p.is_file()}, set(EXPECTED) | OTHER_FILES)
        self.assertEqual(len(EXPECTED), 11)

    def test_02_source_bytes_hashes(self):
        for name in EXPECTED:
            with self.subTest(name=name):
                pinned(name, read(name))

    def test_03_in_memory_append_mutations_rejected(self):
        for name in EXPECTED:
            with self.subTest(name=name), self.assertRaises(ValueError):
                pinned(name, read(name) + b' ')

    def test_04_in_memory_same_length_mutations_rejected(self):
        for name in EXPECTED:
            raw = read(name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                pinned(name, bytes([raw[0] ^ 1]) + raw[1:])

    def test_05_quoted_includes_are_logical_names(self):
        unresolved = set()
        for name in EXPECTED:
            for include in re.findall(r'^#include "([^"]+)"$', source(name), re.M):
                self.assertEqual(Path(include).name, include)
                if not (ROOT / name).parent.joinpath(include).is_file():
                    unresolved.add(include)
        self.assertEqual(unresolved, EXTERNAL_INCLUDES)

    def test_06_no_environment_paths_or_url(self):
        forbidden = re.compile(r'/(?:workspace|home|root|tmp|usr|opt|etc|var)(?:/|\b)|[A-Za-z]:[\\/]|(?:https?|file)[:][/][/]')
        for name in EXPECTED | dict.fromkeys(OTHER_FILES):
            with self.subTest(name=name):
                self.assertIsNone(forbidden.search(source(name)))

    def test_07_no_actual_runtime_handle_literals(self):
        for name in EXPECTED:
            self.assertIsNone(re.search(r'0[xX][0-9a-fA-F]{10,}|"handle"\s*:\s*[1-9]\d{9,}', source(name)))

    def test_08_shared_inputs_and_forwarders_equal(self):
        for name in ('startup_inputs.hpp', 'dpi_forwarders.hpp'):
            self.assertEqual(read('startup/' + name), read('pc0/' + name))

    def test_09_original_startup_end_eval_preserved(self):
        self.assertEqual(method(source('startup/startup_ledger.hpp'), 'end_eval'), method(source('pc0/startup_ledger.hpp'), 'end_eval'))

    def test_10_startup_schedule(self):
        text = source('startup/startup_main.cpp')
        for token in ('step(0,0,1)', 'step(1,0,0)', 'step(2,0,1)', 'step(11,0,0)', 'phase<=19', 'context.randReset(0)', 'context.randSeed(1)'):
            self.assertIn(token, text)
        self.assertEqual(text.count('model.eval()'), 1)
        self.assertLess(text.index('model.final()'), text.index('audit.report(std::cout)'))

    def test_11_zero_inputs_and_snapshot(self):
        text = source('startup/startup_inputs.hpp')
        self.assertIn('std::array<uint64_t,54> input_snapshot', text)
        self.assertIn('std::array<uint64_t,8> root_handles', text)
        self.assertIn('std::array<unsigned,8> gate_clocks', text)
        for token in ('d.io_launch_valid=0;', 'd.io_completion_ready=0;', 'd.io_result_ready=0;'):
            self.assertIn(token, text)

    def test_12_forward_actual_calls_and_fail_closed(self):
        text = source('pc0/dpi_forwarders.hpp')
        self.assertEqual(text.count('catch(...) {a.poison();throw;}'), 6)
        self.assertEqual(text.count('return actual;'), 3)
        self.assertEqual(text.count('a.no_job('), 2)
        self.assertNotIn('model.eval()', text)

    def test_13_startup_before_work_delta(self):
        original = method(source('startup/startup_ledger.hpp'), 'begin_eval')
        expected = original.replace('!active_eval_&&!active_final_,"nested or closed eval"',
                                    '!active_eval_&&!active_final_&&!work_started_,"nested or closed startup eval"')
        self.assertEqual(method(source('pc0/startup_ledger.hpp'), 'begin_eval'), expected)

    def test_14_unique_actual_handles_preserved(self):
        for name in ('after_create', 'lookup', 'no_job'):
            self.assertEqual(method(source('startup/startup_ledger.hpp'), name), method(source('pc0/startup_ledger.hpp'), name))

    def test_15_legacy_cap_explicitly_preserved(self):
        self.assertIn('inline constexpr uint64_t max_cycles=2000000;', source('pc0/pc0_main.cpp'))
        self.assertIn('static constexpr uint64_t kMaxWorkCycles=2000000ULL;', source('pc0/startup_ledger.hpp'))
        self.assertIn('work_evals_<kMaxWorkCycles*2ULL', source('pc0/startup_ledger.hpp'))

    def test_16_pc0_guard_before_high(self):
        text = source('pc0/pc0_main.cpp')
        self.assertLess(text.index('host_pc0::exact_pre_high(model,pre);'), text.index('runtime.rise_and_observe(edge)'))
        for token in ('d.io_pc==0', 'j.kind==0', 'j.m==128', 'j.n==1536', 'j.k==1536', '!d.io_result_valid'):
            self.assertIn(token, text)

    def test_17_pc0_stop_on_real_ack(self):
        text = source('pc0/pc0_main.cpp')
        start = text.index('if(completion_fire) {')
        stop = text.index('acked=true;break;', start)
        self.assertIn('runtime.require_n0_published();', text[start:stop])
        self.assertIn('publication.completion_ack_word==completion_word', text[start:stop])
        self.assertNotIn('.eval()', text[start:stop])
        self.assertNotIn('rise_and_observe', text[start:stop])

    def test_18_no_reference_as_actual(self):
        text = source('pc0/pc0_main.cpp')
        self.assertIn('runtime.actual_byte(outputs[0].base+i)', text)
        self.assertNotIn('native_n0', text)
        self.assertNotIn('phase_0_n0_recipe', text)
        self.assertEqual(text.count('model.eval()'), 1)

    def test_19_real_load_and_ram_checks_preserved(self):
        text = source('pc0/pc0_main.cpp')
        self.assertIn('loaded.require_all14_v2_streams_exhausted();', text)
        self.assertIn('runtime.read_input_span(i,0,inputs[i].bytes)', text)
        self.assertIn('ram_hashes[i]==inputs[i].sha256', text)

    def test_20_progress_reports_owner_aggregate_only(self):
        text = source('pc0/pc0_main.cpp')
        self.assertIn('d.io_writeBytes', text[text.index('static void progress'):text.index('int main')])
        self.assertNotIn('b_count_', text[text.index('static void progress'):text.index('int main')])

    def test_21_shared_low_high_single_scheduler(self):
        text = source('pc0/shared_edge_runtime.hpp')
        self.assertEqual(text.count('model_.eval()'), 2)
        self.assertIn('model_.clock=0;model_.eval();', text)
        self.assertIn('model_.clock=1;model_.eval();', text)
        self.assertLess(text.index('resident_.observe_settled_high(edge)'), text.index('memory_.observe_settled_high(edge)'))

    def test_22_same_memory_and_no_redundant_eval(self):
        text = source('pc0/n0_participant.hpp')
        self.assertEqual(text.count('HostMemory memory_{*this};'), 1)
        self.assertIn('AxiService<N0PhysicalMemory> axi_{memory_,*this};', text)
        for name in ('pc0/n0_participant.hpp', 'pc0/resident_participant.hpp'):
            self.assertNotIn('.eval()', source(name))

    def test_23_actual_b_before_private_retirement(self):
        text = source('pc0/n0_participant.hpp')
        self.assertIn('s.bf()&&pre_.axi.bf()&&s.b==pre_.axi.b&&s.b.resp==0', text)
        self.assertIn('committed_bytes_+=64;++b_count_;', method(text, 'end_b'))
        self.assertIn('b_window_&&b_ack_checked_&&write_&&!write_->b_committed', method(text, 'end_b'))

    def test_24_ack_gated_publication_and_known_gaps(self):
        text = source('pc0/n0_participant.hpp')
        self.assertIn('completion_ack_word_=*held_completion_;published_=true;held_completion_.reset();', text)
        self.assertIn('published_&&done_&&committed_bytes_==outputs[0].bytes', text)
        self.assertIn('17 owners and 27 captures INCOMPLETE', text)
        self.assertIn('full-domain', text)

    def test_25_work_dpi_and_final_gate(self):
        text = source('pc0/startup_ledger.hpp')
        self.assertIn('clock==unsigned(work_evals_&1ULL)', method(text, 'begin_work_eval'))
        self.assertIn('work_evals_>0&&(work_evals_&1ULL)==0', method(text, 'end_work'))
        self.assertIn('work_done_&&!work_active_', method(text, 'begin_final'))
        self.assertIn('The caller may close work ONLY after independently proving actual ACK0.', text)

    def test_26_failure_summary_honest(self):
        validate_summary(json.loads(source('failure_summary.json')))

    def test_27_failure_summary_false_success_rejected(self):
        summary = json.loads(source('failure_summary.json'))
        summary['status'] = 'PASS'
        with self.assertRaises(ValueError):
            validate_summary(summary)

    def test_28_no_b_or_final_state_inference(self):
        for key in ('actual_B_count_known', 'last_saved_cycle_is_exact_final', 'internal_final_state_known', 'numerical_comparison_available'):
            summary = json.loads(source('failure_summary.json'))
            summary['observed_prior_attempt'][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_summary(summary)

    def test_29_bound_arithmetic_and_negative_case(self):
        self.assertEqual(1536 * 128, 196608)
        self.assertEqual(1536 + 96 + 32 + 8, 1672)
        summary = json.loads(source('failure_summary.json'))
        summary['read_only_source_analysis']['source_cycle_cap'] = 3000000
        with self.assertRaises(ValueError):
            validate_summary(summary)

    def test_30_no_build_qualification(self):
        summary = json.loads(source('failure_summary.json'))
        for key in ('independently_compilable_model', 'full_block_pass', 'native_model_eda_or_cpp_executed'):
            mutated = json.loads(json.dumps(summary))
            mutated['candidate_work'][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_summary(mutated)

if __name__ == '__main__':
    unittest.main(verbosity=2)
