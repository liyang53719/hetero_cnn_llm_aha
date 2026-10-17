"""SYNTHETIC PUBLIC-SCHEMA FIXTURES ONLY. Never numerical/CI acceptance evidence.

Every unconstrained digest starts as a distinct SHA256 of a fixture label and
JSON position. Only required public equalities merge those placeholder hashes.
Pinned source/payload hashes are genuine constants; no private tensor bytes,
actual run receipts, compiler objects, model evaluation or native code is used.
The shape fixture is generated from the reviewed copied schema. Independent
expected-count assertions and targeted corruption tests guard that schema.
"""
import copy
import hashlib
import identity_schema as S


def placeholder(label):
    return hashlib.sha256(('SYNTHETIC-NO-NUMERICAL-EVIDENCE:' + label).encode('ascii')).hexdigest()


def synthetic_sources():
    """464 structural source entries; deliberately not an authentic source map."""
    result = {path: placeholder('source:' + path) for path in (
        *S.RECIPE_SOURCES.values(), *S.COMBINED_SOURCE_PATHS,
        S.BASE + 'portable_official_producer/driver.py',
        S.BASE + 'portable_official_producer_m128/driver.py',
        S.BASE + 'portable_official_producer_launch/wheel-lock.json')}
    result.update({S.LEDGER: S.LEDGER_SHA, S.CONFIG: S.CONFIG_SHA,
        'spec/numerical_contract.md': S.POLICY_SHA,
        S.BASE + 'portable_same_host_m128_launch/replay_identity.py': S.EMITTER_SHA})
    for index in range(464 - len(result)):
        key = f'synthetic_fixture_only/source_{index:03d}.py'
        result[key] = placeholder(key)
    return result


def _materialize(schema, path='manifest'):
    if isinstance(schema, S._Rule):
        if schema.kind == 'sha256':
            return placeholder(path)
        if schema.kind == 'commit':
            return placeholder(path)[:40]
        if schema.kind == 'run_id':
            return '123456789'
        if schema.kind == 'version':
            return 13 if path.endswith('[0]') else 2 if path.endswith('[1]') else 0
        if schema.kind == 'bool':
            return False  # Auxiliary failures must not become assigned gates.
        raise ValueError('UNKNOWN_FIXTURE_RULE')
    if type(schema) is dict:
        return {key: _materialize(value, path + '.' + key) for key, value in schema.items()}
    if type(schema) is list:
        return [_materialize(value, path + f'[{index}]') for index, value in enumerate(schema)]
    return schema


def seal(value):
    value['identity_sha256'] = S.identity_digest(value['identity'])
    return value


# Fixture-only input copied from the reviewed tiny/generated contract. This is
# not authentication; production callers must independently derive this map.
SYNTHETIC_GENERATED_MATRIX_SHA = '1ddf017ffda70af19a70385cfffe1d5a405113f27d73378410a7fa2575bcfa25'


def synthetic_compile_sources(source_inputs=None):
    """Explicit synthetic compile map; three raw inputs plus generated matrix."""
    sources = synthetic_sources() if source_inputs is None else source_inputs
    result = {path: sources[path] for path in S.COMBINED_SOURCE_PATHS}
    result[S.COMBINED_SOURCE_PATHS[0]] = SYNTHETIC_GENERATED_MATRIX_SHA
    return result


def build_manifest(source_inputs=None, compile_sources=None):
    """Return a fully linked synthetic body; supplying sources does not authenticate it."""
    sources = synthetic_sources() if source_inputs is None else source_inputs
    compiles = synthetic_compile_sources(sources) if compile_sources is None else compile_sources
    value = _materialize(S._manifest_schema(sources, compile_sources=compiles))
    for run in value['identity']['runs'].values():
        full = run['full']
        tables = (run['payload'], run['readonly'], run['native'], *run['scalar_raw'].values(),
                  run['sequential_exports'], full['persisted_actual'])
        for table in tables:
            for item in table.values():
                if item['canonical_mapping'] != 'TOKEN_HEAD_BYTE_PERMUTATION':
                    item['content_sha256'] = item['file_sha256']
        for name in S.WIDTHS:
            actual = full['persisted_actual'][name]
            reduced = run['scalar_raw']['reduced'][name]
            reduced['file_sha256'] = actual['file_sha256']
            reduced['content_sha256'] = actual['content_sha256']
        reduced_silu = run['scalar_raw']['reduced']['silu']
        reduced_silu['file_sha256'] = reduced_silu['content_sha256'] = full['persisted_actual']['silu']['content_sha256']
        for name in (*S.WIDTHS, 'silu'):
            full['actual_stages'][name] = copy.deepcopy(full['persisted_actual'][name])
        full['actual_stages']['x']['content_sha256'] = run['readonly']['input_x']['content_sha256']
        for cap in full['attention_captures'].values():
            for part in ('raw', 'presence', 'frequency'):
                cap[part]['content_sha256'] = cap[part]['file_sha256']
            if cap['coverage'] == 'COMPLETE':
                cap['present_content_sha256'] = cap['raw']['content_sha256']
        for stage in full['actual_stages'].values():
            if 'capture_field' in stage:
                cap = full['attention_captures'][stage['capture_field']]
                for key in ('file_sha256', 'content_sha256'):
                    stage[key] = cap['raw'][key]
                stage['present_content_sha256'] = cap['present_content_sha256']
        for table in (*full['gate_bindings'].values(), full['fixed_arithmetic_bindings']):
            for gate in table.values():
                actual = S._resolve(run, gate['actual_tensor'])
                reference = S._resolve(run, gate['reference_tensor'])
                mapping = gate['comparison_mapping']
                if mapping == 'STORED_C_ORDER':
                    gate['actual_comparison_sha256'] = actual['file_sha256']
                    gate['reference_comparison_sha256'] = reference['file_sha256']
                else:
                    gate['actual_comparison_sha256'] = actual.get('present_content_sha256', actual['content_sha256'])
                    if mapping == 'LOGICAL_C_ORDER':
                        gate['reference_comparison_sha256'] = reference['content_sha256']
                if 'qualified_bit_exact' in gate:
                    gate['reference_comparison_sha256'] = gate['actual_comparison_sha256']
    compiler = value['provenance']['runtime']['compiler']['executable_sha256']
    value['provenance']['combined_library']['compiler_executable_sha256'] = compiler
    for build in value['provenance']['builds'].values():
        for library in build['recipe_libraries'].values():
            library['compiler_executable_sha256'] = compiler
    return seal(value)
