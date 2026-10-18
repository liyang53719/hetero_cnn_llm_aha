"""Read-only M128 identity check: hash source buffers, parse JSON, run no producer."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDENTITY_BYTES = 14530
IDENTITY_SHA256 = 'f5fd835b06cf76b28c9dcc22db6eb2f919de1315420fc54ff23033c2b3fe1d98'
COMMIT = 'b8ca25fa71e5b68cddbf0dd8eabf3dc787688f65'
TREE = '570f2e6724ae71445d78ab00b17bd5da5f31f4b9'
SOURCE_PATHS = (
    'config/payload_pins/qwen2_layer0.json',
    'config/upstream/weight_headers/qwen2_1p5b/manifest.json',
    'scripts/qwen2_layer0_payload.py',
    'candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py',
    'candidates/qwen2_resident_matrix/ffn_public/check_fullgraph_numeric.py',
    'candidates/qwen2_resident_matrix/ffn_public/fullgraph_numerical_receipt.json',
    'development_snapshots/canonical_host_metadata_source_20261018/EXPECTED_LAYOUT.json',
)
PROVIDERS = frozenset(('bk', 'bq', 'bv', 'gamma0', 'gamma1', 'rope',
                       'wd', 'wg', 'wk', 'wo', 'wq', 'wu', 'wv', 'x'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    # Git's object framing is independently recomputed; no Git process is run.
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('nonfinite JSON constant')

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def relative(name):
    require(isinstance(name, str) and name and '\\' not in name
            and not name.startswith('/') and all(p not in ('', '.', '..')
            for p in name.split('/')), 'unsafe relative source path')
    return Path(name)


def read_exact(path, size):
    require(type(size) is int and 0 < size <= 131072, 'invalid bounded source size')
    with path.open('rb') as stream:
        raw = stream.read(size + 1)
    require(len(raw) == size, 'source length differs')
    return raw


def identity_from_bytes(raw):
    require(len(raw) == IDENTITY_BYTES and sha(raw) == IDENTITY_SHA256,
            'frozen identity bytes differ')
    identity = parse_json(raw)
    require(identity['schema'] == 1 and identity['repository_commit'] == COMMIT
            and identity['repository_tree'] == TREE, 'identity provenance differs')
    require(tuple(r['path'] for r in identity['source_files']) == SOURCE_PATHS,
            'source inventory differs')
    return identity


def load_identity():
    return identity_from_bytes(read_exact(HERE / 'INPUT_IDENTITY.json', IDENTITY_BYTES))


def load_sources(repository, identity):
    root = Path(repository).resolve(strict=True)
    require(root.is_dir(), 'repository is not a directory')
    result = {}
    require(tuple(r['path'] for r in identity['source_files']) == SOURCE_PATHS,
            'source inventory differs')
    for entry in identity['source_files']:
        name = entry['path']
        path = root / relative(name)
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                'source path escapes repository or is a symlink')
        raw = read_exact(path, entry['bytes'])
        require(sha(raw) == entry['sha256'], 'source SHA256 differs: ' + name)
        require(git_blob(raw) == entry['git_blob'], 'source Git blob differs: ' + name)
        result[name] = raw
    return result


def derive_projection(sources):
    # Parse the exact buffers checked by load_sources; never reopen or import them.
    pin = parse_json(sources[SOURCE_PATHS[0]])
    upstream = parse_json(sources[SOURCE_PATHS[1]])
    receipt = parse_json(sources[SOURCE_PATHS[5]])
    layout = parse_json(sources[SOURCE_PATHS[6]])
    require(pin['model_id'] == upstream['model_id'] == receipt['model']
            == 'Qwen/Qwen2-1.5B-Instruct', 'model identity differs')
    require(pin['revision'] == upstream['revision'] == receipt['revision']
            == 'ba1cf1846d7df0a0591d6c00649f57e798519da8', 'model revision differs')
    require(type(pin['layer_id']) is int and pin['layer_id'] == receipt['layer'] == 0,
            'layer identity differs')
    cases = [c for c in receipt['cases'] if type(c['rows']) is int and c['rows'] == 128]
    require(len(cases) == 1, 'unique M128 case required')
    case = cases[0]
    allocations = [a for a in layout['allocations'] if a['readonly'] is True]
    require(len(allocations) == 14, 'readonly allocation count differs')
    alloc = {a['name']: a for a in allocations}
    require(len(alloc) == 14 and set(alloc) == set(case['loaded_inputs']) == PROVIDERS,
            'provider inventory differs')
    for name, value in case['loaded_inputs'].items():
        require(type(value['bytes']) is int and type(alloc[name]['bytes']) is int
                and value['bytes'] == alloc[name]['bytes'], 'provider size differs: ' + name)
    require(layout['rows'] == case['rows'] == 128 and layout['epoch'] == 7
            and layout['relocate'] == 0, 'fixed M128 layout differs')
    for key, target in (('command', 'commands'), ('descriptor', 'descriptors')):
        require(json_bytes(case['public_metadata'][key]) == json_bytes(layout['tables'][target]),
                'public table identity differs: ' + key)
    original = receipt['original_input']
    require(original['token_ids'] == original['positions'] == list(range(128))
            and original['rope_theta'] == 1000000.0 and original['intermediate_preloads'] == 0
            and original['rope_table_recipe'] == 'canonical_cpp_initialize_double_libm_then_FP32'
            and original['input_x_sha256'] == case['loaded_inputs']['x']['sha256'],
            'original input recipe differs')
    tensors = pin['tensors']
    require(len(tensors) == len({t['local_name'] for t in tensors}) == 13,
            'raw tensor inventory differs')
    require(all(t['dtype'] == 'BF16' for t in tensors)
            and sum(t['bytes'] for t in tensors) == pin['payload_bytes'] == 94382080,
            'raw tensor identity extent differs')
    provider_bytes = sum(v['bytes'] for v in case['loaded_inputs'].values())
    require(provider_bytes == 94916608 and provider_bytes + sum(t['bytes'] for t in
            layout['tables'].values()) == layout['payload_layout_bytes'] == 94920448,
            'total input extent differs')
    return dict(model_id=pin['model_id'], revision=pin['revision'], layer_id=pin['layer_id'],
        rows=128, epoch=layout['epoch'], relocate=layout['relocate'], shape=layout['shape'],
        original_input={k: original[k] for k in ('token_ids', 'positions', 'rope_theta',
            'rope_table_recipe', 'input_x_sha256', 'intermediate_preloads')},
        raw_tensors=[{k: t[k] for k in ('name', 'local_name', 'dtype', 'shape', 'bytes', 'sha256')}
                     for t in tensors],
        providers=[dict(name=n, base=alloc[n]['base'], shape=alloc[n]['shape'],
            descriptor_dtype=alloc[n]['descriptor_dtype'], bytes=d['bytes'], sha256=d['sha256'])
            for n, d in sorted(case['loaded_inputs'].items())],
        tables=layout['tables'], provider_payload_bytes=provider_bytes,
        payload_with_tables_bytes=layout['payload_layout_bytes'])


def verify_projection(identity, sources):
    actual = derive_projection(sources)
    # Canonical JSON comparison distinguishes booleans from integer sizes.
    require(json_bytes(identity['projection']) == json_bytes(actual),
            'frozen provider projection differs')
    return actual


def verify(repository):
    identity = load_identity()
    sources = load_sources(repository, identity)
    projection = verify_projection(identity, sources)
    return dict(status='PASS_SOURCE_INPUT_IDENTITIES_ONLY', schema=1,
        identity_sha256=IDENTITY_SHA256, source_files_checked=len(sources),
        raw_tensor_identities=13, provider_identities=len(projection['providers']),
        provider_payload_bytes=projection['provider_payload_bytes'],
        payload_with_tables_bytes=projection['payload_with_tables_bytes'],
        source_buffers_hashed_and_parsed_same=True, project_sources_imported=False,
        producer_executed=False, payload_bytes_read=0, reference_payloads_read=0,
        historical_stream_framing_recovered=False, launch_admission=False,
        whole_repository_identity_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo), sort_keys=True))


if __name__ == '__main__':
    main()
