"""Offline rejection tests using SYNTHETIC metadata, never real-run acceptance.

Run normal and optimized under isolated stdlib Python. No numerical or native
entry point is loaded; no package, network, process or workflow is launched.
The positive fixture is structurally generated; independent count, geometry,
constant, coverage-pattern and corruption checks provide separate assertions.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identity_schema as S
from test_fixture import build_manifest, placeholder, seal, synthetic_sources, synthetic_compile_sources


class PublicSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = synthetic_sources()
        cls.compile_sources = synthetic_compile_sources(cls.sources)
        cls.good = build_manifest(cls.sources, compile_sources=cls.compile_sources)

    def changed(self, path, replacement, reseal=True):
        value = copy.deepcopy(self.good)
        target = value
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
        return seal(value) if reseal else value

    def reject(self, path, replacement, reseal=True):
        with self.assertRaises(S.ManifestError) as caught:
            S.validate_manifest(self.changed(path, replacement, reseal), self.sources, compile_sources=self.compile_sources)
        self.assertRegex(str(caught.exception), r'^[A-Z][A-Z0-9_]*$')

    def test_synthetic_success_has_no_acceptance(self):
        result = S.validate_manifest(copy.deepcopy(self.good), self.sources, compile_sources=self.compile_sources)
        self.assertEqual(result['status'], 'PUBLIC_IDENTITY_SCHEMA_AND_BINDINGS_VALID')
        for key in ('private_tensor_bytes_rehashed', 'numerical_replay_performed',
                    'provenance_authenticated_by_this_function', 'parent_completion_verified_by_this_function',
                    'numerical_acceptance_granted', 'freeze_readiness_granted',
                    'full_29_node_acceptance', 'rtl_acceptance', 'hardware_acceptance'):
            self.assertIs(result[key], False)

    def test_inventory_counts_independently(self):
        self.assertEqual(set(self.good['identity']['runs']), {'16', '128'})
        for run in self.good['identity']['runs'].values():
            for key, count in (('payload', 13), ('readonly', 3), ('native', 116), ('sequential_exports', 29)):
                self.assertEqual(len(run[key]), count)
            self.assertEqual({k: len(v) for k, v in run['scalar_raw'].items()}, {'sequential': 22, 'reduced': 22})
            full = run['full']
            for key, count in (('persisted_actual', 20), ('attention_captures', 10), ('actual_stages', 28),
                               ('loaded_providers', 14), ('fixed_arithmetic_bindings', 21)):
                self.assertEqual(len(full[key]), count)
            for method, table in full['gate_bindings'].items():
                self.assertEqual(len(table), 28)
                self.assertEqual(sum(item['assigned'] for item in table.values()), 27 if method == 'official_self_cache' else 0)

    def test_distinct_opaque_placeholders(self):
        p = self.good['provenance']
        self.assertNotEqual(p['qualification_sha256'], p['m16_prerequisite_sha256'])
        self.assertNotEqual(p['producer_manifest_sha256']['16'], p['producer_manifest_sha256']['128'])
        self.assertNotEqual(p['runtime']['runtime_files']['libc'], p['runtime']['runtime_files']['libm'])
        self.assertTrue(any(k.startswith('synthetic_fixture_only/') for k in self.sources))

    def test_public_body_is_under_two_mib(self):
        self.assertLess(len(S.canonical(self.good)), 2 * 1024 * 1024)

    def test_top_level_missing_and_extra(self):
        for key in self.good:
            with self.subTest(missing=key):
                value = copy.deepcopy(self.good)
                del value[key]
                with self.assertRaises(S.ManifestError):
                    S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)
        value = copy.deepcopy(self.good)
        value['private_path'] = '/private/secret'
        with self.assertRaisesRegex(S.ManifestError, '^FIELDS$'):
            S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)

    def test_nested_extra_keys_are_rejected(self):
        paths = [
            ('identity',), ('identity', 'model'), ('identity', 'serialization'), ('identity', 'stimulus'),
            ('identity', 'policy'), ('identity', 'recipe_sources'), ('identity', 'runs'),
            ('identity', 'runs', '16'), ('identity', 'runs', '16', 'full'),
            ('identity', 'runs', '16', 'payload', 'input_layernorm.weight'),
            ('identity', 'runs', '128', 'native', 'fp32.official_self_cache.q', 'native_storage'),
            ('identity', 'runs', '128', 'full', 'attention_captures', 'scores_bf16'),
            ('identity', 'runs', '128', 'full', 'attention_captures', 'scores_bf16', 'raw'),
            ('identity', 'runs', '128', 'full', 'actual_stages', 'cache_k', 'reconstruction'),
            ('identity', 'runs', '128', 'full', 'loaded_providers', 'wq', 'reconstruction'),
            ('identity', 'runs', '16', 'full', 'gate_bindings', 'official_self_cache', 'y'),
            ('identity', 'runs', '16', 'full', 'fixed_arithmetic_bindings', 'q'),
            ('provenance',), ('provenance', 'ci'), ('provenance', 'runtime'),
            ('provenance', 'runtime', 'compiler'), ('provenance', 'runtime', 'fenv'),
            ('provenance', 'builds', '16', 'scalar_builds', 'sequential'),
            ('provenance', 'builds', '128', 'recipe_libraries', 'qkv'), ('provenance', 'combined_library'), ('authority',)]
        for path in paths:
            with self.subTest(path=path):
                target = self.good
                for key in path:
                    target = target[key]
                self.reject(path, dict(target, raw_private_banner='/private/secret'))

    def test_all_inventory_containers_reject_missing_and_duplicate_alias(self):
        for rows in ('16', '128'):
            prefix = ('identity', 'runs', rows)
            paths = [(key,) for key in ('payload', 'readonly', 'native', 'sequential_exports')]
            paths += [('scalar_raw', role) for role in ('sequential', 'reduced')]
            paths += [('full', key) for key in ('persisted_actual', 'attention_captures', 'actual_stages', 'loaded_providers', 'fixed_arithmetic_bindings')]
            paths += [('full', 'gate_bindings', method) for method in S.METHODS]
            for suffix in paths:
                path = prefix + suffix
                target = self.good
                for key in path:
                    target = target[key]
                missing = dict(target)
                del missing[next(iter(missing))]
                with self.subTest(path=path):
                    self.reject(path, missing)
                    self.reject(path, dict(target, unexpected_alias=next(iter(target.values()))))

    def test_wrong_schema_and_status(self):
        self.reject(('schema',), 'qwen2-same-host-replay-identity-v2')
        self.reject(('status',), 'PASS_FRESH_SAME_HOST_M128_ASSIGNED27')

    def test_authority_all_exact_booleans(self):
        for key, value in self.good['authority'].items():
            with self.subTest(key=key):
                self.reject(('authority', key), not value)
                self.reject(('authority', key), int(value))

    def test_integer_bool_and_float_confusion(self):
        for path in [('identity', 'model', 'layer'), ('identity', 'stimulus', 'batch'),
                     ('provenance', 'runtime', 'threads'), ('provenance', 'runtime', 'fenv', 'x87_round'),
                     ('identity', 'runs', '16', 'readonly', 'input_x', 'bytes')]:
            for replacement in (True, False, 1.0, '1', None):
                with self.subTest(path=path, replacement=replacement):
                    self.reject(path, replacement)

    def test_non_json_scalars_and_collections(self):
        for replacement in (b'cpu', ('cpu',), {'cpu'}, object()):
            self.reject(('provenance', 'runtime', 'device'), replacement, reseal=False)

    def test_nonfinite_numbers(self):
        for number in (float('nan'), float('inf'), float('-inf')):
            self.reject(('identity', 'policy', 'operator', 'max_abs'), number, reseal=False)

    def test_digest_format_types_and_unsafe_strings(self):
        for value in (None, True, 13, 'A' * 64, '1' * 63, 'g' * 64, '/private/data',
                      'https://secret.invalid/data', 'a' * 63 + '\n', 'a' * 63 + '\x00', 'é' * 64):
            with self.subTest(value=value):
                self.reject(('provenance', 'qualification_sha256'), value)

    def test_stable_identity_digest_is_checked_after_content_changes(self):
        self.reject(('identity_sha256',), placeholder('wrong-identity'), reseal=False)
        value = copy.deepcopy(self.good)
        item = value['identity']['runs']['16']['native']['fp32.official_self_cache.q']
        item['native_storage']['content_sha256'] = placeholder('changed-opaque-storage')
        with self.assertRaisesRegex(S.ManifestError, '^IDENTITY_SHA256$'):
            S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)
        seal(value)
        S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)  # An opaque valid commitment is allowed.

    def test_dimensions_shapes_bytes_encoding_and_mapping(self):
        path = ('identity', 'runs', '128', 'native', 'bf16.official_self_cache.q')
        for key, val in [('stored_shape', [1, 12, 128, 128]), ('logical_shape', [1, 128, 1536]),
                         ('bytes', 786431), ('bytes', True), ('logical_dtype', 'float32'),
                         ('storage_encoding', 'bfloat16_le'), ('canonical_mapping', 'IDENTITY_C_ORDER')]:
            with self.subTest(key=key, val=val):
                self.reject(path + (key,), val)
        self.reject(path + ('logical_shape',), [True, 12, 128, 128])
        self.reject(path + ('logical_shape',), [1, 12, -128, 128])
        self.reject(path + ('logical_shape',), [1, 12, 128.0, 128])

    def test_kv_plane_order_and_actual_provenance(self):
        path = ('identity', 'runs', '16', 'full', 'persisted_actual')
        self.reject(path + ('kv', 'stored_shape'), [1, 16, 512])
        self.reject(path + ('kv', 'canonical_mapping'), 'V_PLANE_THEN_K_PLANE')
        self.reject(path + ('gate', 'origin'), 'ACKED_PHYSICAL_OUTPUT')
        self.reject(path + ('qraw', 'logical_dtype'), 'bfloat16')

    def test_native_storage_status_and_diagnostic_scope(self):
        path = ('identity', 'runs', '16', 'native')
        self.reject(path + ('bf16.independent_self_cache.q', 'native_storage', 'content_sha256'), placeholder('invented-storage'))
        self.reject(path + ('bf16.independent_self_cache.q', 'native_storage', 'verification'), 'DIRECT_FILE_REHASH')
        self.reject(path + ('bf16.official_self_cache.q', 'native_storage', 'verification'), 'DIRECT_FILE_REHASH')
        self.reject(path + ('fp32.official_self_cache.q', 'acceptance_scope'), 'BF16_REFERENCE')
        self.reject(path + ('bf16.official_self_cache.softmax_fp32', 'logical_dtype'), 'bfloat16')

    def test_identity_mapping_hashes_bind(self):
        self.reject(('identity', 'runs', '16', 'native', 'bf16.official_self_cache.x', 'content_sha256'), placeholder('mismatch'))

    def test_payload_ledger_and_scope(self):
        path = ('identity', 'runs', '128', 'payload', 'embed_tokens.rows_0_255')
        for key, val in [('selected_rows', [0, 128]), ('source_shape', [256, 1536]),
                         ('file_sha256', placeholder('wrong-payload')), ('bytes', 786431)]:
            self.reject(path + (key,), val)
        self.reject(('identity', 'model', 'whole_checkpoint_hash_verified'), True)
        self.reject(('identity', 'model', 'revision'), '0' * 40)
        self.reject(('identity', 'model', 'layer'), 1)

    def test_stimulus_and_no_random_claim(self):
        for key, val in [('token_ids', 'RANDOM'), ('past_tokens', 16), ('carried', True), ('rows', [128, 16]),
                         ('stimulus_seed', 0), ('stimulus_random_draw', True), ('framework_construction_rng_claim', True),
                         ('intermediate_preloads', 1), ('tokenizer_or_template', True)]:
            self.reject(('identity', 'stimulus', key), val)

    def test_readonly_pins_and_table_scope(self):
        self.reject(('identity', 'runs', '16', 'readonly', 'input_x', 'file_sha256'), S.INPUT_PINS[128][0])
        self.reject(('identity', 'runs', '128', 'full', 'actual_stages', 'cos', 'origin'), 'ACTUAL_ATTENTION_CAPTURE')
        self.reject(('identity', 'runs', '128', 'full', 'actual_stages', 'x', 'content_sha256'), placeholder('wrong-x'))

    def test_provider_actual_metadata_distinction(self):
        path = ('identity', 'runs', '16', 'full', 'loaded_providers')
        self.reject(path + ('wq', 'file_sha256'), placeholder('invented-direct-file'))
        self.reject(path + ('wq', 'verification'), 'DIRECT_FILE_REHASH')
        self.reject(path + ('x', 'verification'), 'QUALIFIED_METADATA_ONLY')
        self.reject(path + ('x', 'content_sha256'), placeholder('wrong-x-provider'))
        self.reject(path + ('rope', 'qualified_snapshot_rows'), 128)
        self.reject(path + ('rope', 'reconstruction', 'recipe'), 'UNQUALIFIED_EXPANSION')
        self.reject(path + ('wq', 'reconstruction', 'source_content_sha256'), placeholder('wrong-source'))

    def test_logical_reference_namespace_and_row_scope(self):
        path = ('identity', 'runs', '16', 'full')
        for value in ('payload:missing', 'payload:input_layernorm.weight:extra', 'full.actual_stages:x',
                      '/private/file', 'runs.128.payload:self_attn.q_proj.weight'):
            self.reject(path + ('loaded_providers', 'wq', 'reconstruction', 'source_tensor'), value)
        self.reject(path + ('actual_stages', 'cache_k', 'reconstruction', 'source_tensors'), ['full.persisted_actual:att'])
        self.reject(path + ('actual_stages', 'repeat_k', 'reconstruction', 'source_tensors'), ['full.actual_stages:repeat_k'])

    def test_causal_counts_independently(self):
        for rows, observed, future in (('16', 1632, 1440), ('128', 99072, 97536)):
            full = self.good['identity']['runs'][rows]['full']
            for name in ('scores', 'logits', 'prob', 'softmax_fp32'):
                self.assertEqual(full['actual_stages'][name]['observed_elements'], observed)
                self.assertEqual(full['actual_stages'][name]['unobserved_elements'], future)
            dot = full['attention_captures']['dot_parts']
            self.assertEqual(dot['observed_elements'], 16 * observed)
            self.assertEqual(dot['unobserved_elements'], 16 * future)

    def test_presence_frequency_pattern_is_independent_byte_metadata(self):
        for rows in (16, 128):
            # Independent source-defined integer-mask construction, no values.
            mask = bytes(int(key <= query) for head in range(12) for query in range(rows) for key in range(rows))
            frequency = b''.join(bytes((value, 0)) for value in mask)
            cap = self.good['identity']['runs'][str(rows)]['full']['attention_captures']['scores_bf16']
            self.assertEqual(cap['presence']['file_sha256'], hashlib.sha256(mask).hexdigest())
            self.assertEqual(cap['frequency']['file_sha256'], hashlib.sha256(frequency).hexdigest())

    def test_capture_coverage_sentinel_hash_scopes(self):
        path = ('identity', 'runs', '128', 'full', 'attention_captures', 'scores_bf16')
        for key, val in [('observed_elements', 196608), ('unobserved_elements', 0), ('coverage', 'COMPLETE'),
                         ('absent_word_hex', 'c33c96a5'), ('future_positions_observed', True),
                         ('raw_hash_scope', 'OBSERVED_LOGICAL_VALUES_ONLY'), ('present_hash_scope', 'FULL_STORAGE'),
                         ('present_mapping', 'ALL_WORDS_IN_C_ORDER'), ('semantic_value_dtype', 'uint32')]:
            self.reject(path + (key,), val)
        self.reject(path + ('presence', 'file_sha256'), placeholder('wrong-mask'))
        self.reject(path + ('frequency', 'file_sha256'), placeholder('wrong-frequency'))
        self.reject(path + ('raw', 'bytes'), 196608)

    def test_present_raw_and_actual_capture_bindings(self):
        self.reject(('identity', 'runs', '16', 'full', 'attention_captures', 'pv_bf16', 'present_content_sha256'), placeholder('wrong-complete-present'))
        self.reject(('identity', 'runs', '128', 'full', 'actual_stages', 'scores', 'content_sha256'), placeholder('wrong-raw'))
        self.reject(('identity', 'runs', '128', 'full', 'actual_stages', 'logits', 'present_content_sha256'), placeholder('wrong-present'))
        self.reject(('identity', 'runs', '128', 'full', 'actual_stages', 'scores', 'capture_field'), 'prob_bf16')

    def test_actual_descriptor_aliases_must_match(self):
        self.reject(('identity', 'runs', '128', 'full', 'actual_stages', 'q', 'file_sha256'), placeholder('wrong-actual-alias'))

    def test_gate_diagnostic_assigned_and_official_rules(self):
        path = ('identity', 'runs', '16', 'full', 'gate_bindings')
        for method, name, key, val in [('official_self_cache', 'y', 'qualified_verdict', False),
            ('official_self_cache', 'q', 'assigned', False), ('independent_self_cache', 'q', 'assigned', True),
            ('independent_self_cache', 'q', 'qualified_verdict', 1),
            ('official_self_cache', 'softmax_fp32', 'qualified_verdict', True),
            ('official_self_cache', 'softmax_fp32', 'assigned', True),
            ('official_self_cache', 'softmax_fp32', 'policy', 'BF16_OPERATOR'),
            ('official_self_cache', 'scores', 'comparison_mapping', 'LOGICAL_C_ORDER')]:
            self.reject(path + (method, name, key), val)

    def test_gate_hash_and_reference_bindings(self):
        path = ('identity', 'runs', '128', 'full', 'gate_bindings', 'official_self_cache', 'y')
        self.reject(path + ('actual_comparison_sha256',), placeholder('wrong-gate-actual'))
        self.reject(path + ('reference_comparison_sha256',), placeholder('wrong-gate-reference'))
        self.reject(path + ('reference_tensor',), 'native:fp32.official_self_cache.y')
        self.reject(path + ('actual_tensor',), 'full.persisted_actual:y')

    def test_fixed_arithmetic_bindings_and_hash_equality(self):
        path = ('identity', 'runs', '16', 'full', 'fixed_arithmetic_bindings')
        self.reject(path + ('q', 'qualified_bit_exact'), False)
        self.reject(path + ('q', 'reference_tensor'), 'scalar_raw.sequential:q')
        self.reject(path + ('scores', 'reference_comparison_sha256'), placeholder('wrong-bit-exact'))
        self.reject(path + ('pv', 'comparison_mapping'), 'LOGICAL_C_ORDER')
        self.reject(path + ('softmax_fp32', 'comparison_mapping'), 'LOGICAL_C_ORDER')

    def test_provenance_ci_types_and_ranges(self):
        for key, values in [('commit', ['a' * 39, 'A' * 40, None]),
                            ('run_id', [123, '', '0', '-1', '1e3', '１', '9' * 25]),
                            ('run_attempt', [1, '2', True])]:
            for val in values:
                self.reject(('provenance', 'ci', key), val)
        # Actual CI identity equality is the wrapper's responsibility.
        value = self.changed(('provenance', 'ci', 'run_id'), '39017864296')
        S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)

    def test_provenance_hash_map_types_and_counts(self):
        self.reject(('provenance', 'native_result_sha256'), {'16': placeholder('16')})
        self.reject(('provenance', 'producer_manifest_sha256', '128'), 123)
        self.reject(('provenance', 'producer_context_sha256'), {'sha256': placeholder('private')})

    def test_runtime_versions_and_configuration(self):
        path = ('provenance', 'runtime')
        for suffix, val in [(('packages', 'torch'), '2.10.0+cuda'), (('threads',), 1), (('interop_threads',), 4),
            (('deterministic_algorithms',), 1), (('device',), 'cuda'), (('attention',), 'flash'),
            (('fenv', 'ftz'), True), (('fenv', 'sse_round'), False),
            (('settings_basis', 'interop_threads'), 'OBSERVED'),
            (('blas_environment', 'OMP_NUM_THREADS'), 4), (('runtime_files_verification',), 'DIRECT_FILE_REHASH')]:
            self.reject(path + suffix, val)

    def test_compiler_projection_never_accepts_raw_banner(self):
        path = ('provenance', 'runtime', 'compiler')
        for val in ([13, 2], [True, 2, 0], [-1, 2, 0], [100, 2, 0], ['13', '2', '0'], [13.0, 2, 0]):
            self.reject(path + ('version_components',), val)
        self.reject(path + ('family',), '/private/g++')
        self.reject(path + ('version_text_sha256',), 'g++ (private host compiler) 13.2.0')

    def test_all_build_flags_and_compiler_bindings(self):
        path = ('provenance',)
        self.reject(path + ('combined_library', 'shared_m16_m128'), False)
        self.reject(path + ('combined_library', 'verification'), 'QUALIFIED_METADATA_ONLY')
        self.reject(path + ('combined_library', 'compiler_executable_sha256'), placeholder('wrong-compiler'))
        self.reject(path + ('combined_library', 'source_map_sha256'), placeholder('wrong-four-source-map'))
        self.reject(path + ('builds', '128', 'recipe_libraries', 'qk', 'compiler_executable_sha256'), placeholder('wrong-library-compiler'))
        self.reject(path + ('builds', '16', 'scalar_builds', 'sequential', 'flags'), ['-O3', '-ffast-math'])
        self.reject(path + ('builds', '128', 'recipe_libraries', 'qkv', 'flags'), list(S.RECIPE_FLAGS[:-1]))

    def test_source_model_recipe_driver_wheel_and_emitter_bindings(self):
        for path in [('identity', 'model', 'config_sha256'), ('identity', 'model', 'payload_ledger_sha256'),
                     ('identity', 'recipe_sources', 'native_gate'), ('identity', 'policy', 'numerical_contract_sha256'),
                     ('provenance', 'driver_sha256', '16'), ('provenance', 'driver_sha256', '128'),
                     ('provenance', 'wheel_lock_sha256'), ('provenance', 'emitter_sha256'),
                     ('provenance', 'raw_source_map_sha256')]:
            self.reject(path, placeholder('wrong-source-binding'))

    def test_source_input_count_paths_digests_and_pins(self):
        for operation in ('missing', 'extra', 'path', 'digest', 'pin'):
            source = dict(self.sources)
            key = next(k for k in source if k.startswith('synthetic_fixture_only/'))
            if operation == 'missing': del source[key]
            elif operation == 'extra': source['extra.py'] = placeholder('extra')
            elif operation == 'path': source['../private.py'] = source.pop(key)
            elif operation == 'digest': source[key] = True
            elif operation == 'pin': source[S.LEDGER] = placeholder('wrong-ledger')
            with self.subTest(operation=operation), self.assertRaises(S.ManifestError):
                S.validate_manifest(self.good, source, compile_sources=self.compile_sources)

    def test_policy_exact_tolerances_and_no_fp32_upgrade(self):
        for key, val in [('new_tolerances', True), ('assigned_official_gates', 28),
                         ('missing_stages', []), ('diagnostic_stages', []),
                         ('partially_observed_stages', []), ('official_reference', 'INDEPENDENT_SELF_CACHE')]:
            self.reject(('identity', 'policy', key), val)
        self.reject(('identity', 'policy', 'operator', 'max_abs'), 0.1)

    def test_complexity_cycles_and_large_scalars_fail_safely(self):
        value = copy.deepcopy(self.good)
        value['unknown'] = value
        with self.assertRaisesRegex(S.ManifestError, '^JSON_COMPLEXITY$'):
            S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)
        self.reject(('provenance', 'qualification_sha256'), 'x' * 257, reseal=False)
        self.reject(('provenance', 'qualification_sha256'), 2 ** 128, reseal=False)

    def test_validate_does_not_mutate_input_or_sources(self):
        value, sources = copy.deepcopy(self.good), dict(self.sources)
        before = S.canonical(value)
        S.validate_manifest(value, sources, compile_sources=self.compile_sources)
        self.assertEqual(S.canonical(value), before)
        self.assertEqual(sources, self.sources)

    def test_pinned_emitter_pure_helpers_independent_parity(self):
        # Execute only the reviewed stdlib module's definitions, never its
        # prepare/finalize/readers, production entry points or numerical code.
        source = Path(__file__).resolve().parent.parent / (
            'same_host_m128_replay_identity_20261017_freeze_cded2ae5/source/'
            'candidates/qwen2_resident_matrix/portable_same_host_m128_launch/replay_identity.py')
        raw = source.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), S.EMITTER_SHA)
        emitter = {'__name__': 'reviewed_offline_schema_helpers'}
        exec(compile(raw, 'sha256-pinned-stdlib-schema-helpers', 'exec'), emitter)
        for rows in (16, 128):
            self.assertEqual(S._shapes(rows), emitter['shapes'](rows))
            for name in S.STAGES:
                self.assertEqual(S._tensor(rows, name)['stored_shape'], emitter['export_shape'](rows, name))
            for name in S.FIELDS:
                self.assertEqual(S._capture_shape(rows, name), emitter['capture_shape'](rows, name))
            run = self.good['identity']['runs'][str(rows)]
            for table in (run['payload'], run['readonly'], run['native'], *run['scalar_raw'].values(),
                          run['sequential_exports'], run['full']['persisted_actual']):
                for item in table.values():
                    generated = emitter['descriptor'](item['file_sha256'], item['content_sha256'],
                        item['stored_shape'], item['logical_shape'], dtype=item['logical_dtype'],
                        encoding=item['storage_encoding'], mapping=item['canonical_mapping'],
                        origin=item['origin'])
                    self.assertEqual(generated, {key: item[key] for key in generated})
            snapshot = {'loaded_inputs': {name: {'bytes': item['bytes'], 'sha256': item['content_sha256']}
                for name, item in run['full']['loaded_providers'].items()}}
            generated = emitter['loaded_providers'](snapshot, run, rows)
            self.assertEqual(generated, run['full']['loaded_providers'])
            for name in ('cache_k', 'cache_v', 'repeat_k', 'repeat_v', 'x', 'cos', 'sin'):
                item = run['full']['actual_stages'][name]
                generated = emitter['derived_descriptor'](bytes(item['bytes']), item['logical_shape'],
                    recipe=item['reconstruction']['recipe'], source_ids=item['reconstruction']['source_tensors'])
                # Byte contents are fixture zeros, not model values. The emitter
                # is independently responsible for the public keys and types.
                S._match(generated, {key: S._run_schema(rows)['full']['actual_stages'][name][key] for key in generated})
        identity = dict(python='3.12.15', torch='2.10.0+cpu', numpy='2.3.5', transformers='4.40.1',
            device='cpu', attention='eager', model_revision=S.REVISION, forward_revision=S.FORWARD,
            installed_sources_verified_exact=True, runner_sha256=S.RUNNER_SHA,
            cache_utils_sha256=placeholder('cache'), mask_utils_sha256=placeholder('mask'),
            activations_sha256=placeholder('activations'), torch_build='SYNTHETIC BUILD', numpy_build='SYNTHETIC BUILD')
        observed = dict(fenv=dict(status='OBSERVED', x87_round=0, sse_round=0, ftz=False, daz=False),
            mkldnn_enabled=True, torch_commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
            blas_environment=dict(OPENBLAS_NUM_THREADS='4', MKL_NUM_THREADS='4', OMP_NUM_THREADS='4'),
            python_executable_sha256=placeholder('python'), runtime_libc_sha256={'libm.so.6': placeholder('m'), 'libc.so.6': placeholder('c')},
            compiler=dict(sha256=placeholder('compiler'), version='g++ (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0'), cpu={})
        generated = emitter['runtime_projection'](dict(runtime_identity=identity, runtime_observation=observed, dispatch={}))
        S._match(generated, S._manifest_schema(self.sources, compile_sources=self.compile_sources)['provenance']['runtime'])

    def test_compile_sources_is_required_keyword(self):
        with self.assertRaises(TypeError):
            S.validate_manifest(self.good, self.sources)
        with self.assertRaises(TypeError):
            S._manifest_schema(self.sources)
        with self.assertRaises(TypeError):
            S.validate_manifest(self.good, self.sources, self.compile_sources)
        with self.assertRaises(TypeError):
            S._manifest_schema(self.sources, self.compile_sources)

    def test_compile_sources_exact_four_keys(self):
        for operation in ('missing', 'extra', 'generated_service_instead', 'list', 'none'):
            inputs = dict(self.compile_sources)
            if operation == 'missing': del inputs[S.COMBINED_SOURCE_PATHS[0]]
            elif operation == 'extra': inputs['private/extra.cpp'] = placeholder('extra')
            elif operation == 'generated_service_instead':
                inputs[S.BASE + 'ffn_attention/matrix_service.py'] = inputs.pop(S.COMBINED_SOURCE_PATHS[0])
            elif operation == 'list': inputs = list(inputs.items())
            elif operation == 'none': inputs = None
            with self.subTest(operation=operation), self.assertRaisesRegex(S.ManifestError, '^COMPILE_SOURCE_SET$'):
                S.validate_manifest(self.good, self.sources, compile_sources=inputs)

    def test_compile_sources_digest_types(self):
        for invalid in (None, True, 1, 'A' * 64, 'g' * 64, '0' * 63, '/private/source.cpp', 'a' * 63 + '\n'):
            for path in S.COMBINED_SOURCE_PATHS:
                inputs = dict(self.compile_sources)
                inputs[path] = invalid
                with self.subTest(path=path, invalid=invalid), self.assertRaisesRegex(S.ManifestError, '^COMPILE_SOURCE_DIGEST$'):
                    S.validate_manifest(self.good, self.sources, compile_sources=inputs)

    def test_compile_sources_unchanged_three_match_raw(self):
        for path in S.COMBINED_SOURCE_PATHS[1:]:
            inputs = dict(self.compile_sources)
            inputs[path] = placeholder('changed-static-compile-input')
            with self.subTest(path=path), self.assertRaisesRegex(S.ManifestError, '^COMPILE_RAW_SOURCE_BINDING$'):
                S.validate_manifest(self.good, self.sources, compile_sources=inputs)

    def test_generated_source_map_never_falls_back_to_raw(self):
        raw = {path: self.sources[path] for path in S.COMBINED_SOURCE_PATHS}
        self.assertNotEqual(raw[S.COMBINED_SOURCE_PATHS[0]], self.compile_sources[S.COMBINED_SOURCE_PATHS[0]])
        self.assertEqual(self.good['provenance']['combined_library']['source_map_sha256'], S.identity_digest(self.compile_sources))
        with self.assertRaises(S.ManifestError):
            S.validate_manifest(self.good, self.sources, compile_sources=raw)
        value = copy.deepcopy(self.good)
        value['provenance']['combined_library']['source_map_sha256'] = S.identity_digest(raw)
        with self.assertRaises(S.ManifestError):
            S.validate_manifest(value, self.sources, compile_sources=self.compile_sources)

    def test_frozen_generated_contract_regression(self):
        # These are real authenticated source-contract bytes, but the resulting
        # public body is deliberately synthetic and is not run acceptance.
        root = Path(__file__).resolve().parent.parent / 'same_host_m128_replay_identity_20261017_freeze_cded2ae5/source'
        contract_bytes = (root / (S.BASE + 'portable_same_host_m128_launch/input-contract.json')).read_bytes()
        self.assertEqual(hashlib.sha256(contract_bytes).hexdigest(),
                         '2ac3f216a7e5566fc7dad84c4050502c8afd99d82d9d33e05625bc6f774f1e6c')
        sources = json.loads(contract_bytes)['inputs']
        tiny_path = S.BASE + 'portable_consumer_qualification/input-contract.json'
        tiny_bytes = (root / tiny_path).read_bytes()
        self.assertEqual(hashlib.sha256(tiny_bytes).hexdigest(), sources[tiny_path])
        tiny = json.loads(tiny_bytes)
        generated = {path: tiny['generated_sha256'][path] if path in tiny['generated_sha256'] else tiny['source_sha256'][path]
                     for path in S.COMBINED_SOURCE_PATHS}
        self.assertEqual(S.identity_digest(generated), '0e298008babe63514b05405190831b7cf265e6dc82956bef648f9dbbbff36db0')
        raw = {path: sources[path] for path in S.COMBINED_SOURCE_PATHS}
        self.assertEqual(S.identity_digest(raw), '802d3495d3c9d08fe7cda8245843e09e359898a00a088cbc7c341b49f91fd0eb')
        manifest = build_manifest(sources, compile_sources=generated)
        self.assertEqual(manifest['provenance']['combined_library']['source_map_sha256'], S.identity_digest(generated))
        S.validate_manifest(manifest, sources, compile_sources=generated)
        with self.assertRaises(S.ManifestError):
            S.validate_manifest(manifest, sources, compile_sources=raw)

    def test_compile_map_authentication_remains_callers_obligation(self):
        # Structural validation cannot authenticate a supplied digest. The
        # caller must bind it to the tiny contract and both composed maps.
        supplied = dict(self.compile_sources)
        supplied[S.COMBINED_SOURCE_PATHS[0]] = placeholder('different-but-untrusted-generated-map')
        value = build_manifest(self.sources, compile_sources=supplied)
        result = S.validate_manifest(value, self.sources, compile_sources=supplied)
        self.assertIs(result['provenance_authenticated_by_this_function'], False)
        self.assertIs(result['freeze_readiness_granted'], False)

    def test_compile_map_is_not_mutated(self):
        before = dict(self.compile_sources)
        S.validate_manifest(self.good, self.sources, compile_sources=self.compile_sources)
        self.assertEqual(self.compile_sources, before)

    def test_json_roundtrip_fixture_is_valid(self):
        S.validate_manifest(json.loads(S.canonical(self.good)), self.sources, compile_sources=self.compile_sources)


if __name__ == '__main__':
    unittest.main()
