"""Tiny synthetic metadata tests. No native imports, tensor loads or dispatch runs."""
import ast
import copy
import json
from pathlib import Path
import unittest

from . import dispatch_diagnostic as D

ROOT = Path(__file__).resolve().parents[3]


def row(impl='brg_matmul:avx512_core_bf16', shape='16x1536:1536x256', attrs=''):
    return ('onednn_verbose,v1,primitive,exec,cpu,matmul,' + impl +
        ',undef,src:bf16:a:blocked:ab::f0 wei:bf16:a:blocked:BA16a32b2a::f0 '
        'dst:bf16:a:blocked:ab::f0,' + attrs + ',,' + shape + ',0.0129395\n').encode()


GRAPH_HEADER = (b'onednn_verbose,v1,graph,info,template:operation,engine,partition_id,'
    b'partition_kind,op_names,data_formats,logical_tensors,fpmath_mode,implementation,backend,exec_time\n')


def manifest():
    return {'tensors': [{'local_name': name, 'shape': list(shape), 'dtype': 'BF16',
        'sha256': 'a' * 64, 'file': '/private/never-exported'} for name, shape in D.PAYLOAD_SHAPES.items()]}


def result(tokens=16):
    stage = {name: {key: char * 64 for key, char in zip(D.HASH_FIELDS, 'ab')} for name in D.STAGES}
    return {'tokens': tokens, 'carried': False, 'modes': {mode: {'phases': [{
        'phase': 0, 'past_tokens': 0, 'token_ids': list(range(tokens)),
        'position_ids': list(range(tokens)), 'stages': copy.deepcopy(stage)}]} for mode in ('bf16', 'fp32')}}


