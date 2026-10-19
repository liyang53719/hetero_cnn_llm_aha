"""Thin FIFO-ready preflight; source import never acquires or invokes software.

The owning coordinator supplies its existing supervised call_phase and shared
job deadline. Only its icarus_acquire, fifo_compile and fifo_run phases are used.
Four already-verified source buffers are rebound to fixed pins before either
reviewed Python helper is compiled. No whole micro-diagnostic job is required.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loads')
import hashlib
import os
from pathlib import Path
import types

MIB = 1024**2
MICRO = 'candidates/host93_micro_diagnostics/'
BASE = 'candidates/host93_ci_recovery/fifo_preflight/'
RUNNER = MICRO + 'run.py'
ACQUISITION = MICRO + 'icarus_stage.py'
CASES = MICRO + 'fixtures/fifo_valid_split_cases.sv'
MITER = BASE + 'fifo_ready_split_miter.sv'
REQUIRED_SOURCES = {
    RUNNER: {'bytes': 53278, 'sha256': '235a619fc7d304578ff78a958c173a33cb50d1a860dbf56fe2051fd4396ba3b8'},
    ACQUISITION: {'bytes': 39139, 'sha256': '907dd10148db6d3de4e614453fb130638d2149ee523b16b4aa97246d04c29554'},
    CASES: {'bytes': 11336, 'sha256': '90ec11c7a463bfebff87c2e026204cc84de37bd19b6ed5013eb817d1e7abb4e1'},
    MITER: {'bytes': 5992, 'sha256': 'f243a444637c373cacac66a78cffafaf882b2526ae0108bd396b6e9e4be1ee54'},
}
# Fixed scalar limits match the existing reviewed micro supervisor contract.
ACQUIRE_LIMITS = {'total_seconds': 120, 'work_seconds': 90, 'cpu_seconds': 40,
    'as_bytes': 512*MIB, 'fsize_bytes': 4*MIB, 'tree_bytes': 16*MIB,
    'log_bytes': 65536, 'sample_rows': 122, 'file_count': 512, 'entry_count': 1024}
MICRO_LIMITS = {'total_seconds': 30, 'work_seconds': 10, 'cpu_seconds': 10,
    'as_bytes': 512*MIB, 'fsize_bytes': 4*MIB, 'tree_bytes': 8*MIB,
    'log_bytes': 65536, 'sample_rows': 32, 'file_count': 512, 'entry_count': 1024}
TRANSPORT_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
    'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
    'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE')
# Finite public labels only; the values must match the verified helper below.
PARENT_CONTRACTS = {'PHASE_LOG_POSTFLIGHT': 'PHASE_LOG_BOUND',
 'ICARUS_CONTRACT_LOAD': 'SOURCE_LOAD',
 'ICARUS_RECEIPT_READ': 'RECEIPT_READ',
 'ICARUS_RECEIPT_DECODE': 'INPUT_JSON',
 'ICARUS_STAGE_VERIFY': 'PACKAGE_STAGE',
 'ICARUS_PACKAGE_ELF': 'PACKAGE_ELF',
 'ICARUS_LIBRARY_IDENTITIES': 'LIBRARY_IDENTITIES',
 'ICARUS_LIBRARY_RECEIPT': 'RECEIPT_WRITE',
 'ICARUS_TOOL_IDENTITIES': 'TOOL_IDENTITY',
 'FIFO_WORKROOT': 'WORKROOT',
 'FIFO_COMPILED_IDENTITY': 'COMPILED_IDENTITY',
 'FIFO_COMPILED_NONEMPTY': 'COMPILED_EMPTY',
 'FIFO_COMPILED_READ': 'COMPILED_READ',
 'FIFO_COMPILED_MODULES': 'VVP_MODULES',
 'FIFO_MODULE_RECEIPT': 'RECEIPT_WRITE',
 'FIFO_RUN_SAME_COMPILED': 'COMPILED_CHANGED',
 'FIFO_RUN_OBSERVATION': 'FIFO_OBSERVATION',
 'FINAL_SOURCE_IDENTITIES': 'SOURCE_CHANGED',
 'FIFO_BEFORE_COMPILE_STAGE': 'PACKAGE_STAGE',
 'FIFO_BEFORE_COMPILE_FIXTURES': 'FIXTURE_CHANGED',
 'FIFO_BEFORE_COMPILE_LIBRARIES': 'LIBRARY_CHANGED',
 'FIFO_AFTER_COMPILE_STAGE': 'PACKAGE_STAGE',
 'FIFO_AFTER_COMPILE_FIXTURES': 'FIXTURE_CHANGED',
 'FIFO_AFTER_COMPILE_LIBRARIES': 'LIBRARY_CHANGED',
 'FIFO_AFTER_RUN_STAGE': 'PACKAGE_STAGE',
 'FIFO_AFTER_RUN_FIXTURES': 'FIXTURE_CHANGED',
 'FIFO_AFTER_RUN_LIBRARIES': 'LIBRARY_CHANGED',
 'FIFO_AFTER_COMPILE_TREE': 'TREE_INVENTORY',
 'FIFO_AFTER_RUN_TREE': 'TREE_INVENTORY',
 'LIBRARY_BZ2_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_BZ2_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_BZ2_READ': 'LIBRARY_READ',
 'LIBRARY_BZ2_ELF': 'LIBRARY_ELF',
 'LIBRARY_BZ2_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_C_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_C_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_C_READ': 'LIBRARY_READ',
 'LIBRARY_C_ELF': 'LIBRARY_ELF',
 'LIBRARY_C_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_GCC_S_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_GCC_S_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_GCC_S_READ': 'LIBRARY_READ',
 'LIBRARY_GCC_S_ELF': 'LIBRARY_ELF',
 'LIBRARY_GCC_S_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_M_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_M_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_M_READ': 'LIBRARY_READ',
 'LIBRARY_M_ELF': 'LIBRARY_ELF',
 'LIBRARY_M_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_READLINE_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_READLINE_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_READLINE_READ': 'LIBRARY_READ',
 'LIBRARY_READLINE_ELF': 'LIBRARY_ELF',
 'LIBRARY_READLINE_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_STDCXX_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_STDCXX_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_STDCXX_READ': 'LIBRARY_READ',
 'LIBRARY_STDCXX_ELF': 'LIBRARY_ELF',
 'LIBRARY_STDCXX_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_Z_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_Z_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_Z_READ': 'LIBRARY_READ',
 'LIBRARY_Z_ELF': 'LIBRARY_ELF',
 'LIBRARY_Z_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_TINFO_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_TINFO_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_TINFO_READ': 'LIBRARY_READ',
 'LIBRARY_TINFO_ELF': 'LIBRARY_ELF',
 'LIBRARY_TINFO_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_LOADER_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_LOADER_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_LOADER_READ': 'LIBRARY_READ',
 'LIBRARY_LOADER_ELF': 'LIBRARY_ELF',
 'LIBRARY_LOADER_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_READLINE_TRANSITIVE': 'LIBRARY_TRANSITIVE'}
REQUIRE_CODES = {'fixed system library directory': 'LIBRARY_PATH',
 'protected root-owned host library': 'LIBRARY_OWNERSHIP',
 'stable library resolution': 'LIBRARY_STABLE',
 'target readline transitive dependency': 'LIBRARY_TRANSITIVE',
 'ELF64 little endian': 'ELF_ENCODING',
 'fixed x86-64 ELF header': 'ELF_HEADER',
 'ELF program-header bound': 'ELF_PROGRAM_HEADERS',
 'ELF segment bound': 'ELF_SEGMENT',
 'ELF dynamic bound': 'ELF_DYNAMIC_BOUND',
 'fixed dynamic interpreter': 'ELF_INTERPRETER',
 'one dynamic table': 'ELF_DYNAMIC_COUNT',
 'no RPATH and exact string table': 'ELF_DYNAMIC_TAGS',
 'mapped bounded string table': 'ELF_STRING_TABLE',
 'dynamic dependency offset': 'ELF_DEPENDENCY_OFFSET',
 'bounded soname': 'ELF_SONAME',
 'fixed dependency soname': 'ELF_DEPENDENCY_NAME',
 'unique needed sonames': 'ELF_DEPENDENCY_DUPLICATE',
 'absolute normalized ASCII path': 'INPUT_PATH_SYNTAX',
 'symlink refused': 'INPUT_SYMLINK',
 'bounded regular input': 'INPUT_REGULAR',
 'stable same-buffer input': 'INPUT_CHANGED',
 'fixed source identity': 'INPUT_SHA'}

# Counts of EXIT0_CLEANED FIFO-prefix rows allowed for each public boundary.
# A failed native row keeps its own original exception and is never relabelled
# as a clean-parent postflight. These counts bind labels to actual progress.
CONTRACT_COMPLETED_COUNTS = {
    name: ((0,) if name in ('ICARUS_CONTRACT_LOAD', 'FIFO_WORKROOT') else
           (0, 1, 2, 3) if name == 'FINAL_SOURCE_IDENTITIES' else
           (1, 2, 3) if name == 'PHASE_LOG_POSTFLIGHT' or name.startswith('LIBRARY_') else
           (0, 1) if name == 'FIFO_BEFORE_COMPILE_FIXTURES' else
           (1,) if name.startswith(('ICARUS_', 'FIFO_BEFORE_COMPILE_')) else
           (3,) if name.startswith(('FIFO_AFTER_RUN_', 'FIFO_RUN_')) else
           (2,))
    for name in PARENT_CONTRACTS
}


def _load_helpers(repo, buffers):
    # Verify the entire required closure first, then compile these exact buffers.
    try:
        if type(buffers) is not dict:
            raise ValueError('fixed source buffer mapping required')
        for name, pin in REQUIRED_SOURCES.items():
            raw = buffers[name]
            if (type(raw) is not bytes or len(raw) != pin['bytes'] or
                    hashlib.sha256(raw).hexdigest() != pin['sha256']):
                raise ValueError('fixed FIFO source buffer required')
        micro = types.ModuleType('fixed_fifo_reviewed_micro')
        micro.__file__ = str(Path(repo) / RUNNER)
        exec(compile(buffers[RUNNER], micro.__file__, 'exec', dont_inherit=True), micro.__dict__)
        with micro.contract_check('ICARUS_CONTRACT_LOAD'):
            micro.require(all(micro.PARENT_CONTRACTS.get(k) == v for k, v in PARENT_CONTRACTS.items())
                and micro.REQUIRE_CODES == REQUIRE_CODES, 'unchanged finite FIFO labels')
            micro.require(micro.ACQUIRE_LIMITS == ACQUIRE_LIMITS and micro.MICRO_LIMITS == MICRO_LIMITS,
                          'unchanged FIFO limits')
            acquisition = micro.module(buffers[ACQUISITION], Path(repo) / ACQUISITION,
                                       'fixed_fifo_reviewed_acquisition')
        return micro, acquisition
    except BaseException as error:
        # The verified context manager preserves finer labels, including errors
        # from module compile. Before it exists, use one finite load boundary.
        try:
            if not hasattr(error, 'safe_contract_boundary'):
                error.safe_contract_boundary = 'ICARUS_CONTRACT_LOAD'
                error.safe_contract_code = 'SOURCE_LOAD'
        except BaseException:
            pass
        raise


def _unchanged_sources(micro, repo, buffers):
    for name, pin in REQUIRED_SOURCES.items():
        micro.require(micro.exact(repo / name, pin) == buffers[name], 'unchanged FIFO source buffers')


def _write_fixture(micro, target, raw, pin):
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        micro.require(stream.write(raw) == len(raw), 'complete FIFO fixture write')
        stream.flush()
        os.fsync(stream.fileno())
    micro.require(micro.exact(target, pin) == raw, 'same FIFO fixture readback')


def _phase(micro, call_phase, name, argv, cwd, environment, bounds, postflight):
    failure = None
    try:
        result = call_phase(name, argv, cwd, environment, dict(bounds))
    except BaseException as error:
        failure = error
        raise
    finally:
        # Inspect even failed children, but a postflight must never replace the
        # original phase exception (including cancellation and timeout).
        try:
            postflight()
        except BaseException:
            if failure is None:
                raise
    with micro.contract_check('PHASE_LOG_POSTFLIGHT'):
        micro.require(type(result) is dict and type(result.get('raw_log')) is bytes and
                      len(result['raw_log']) <= bounds['log_bytes'], 'bounded complete FIFO phase log')
    return result


def run(repo, work, call_phase, support, buffers):
    """Run exactly three supervised phases; expose no private paths or receipts.

    support is the existing filesystem support from fixed_support(repo), not
    the supervisor. buffers is the coordinator's verified repo-relative map.
    call_phase owns phase ordering, actual process cleanup and shared deadline.
    """
    micro, acquisition = _load_helpers(repo, buffers)
    with micro.contract_check('FIFO_WORKROOT'):
        repo, work = micro.path(repo), micro.path(work)
        micro.require(repo.is_dir() and work.parent.is_dir() and not os.path.lexists(work)
            and not work.is_relative_to(repo) and not repo.is_relative_to(work), 'fresh disjoint FIFO workroot')
        work.mkdir(mode=0o700)
        for name in ('home', 'tmp', 'fixtures', 'fifo'):
            (work / name).mkdir(mode=0o700)
    with micro.contract_check('FINAL_SOURCE_IDENTITIES'):
        _unchanged_sources(micro, repo, buffers)
    fixtures = ((MITER, work / 'fixtures/fifo_ready_split_miter.sv'),
                (CASES, work / 'fixtures/fifo_valid_split_cases.sv'))
    with micro.contract_check('FIFO_BEFORE_COMPILE_FIXTURES'):
        for name, target in fixtures:
            _write_fixture(micro, target, buffers[name], REQUIRED_SOURCES[name])
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
           'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC', 'PYTHONNOUSERSITE': '1',
           'PYTHONDONTWRITEBYTECODE': '1'}
    transport = dict(env)
    for key in TRANSPORT_KEYS:
        if key in os.environ:
            transport[key] = os.environ[key]
    stage = work / 'icarus'
    def sources_postflight():
        with micro.contract_check('FINAL_SOURCE_IDENTITIES'):
            _unchanged_sources(micro, repo, buffers)
    _phase(micro, call_phase, 'icarus_acquire',
           micro.acquisition_argv(buffers[ACQUISITION], stage, repo / ACQUISITION),
           work, transport, ACQUIRE_LIMITS, sources_postflight)
    with micro.contract_check('ICARUS_RECEIPT_READ'):
        package_raw = micro.read(stage / 'RECEIPT.json', 32768)
    with micro.contract_check('ICARUS_RECEIPT_DECODE'):
        package = micro.decode(package_raw)
    with micro.contract_check('ICARUS_STAGE_VERIFY'):
        acquisition.verify_stage(stage, package)
        micro.require(len(package['selected']) == 39, 'fixed selected package count')
    with micro.contract_check('ICARUS_PACKAGE_ELF'):
        micro.verify_package_elf(stage, package)
    with micro.contract_check('ICARUS_LIBRARY_IDENTITIES'):
        libraries = micro.library_identities()
    with micro.contract_check('ICARUS_LIBRARY_RECEIPT'):
        micro.write_json(work / 'icarus_libraries_private.json', libraries)
    with micro.contract_check('ICARUS_TOOL_IDENTITIES'):
        members = {row['path']: row for row in package['selected']}
        tools = {alias: {key: members['usr/bin/' + name][key] for key in ('bytes', 'sha256')}
                 for alias, name in (('icarus', 'iverilog'), ('vvp', 'vvp'))}
        micro.require(tools == micro.ICARUS_IDENTITIES, 'fixed Icarus and vvp identity')
    ivl = stage / 'usr/lib/x86_64-linux-gnu/ivl'
    fifo = work / 'fifo'
    def fifo_identity(boundary):
        with micro.contract_check(boundary + '_STAGE'):
            acquisition.verify_stage(stage, package)
        with micro.contract_check(boundary + '_FIXTURES'):
            _unchanged_sources(micro, repo, buffers)
            for name, target in fixtures:
                micro.exact(target, REQUIRED_SOURCES[name])
        with micro.contract_check(boundary + '_LIBRARIES'):
            micro.require(micro.library_identities() == libraries, 'unchanged Icarus library closure')
    def compile_postflight():
        fifo_identity('FIFO_AFTER_COMPILE')
        with micro.contract_check('FIFO_AFTER_COMPILE_TREE'):
            support.tree_inventory(fifo, 8*MIB, 512, 1024, 4*MIB)
    fifo_identity('FIFO_BEFORE_COMPILE')
    _phase(micro, call_phase, 'fifo_compile',
           [str(stage / 'usr/bin/iverilog'), '-B' + str(ivl), '-g2012', '-s',
            'fifo_valid_split_tb', '-o', str(fifo / 'fifo.vvp')] + [str(p) for _, p in fixtures],
           fifo, env, MICRO_LIMITS, compile_postflight)
    with micro.contract_check('FIFO_COMPILED_IDENTITY'):
        compiled = support.identity(fifo / 'fifo.vvp', 4*MIB)
    with micro.contract_check('FIFO_COMPILED_NONEMPTY'):
        micro.require(compiled['bytes'] > 0, 'new compiled FIFO')
    with micro.contract_check('FIFO_COMPILED_READ'):
        compiled_raw = support.checked_read(fifo / 'fifo.vvp', compiled['bytes'], compiled['sha256'])
    with micro.contract_check('FIFO_COMPILED_MODULES'):
        modules = micro.verify_vvp_modules(compiled_raw, ivl)
    with micro.contract_check('FIFO_MODULE_RECEIPT'):
        micro.write_json(work / 'fifo_modules_private.json', {'modules': modules, 'staged_only': True})
    def run_postflight():
        fifo_identity('FIFO_AFTER_RUN')
        with micro.contract_check('FIFO_RUN_SAME_COMPILED'):
            micro.require(support.identity(fifo / 'fifo.vvp', 4*MIB) == compiled, 'same compiled FIFO')
        with micro.contract_check('FIFO_AFTER_RUN_TREE'):
            support.tree_inventory(fifo, 8*MIB, 512, 1024, 4*MIB)
    result = _phase(micro, call_phase, 'fifo_run',
                    [str(stage / 'usr/bin/vvp'), '-N', '-M' + str(ivl), str(fifo / 'fifo.vvp')],
                    fifo, env, MICRO_LIMITS, run_postflight)
    with micro.contract_check('FIFO_RUN_OBSERVATION'):
        observed = micro.fifo_observation(result['raw_log'], fixtures[1][1])
    with micro.contract_check('FINAL_SOURCE_IDENTITIES'):
        _unchanged_sources(micro, repo, buffers)
    return {**observed, 'tools': tools}
