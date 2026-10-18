"""SOURCE-only fixed canonical16 binding check. No C++ execution or payload reads."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN_BYTES = 2174
PIN_SHA256 = '07cd317377766e169c992fdc8003753d18d83477a1dfc93ac71a2f84dbd20b56'
SOURCE_COMMIT = '9f1ca820c6d2ca241eea9bbd38457f60849994b2'
PATHS = (
    'development_snapshots/canonical_payload_identity_source_20261018/INPUT_IDENTITY.json',
    'development_snapshots/canonical_host_metadata_source_20261018/EXPECTED_LAYOUT.json',
    'development_snapshots/canonical_same_ram_source_20261018/initialization_ram.hpp',
)
ORDER = ('commands', 'descriptors', 'wq', 'wk', 'wv', 'wo', 'wg', 'wu', 'wd',
         'gamma0', 'gamma1', 'bq', 'bk', 'bv', 'rope', 'x')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def parse(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, 'duplicate JSON key')
            result[name] = value
        return result
    def bad_constant(value):
        raise ValueError('nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=bad_constant)


def checked_bytes(path, expected):
    size = expected['bytes']
    require(type(size) is int and 0 < size <= 131072, 'bounded source extent required')
    with path.open('rb') as source:
        raw = source.read(size + 1)
    require(len(raw) == size and sha(raw) == expected['sha256'], 'source bytes/hash differ')
    if 'git_blob' in expected:
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(blob == expected['git_blob'], 'Git blob identity differs')
    return raw


def relative(name):
    require(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
            and all(p not in ('', '.', '..') for p in name.split('/')), 'unsafe source path')
    return Path(name)


def load(repository):
    pin = parse(checked_bytes(HERE / 'SOURCE_PIN.json', dict(bytes=PIN_BYTES, sha256=PIN_SHA256)))
    require(pin['repository_commit'] == SOURCE_COMMIT
            and tuple(x['path'] for x in pin['repository_source_files']) == PATHS,
            'fixed source pin differs')
    root = Path(repository).resolve(strict=True)
    sources = {}
    for entry in pin['repository_source_files']:
        path = root / relative(entry['path'])
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                'source symlink or path escape')
        sources[entry['path']] = checked_bytes(path, entry)
    dependencies = {name: checked_bytes(HERE / relative(name), expected)
                    for name, expected in pin['unchanged_dependencies'].items()}
    require(dependencies['initialization_ram.hpp'] == sources[PATHS[2]],
            'copied RAM differs from published source')
    # These are the very same source buffers whose hashes were checked above.
    return parse(sources[PATHS[0]]), parse(sources[PATHS[1]])


def integer(value, positive=False):
    return type(value) is int and (value > 0 if positive else value >= 0) and value < 1 << 64


def derive(identity, layout):
    p = identity['projection']
    require((p['rows'], p['epoch'], p['relocate']) == (128, 7, 0)
            and encoded(p['shape']) == encoded(layout['shape']), 'fixed profile differs')
    require(encoded(p['tables']) == encoded(layout['tables']), 'table identities differ')
    require(len(layout['regions']) == 4 and len(layout['allocations']) == 35,
            'four regions and 35 reservations required')
    regions = layout['regions']
    for region in regions:
        require(integer(region['base']) and integer(region['limit'])
                and region['base'] < region['limit'] < 1 << 56
                and region['base'] % 64 == region['limit'] % 64 == 0
                and type(region['read']) is bool and type(region['write']) is bool,
                'region bounds or fixture permissions differ')
    require([(r['read'], r['write']) for r in regions]
            == [(True, False), (True, True), (True, False), (True, True)],
            'fixture region permission order differs')
    ordered_regions = sorted(regions, key=lambda r: r['base'])
    require(all(a['limit'] == b['base'] for a, b in zip(ordered_regions, ordered_regions[1:])),
            'four-region arena is not contiguous')
    base, limit = ordered_regions[0]['base'], ordered_regions[-1]['limit']
    require((base, limit, limit - base) == (4294967296, 4508440896, 213473600)
            and limit - base <= 256 * 1024 * 1024, 'fixed full-arena extent differs')
    providers = {v['name']: v for v in p['providers']}
    require(len(p['providers']) == len(providers) == 14, 'provider count differs')
    allocations = layout['allocations']
    require(len({a['name'] for a in allocations}) == 35, 'duplicate reservation name')
    readonly = [a for a in allocations if a['readonly'] is True]
    require(len(readonly) == 14 and tuple(a['name'] for a in readonly) == ORDER[2:]
            and set(providers) == set(ORDER[2:]), 'metadata input order or names differ')
    spans = []
    for allocation in allocations:
        a, size, reserved = (allocation[k] for k in ('base', 'bytes', 'reserved_bytes'))
        require(integer(a) and integer(size, True) and integer(reserved, True)
                and 0 < size <= reserved and a % 64 == size % 64 == reserved % 64 == 0
                and type(allocation['readonly']) is bool and type(allocation['virtual']) is bool,
                'reservation size/alignment/type differs')
        region = regions[0 if allocation['readonly'] else 1]
        require(region['base'] <= a < a + reserved <= region['limit'],
                'reservation outside its fixture region')
        spans.append((a, a + reserved, allocation['name']))
        if allocation['readonly']:
            v = providers[allocation['name']]
            require(encoded({k: v[k] for k in ('name', 'base', 'bytes', 'shape', 'descriptor_dtype')})
                    == encoded({k: allocation[k] for k in ('name', 'base', 'bytes', 'shape', 'descriptor_dtype')}),
                    'provider allocation identity differs')
    inputs = []
    for name, count in (('commands', 21), ('descriptors', 215)):
        table = p['tables'][name]
        require(integer(table['base']) and integer(table['bytes'], True)
                and type(table['count']) is int and table['count'] == count
                and table['limit'] == table['base'] + table['bytes']
                and regions[2]['base'] <= table['base'] < table['limit'] <= regions[2]['limit']
                and table['base'] % 64 == table['bytes'] % 64 == 0,
                'metadata table extent differs')
        inputs.append(dict(name=name, **{k: table[k] for k in ('base', 'bytes', 'sha256')}))
        spans.append((table['base'], table['limit'], name))
    spans.append((regions[3]['base'], regions[3]['limit'], 'workspace'))
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            require(max(a[0], b[0]) >= min(a[1], b[1]), 'reservation/table/workspace overlap')
    for name in ORDER[2:]:
        inputs.append({k: providers[name][k] for k in ('name', 'base', 'bytes', 'sha256')})
    for row in inputs:
        require(isinstance(row['sha256'], str) and len(row['sha256']) == 64
                and all(c in '0123456789abcdef' for c in row['sha256']), 'invalid input SHA256')
    require(sum(v['bytes'] for v in inputs) == 94920448
            and inputs[9]['name'] == 'gamma0' and inputs[15]['name'] == 'x', 'N0 indexes or bytes differ')
    return dict(base=base, bytes=limit-base, limit=limit, inputs=inputs)


def render(binding):
    lines = [
        '// New fixed M128 input binding. Factory is SOURCE ONLY and has not been called.',
        '// Full arena reservation does not grant output/DDR permissions or Host launch.',
        '// Ordered by the original metadata allocations; N0 gamma0=9, x=15.',
        '#pragma once', '#include "same_buffer_loader.hpp"', '#include <array>',
        '#include <cstdint>', '#include <vector>', 'namespace canonical16_binding_v1 {',
        'struct FixedInput {', '    const char* name;', '    std::uint64_t base, bytes;',
        '    same_buffer_loader_v1::Sha256::Digest sha256;', '};',
        'inline constexpr std::uint64_t ram_base = %dULL;' % binding['base'],
        'inline constexpr std::uint64_t ram_bytes = %dULL;' % binding['bytes'],
        'inline constexpr std::uint64_t ram_byte_budget = %dULL;' % binding['bytes'],
        'inline constexpr std::uint64_t ram_limit = %dULL;' % binding['limit'],
        'inline constexpr std::array<FixedInput, 16> expected_inputs{{']
    for row in binding['inputs']:
        digest = ','.join('0x' + row['sha256'][i:i+2] for i in range(0, 64, 2))
        lines.append('    {"%s", %dULL, %dULL, {{%s}}},' % (row['name'], row['base'], row['bytes'], digest))
    lines += ['}};', 'static_assert(ram_base + ram_bytes == ram_limit);',
        'static_assert(ram_bytes <= canonical_load_storage_v2::InitializationRam::maximum_bytes);',
        'static_assert(expected_inputs[9].base == 4482204160ULL);',
        'static_assert(expected_inputs[15].base == 4482749312ULL);',
        '// No caller-supplied expected list, addresses, budget, or digest override.',
        '// Calling this factory later allocates 426947200 backing-array bytes plus overhead.',
        'inline same_buffer_loader_v1::SameBufferLoader make_canonical16_loader() {',
        '    std::vector<same_buffer_loader_v1::ExpectedInput> fixed;',
        '    fixed.reserve(expected_inputs.size());',
        '    for (const auto& row : expected_inputs)',
        '        fixed.push_back({{row.name, row.base, row.bytes}, row.sha256});',
        '    return same_buffer_loader_v1::SameBufferLoader(',
        '        ram_base, ram_bytes, ram_byte_budget, fixed);',
        '}', '} // namespace canonical16_binding_v1', '']
    return '\n'.join(lines).encode()


def verify(repository):
    identity, layout = load(repository)
    binding = derive(identity, layout)
    actual = (HERE / 'canonical16_binding.hpp').read_bytes()
    require(actual == render(binding), 'fixed binding source differs from authenticated inputs')
    return dict(status='PASS_SOURCE_ONLY_CANONICAL16_BINDING', inputs=16, reservations=35, regions=4,
        binding_sha256=sha(actual), payload_bytes=94920448, ram_bytes=binding['bytes'],
        backing_arrays_bytes=2*binding['bytes'], source_buffers_hashed_and_parsed_same=True,
        factory_called=False, native_executed=False, canonical_payload_loaded=False,
        reference_payloads_read=False, ddr_permissions_established=False, launch_admission=False,
        whole_repository_identity_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    print(json.dumps(verify(parser.parse_args().repo), sort_keys=True))
