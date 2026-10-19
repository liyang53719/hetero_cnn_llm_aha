"""Portable Host C++ generation, compile and reset/launch gate; SOURCE ONLY locally."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Python -I -S -B required before project loading')
if __name__ == '__main__':
    raise SystemExit('Load from a pinned same-buffer CI coordinator')
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import types

HERE = Path(__file__).absolute().parent
PINS_SIZE = 1155
PINS_SHA = '777cbe5288224509388e10eeb613db4c61d90caeb815cf81b35cbd4e7bd40f5e'
SUPPORT = 'development_snapshots/canonical_host93_fixed_core_build_source_20261018/run_build_gate.py'
INIT = 'development_snapshots/canonical_host93_derived_micro_source_20261018/init_contract.py'
CONTRACT = 'development_snapshots/canonical_host93_same_sv_source_20261018/checker/CONTRACT.json'
LAUNCH = 'development_snapshots/canonical_n0_model_wiring_source_20261018/canonical_launch.hpp'
RETAINED_PLAN = 'candidates/host93_ci_recovery/retained13/SOURCE_PLAN.json'
CONFIG_NAMES = ('hierarchy.vlt', 'readonly.vlt', 'dma_hints.vlt', 'precision_warnings.vlt')
DROP = {'deps/axi_stream/src/axi_stream_cut.sv', 'deps/axi_stream/src/axi_stream_multicut.sv'}
CLOCK = 'deps/tech_cells_generic/src/rtl/tc_clk.sv'
DEFINES = {'TARGET_ASIC': '', 'TARGET_RTL': '', 'TARGET_SYNTHESIS': '', 'TARGET_VERILATOR': ''}
IDMA_META = {'SHA256SUMS.json': (104165, 'a699b8074b8099e00859d5174c0a5fb6b5a171a28cad30bab8dd96226dc67b19'),
             'SOURCE_CLOSURE.json': (73326, 'a3161f06be82894bbab48e3efae325e868385ea204d5f2aab47978ce9bd10aa1')}
SV_PIN = (76366612, '2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61')
FIFO_PATH = 'deps/common_cells/src/cc_passthrough_stream_fifo.sv'
FIFO_BASE = (4411, '68de1c713e40d97950591111dccd37a7546025f7fe6750fa3092826422557352')
FIFO_SPLIT = (4662, 'cf5607bf61d0e1ca95d523689ba5170fe937dcfb2f94c001661b4a897bf9e5f6')
CLUSTER_MODULE = 'bf16_context_lane_cluster16_rev8b_b_candidate'
CLUSTER_LEAF = re.compile(re.escape(CLUSTER_MODULE) + r'_[0-9a-f]{1,127}\Z')
CLUSTER_PARAMETER_HASH = '30c271aa0606321f6461b96aaa068709c25b914c50dd86a54a5813ec65e7b238da67ba144083832b8f6cc572100e57e0d59bfdbcb748931891ef0b6ea82c6073'
CLUSTER_SEED_ARGUMENT = "-GENABLE_ACCUMULATOR_SEED=1'h1"
CLUSTER_CONTRACT_BOUNDARY = 'CLUSTER_GENERATION_WITNESS'
CLUSTER_CONTRACT_CODES = ('CLUSTER_CHILD_ARGS', 'CLUSTER_TOP_LINK', 'CLUSTER_LIBRARY_GRAPH',
                          'CLUSTER_INITIALIZER', 'CLUSTER_ABI', 'CLUSTER_ARTIFACTS', 'CLUSTER_CENSUS')
CLUSTER_HIERARCHY = b'`verilator_config\nhier_block -module "bf16_context_lane_cluster16_rev8b_b_candidate"\n'
FIRST_N0_CATALOG_SIZE = 5251
FIRST_N0_CATALOG_SHA = '0fb411a09f1643ba8d248beb8db4cad34ab622e685e11a3156d39d67695dc04d'
FIRST_N0_PREFIX = 'candidates/host93_first_n0_sources/bridge/'
FIRST_N0_EXTERNAL_INCLUDES = frozenset(('VHostBlockTop.h', 'VHostBlockTop__Syms.h',
    'VHostBlockTop___024root.h', 'verilated.h', 'verilated_sym_props.h'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def clean(path):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts and not any(c in str(path) for c in ('\n', '\r', '\x00', '"', '\\', '*', '?', '[', ']', ' ')), 'safe absolute CI path')
    return path


def small_read(path, size, digest):
    path = clean(path)
    need(type(size) is int and 0 <= size <= 4 * 1024**2, 'small read bound')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = nxt
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            need(stat.S_ISREG(before.st_mode) and before.st_size == size, 'input regular/exact size')
            raw = stream.read(size + 1)
            after = os.fstat(stream.fileno())
        stamp = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        need(len(raw) == size and sha(raw) == digest and stamp(before) == stamp(after) == stamp(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'input same-buffer identity before compile/parse')
        return raw
    finally:
        os.close(parent)


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def verified_module(raw, path, pin, name):
    need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'module identity before compile')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def load(repo):
    pins = unique_json(small_read(HERE / 'SOURCE_PINS.json', PINS_SIZE, PINS_SHA))
    buffers = {p: small_read(repo / p, pin['bytes'], pin['sha256']) for p, pin in pins['repo'].items()}
    short = pins['short_launch.cpp']
    buffers['short_launch.cpp'] = small_read(HERE / 'short_launch.cpp', short['bytes'], short['sha256'])
    support = verified_module(buffers[SUPPORT], repo / SUPPORT, pins['repo'][SUPPORT], 'verified_host_execution_fs')
    lexical = verified_module(buffers[INIT], repo / INIT, pins['repo'][INIT], 'verified_host_execution_lexical')
    return pins, buffers, support, lexical



def load_first_n0(repo):
    """Read only the fixed 22-source catalog and compile exactly the verified buffers."""
    catalog = unique_json(small_read(HERE / 'FIRST_N0_SOURCES.json',
                                    FIRST_N0_CATALOG_SIZE, FIRST_N0_CATALOG_SHA))
    need(set(catalog) == {'schema', 'origin_manifest_sha256', 'sources'} and
         catalog['schema'] == 'FIXED_FIRST_N0_COMPILE_SOURCES_V1' and
         catalog['origin_manifest_sha256'] == '38afc16d7a5c56e47b950e47c8a5ddfe2a8abc5374b77884539296407d8705fc',
         'fixed first N0 catalog schema/origin')
    rows = catalog['sources']; fixtures = {}
    need(type(rows) is dict and len(rows) == 22, 'fixed first N0 source count')
    for path, pin in rows.items():
        need(type(path) is str and path.startswith(FIRST_N0_PREFIX) and
             re.fullmatch(r'(?:source/first_n0_main\.cpp|include/[a-z0-9_]+\.(?:hpp|inc))',
                          path[len(FIRST_N0_PREFIX):]) is not None,
             'fixed first N0 source location')
        need(type(pin) is dict and set(pin) == {'bytes', 'sha256', 'fixture'} and
             pin['fixture'] == Path(path).name and pin['fixture'] not in fixtures and
             pin['fixture'] not in FIRST_N0_EXTERNAL_INCLUDES,
             'collision-free first N0 flat fixture names')
        fixtures[pin['fixture']] = small_read(repo / path, pin['bytes'], pin['sha256'])
    need('first_n0_main.cpp' in fixtures, 'fixed first N0 driver')
    # Fixed generated/runtime names remain covered by the existing toolchain and
    # generated-source gates. Root syntax and runtime handles remain UNKNOWN.
    for raw in fixtures.values():
        quoted = re.findall(r'^\s*#\s*include\s*"([^"\n]+)"', raw.decode('ascii'), re.MULTILINE)
        need(all(name in fixtures or name in FIRST_N0_EXTERNAL_INCLUDES for name in quoted),
             'fixed first N0 quoted include closure')
    return catalog, fixtures


def stable_first_n0(repo, catalog, fixtures, support, work):
    current_catalog, current = load_first_n0(repo)
    need(current_catalog == catalog and current == fixtures, 'fixed first N0 source drift')
    tree = support.tree_inventory(work / 'fixtures', 4 * 1024**2, 22, 22, 1024**2)
    need(set(tree['entries']) == set(fixtures), 'exact first N0 fixture include closure')
    for name, raw in fixtures.items():
        row = tree['entries'][name]
        need(row['kind'] == 'regular' and row['bytes'] == len(raw) and
             row['sha256'] == sha(raw) and row['mode'] == '0o600',
             'first N0 fixture identity/mode drift')
        need(small_read(work / 'fixtures' / name, len(raw), sha(raw)) == raw,
             'first N0 fixture same-buffer drift')


def compiled_first_n0_elf(support, work, tree):
    """Bounded identity and ELF magic, with no invocation or qualification."""
    path = work / 'obj/VHostBlockTop'
    row = tree['entries'].get('obj/VHostBlockTop', {})
    need(row.get('kind') == 'regular', 'new first N0 ELF missing')
    expected = {key: row[key] for key in ('bytes', 'sha256', 'mode')}
    need(expected['bytes'] > 4 and int(expected['mode'], 8) & 0o111 and
         support.identity(path, 512 * 1024**2) == expected, 'new first N0 compiled ELF identity/mode')
    parent, fd, before = support.regular_fd(path)
    try:
        need(os.read(fd, 4) == b'\x7fELF', 'new first N0 host is not an ELF')
        stamp = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        need(stamp(before) == stamp(os.fstat(fd)) ==
             stamp(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
             'new first N0 ELF changed during header read')
    finally:
        os.close(fd); os.close(parent)
    need(support.identity(path, 512 * 1024**2) == expected, 'new first N0 ELF changed after compile')
    return {'path': str(path), **expected}


def json_current(support, path, cap=1024**2):
    pin = support.identity(path, cap)
    return unique_json(small_read(path, pin['bytes'], pin['sha256'])), pin


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    need(len(raw) <= 32 * 1024**2, 'private receipt size')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        need(stream.write(raw) == len(raw), 'short receipt write')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def parse_filelist(raw):
    sources, includes, defines = [], [], {}
    for line in raw.decode('ascii').splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        for token in shlex.split(line):
            if token.startswith('+define+'):
                for value in token[8:].split('+'):
                    key, separator, content = value.partition('=')
                    need(key in DEFINES and content == '', 'unexpected define')
                    need(key not in defines or defines[key] == content, 'define conflict')
                    defines[key] = content
            elif token.startswith('+incdir+@ROOT@/'):
                includes.append(token[len('+incdir+@ROOT@/'):])
            elif token.startswith('@ROOT@/'):
                sources.append(token[7:])
            else:
                raise ValueError('unknown filelist token')
    includes = list(dict.fromkeys(includes))
    for relative in sources + includes:
        need(relative and not relative.startswith('/') and all(p not in ('', '.', '..') for p in relative.split('/')) and not any(c in relative for c in ('\\', '\n', '"')), 'unsafe filelist path')
    need(len(sources) == len(set(sources)) == 294 and len(includes) == 8 and defines == DEFINES and DROP <= set(sources), '294/8/4 fixed source contract')
    return sources, includes, defines


def closure(support, idma, retained, configuration, sv, buffers, *, fifo_valid_split=False):
    need(type(fifo_valid_split) is bool, 'explicit FIFO derivation bool')
    root = idma / 'sources'
    metadata = {p: unique_json(small_read(root / p, size, digest)) for p, (size, digest) in IDMA_META.items()}
    sums, admitted = metadata['SHA256SUMS.json'], metadata['SOURCE_CLOSURE.json']['admitted_input_hashes']
    need(len(sums) == 927 and len(admitted) == 312, 'iDMA metadata counts')
    tree = support.tree_inventory(root, 8 * 1024**2, 319, 1024, 2 * 1024**2)
    actual = {p: row for p, row in tree['entries'].items() if row['kind'] == 'regular'}
    need(len(actual) == 319 and tree['bytes'] == 3072200 + (251 if fifo_valid_split else 0), 'exact iDMA319 tree')
    if fifo_valid_split:
        need(sums.get(FIFO_PATH) == admitted.get(FIFO_PATH) == FIFO_BASE[1], 'original FIFO provenance')
        need(FIFO_PATH in actual and (actual[FIFO_PATH]['bytes'], actual[FIFO_PATH]['sha256']) == FIFO_SPLIT,
             'exact sole derived FIFO identity')
    for name, row in actual.items():
        expected = IDMA_META['SHA256SUMS.json'][1] if name == 'SHA256SUMS.json' else sums.get(name)
        if fifo_valid_split and name == FIFO_PATH: expected = FIFO_SPLIT[1]
        need(row['sha256'] == expected, 'iDMA bytes disagree with pinned manifest')
    for name, digest in admitted.items():
        expected = FIFO_SPLIT[1] if fifo_valid_split and name == FIFO_PATH else digest
        need(name in actual and actual[name]['sha256'] == expected and digest == sums.get(name), 'iDMA admitted closure disagreement')
    source_pin = actual['idma.f.in']
    sources, includes, defines = parse_filelist(small_read(root / 'idma.f.in', source_pin['bytes'], source_pin['sha256']))
    need(set(sources) <= set(admitted) and metadata['SOURCE_CLOSURE.json']['initial_filelist_defines'] == DEFINES, 'filelist/manifest contract')
    plan = unique_json(buffers[RETAINED_PLAN])
    retained_tree = support.tree_inventory(retained / 'source', 4 * 1024**2, 13, 64, 2 * 1024**2)
    regular = {p: row for p, row in retained_tree['entries'].items() if row['kind'] == 'regular'}
    need(set(regular) == set(plan['expected13']) and len(plan['source_order']) == 13 and set(plan['source_order']) == set(regular), 'exact retained13 tree/order')
    need(all(regular[p]['sha256'] == digest for p, digest in plan['expected13'].items()), 'retained13 final pins')
    config_tree = support.tree_inventory(configuration, 1024**2, 5, 8, 512 * 1024)
    need(set(config_tree['entries']) == set(CONFIG_NAMES) | {'MANIFEST.json'}, 'exact four config files plus manifest')
    manifest, unused = json_current(support, configuration / 'MANIFEST.json')
    need(manifest['readonly_count'] == 610 and manifest['precision_warning_directives'] == 21 and manifest['sv'] == {'bytes': SV_PIN[0], 'sha256': SV_PIN[1]}, 'config scope and same-SV identity')
    for name in CONFIG_NAMES:
        need({k: config_tree['entries'][name][k] for k in ('bytes', 'sha256')} == manifest['files'][name], 'config output identity')
    if fifo_valid_split:
        need(small_read(configuration / 'hierarchy.vlt', len(CLUSTER_HIERARCHY), sha(CLUSTER_HIERARCHY)) == CLUSTER_HIERARCHY,
             'diagnostic variant requires sole cluster hierarchy')
    svpath = clean(sv['path'])
    observed = support.identity(svpath, 80 * 1024**2)
    need((observed['bytes'], observed['sha256']) == SV_PIN and observed['bytes'] == sv['bytes'] and observed['sha256'] == sv['sha256'], 'fresh emission same-SV pin')
    ordered = [str(root / p) for p in sources if p not in DROP]
    ordered += [str(retained / 'source' / p) for p in plan['source_order']]
    ordered += [str(root / CLOCK), str(svpath)]
    need(len(ordered) == len(set(ordered)) == 307, 'exact 307 compilation sources')
    return {'idma_tree': tree, 'retained_tree': retained_tree, 'configuration_tree': config_tree,
            'sv': {'path': str(svpath), **observed}, 'sources': ordered,
            'includes': [str(root / p) for p in includes], 'defines': defines}



def generation_source_map(before, idma, retained):
    """Finite diagnostic aliases from the already verified compilation closure."""
    sources = before['sources']
    need(type(sources) is list and len(sources) == 307 and
         all(type(path) is str for path in sources) and len(set(sources)) == 307,
         'exact 307 diagnostic sources')
    admitted = {}
    for prefix, root, tree in (('idma', clean(idma) / 'sources', before['idma_tree']),
                               ('retained', clean(retained) / 'source', before['retained_tree'])):
        for relative, row in tree['entries'].items():
            if row['kind'] != 'regular':
                continue
            need(type(relative) is str and relative and not relative.startswith('/') and
                 all(part not in ('', '.', '..') for part in relative.split('/')),
                 'diagnostic relative source path')
            path = str(clean(root / relative))
            need(path not in admitted, 'ambiguous diagnostic source path')
            admitted[path] = {'id': prefix + '/' + relative,
                              'bytes': row['bytes'], 'sha256': row['sha256']}
    sv = before['sv']; svpath = str(clean(sv['path']))
    need(svpath not in admitted, 'ambiguous diagnostic Host source path')
    admitted[svpath] = {'id': 'host/HostBlockCollection.sv',
                        'bytes': sv['bytes'], 'sha256': sv['sha256']}
    result = []
    for path in sources:
        need(str(clean(path)) == path and path in admitted, 'unknown diagnostic source path')
        row = admitted[path]
        need(type(row['bytes']) is int and row['bytes'] >= 0 and
             type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None,
             'diagnostic source identity')
        result.append({'path': path, **row})
    need(len({row['id'] for row in result}) == 307,
         'unique diagnostic source aliases')
    return result


def verify_tools(support, toolchain):
    backend = toolchain['backend']; root = clean(toolchain['verilator_root'])
    need(clean(backend['path']) == root / 'bin/verilator_bin', 'fresh backend root')
    need(support.identity(backend['path'], 64 * 1024**2) == {k: backend[k] for k in ('bytes', 'sha256', 'mode')} and int(backend['mode'], 8) & 0o111, 'same-job backend changed')
    for invoked, pin in toolchain['host_programs'].items():
        need(os.path.realpath(invoked) == pin['path'] and support.identity(pin['path'], 64 * 1024**2) == {k: pin[k] for k in ('bytes', 'sha256', 'mode')}, 'host program identity/resolution changed')
    need({'/usr/bin/make', '/usr/bin/g++', '/usr/bin/ar', '/usr/bin/perl', '/bin/sh'} <= set(toolchain['host_programs']), 'host programs missing')
    pin = toolchain['configured_runtime']; runtime = unique_json(small_read(pin['path'], pin['bytes'], pin['sha256']))
    need(support.tree_inventory(root / 'include', 32 * 1024**2, 256, 512, 4 * 1024**2) == runtime['include'], 'configured runtime include drift')
    need(set(runtime['wrappers']) == {'verilator', 'verilator_includer'}, 'runtime wrapper set')
    for name, item in runtime['wrappers'].items():
        need(item['path'] == str(root / 'bin' / name) and support.identity(item['path'], 4 * 1024**2) == {k: item[k] for k in ('bytes', 'sha256', 'mode')}, 'configured wrapper drift')
    return runtime



def stable_sources(repo, pins, buffers):
    for name, pin in pins['repo'].items():
        need(small_read(repo / name, pin['bytes'], pin['sha256']) == buffers[name], 'fixed repository source drift')
    pin = pins['short_launch.cpp']
    need(small_read(HERE / 'short_launch.cpp', pin['bytes'], pin['sha256']) == buffers['short_launch.cpp'], 'short consumer source drift')
    small_read(HERE / 'SOURCE_PINS.json', PINS_SIZE, PINS_SHA)


def verify_emission(support, emission):
    expected = {'fir': (42417256, '264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'), 'sv': SV_PIN}
    result = {}
    for name, wanted in expected.items():
        pin = emission[name]
        observed = support.identity(clean(pin['path']), 80 * 1024**2)
        need((observed['bytes'], observed['sha256']) == wanted and pin['bytes'] == wanted[0] and pin['sha256'] == wanted[1], 'same-job emission input drift')
        result[name] = {'path': pin['path'], **observed}
    return result


def environment(work, root):
    return {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC',
            'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'), 'SHELL': '/bin/sh',
            'VERILATOR_ROOT': str(root), 'VERILATOR_BIN': 'verilator_bin',
            'MAKE': '/usr/bin/make', 'CC': '/usr/bin/gcc', 'CXX': '/usr/bin/g++',
            'AR': '/usr/bin/ar', 'PERL': '/usr/bin/perl', 'OBJCACHE': '',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}


def limits(total, work, as_gib, fsize_mib, tree_mib, log_mib):
    return {'total_seconds': total, 'work_seconds': work, 'cpu_seconds': work,
            'as_bytes': as_gib * 1024**3, 'fsize_bytes': fsize_mib * 1024**2,
            'tree_bytes': tree_mib * 1024**2, 'log_bytes': log_mib * 1024**2,
            'sample_rows': total + 2, 'file_count': 32768, 'entry_count': 65536}


LIMITS = {'host93_cpp_generate': limits(600, 540, 6, 128, 512, 4),
          'host93_cpp_compile': limits(1800, 1740, 6, 512, 2048, 4),
          'host93_reset_launch': limits(30, 10, 2, 8, 2048, 1)}


def commands(work, backend, inputs, configuration):
    obj, fixture = work / 'obj', work / 'fixtures'
    generation = [backend['path'], '--cc', '--hierarchical', '--exe', str(fixture / 'short_launch.cpp'),
        '--top-module', 'HostBlockTop', '--prefix', 'VHostBlockTop', '--Mdir', str(obj),
        '--threads', '1', '--build-jobs', '1', '--verilate-jobs', '1',
        '--comp-limit-parens', '16', '--output-split', '3000', '--output-split-cfuncs', '200',
        '--no-std', '--relative-includes', '--timescale', '1ns/1ps',
        '-CFLAGS', '-std=c++17 -I' + str(fixture)]
    generation += [str(configuration / p) for p in CONFIG_NAMES]
    generation += ['+define+' + name for name in inputs['defines']]
    generation += ['+incdir+' + folder for folder in inputs['includes']]
    generation += inputs['sources']
    return {'host93_cpp_generate': generation,
            'host93_cpp_compile': ['/usr/bin/make', '-C', str(obj), '-f', 'VHostBlockTop.mk', '-j1',
                'OPT_FAST=-O0', 'OPT_SLOW=-O0', 'OPT_GLOBAL=-O0', 'CXX=/usr/bin/g++',
                'AR=/usr/bin/ar', 'SHELL=/bin/sh', 'MAKE=/usr/bin/make', 'OBJCACHE=', 'VHostBlockTop'],
            'host93_reset_launch': [str(obj / 'VHostBlockTop')]}


def generated_text(support, tree, name, cap=4 * 1024**2):
    row = tree['entries'].get(name)
    need(row is not None and row['kind'] == 'regular' and row['bytes'] <= cap, 'bounded generated text missing: ' + name)
    return small_read(Path(tree['root']) / name, row['bytes'], row['sha256']).decode('ascii')


def initialized_endpoint(raw, leaf, lexical):
    need(re.fullmatch(r'qwen2_matrix_command_endpoint[A-Za-z0-9_]*', leaf) and len(raw) <= 65536, 'bounded actual endpoint wrapper')
    text = raw.decode('ascii'); clean_text, ignored = lexical.lexical_mask(text)
    child, container = 'V' + leaf, 'V' + leaf + '_container'
    declarations = list(re.finditer(r'\bclass\s+' + re.escape(container) + r'\b', clean_text))
    need(len(declarations) == 1, 'one actual target container')
    start = declarations[0].start(); depth = 0
    for char in clean_text[:start]:
        depth += (char == '{') - (char == '}')
        need(depth >= 0, 'invalid class scope')
    need(depth == 0, 'container must have top-level scope')
    pattern = (r'class\s+' + re.escape(container) + r'\s*:\s*public\s+' + re.escape(child) +
        r'\s*\{\s*public\s*:\s*long\s+long\s+m_seqnum\s*;\s*' + re.escape(container) +
        r'\s*\(\s*const\s+char\s*\*\s*scopep__V\s*\)\s*:\s*' + re.escape(child) +
        r'\s*\(\s*scopep__V\s*\)\s*,\s*m_seqnum\s*\{\s*0\s*\}\s*\{\s*\}\s*\}\s*;')
    match = re.match(pattern, text[start:])
    need(match is not None, 'actual scoped ctor requires m_seqnum{0}')
    end = start + match.end()
    need(not any(a < end and b > start for a, b, kind in ignored), 'comment/literal inside scoped ctor')
    return {'leaf': leaf, 'class_byte_range': [start, end], 'class_sha256': sha(raw[start:end]), 'wrapper_sha256': sha(raw), 'm_seqnum_initializer': 0}


def generated_witness(support, tree, lexical, host_ports, compiled=False, sv_path=None):
    names = tree['entries']
    candidates = [p for p in names if re.fullmatch(r'obj/Vqwen2_matrix_command_endpoint[A-Za-z0-9_]*__hierMkArgs\.f', p)]
    need(len(candidates) == 1, 'one new actual endpoint specialization')
    tokens = shlex.split(generated_text(support, tree, candidates[0]))
    def option(flag):
        need(tokens.count(flag) == 1 and tokens.index(flag) + 1 < len(tokens), 'unique generated child option')
        return tokens[tokens.index(flag) + 1]
    leaf = option('--lib-create')
    need(re.fullmatch(r'qwen2_matrix_command_endpoint[A-Za-z0-9_]*', leaf) is not None and option('--hierarchical-child') == '1' and option('--top-module-encoded') == leaf, 'actual child hierarchy arguments')
    parameter = [v.split('=', 1)[1] for v in tokens if v.startswith('-GENABLE_ACCUMULATOR_SEED=')]
    need(len(parameter) == 1 and parameter[0] in ('1', "32'h1", "32'sh1", "32'd1", "32'sd1", "'sh1"), 'actual accumulator-seed specialization')
    child = 'V' + leaf; wrapper = child + '/' + leaf + '.sv'; archive = child + '/lib' + leaf + '.a'
    top_args = shlex.split(generated_text(support, tree, 'obj/VHostBlockTop__hierMkArgs.f'))
    need(wrapper in top_args, 'new child wrapper in top args')
    need(sv_path is not None and str(sv_path) in top_args and top_args.index(wrapper) < top_args.index(str(sv_path)), 'new wrapper precedes same-job Host SV')
    top_mk = generated_text(support, tree, 'obj/VHostBlockTop.mk')
    hier_mk = generated_text(support, tree, 'obj/VHostBlockTop_hier.mk')
    need('include VHostBlockTop_hier.mk' in top_mk and 'VM_HIER_LIBS' in hier_mk and archive in hier_mk and child + '.mk' in hier_mk, 'new actual hierarchy make graph')
    cpp = generated_text(support, tree, 'obj/' + child + '/' + leaf + '.cpp', 65536)
    initializer = initialized_endpoint(cpp.encode('ascii'), leaf, lexical)
    wrapper_text = generated_text(support, tree, 'obj/' + wrapper)
    need('chandle handle__V' in wrapper_text and leaf + '_protectlib_create' in wrapper_text, 'actual protected wrapper handle')
    for suffix in ('create', 'combo_update', 'seq_update', 'final'):
        symbol = leaf + '_protectlib_' + suffix
        need(symbol in cpp and symbol in wrapper_text, 'actual protected boundary missing')
    # Hierarchical protected imports need not emit registered VerilatedScope
    # objects. Count the eight fresh generated chandle-storage declarations.
    root_header = generated_text(support, tree, 'obj/VHostBlockTop___024root.h')
    handles = re.findall(r'^\s*void\s*\*\s*((?:__PVT__)?HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_(\d+)__DOT__handle(?:___05F|__)V)\s*;', root_header, re.MULTILINE)
    need(len(handles) == 8 and sorted(int(index) for name, index in handles) == list(range(8)), 'eight actual generated protected-hierarchy chandle declarations')
    scopes = ['HostBlockTop.owner.matrix.leaves_' + str(i) for i in range(8)]
    header = generated_text(support, tree, 'obj/VHostBlockTop.h')
    observed = {}
    for direction, widthkind, name, high, low, words in re.findall(r'VL_(IN|OUT)(8|16|64|W)?\s*\(\s*&?([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*\)', header):
        need(name not in observed and low == '0', 'duplicate/nonzero-low actual top port')
        observed[name] = ['input' if direction == 'IN' else 'output', int(high) + 1]
    need(observed == host_ports and len(observed) == 83, 'new actual Host83-port declaration contract')
    if compiled:
        for path in ('obj/' + archive, 'obj/VHostBlockTop__ALL.a', 'obj/VHostBlockTop'):
            need(names.get(path, {}).get('bytes', 0) > 0, 'new child/top archive or ELF missing')
    return {'status': 'FINITE_NEW_GENERATED_HOST_WITNESS', 'leaf': leaf, 'scopes': scopes,
            'generated_chandle_members': [name for name, index in handles],
            'initializer': initializer, 'child_archive': 'obj/' + archive, 'host_ports': 83,
            'eight_runtime_handles_verified': False, 'old_abi_inherited': False}


def cluster_failure(error, code):
    # Finite private-gate labels only; never publish the exception text.
    need(code in CLUSTER_CONTRACT_CODES, 'finite cluster contract code')
    error.safe_contract_boundary = CLUSTER_CONTRACT_BOUNDARY
    error.safe_contract_code = code
    return error


def validate_cluster_census(report):
    """Admission for a limited compile/reset continuation, not a handle proof.

    The pinned coordinator validates the complete census schema first. This pure
    predicate checks only the already-observed finite generation prerequisites.
    It deliberately does not require recognized root syntax or 256 handles.
    """
    try:
        need(type(report) is dict and report['state'] == 'AVAILABLE' and
             report['scan_complete'] is True, 'available complete cluster census')
        need(type(report['counts']) is dict and
             all(type(value) is int and value == 0 for value in report['counts'].values()) and
             set(report['counts']) == {'warning_headers', 'error_headers', 'fatal_summary_headers',
                                      'example_paths', 'unparsed_headers'}, 'clean cluster diagnostic headers')
        need(type(report['caps']) is dict and report['records'] == [] and report['by_rule'] == {} and
             report['omission'] == {'records': 0, 'examples': 0} and
             set(report['caps']) == {'record_cap', 'example_cap', 'report_byte_cap', 'partial'} and
             all(value is False for value in report['caps'].values()), 'complete untruncated cluster census')
        wrapper = report['wrapper']
        need(type(wrapper) is dict, 'finite cluster wrapper object')
        cluster = wrapper['cluster_structure']
        need(wrapper['state'] == 'AVAILABLE' and wrapper['module'] == CLUSTER_MODULE and
             type(wrapper['candidate_count']) is int and wrapper['candidate_count'] == 1 and
             type(wrapper['hierarchical_child']) is int and wrapper['hierarchical_child'] == 1 and
             wrapper['top_references_wrapper'] is True and
             wrapper['syntax_state'] == 'FINITE_PARSE_AVAILABLE', 'finite sole cluster wrapper')
        for key, value in (('combo_input_count', 18), ('combo_output_count', 2),
                           ('dpi_import_count', 6), ('combo_update_import_count', 1),
                           ('combo_update_call_count', 1), ('always_comb_count', 2)):
            need(type(wrapper[key]) is int and wrapper[key] == value, 'fixed cluster wrapper counts')
        need(type(cluster) is dict and cluster['makegraph_state'] == 'AVAILABLE' and
             type(cluster['library_target_count']) is int and cluster['library_target_count'] == 1 and
             type(cluster['matching_library_target_count']) is int and
             cluster['matching_library_target_count'] == 1, 'single cluster library graph')
        return True
    except (ValueError, KeyError, TypeError, AssertionError) as error:
        raise cluster_failure(ValueError('cluster census admission rejected'), 'CLUSTER_CENSUS') from error


def valid_cluster_leaf(leaf):
    # V3Param hashes base + '_ENABLE_ACCUMULATOR_SEED=' + ascii(false).
    # Only a prefix of this fixed seed-one digest is admitted; rehash collisions
    # remain unknown and fail closed. No actual private suffix is presumed.
    return bool(type(leaf) is str and CLUSTER_LEAF.fullmatch(leaf) is not None and
                CLUSTER_PARAMETER_HASH.startswith(leaf[len(CLUSTER_MODULE) + 1:]))


def initialized_cluster(raw, lexical, leaf):
    need(valid_cluster_leaf(leaf), 'fixed seed-one parameterized cluster leaf')
    need(type(raw) is bytes and len(raw) <= 65536, 'bounded actual cluster wrapper')
    text = raw.decode('ascii'); clean_text, ignored = lexical.lexical_mask(text)
    child, container = 'V' + leaf, 'V' + leaf + '_container'
    declarations = list(re.finditer(r'\bclass\s+' + re.escape(container) + r'\b', clean_text))
    need(len(declarations) == 1, 'one actual cluster container')
    start = declarations[0].start(); depth = 0
    for char in clean_text[:start]:
        depth += (char == '{') - (char == '}')
        need(depth >= 0, 'invalid cluster class scope')
    need(depth == 0, 'cluster container must have top-level scope')
    pattern = (r'class\s+' + re.escape(container) + r'\s*:\s*public\s+' + re.escape(child) +
        r'\s*\{\s*public\s*:\s*long\s+long\s+m_seqnum\s*;\s*' + re.escape(container) +
        r'\s*\(\s*const\s+char\s*\*\s*scopep__V\s*\)\s*:\s*' + re.escape(child) +
        r'\s*\(\s*scopep__V\s*\)\s*,\s*m_seqnum\s*\{\s*0\s*\}\s*\{\s*\}\s*\}\s*;')
    match = re.match(pattern, text[start:])
    need(match is not None, 'actual scoped cluster ctor requires m_seqnum{0}')
    end = start + match.end()
    need(not any(a < end and b > start for a, b, kind in ignored), 'comment/literal inside cluster ctor')
    return {'leaf': leaf, 'class_byte_range': [start, end], 'class_sha256': sha(raw[start:end]),
            'wrapper_sha256': sha(raw), 'm_seqnum_initializer': 0}


def cluster_generated_witness(support, tree, lexical, host_ports, report,
                              compiled=False, sv_path=None):
    """Same-job cluster linkage and limited native smoke acceptance only."""
    code = 'CLUSTER_CENSUS'
    try:
        validate_cluster_census(report)
        names = tree['entries']
        observed = report['wrapper']; cluster = observed['cluster_structure']
        for identity in (observed['args_identity'], observed['top_args_identity'],
                         observed['wrapper_identity'], cluster['makegraph_identity']):
            need(type(identity) is dict and set(identity) == {'bytes', 'sha256'} and
                 type(identity['bytes']) is int and 0 < identity['bytes'] <= 512 * 1024 and
                 type(identity['sha256']) is str and re.fullmatch('[0-9a-f]{64}', identity['sha256']),
                 'finite nonempty cluster census identities')
        def text(name, cap=4 * 1024**2, identity=None):
            raw = generated_text(support, tree, name, cap)
            if identity is not None:
                need({'bytes': len(raw.encode('ascii')), 'sha256': sha(raw.encode('ascii'))} == identity,
                     'cluster census and generated closure disagree')
            return raw
        code = 'CLUSTER_CHILD_ARGS'
        candidates = [p for p in names if p.startswith('obj/V') and p.endswith('__hierMkArgs.f') and
                      p != 'obj/VHostBlockTop__hierMkArgs.f']
        need(len(candidates) == 1, 'one parameterized cluster child')
        expected_args = candidates[0]
        leaf = expected_args[len('obj/V'):-len('__hierMkArgs.f')]
        need(valid_cluster_leaf(leaf), 'fixed seed-one parameterized cluster child family')
        child = 'V' + leaf
        wrapper = child + '/' + leaf + '.sv'; archive = child + '/lib' + leaf + '.a'
        tokens = shlex.split(text(expected_args, 256 * 1024, observed['args_identity']))
        def option(flag):
            need(tokens.count(flag) == 1 and tokens.index(flag) + 1 < len(tokens) and
                 not any(value.startswith(flag + '=') for value in tokens), 'unique cluster child option')
            return tokens[tokens.index(flag) + 1]
        need(option('--lib-create') == leaf and option('--hierarchical-child') == '1' and
             option('--top-module-encoded') == leaf and option('--prefix') == child and
             option('--mod-prefix') == child and
             [value for value in tokens if value.startswith('-G')] == [CLUSTER_SEED_ARGUMENT] and
             not any(value == '--hierarchical-params-file' or value.startswith('--hierarchical-params-file=') for value in tokens),
             'same parameterized cluster leaf and sole typed seed-one argument')
        code = 'CLUSTER_TOP_LINK'
        top_args = shlex.split(text('obj/VHostBlockTop__hierMkArgs.f', 256 * 1024, observed['top_args_identity']))
        need(top_args.count(wrapper) == 1 and sv_path is not None and top_args.count(str(sv_path)) == 1 and
             top_args.index(wrapper) < top_args.index(str(sv_path)) and
             not any(value.startswith('-G') for value in top_args), 'same-job cluster wrapper precedes Host SV')
        code = 'CLUSTER_LIBRARY_GRAPH'
        top_mk = text('obj/VHostBlockTop.mk')
        hier_mk = text('obj/VHostBlockTop_hier.mk', 256 * 1024, cluster['makegraph_identity'])
        need('include VHostBlockTop_hier.mk' in top_mk and archive in hier_mk and
             child + '.mk' in hier_mk, 'same-job single cluster library make graph')
        code = 'CLUSTER_INITIALIZER'
        cpp = text('obj/' + child + '/' + leaf + '.cpp', 65536)
        initializer = initialized_cluster(cpp.encode('ascii'), lexical, leaf)
        wrapper_text = text('obj/' + wrapper, 512 * 1024, observed['wrapper_identity'])
        need('chandle handle__V' in wrapper_text, 'actual cluster protected wrapper handle')
        for suffix in ('create', 'combo_update', 'seq_update', 'final'):
            symbol = leaf + '_protectlib_' + suffix
            need(symbol in cpp and symbol in wrapper_text, 'actual cluster protected boundary missing')
        code = 'CLUSTER_ABI'
        header = text('obj/VHostBlockTop.h')
        ports = {}
        for direction, widthkind, name, high, low, words in re.findall(r'VL_(IN|OUT)(8|16|64|W)?\s*\(\s*&?([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*\)', header):
            need(name not in ports and low == '0', 'duplicate/nonzero-low actual cluster top port')
            ports[name] = ['input' if direction == 'IN' else 'output', int(high) + 1]
        need(ports == host_ports and len(ports) == 83, 'new actual cluster Host83-port declaration contract')
        code = 'CLUSTER_ARTIFACTS'
        if compiled:
            for path in ('obj/' + archive, 'obj/VHostBlockTop__ALL.a', 'obj/VHostBlockTop'):
                need(names.get(path, {}).get('kind') == 'regular' and names[path]['bytes'] > 0,
                     'new cluster/top archive or ELF missing')
        return {'status': 'FINITE_CLUSTER_RESET_LAUNCH_WITNESS', 'leaf': leaf,
                'initializer': initializer, 'child_archive': 'obj/' + archive, 'host_ports': 83,
                'accumulator_seed_parameter': 1, 'instance_handle_count': None, 'runtime_handles_verified': False,
                'root_header_parsed': False, 'old_abi_inherited': False,
                'ram_or_weights_or_n0_or_full_block_claim': False}
    except (ValueError, KeyError, TypeError, AssertionError) as error:
        if getattr(error, 'safe_contract_boundary', None) != CLUSTER_CONTRACT_BOUNDARY:
            cluster_failure(error, code)
        raise


def check_log(raw):
    need(type(raw) is bytes and len(raw) <= 1024**2, 'short launch log bound')
    lines = raw.decode('ascii').splitlines()
    need(len(lines) == 3 and lines[0] == 'HOST93_RESET_OK asserted_high_edges=4 released_high_edges=4' and
         re.fullmatch(r'HOST93_LAUNCH_OK handshakes=1 high_edge=(?:[0-9]|1[0-5]) further_eval_calls=0', lines[1]) and
         lines[2] == 'HOST93_SHORT_PASS reset_and_launch_only=1', 'exact limited launch markers')
    return {'scope': 'REAL_RESET_AND_ONE_LAUNCH_EDGE_ONLY', 'markers': lines,
            'ram_model': False, 'weights_loaded': False, 'n0_numerics': False, 'full_block_claim': False}


def run(repo, work, call_phase, toolchain, host_emission, idma: Path, retained: Path, configuration: Path,
        *, stop_after_generation=False, diagnostic_callback=None, cluster_boundary=False, first_n0=False):
    need(type(stop_after_generation) is bool, 'explicit generation-only bool')
    need(type(cluster_boundary) is bool and not (stop_after_generation and cluster_boundary),
         'explicit disjoint cluster continuation bool')
    need(type(first_n0) is bool and (not first_n0 or (cluster_boundary and not stop_after_generation)),
         'explicit first N0 cluster compile-only bool')
    variant = stop_after_generation or cluster_boundary
    need(callable(diagnostic_callback) if variant else diagnostic_callback is None,
         'cluster generation callback pairing')
    repo, work, idma, retained, configuration = map(clean, (repo, work, idma, retained, configuration))
    for root in (repo, HERE, idma, retained, configuration, clean(toolchain['verilator_root'])):
        need(work != root and root not in work.parents and work not in root.parents, 'fresh disjoint work root')
    need(not os.path.lexists(work), 'work already exists')
    pins, buffers, support, lexical = load(repo)
    n0_catalog, n0_fixtures = load_first_n0(repo) if first_n0 else (None, None)
    fixtures = tuple(n0_fixtures.items()) if first_n0 else (
        ('short_launch.cpp', buffers['short_launch.cpp']), ('canonical_launch.hpp', buffers[LAUNCH]))
    before = closure(support, idma, retained, configuration, host_emission['sv'], buffers,
                     fifo_valid_split=variant)
    source_map = generation_source_map(before, idma, retained) if variant else None
    verify_tools(support, toolchain)
    emission_before = verify_emission(support, host_emission)
    ports = unique_json(buffers[CONTRACT])['HOST_PORTS']
    old_umask = os.umask(0o077)
    try:
        support.fresh_directory(work)
        for name in ('obj', 'fixtures', 'home', 'tmp'):
            support.fresh_directory(work / name)
        for name, raw in fixtures:
            fd = os.open(work / 'fixtures' / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                need(stream.write(raw) == len(raw), 'short fixed fixture write')
        save(work / 'INPUTS_BEFORE.json', before)
        save(work / 'SOURCE_INPUTS.json', {'pins': pins, 'emission': emission_before, 'backend': toolchain['backend'], 'configured_runtime': toolchain['configured_runtime'], 'host_programs': toolchain['host_programs']})
        argv = commands(work, toolchain['backend'], before, configuration)
        if first_n0:
            command = argv['host93_cpp_generate']
            need(command.count('--exe') == 1 and
                 command[command.index('--exe') + 1] == str(work / 'fixtures/short_launch.cpp'),
                 'fixed first N0 generation command')
            command[command.index('--exe') + 1] = str(work / 'fixtures/first_n0_main.cpp')
        env = environment(work, toolchain['verilator_root'])
        results = {}; witness = None; previous = None; qualification = None
        frozen_generated = None; executed_elf = None; generation_report = None
        phases = ('host93_cpp_generate',) if stop_after_generation else (
            ('host93_cpp_generate', 'host93_cpp_compile') if first_n0 else
            ('host93_cpp_generate', 'host93_cpp_compile', 'host93_reset_launch'))
        for phase in phases:
            need(closure(support, idma, retained, configuration, host_emission['sv'], buffers,
                         fifo_valid_split=variant) == before, 'pre-phase input drift')
            verify_tools(support, toolchain)
            stable_sources(repo, pins, buffers)
            if first_n0:
                stable_first_n0(repo, n0_catalog, n0_fixtures, support, work)
            need(verify_emission(support, host_emission) == emission_before, 'pre-phase emission drift')
            for name, raw in fixtures:
                need(small_read(work / 'fixtures' / name, len(raw), sha(raw)) == raw, 'fixture drift')
            if frozen_generated is not None:
                for name, pin in frozen_generated.items():
                    need(support.identity(work / name, 128 * 1024**2) == pin, 'generated source changed before phase')
            if phase == 'host93_reset_launch':
                executed_elf = support.identity(work / 'obj/VHostBlockTop', 512 * 1024**2)
                parent, fd, unused = support.regular_fd(work / 'obj/VHostBlockTop')
                try:
                    need(os.read(fd, 4) == b'\x7fELF', 'new host is not an ELF')
                finally:
                    os.close(fd); os.close(parent)
            if phase != 'host93_cpp_generate':
                witness = (cluster_generated_witness(support, previous, lexical, ports, generation_report,
                           phase == 'host93_reset_launch', before['sv']['path']) if cluster_boundary else
                           generated_witness(support, previous, lexical, ports, phase == 'host93_reset_launch', before['sv']['path']))
            bound = LIMITS[phase]
            if variant and phase == 'host93_cpp_generate':
                native_failed = False; callback_error = None
                try:
                    result = call_phase(phase, argv[phase], work, dict(env), dict(bound))
                except BaseException:
                    native_failed = True
                    raise
                finally:
                    try:
                        generation_report = diagnostic_callback(work, source_map)
                    except BaseException as error:
                        if not native_failed:
                            callback_error = error
            else:
                result = call_phase(phase, argv[phase], work, dict(env), dict(bound))
            record = result['record']
            need(record.get('exit_code') == 0 and record.get('cleanup_confirmed') is True, 'phase failed or cleanup unconfirmed')
            if variant and phase == 'host93_cpp_generate' and callback_error is not None:
                raise callback_error
            if cluster_boundary and phase == 'host93_cpp_generate':
                validate_cluster_census(generation_report)
                generation_report = unique_json(json.dumps(generation_report, sort_keys=True, allow_nan=False).encode())
            need(type(result['raw_log']) is bytes and len(result['raw_log']) <= bound['log_bytes'], 'phase raw log bound')
            need(closure(support, idma, retained, configuration, host_emission['sv'], buffers,
                         fifo_valid_split=variant) == before, 'post-phase input drift')
            verify_tools(support, toolchain)
            stable_sources(repo, pins, buffers)
            if first_n0:
                stable_first_n0(repo, n0_catalog, n0_fixtures, support, work)
            need(verify_emission(support, host_emission) == emission_before, 'post-phase emission drift')
            tree = support.tree_inventory(work, bound['tree_bytes'], bound['file_count'], bound['entry_count'], 128 * 1024**2 if phase == 'host93_cpp_generate' else 512 * 1024**2)
            if stop_after_generation:
                result_pin = save(work / (phase + '_TREE.json'), tree)
                results[phase] = {'exit_code': 0, 'cleanup_confirmed': True,
                                  'log_sha256': sha(result['raw_log']), 'usage': result['usage'],
                                  'evidence_root': str(result['evidence_root']), 'tree': result_pin}
                save(work / 'INPUTS_AFTER.json', before)
                report = {'status': 'GENERATION_DIAGNOSTIC_ONLY', 'diagnostic_only': True,
                          'phases': results, 'source_count': 307, 'include_count': 8,
                          'define_count': 4, 'inputs_unchanged': True,
                          'host_qualification_claim': False,
                          'ram_or_weights_or_n0_or_full_block_claim': False}
                save(work / 'GENERATION_ONLY_RESULT.json', report)
                return report
            if frozen_generated is None:
                frozen_generated = {p: {k: row[k] for k in ('bytes', 'sha256', 'mode')} for p, row in tree['entries'].items() if row['kind'] == 'regular' and p.startswith('obj/') and p.endswith(('.cpp', '.h', '.mk', '.f', '.sv', '.vlt'))}
                need(bool(frozen_generated), 'no generated source closure')
            else:
                for name, pin in frozen_generated.items():
                    need(support.identity(work / name, 128 * 1024**2) == pin, 'generated source changed after phase')
            witness = (cluster_generated_witness(support, tree, lexical, ports, generation_report,
                       phase != 'host93_cpp_generate', before['sv']['path']) if cluster_boundary else
                       generated_witness(support, tree, lexical, ports, phase != 'host93_cpp_generate', before['sv']['path']))
            if phase == 'host93_reset_launch':
                qualification = check_log(result['raw_log'])
            result_pin = save(work / (phase + '_TREE.json'), tree)
            results[phase] = {'exit_code': 0, 'cleanup_confirmed': True, 'log_sha256': sha(result['raw_log']),
                              'usage': result['usage'], 'evidence_root': str(result['evidence_root']), 'tree': result_pin}
            previous = tree
        if first_n0:
            elf = compiled_first_n0_elf(support, work, previous)
            after = closure(support, idma, retained, configuration, host_emission['sv'], buffers,
                            fifo_valid_split=variant)
            need(after == before, 'final first N0 input drift')
            stable_sources(repo, pins, buffers)
            stable_first_n0(repo, n0_catalog, n0_fixtures, support, work)
            need(verify_emission(support, host_emission) == emission_before, 'final first N0 emission drift')
            verify_tools(support, toolchain)
            need(compiled_first_n0_elf(support, work, previous) == elf, 'final first N0 ELF drift')
            save(work / 'INPUTS_AFTER.json', after)
            report = {'status': 'COMPILED_FIRST_N0_FIXTURE_ONLY', 'compiled_executable': elf,
                      'generated_witness': witness, 'phases': results,
                      'source_count': 307, 'include_count': 8, 'define_count': 4,
                      'fixture_catalog': {'bytes': FIRST_N0_CATALOG_SIZE, 'sha256': FIRST_N0_CATALOG_SHA},
                      'inputs_unchanged': True, 'execution_qualification': 'NOT_RUN',
                      'current_abi_or_runtime_handles_claim': False,
                      'ram_or_weights_or_n0_or_full_block_claim': False}
            save(work / 'RESULT.json', report)
            return report
        elf_path = work / 'obj/VHostBlockTop'
        elf = {'path': str(elf_path), **support.identity(elf_path, 512 * 1024**2)}
        need(int(elf['mode'], 8) & 0o111 and {k: elf[k] for k in ('bytes', 'sha256', 'mode')} == executed_elf, 'new host ELF changed around execution')
        after = closure(support, idma, retained, configuration, host_emission['sv'], buffers,
                                fifo_valid_split=variant)
        need(after == before, 'final input drift')
        save(work / 'INPUTS_AFTER.json', after)
        report = {'status': 'PASS_NEW_HOST_RESET_AND_ONE_LAUNCH_ONLY', 'elf': elf,
                  'qualification': qualification, 'generated_witness': witness, 'phases': results,
                  'source_count': 307, 'include_count': 8, 'define_count': 4,
                  'inputs_unchanged': True, 'current_abi_or_runtime_handles_claim': False,
                  'ram_or_weights_or_n0_or_full_block_claim': False}
        save(work / 'RESULT.json', report)
        return report
    except Exception as error:
        failed = {'status': 'FAILED_HOST_EXECUTION', 'error': {'type': type(error).__name__, 'message': str(error)[:2048]}, 'production_or_numerical_claim': False}
        if work.is_dir() and not work.is_symlink():
            try:
                after = closure(support, idma, retained, configuration, host_emission['sv'], buffers,
                                fifo_valid_split=variant)
                failed['input_postcheck'] = {'unchanged': after == before, 'sha256': sha(json.dumps(after, sort_keys=True).encode())}
            except Exception as post_error:
                failed['input_postcheck'] = {'unchanged': False, 'error': str(post_error)[:1024]}
            try:
                tree = support.tree_inventory(work, 2048 * 1024**2, 32768, 65536, 512 * 1024**2)
                failed['tree'] = save(work / 'FAILED_TREE.json', tree)
            except Exception as tree_error:
                failed['tree_error'] = str(tree_error)[:1024]
            try:
                save(work / 'FAILED.json', failed)
            except Exception:
                pass  # A private receipt failure must preserve the original failure.
        raise
    finally:
        os.umask(old_umask)
