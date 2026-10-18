"""Portable read-only SOURCE checks. No compilation, model, trace, or numeric claim."""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

P = Path(__file__).resolve().parent
HEADERS = {
    'generated_binding.hpp', 'host_fields.hpp', 'silu_edge_runtime.hpp',
    'resident_evidence.hpp', 'physical_observer_bridge.hpp',
    'n0_fields.hpp', 'n0_physical_memory.hpp', 'axi_service.hpp',
}
FILES = HEADERS | {'README_CN.md', 'SOURCE_MAP.json', 'test_source_only.py', 'MANIFEST.json'}
DATA = {n: (P / n).read_bytes() for n in FILES}
TEXT = {n: b.decode('utf-8') for n, b in DATA.items()}
MAP = json.loads(TEXT['SOURCE_MAP.json'])
MANIFEST = json.loads(TEXT['MANIFEST.json'])

def sha(data):
    return hashlib.sha256(data).hexdigest()

def need(ok, message):
    if not ok:
        raise ValueError(message)

def digest_matches(data, record):
    need(len(data) == record['bytes'] and sha(data) == record['sha256'], 'payload identity mismatch')

def reverse_projection(data, item):
    need(sha(data) == item['payload_sha256'], 'mapped payload identity mismatch')
    lines = data.decode('utf-8').splitlines(keepends=True)
    used = set()
    for change in item['include_relocations']:
        index = change['line'] - 1
        need(index not in used, 'duplicate relocation')
        used.add(index)
        need(lines[index] == change['portable'] + '\n', 'portable include mismatch')
        need(re.fullmatch(r'#include "\.\./[^"\n]+"', change['original']) is not None, 'only original relative includes allowed')
        original_name = change['original'].split('/')[-1]
        need(change['portable'] == '#include "' + original_name, 'only include basename relocation allowed')
        lines[index] = change['original'] + '\n'
    restored = ''.join(lines).encode('utf-8')
    need(len(restored) == item['original_bytes'], 'restored byte length mismatch')
    need(sha(restored) == item['original_sha256'], 'restored source identity mismatch')
    return restored

def ordered(text, *terms):
    start = 0
    for term in terms:
        pos = text.find(term, start)
        need(pos >= 0, 'missing or reordered source clause: ' + term)
        start = pos + len(term)

def method_between(text, start, stop):
    return text.split(start, 1)[1].split(stop, 1)[0]

def require_fatal_domains(text, markers):
    for start, stop in markers:
        body = method_between(text, start, stop)
        need('missing(' in body, 'full domain must stay fail closed')

def has_environment_path(text):
    # Absolute filesystem strings, including drive-rooted strings, are forbidden.
    return bool(re.search(r'''["']/(?!/)[^"'\n\s]+''', text) or
                re.search(r'''["'][A-Za-z]:[\\/]''', text) or
                re.search(r'^#include\s*[<"]/|^#include\s*"\.\./', text, re.M))