class DiagnosticTests(unittest.TestCase):
    def test_source_inventories_are_original_without_importing_numerics(self):
        tree = ast.parse((ROOT / 'scripts/qwen2_layer0_model_gate.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id == 'REQUIRED_STAGES' for t in n.targets)]
        self.assertEqual(set(D.STAGES), ast.literal_eval(nodes[0].value))
        pin = json.loads((ROOT / 'config/payload_pins/qwen2_layer0.json').read_text())
        self.assertEqual(D.PAYLOAD_SHAPES, {r['local_name']: r['shape'] for r in pin['tensors']})
        self.assertEqual((len(D.STAGES), len(D.PAYLOAD_SHAPES)), (29, 13))

    def test_exact_dispatch_and_consecutive_order_survive_json(self):
        raw = row() * 2 + row('gemm:jit:bf16') + row()
        value = D.parse_verbose(raw)
        self.assertEqual(value['status'], 'COMPLETE_DIAGNOSTIC')
        self.assertEqual([r['count'] for r in value['records']], [2, 1, 1])
        self.assertEqual([r['isa'] for r in value['records']],
                         ['avx512_core_bf16', 'unspecified', 'avx512_core_bf16'])
        self.assertTrue(all(r['role'] == 'QKV_KV' for r in value['records']))
        self.assertEqual(D.validate_verbose(json.loads(json.dumps(value))), value)
        self.assertNotIn('0.0129395', json.dumps(value))
        self.assertNotIn('1536', json.dumps(value))
        self.assertFalse(value['numerical_acceptance'])
        self.assertFalse(value['backend_order_proven'])

    def test_shapes_do_not_false_attribute_square_attention_or_hidden_projection(self):
        shapes = ('16x1536:1536x1536', '12x16x128:12x128x16', '12x16x16:12x16x128',
                  '12x128x128:12x128x128', '128x1536:1536x8960')
        self.assertEqual([D.parse_verbose(row(shape=s))['records'][0]['role'] for s in shapes],
                         ['DENSE_HIDDEN', 'QK', 'PV', 'ATTENTION_SQUARE', 'MLP'])

    def test_info_headers_are_counted_but_not_execution_evidence(self):
        info = (b'onednn_verbose,v1,info,oneDNN v3.7.1 (commit abcdef0)\n'
                b'onednn_verbose,v1,info,cpu,runtime:OpenMP,nthr:4\n'
                b'onednn_verbose,v1,primitive,info,template:operation,engine,primitive,implementation,prop_kind,memory_descriptors,attributes,auxiliary,problem_desc,exec_time\n')
        self.assertEqual(D.parse_verbose(info)['status'], 'NO_ONEDNN_EXECUTION_OBSERVED')
        report = D.parse_verbose(info + row())
        self.assertEqual((report['info_records'], report['exec_records']), (3, 1))
        self.assertEqual(report['status'], 'COMPLETE_DIAGNOSTIC')

    def test_exact_reviewed_graph_header_is_info_only(self):
        value = D.parse_verbose(GRAPH_HEADER)
        self.assertEqual(value['status'], 'NO_ONEDNN_EXECUTION_OBSERVED')
        self.assertEqual((value['info_records'], value['exec_records'], value['records']), (1, 0, []))
        value = D.parse_verbose(GRAPH_HEADER + row())
        self.assertEqual(value['status'], 'COMPLETE_DIAGNOSTIC')
        self.assertEqual((value['info_records'], value['exec_records']), (1, 1))
        self.assertNotIn('partition_id', json.dumps(value))
        for changed in (GRAPH_HEADER.replace(b'implementation,', b''),
                        GRAPH_HEADER.replace(b'implementation,', b'private_implementation,'),
                        GRAPH_HEADER.replace(b'exec_time\n', b'exec_time,PRIVATE\n')):
            value = D.parse_verbose(changed + row())
            self.assertEqual(value['status'], 'UNSUPPORTED')
            self.assertEqual(value['unsupported_records'], 1)
            self.assertEqual(value['unsupported_reasons']['information_header'], 1)
            self.assertNotIn('PRIVATE', json.dumps(value))
            self.assertNotIn('private_implementation', json.dumps(value))

    def test_exact_reviewed_sum_attribute_accepts_no_variants(self):
        for attrs in ('attr-post-ops:sum', 'attr-scratchpad:user attr-post-ops:sum'):
            value = D.parse_verbose(GRAPH_HEADER + row(attrs=attrs) * 3)
            self.assertEqual(value['status'], 'COMPLETE_DIAGNOSTIC')
            self.assertEqual((value['info_records'], value['exec_records']), (1, 3))
            self.assertEqual(value['unsupported_records'], 0)
            self.assertEqual(value['unsupported_reasons'], dict.fromkeys(D.UNSUPPORTED_REASONS, 0))
            self.assertNotIn('attr-post-ops', json.dumps(value))
            self.assertFalse(value['numerical_acceptance'])
            self.assertFalse(value['backend_order_proven'])
        for attrs in ('attr-post-ops:sum:1', 'attr-post-ops:sum_PRIVATE',
                      'attr-post-ops:sum attr-PRIVATE:secret', 'attr-bia_mask:2'):
            value = D.parse_verbose(row(attrs=attrs))
            self.assertEqual(value['status'], 'UNSUPPORTED')
            self.assertEqual(value['unsupported_reasons']['attributes'], 1)
            self.assertEqual(value['exec_records'], 0)
            self.assertNotIn(attrs, json.dumps(value))
            self.assertNotIn('PRIVATE', json.dumps(value))
        value = D.parse_verbose(row(attrs='attr-post-ops:sum').replace(b',,16x', b',bia_mask:2,16x'))
        self.assertEqual(value['status'], 'UNSUPPORTED')
        self.assertEqual(value['unsupported_reasons']['auxiliary'], 1)
        self.assertNotIn('bia_mask', json.dumps(value))

    def test_unsupported_reason_counters_are_fixed_and_first_failure_only(self):
        fixtures = {
            'verbose_version': row().replace(b',v1,', b',v9,'),
            'engine': row().replace(b',cpu,', b',PRIVATE,'),
            'primitive': row().replace(b',matmul,', b',PRIVATE,'),
            'implementation': row(impl='PRIVATE'),
            'prop_kind': row().replace(b',undef,', b',PRIVATE,'),
            'memory_descriptor': row().replace(b'BA16a32b2a', b'PRIVATE'),
            'attributes': row(attrs='PRIVATE'),
            'auxiliary': row().replace(b',,,', b',,PRIVATE,'),
            'information_header': GRAPH_HEADER.replace(b'implementation,', b'PRIVATE,'),
            'information_record': b'onednn_verbose,v1,info,PRIVATE\n',
            'unknown_operation': b'onednn_verbose,v1,PRIVATE,exec\n',
        }
        self.assertEqual(set(fixtures), set(D.UNSUPPORTED_REASONS))
        for reason, raw in fixtures.items():
            with self.subTest(reason=reason):
                value = D.parse_verbose(raw)
                self.assertEqual(value['status'], 'UNSUPPORTED')
                self.assertEqual(value['unsupported_records'], 1)
                self.assertEqual(value['unsupported_reasons'],
                    {key: int(key == reason) for key in D.UNSUPPORTED_REASONS})
                self.assertNotIn('PRIVATE', json.dumps(value))
        value = D.parse_verbose(b''.join(fixtures.values()))
        self.assertEqual(value['unsupported_records'], len(fixtures))
        self.assertEqual(value['unsupported_reasons'], dict.fromkeys(D.UNSUPPORTED_REASONS, 1))
        self.assertEqual(D.validate_verbose(json.loads(json.dumps(value))), value)
        value = D.parse_verbose(row(impl='PRIVATE', attrs='PRIVATE').replace(b',cpu,', b',PRIVATE,'))
        self.assertEqual(value['unsupported_records'], 1)
        self.assertEqual(value['unsupported_reasons']['engine'], 1)
        self.assertEqual(value['unsupported_reasons']['implementation'], 0)
        self.assertEqual(value['unsupported_reasons']['attributes'], 0)

    def test_unsupported_reason_schema_rejects_missing_unknown_and_forged_counts(self):
        baseline = D.parse_verbose(row(attrs='PRIVATE'))
        for mutate in (lambda v: v.pop('unsupported_reasons'),
                       lambda v: v.update(unsupported_reasons=[]),
                       lambda v: v['unsupported_reasons'].pop('attributes'),
                       lambda v: v['unsupported_reasons'].update(PRIVATE=0),
                       lambda v: v['unsupported_reasons'].update(attributes=True),
                       lambda v: v['unsupported_reasons'].update(attributes=1.0),
                       lambda v: v['unsupported_reasons'].update(attributes=-1),
                       lambda v: v['unsupported_reasons'].update(attributes=D.MAX_LINES + 1),
                       lambda v: v['unsupported_reasons'].update(attributes=0),
                       lambda v: v['unsupported_reasons'].update(engine=1)):
            changed = copy.deepcopy(baseline); mutate(changed)
            with self.assertRaises(ValueError): D.validate_verbose(changed)
        projected = D.validate_verbose(baseline)
        projected['unsupported_reasons']['attributes'] = 0
        self.assertEqual(baseline['unsupported_reasons']['attributes'], 1)

    def test_clean_empty_capture_is_only_an_explicit_absence_observation(self):
        value = D.parse_verbose(b'')
        self.assertEqual(value['status'], 'NO_ONEDNN_EXECUTION_OBSERVED')
        self.assertEqual(value['exec_records'], 0)
        self.assertEqual(value['records'], [])
        self.assertFalse(value['numerical_acceptance'])
        self.assertFalse(value['backend_order_proven'])
        self.assertEqual(D.validate_verbose(json.loads(json.dumps(value))), value)
        for field in ('numerical_acceptance', 'backend_order_proven'):
            changed = copy.deepcopy(value); changed[field] = True
            with self.assertRaises(ValueError): D.validate_verbose(changed)
        for raw, truncated in ((b'', True), (b'\n', False), (b'private', False)):
            self.assertEqual(D.parse_verbose(raw, truncated=truncated)['status'], 'INCOMPLETE')
        changed = copy.deepcopy(value); changed['status'] = 'COMPLETE_DIAGNOSTIC'
        with self.assertRaises(ValueError): D.validate_verbose(changed)

    def test_exact_comma_containing_isa_header(self):
        header = (b'onednn_verbose,v1,info,cpu,isa:Intel AVX-512 with float16, '
                  b'Intel DL Boost and bfloat16 support and Intel AMX with bfloat16 and 8-bit integer support\n')
        value = D.parse_verbose(header + row())
        self.assertEqual(value['status'], 'COMPLETE_DIAGNOSTIC')
        self.assertEqual(value['info_records'], 1)
        self.assertNotIn('Intel', json.dumps(value))
        self.assertEqual(D.parse_verbose(header[:-1] + b',PRIVATE\n' + row())['status'], 'UNSUPPORTED')

    def test_pinned_amx_fp16_isa_and_sequential_runtime_info(self):
        header = (b'onednn_verbose,v1,info,cpu,isa:Intel AVX-512 with float16, '
                  b'Intel DL Boost and bfloat16 support and Intel AMX with bfloat16, '
                  b'float16 and 8-bit integer support\n')
        sequential = b'onednn_verbose,v1,info,cpu,runtime:sequential,nthr:1\n'
        value = D.parse_verbose(header + sequential + row())
        self.assertEqual(value['status'], 'COMPLETE_DIAGNOSTIC')
        self.assertEqual((value['info_records'], value['exec_records']), (2, 1))
        self.assertEqual(value['records'][0]['isa'], 'avx512_core_bf16')
        self.assertNotIn('Intel', json.dumps(value))
        self.assertNotIn('sequential', json.dumps(value))
        self.assertFalse(D.has_only_informational_unknowns(value))
        for changed in (header.replace(b'bfloat16, float16', b'bfloat16, PRIVATE'),
                        sequential.replace(b'sequential', b'SEQ')):
            value = D.parse_verbose(changed)
            self.assertEqual(value['status'], 'UNSUPPORTED')
            self.assertTrue(D.has_only_informational_unknowns(value))
            self.assertNotIn('PRIVATE', json.dumps(value))

    def test_informational_unknown_subtypes_are_fixed_and_not_execution_evidence(self):
        fixtures = {
            'version': b'oneDNN vPRIVATE (commit PRIVATE)',
            'cpu_runtime': b'cpu,runtime:PRIVATE,nthr:4',
            'cpu_isa': b'cpu,isa:PRIVATE, PRIVATE',
            'gpu_runtime': b'gpu,runtime:PRIVATE',
            'graph_backend': b'graph,backend,PRIVATE',
            'other': b'PRIVATE',
        }
        self.assertEqual(set(fixtures), set(D.UNSUPPORTED_INFO_SUBTYPES))
        for subtype, body in fixtures.items():
            raw = b'onednn_verbose,v1,info,' + body + b'\n'
            for capture in (raw, raw + row()):
                with self.subTest(subtype=subtype, execution=bool(capture != raw)):
                    value = D.parse_verbose(capture)
                    self.assertEqual(value['status'], 'UNSUPPORTED')
                    self.assertTrue(D.has_only_informational_unknowns(value))
                    self.assertEqual(value['unsupported_reasons']['information_record'], 1)
                    self.assertEqual(value['unsupported_info_subtypes'],
                        {key: int(key == subtype) for key in D.UNSUPPORTED_INFO_SUBTYPES})
                    self.assertFalse(value['numerical_acceptance'])
                    self.assertFalse(value['backend_order_proven'])
                    self.assertNotIn('PRIVATE', json.dumps(value))
        value = D.parse_verbose(b''.join(b'onednn_verbose,v1,info,' + body + b'\n'
            for body in fixtures.values()))
        self.assertTrue(D.has_only_informational_unknowns(value))
        self.assertEqual(value['exec_records'], 0)
        self.assertEqual(value['unsupported_info_subtypes'], dict.fromkeys(D.UNSUPPORTED_INFO_SUBTYPES, 1))
        self.assertEqual(D.validate_verbose(json.loads(json.dumps(value))), value)

    def test_only_info_helper_rejects_headers_operations_versions_and_execution_unknowns(self):
        info = b'onednn_verbose,v1,info,cpu,isa:PRIVATE\n'
        blockers = (
            GRAPH_HEADER.replace(b'implementation,', b'PRIVATE,'),
            b'onednn_verbose,v1,primitive,info,PRIVATE\n',
            b'onednn_verbose,v1,graph,exec,PRIVATE\n',
            b'onednn_verbose,v1,primitive,create,PRIVATE\n',
            b'onednn_verbose,v1,common,info,PRIVATE\n',
            b'onednn_verbose,v1,error,PRIVATE\n',
            info.replace(b',v1,', b',v2,'),
            row(impl='PRIVATE'), row(attrs='PRIVATE'),
            row().replace(b',,,', b',,bia_mask:2,'),
        )
        for blocker in blockers:
            for capture in (blocker, info + blocker, blocker + info):
                value = D.parse_verbose(row() + capture)
                self.assertEqual(value['status'], 'UNSUPPORTED')
                self.assertFalse(D.has_only_informational_unknowns(value))
                self.assertNotIn('PRIVATE', json.dumps(value))
        for raw in (b'onednn_verbose,v1,graph,exec,PRIVATE\n',
                    b'onednn_verbose,v1,primitive,create,PRIVATE\n',
                    b'onednn_verbose,v1,common,info,PRIVATE\n'):
            value = D.parse_verbose(raw)
            self.assertEqual(value['unsupported_reasons']['unknown_operation'], 1)
            self.assertEqual(value['unsupported_reasons']['information_record'], 0)
            self.assertEqual(value['unsupported_info_subtypes'], dict.fromkeys(D.UNSUPPORTED_INFO_SUBTYPES, 0))
        for capture in (b'', row(), GRAPH_HEADER):
            self.assertFalse(D.has_only_informational_unknowns(D.parse_verbose(capture)))

    def test_info_helper_never_qualifies_malformed_or_truncated_records(self):
        info = b'onednn_verbose,v1,info,cpu,isa:PRIVATE\n'
        malformed = (b'onednn_verbose,v1,info,\n', b'onednn_verbose,v1,info, \n',
                     b'onednn_verbose,v1,info,PRIVATE,\n',
                     b'onednn_verbose,v1,info,PRIVATE\x00\n',
                     b'private,v1,info,PRIVATE\n', b'onednn_verbose,v1,info,\xff\n',
                     row().replace(b'0.0129395', b'NaN'))
        for raw in malformed:
            value = D.parse_verbose(info + row() + raw)
            self.assertEqual(value['status'], 'INCOMPLETE')
            self.assertGreater(value['malformed_records'], 0)
            self.assertFalse(D.has_only_informational_unknowns(value))
        for raw, flag in ((info[:-1], False), (info + row(), True)):
            value = D.parse_verbose(raw, truncated=flag)
            self.assertEqual(value['status'], 'INCOMPLETE')
            self.assertFalse(D.has_only_informational_unknowns(value))

    def test_info_subtype_schema_rejects_aliases_unknown_keys_and_forged_totals(self):
        baseline = D.parse_verbose(b'onednn_verbose,v1,info,cpu,isa:PRIVATE\n')
        for mutate in (lambda v: v.pop('unsupported_info_subtypes'),
                       lambda v: v.update(unsupported_info_subtypes=[]),
                       lambda v: v['unsupported_info_subtypes'].pop('other'),
                       lambda v: v['unsupported_info_subtypes'].update(PRIVATE=0),
                       lambda v: v['unsupported_info_subtypes'].update(cpu_isa=True),
                       lambda v: v['unsupported_info_subtypes'].update(cpu_isa=1.0),
                       lambda v: v['unsupported_info_subtypes'].update(cpu_isa=-1),
                       lambda v: v['unsupported_info_subtypes'].update(cpu_isa=D.MAX_LINES + 1),
                       lambda v: v['unsupported_info_subtypes'].update(cpu_isa=0),
                       lambda v: v['unsupported_info_subtypes'].update(other=1),
                       lambda v: v['unsupported_reasons'].update(information_record=0, unknown_operation=1)):
            changed = copy.deepcopy(baseline); mutate(changed)
            with self.assertRaises(ValueError): D.validate_verbose(changed)
            with self.assertRaises(ValueError): D.has_only_informational_unknowns(changed)
        projected = D.validate_verbose(baseline)
        projected['unsupported_info_subtypes']['cpu_isa'] = 0
        self.assertEqual(baseline['unsupported_info_subtypes']['cpu_isa'], 1)

    def test_unknowns_are_explicit_and_never_echoed(self):
        unknown = (
            row('/private/secret'), row().replace(b'v1,', b'v9,'),
            row().replace(b'BA16a32b2a', b'PRIVATE_LAYOUT'),
            row().replace(b',,,', b',secret-attribute,,'),
            b'onednn_verbose,v1,info,PRIVATE_SECRET\n')
        for raw in unknown:
            with self.subTest(raw=raw[:25]):
                report = D.parse_verbose(raw)
                self.assertEqual(report['status'], 'UNSUPPORTED')
                self.assertEqual(report['unsupported_records'], 1)
                text = json.dumps(report)
                for marker in ('private', 'secret', 'PRIVATE', 'v9'):
                    self.assertNotIn(marker, text)

    def test_malformed_nonfinite_and_truncation_never_complete(self):
        inputs = (b'private payload text\n', b'\xff\n', row()[:-1],
            row().replace(b'0.0129395', b'1e999'), row().replace(b'0.0129395', b'NaN'),
            row().replace(b'16x1536', b'0x1536'), b'x' * (D.MAX_LINE_BYTES + 1) + b'\n',
            b'x' * (D.MAX_LOG_BYTES + 1))
        for raw in inputs:
            self.assertEqual(D.parse_verbose(raw)['status'], 'INCOMPLETE')
        self.assertEqual(D.parse_verbose(row(), truncated=True)['status'], 'INCOMPLETE')
        for raw, flag in ((bytearray(row()), False), (row(), 1)):
            with self.assertRaises(ValueError): D.parse_verbose(raw, truncated=flag)

    def test_group_record_line_bounds_fail_closed(self):
        raw = b''.join(row('gemm:jit:bf16' if i % 2 else 'gemm:jit') for i in range(D.MAX_GROUPS + 1))
        report = D.parse_verbose(raw)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(len(report['records']), D.MAX_GROUPS)
        self.assertTrue(report['truncated'])
        self.assertEqual(D.parse_verbose(row() * (D.MAX_RECORDS + 1))['status'], 'INCOMPLETE')
        self.assertEqual(D.parse_verbose(b'\n' * (D.MAX_LINES + 1))['lines_observed'], D.MAX_LINES)

    def test_verbose_validator_rejects_type_aliases_and_forged_complete(self):
        baseline = D.parse_verbose(row())
        mutations = [('schema', True), ('exec_records', True), ('numerical_acceptance', 0),
                     ('backend_order_proven', 0), ('truncated', 0), ('status', 'PASS'), ('extra', 'secret')]
        for key, value in mutations:
            report = copy.deepcopy(baseline); report[key] = value
            with self.assertRaises(ValueError): D.validate_verbose(report)
        report = D.parse_verbose(row(), truncated=True); report['status'] = 'COMPLETE_DIAGNOSTIC'
        with self.assertRaises(ValueError): D.validate_verbose(report)
        report = copy.deepcopy(baseline); report['records'][0]['implementation'] = 'private-path'
        with self.assertRaises(ValueError): D.validate_verbose(report)

    def test_cpu_flags_intersect_every_processor_without_changing_eligibility(self):
        all_flags = ' '.join(D.FLAGS)
        raw = (f'processor : 0\nflags : {all_flags}\nvendor_id : PRIVATE\n\n'
               f'processor : 1\nflags : {" ".join(D.REQUIRED_FLAGS)}\n').encode()
        value = D.cpu_features(raw)
        self.assertEqual(value['processor_records'], 2)
        self.assertTrue(all(value['flags'][f] for f in D.REQUIRED_FLAGS))
        self.assertTrue(all(not value['flags'][f] for f in D.OPTIONAL_FLAGS))
        self.assertNotIn('eligible', value)
        self.assertNotIn('PRIVATE', json.dumps(value))
        self.assertEqual(D.validate_cpu_features(json.loads(json.dumps(value))), value)
        for bad in (b'', b'processor:0\n', b'processor:0\nflags:avx2 avx2\n',
                    b'processor:0\nflags:avx2\n\nprocessor:0\nflags:avx2\n',
                    b'processor:true\nflags:avx2\n', b'\xff', b'x' * (D.CPU_MAX_BYTES + 1)):
            with self.assertRaises(ValueError): D.cpu_features(bad)
        for key in ('schema', 'processor_records'):
            changed = copy.deepcopy(value); changed[key] = True
            with self.assertRaises(ValueError): D.validate_cpu_features(changed)
        value['flags']['avx2'] = 0
        with self.assertRaises(ValueError): D.validate_cpu_features(value)

    def test_payload_projection_exact_names_geometry_and_hashes(self):
        fixture = manifest(); value = D.payload_hashes(fixture)
        self.assertEqual(len(value), 13)
        self.assertNotIn('/private/', json.dumps(value))
        fixture['tensors'][0]['file'] = 'different-private-path'
        self.assertEqual(D.payload_hashes(fixture), value)
        for mutate in (lambda v: v['tensors'].pop(),
                       lambda v: v['tensors'].append(copy.deepcopy(v['tensors'][0])),
                       lambda v: v['tensors'][0].update(local_name='foreign'),
                       lambda v: v['tensors'][0].update(shape=[True, 1536]),
                       lambda v: v['tensors'][0].update(sha256='A' * 64)):
            fixture = manifest(); mutate(fixture)
            with self.assertRaises(ValueError): D.payload_hashes(fixture)
        value['extra'] = 'a' * 64
        with self.assertRaises(ValueError): D.validate_payload_hashes(value)

    def test_stage_hashes_exact_modes_29_names_and_original_digest_fields(self):
        for tokens in (16, 128):
            fixture = result(tokens)
            fixture['modes']['bf16']['phases'][0]['stages']['q']['native_file'] = '/private/payload'
            value = D.stage_hashes(fixture, tokens=tokens)
            self.assertEqual(len(value['bf16']), 29)
            self.assertEqual(set(value['bf16']['q']), set(D.HASH_FIELDS))
            self.assertNotIn('/private/', json.dumps(value))
            self.assertEqual(D.validate_stage_hashes(json.loads(json.dumps(value))), value)
        for mutate in (lambda v: v.update(tokens=True), lambda v: v.update(carried=0),
                       lambda v: v['modes']['bf16']['phases'][0].update(phase=False),
                       lambda v: v['modes']['bf16']['phases'][0]['token_ids'].__setitem__(0, False),
                       lambda v: v['modes']['bf16']['phases'][0]['stages'].pop('q'),
                       lambda v: v['modes']['bf16']['phases'][0]['stages']['q'].update(actual_f32_sha256=True)):
            fixture = result(); mutate(fixture)
            with self.assertRaises(ValueError): D.stage_hashes(fixture, tokens=16)
        value = D.stage_hashes(result(), tokens=16); value['bf16']['q']['extra'] = 'a' * 64
        with self.assertRaises(ValueError): D.validate_stage_hashes(value)

    def test_helpers_import_only_stdlib_and_do_not_execute_numerics(self):
        tree = ast.parse(Path(D.__file__).read_text())
        imports = [node.module if isinstance(node, ast.ImportFrom) else alias.name
                   for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in (node.names if isinstance(node, ast.Import) else [None])]
        self.assertEqual(set(imports), {'math', 're'})


if __name__ == '__main__':
    unittest.main()