class SourceChecks(unittest.TestCase):
    def test_exact_twelve_files(self):
        self.assertEqual({p.name for p in P.iterdir()}, FILES)
        self.assertTrue(all((P / n).is_file() and not (P / n).is_symlink() for n in FILES))

    def test_manifest_exact_set_and_hashes(self):
        self.assertEqual(set(MANIFEST['files']), FILES - {'MANIFEST.json'})
        for name, record in MANIFEST['files'].items():
            digest_matches(DATA[name], record)

    def test_manifest_does_not_claim_runtime(self):
        self.assertEqual(MANIFEST['scope'], 'SOURCE_ONLY_LOCAL_CANDIDATE')
        self.assertFalse(MANIFEST['independent_compile_closure'])
        self.assertFalse(MANIFEST['cpp_compiled_or_executed'])
        self.assertFalse(MANIFEST['host_or_rtl_executed'])
        self.assertFalse(MANIFEST['full_canonical_domain_methods_closed'])
        self.assertFalse(MANIFEST['publication_performed'])

    def test_source_map_exact_header_set(self):
        self.assertEqual({x['file'] for x in MAP['entries']}, HEADERS)
        self.assertEqual(len(MAP['entries']), 8)

    def test_original_review_identities(self):
        expected = {
            'binding': '9235e15bebb481ab370f6fef6dde2a5701a1bd30b5cc9d22a2c6d9848e4a6663',
            'resident': '54b7b61cd7fe9ae38da007756db72303a07e1840f63d602847127ba1f3b559cc',
            'n0': '5f215e893f788081bcffc384a4725444394f8970116665b00aa1130c535efa40',
        }
        self.assertEqual({x['id']: x['review_manifest_sha256'] for x in MAP['originals']}, expected)
        self.assertEqual(len(MAP['originals']), 3)

    def test_reverse_projection_eight_headers(self):
        for item in MAP['entries']:
            reverse_projection(DATA[item['file']], item)

    def test_raw_and_derived_classification(self):
        raw = []
        changes = 0
        for item in MAP['entries']:
            changes += len(item['include_relocations'])
            if item['mode'] == 'RAW_IDENTICAL':
                raw.append(item['file'])
                self.assertFalse(item['include_relocations'])
                self.assertEqual(item['payload_sha256'], item['original_sha256'])
            else:
                self.assertEqual(item['mode'], 'DERIVED_INCLUDE_RELOCATION_ONLY')
                self.assertTrue(item['include_relocations'])
                self.assertNotEqual(item['payload_sha256'], item['original_sha256'])
        self.assertEqual(raw, ['silu_edge_runtime.hpp'])
        self.assertEqual(changes, 10)

    def test_safe_payload_paths_and_types(self):
        for name, content in TEXT.items():
            self.assertNotIn('/', name)
            self.assertFalse(has_environment_path(content), name)
        self.assertEqual({Path(n).suffix for n in FILES}, {'.hpp', '.md', '.json', '.py'})

    def test_omitted_direct_dependencies_accurate(self):
        quoted = set()
        for name in HEADERS:
            quoted.update(re.findall(r'^#include "([^"\n]+)"', TEXT[name], re.M))
        self.assertEqual(quoted - HEADERS, set(MAP['external_direct_quoted_headers_not_included']))
        self.assertTrue(all('/' not in name for name in quoted))
        self.assertTrue(all(name not in DATA for name in quoted - HEADERS))

    def test_no_model_implementation_payload(self):
        self.assertFalse(any(name.startswith('VHost') for name in FILES))
        self.assertFalse(any(Path(name).suffix in {'.cpp', '.sv', '.o', '.a', '.so', '.bin'} for name in FILES))
        self.assertIn('verilated_sym_props.h', MAP['external_direct_quoted_headers_not_included'])

    def test_cold_test_imports_read_only_stdlib(self):
        tree = ast.parse(TEXT['test_source_only.py'])
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        self.assertEqual(imports, {'ast', 'hashlib', 'json', 'pathlib', 're', 'unittest'})
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'exec', 'eval', 'compile', '__import__'} for node in ast.walk(tree)))

    def test_binding_real_identity_checks(self):
        text = TEXT['generated_binding.hpp']
        for token in ('model_.rootp==root_', 'root_->vlSymsp==syms_', '&syms_->TOP==root_', 'syms_->__Vm_modelp==&model_', 'varFind(', 'datap()', 'isPublicRW()', 'require_actual_profile()const'):
            self.assertIn(token, text)

    def test_binding_exact_pre_post_read_counts(self):
        text = TEXT['generated_binding.hpp']
        pre = method_between(text, 'PreEdge read_stable_low()const', 'PostEdge read_settled_high()const')
        post = text.split('PostEdge read_settled_high()const', 1)[1]
        self.assertEqual(len(re.findall(r'out\.[^;\n]+?=read<\d+>\(r\.', pre)), 468)
        self.assertEqual(len(re.findall(r'out\.[^;\n]+?=read<\d+>\(r\.', post)), 13)

    def test_host_ports_and_snapshot(self):
        text = TEXT['host_fields.hpp']
        self.assertEqual(text.count('actual Host port alias '), 83)
        self.assertIn('using InputSnapshot=std::array<uint64_t,54>;', text)
        body = method_between(text, 'static InputSnapshot input_snapshot(', 'static void initialize_inputs(')
        for lane in range(16):
            self.assertIn('d.io_axi_r_bits_data[' + str(lane) + ']', body)

    def test_edge_input_hold_before_high_eval(self):
        text = TEXT['silu_edge_runtime.hpp'].split('rise_and_observe(uint64_t edge)', 1)[1]
        ordered(text, 'HostFields::input_snapshot(model_)==inputs_', 'model_.clock=1;', 'model_.eval();', 'observer_.after_rising(edge)', 'pending_=false;have_edge_=true;')

    def test_resident_actual_binding_only(self):
        text = TEXT['resident_evidence.hpp']
        self.assertIn('silu_observation::GeneratedBinding<VHostBlockTop> actual_;', text)
        self.assertIn('auto p=actual_.read_stable_low();', text)
        self.assertIn('auto p=actual_.read_settled_high();', text)

    def test_resident_counter_commit_after_post(self):
        text = TEXT['resident_evidence.hpp'].split('rise_and_observe(uint64_t edge)', 1)[1]
        ordered(text, 'input_snapshot(model_)==inputs_', 'model_.clock=1;model_.eval();', 'observer_.after_rising(edge)', 'commit_validated_frame(capture);', 'binding_.retire_frame();')

    def test_resident_seven_activity_counters(self):
        text = TEXT['resident_evidence.hpp']
        names = {'groups_accepted', 'groups_retired', 'resident_loans_accepted', 'resident_loans_retired', 'shared_loans_accepted', 'shared_loans_retired', 'captures'}
        self.assertEqual(set(re.findall(r'increment\(counts_\.(\w+)\)', text)), names)
        self.assertIn('pre.resident_group.identity', text)
        self.assertIn('pre.resident_group.act_tag', text)

    def test_checkpoint_lifetime_and_activity(self):
        text = TEXT['resident_evidence.hpp']
        self.assertIn('checkpoint.owner_==this&&checkpoint.lifetime_==lifetime_', text)
        self.assertIn('now.counts==checkpoint.at_.counts', text)
        self.assertIn('ResidentEvidence(const ResidentEvidence&)=delete;', text)
        self.assertIn('const std::shared_ptr<const uint8_t> lifetime_', text)

    def test_resident_full_admission_fatal(self):
        text = TEXT['physical_observer_bridge.hpp']
        require_fatal_domains(text, [('void require_bound_to_actual_host()', 'void settle_low('), ('void require_terminal_retired(', '\n    }\n};')])
        self.assertEqual(text.count('override {'), 11)
        self.assertIn('failed_=true;', text)
        self.assertIn('throw silu_observation::Incomplete', text)

    def test_n0_same_memory_and_private_loader_entry(self):
        text = TEXT['n0_physical_memory.hpp']
        self.assertEqual(text.count('HostMemory memory_{*this};'), 1)
        self.assertIn('private:\n    // Private sink TYPE', text)
        self.assertIn('class StageSealSink {', text)
        self.assertIn('return checked([&]{StageSealSink sink(*this);CanonicalSinkStreamBridge bridge;return bridge.load(source,sink);});', text)
        self.assertNotIn('friend class CanonicalSinkStreamBridge', text)

    def test_n0_successful_actual_b_gate(self):
        text = method_between(TEXT['n0_physical_memory.hpp'], 'void begin_b(', 'void end_b()')
        ordered(text, 'retiring_&&!b_window_&&write_', 's.bf()&&pre_.axi.bf()&&s.b==pre_.axi.b&&s.b.resp==0&&s.b.id==a.id', 'beats[0].data==write_->request.data', 'b_window_=true;b_ack_checked_=false;')

    def test_axi_commits_between_private_b_brackets(self):
        text = TEXT['axi_service.hpp']
        ordered(text, 'proof_.begin_b(', 'memory_.commit_b(', 'proof_.end_b();')
        self.assertIn('if(s.bf())', text)

    def test_n0_publication_waits_for_completion_ack(self):
        text = TEXT['n0_physical_memory.hpp'].split('void rise_and_observe(uint64_t edge)', 1)[1]
        ordered(text, 'input_snapshot(model_)==inputs_', 'const auto post=fields_.read(true);', 'consume_internal(post);axi_.advance(pre_.axi);', 'if(pre_completion_fire_)', 'published_=true;')
        self.assertIn('b_count_==outputs[0].bytes/64', text)

    def test_n0_other_domains_stay_fatal(self):
        text = TEXT['n0_physical_memory.hpp']
        self.assertIn('if(!n0_span(a,n))missing(', text)
        self.assertIn('if(prefix||!n0_span(a,n))missing(', text)
        require_fatal_domains(text, [('void require_bound_to_actual_host()', 'void require_completion_retired('), ('void require_terminal_retired(', '\npublic:')])

    def test_tampered_payload_hash_rejected(self):
        name = 'silu_edge_runtime.hpp'
        with self.assertRaises(ValueError):
            digest_matches(DATA[name] + b' ', MANIFEST['files'][name])

    def test_tampered_include_reverse_rejected(self):
        item = next(x for x in MAP['entries'] if x['file'] == 'generated_binding.hpp')
        data = DATA[item['file']].replace(b'#include "silu_observer.hpp"', b'#include "other.hpp"', 1)
        changed = dict(item, payload_sha256=sha(data))
        with self.assertRaises(ValueError):
            reverse_projection(data, changed)

    def test_noninclude_behavior_mutation_reverse_rejected(self):
        item = next(x for x in MAP['entries'] if x['file'] == 'resident_evidence.hpp')
        data = DATA[item['file']].replace(b'failed_=true;', b'failed_=false;', 1)
        changed = dict(item, payload_sha256=sha(data))
        with self.assertRaises(ValueError):
            reverse_projection(data, changed)

    def test_missing_fail_closed_clause_rejected(self):
        text = TEXT['physical_observer_bridge.hpp'].replace('missing("full reset provenance and remaining physical domains");', '')
        with self.assertRaises(ValueError):
            require_fatal_domains(text, [('void require_bound_to_actual_host()', 'void settle_low(')])

    def test_reordered_post_and_counter_rejected(self):
        text = 'commit_validated_frame(capture); auto capture=observer_.after_rising(edge);'
        with self.assertRaises(ValueError):
            ordered(text, 'observer_.after_rising(edge)', 'commit_validated_frame(capture);')

    def test_absolute_path_negative_fixture(self):
        fabricated = '#include "' + chr(47) + 'fictional_root' + chr(47) + 'header.hpp"'
        self.assertTrue(has_environment_path(fabricated))

if __name__ == '__main__':
    unittest.main(verbosity=2)
