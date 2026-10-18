"""Fixed derived-backend tiny gate; every new actual identity is PENDING."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Python -I -S -B is required before any local module load.')
if __name__ == '__main__':
    raise SystemExit('Use the separately pinned loader; direct unverified loading is refused.')

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import signal
import stat
import subprocess
import time
import types

HERE = Path(__file__).absolute().parent
ROOT = Path('/UNBOUND')
PLAN_BYTES = 19051
PLAN_SHA = 'c0a1f057217fb499bc44a1b6c1a79d5b3f6af056105d0e6f4d763d3f788688f2'
SUPPORT_PIN = {'path': '/UNBOUND/repo/development_snapshots/canonical_host93_fixed_core_build_source_20261018/run_build_gate.py', 'bytes': 28551, 'sha256': '8f1560c5f0a8e78a991f98c30031cbd18df220e3eb82cf2c78de4ec0438bdafb'}
PHASES = ('version', 'generate', 'compile', 'run')
REQUIRED = ('source_gate_review', 'derived_backend_build_review', 'new_backend_binary',
            'derived_patch_identity', 'configured_runtime_inputs', 'host_program_identities')
B = str(ROOT / 'host93_verilator_seqnum_derived_build_attempt_v1_20261018/verilator')
W = str(ROOT / 'host93_verilator_seqnum_micro_work_attempt_v1_20261018')
F = str(ROOT / 'candidate_host93_verilator_micro_source_v1_20261018T2232/fixtures')
CONTRACT_PIN = {'path': '/UNBOUND/package/init_contract.py', 'bytes': 5127, 'sha256': 'd070d9a0841ea034dd684fad3ca9fd4fa32a1ed1afa1417bf4f4a88625996365'}
DEADLINE_PHASE = 'unarmed'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def initial_read(pin):
    path = Path(pin['path'])
    size = pin['bytes']
    require(path.is_absolute() and '..' not in path.parts and type(size) is int and
            0 <= size <= 4 * 1024**2, 'bounded absolute bootstrap input')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            newer = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = newer
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'bootstrap regular size')
            parts = []
            count = 0
            while count <= size:
                part = os.read(fd, min(65536, size + 1 - count))
                if not part:
                    break
                parts.append(part)
                count += len(part)
            raw = b''.join(parts)
            key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(len(raw) == size and digest(raw) == pin['sha256'] and
                    key(before) == key(os.fstat(fd)) ==
                    key(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'bootstrap raw identity')
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def support_module():
    raw = initial_read(SUPPORT_PIN)
    module = types.ModuleType('fixed_build_support_for_micro')
    module.__file__ = SUPPORT_PIN['path']
    exec(compile(raw, SUPPORT_PIN['path'], 'exec', dont_inherit=True), module.__dict__)
    return module


def load_plan():
    return json.loads(initial_read({'path': str(HERE / 'PLAN.json'), 'bytes': PLAN_BYTES, 'sha256': PLAN_SHA}))


def expected_argv(phase):
    return {
        'version': [B + '/bin/verilator_bin', '--version'],
        'generate': [B + '/bin/verilator_bin', '--cc', '--hierarchical', '--exe', '--threads', '1',
                     '--build-jobs', '1', '--verilate-jobs', '1', '--top-module', 'micro_top',
                     '--prefix', 'Vmicro_top', '--Mdir', W + '/obj', F + '/tiny.sv', F + '/main.cpp'],
        'compile': ['/usr/bin/make', '-C', W + '/obj', '-f', 'Vmicro_top.mk', '-j1',
                    'OPT_FAST=-O0', 'OPT_SLOW=-O0', 'OPT_GLOBAL=-O0', 'Vmicro_top'],
        'run': [W + '/obj/Vmicro_top']}[phase]


def validate_contract(plan, phase):
    require(phase in PHASES and tuple(plan['phases']) == PHASES, 'fixed four phase order')
    require(plan['work_root'] == W and plan['build_root'] == B, 'fixed roots')
    require(plan['reused_support_candidate'] == SUPPORT_PIN, 'fixed support identity')
    require(tuple(plan['required_actual']) == REQUIRED, 'fixed actual key order')
    require(plan['parent_only_actual'] is True, 'parent only')
    require(plan['initializer_contract'] == CONTRACT_PIN, 'fixed finite initialization contract')
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC',
           'HOME': W + '/home', 'TMPDIR': W + '/tmp', 'SHELL': '/bin/sh', 'VERILATOR_ROOT': B,
           'VERILATOR_BIN': 'verilator_bin', 'MAKE': '/usr/bin/make', 'CXX': '/usr/bin/g++',
           'AR': '/usr/bin/ar', 'PERL': '/usr/bin/perl', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONNOUSERSITE': '1', 'OBJCACHE': ''}
    require(plan['environment'] == env, 'fixed environment')
    for i, name in enumerate(PHASES):
        c = plan['phases'][name]
        expected = {
            'argv': expected_argv(name), 'cwd': W,
            'evidence_root': str(ROOT / ('host93_verilator_seqnum_micro_' + name + '_attempt_v1_20261018')),
            'total_seconds': (30, 120, 300, 30)[i], 'preflight_seconds': (10, 20, 40, 10)[i],
            'work_max_seconds': (10, 90, 240, 10)[i], 'work_stop_absolute_offset_seconds': (20, 110, 280, 20)[i],
            'cleanup_seconds': 5, 'postflight_reserved_seconds': (5, 5, 15, 5)[i],
            'cpu_seconds': (10, 90, 240, 10)[i], 'as_bytes': (512, 1024, 2048, 512)[i] * 1024**2,
            'fsize_bytes': (4, 8, 32, 4)[i] * 1024**2, 'tree_bytes': (1, 16, 96, 96)[i] * 1024**2,
            'log_bytes': 1024**2, 'sample_rows': (32, 122, 302, 32)[i], 'file_count': 512, 'entry_count': 1024,
            'expected_wall_seconds': (1, 10, 60, 1)[i], 'expected_peak_rss_mib': (64, 256, 768, 128)[i]}
        require(c == expected, 'fixed phase argv/budget/path contract: ' + name)


def pending_gate(plan, phase):
    validate_contract(plan, phase)
    require(plan['actual_entry_enabled'] is True, 'actual entry PENDING')
    for name in REQUIRED:
        require(type(plan['required_actual'][name]) is dict, name + ' PENDING')
    for name in PHASES[:PHASES.index(phase)]:
        require(type(plan['previous_actual'][name]) is dict, name + ' previous accepted actual PENDING')


def accepted_review(support, binding, phase=None):
    require(type(binding) is dict and set(binding) == {'manifest', 'summary', 'summary_claims'}, 'review binding shape')
    claims = binding['summary_claims']
    require(type(claims) is dict and type(claims.get('verdict')) is str and
            claims['verdict'].startswith(('PASS_', 'SOURCE_GO_')), 'explicit accepted review verdict')
    if phase is not None:
        require(claims.get('phase') == phase and claims.get('outer_exit') == 0, 'prior phase terminal review')
    return support.verify_review(binding)


def contract_module():
    raw = initial_read(CONTRACT_PIN)
    module = types.ModuleType('verified_finite_initializer_contract_for_micro')
    module.__file__ = CONTRACT_PIN['path']
    exec(compile(raw, CONTRACT_PIN['path'], 'exec', dont_inherit=True), module.__dict__)
    return module


def verify_patch_identity(support, build_summary, patch):
    require(type(patch) is dict and set(patch) == {'original_source', 'derived_source', 'patch_record'},
            'fixed derived patch identity shape')
    require(build_summary.get('derived_patch_identity') == patch, 'accepted build binds exact derived patch')
    original = {'path': str(ROOT / 'host93_verilator_fixed_build_attempt_v1_20261018/verilator/src/V3ProtectLib.cpp'),
                'bytes': 22417, 'sha256': 'bddc3100c2ce83d7a4fe4656b0ff33cca1be70ea9a8295037c6aea72bc0ec6c1'}
    derived = {'path': B + '/src/V3ProtectLib.cpp', 'bytes': 22430,
               'sha256': '380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb'}
    require(patch['original_source'] == original and patch['derived_source'] == derived,
            'exact original and single-initializer derived source identities')
    for pin in patch.values():
        support.fixed(pin)
    return patch


def verify_inputs(support, plan):
    support.fixed(globals()['__verified_runner_pin__'])
    initial_read({'path': str(HERE / 'PLAN.json'), 'bytes': PLAN_BYTES, 'sha256': PLAN_SHA})
    initial_read(SUPPORT_PIN)
    support.fixed(plan['frozen_fixture_manifest'])
    q = plan['source_qualification']
    support.fixed(q['manifest'])
    summary = json.loads(support.fixed(q['summary']))
    require(summary.get('selected_count') == 473 and summary.get('selected_bytes') == 11747893,
            'qualified original473 source evidence')
    for pin in plan['fixtures']:
        support.fixed(pin)
    for pin in plan['published_sources'].values():
        support.fixed(pin)
    actual = plan['required_actual']
    accepted_review(support, actual['source_gate_review'])
    built = accepted_review(support, actual['derived_backend_build_review'], 'derived_incremental')
    require(built.get('verdict') == 'PASS_ACTUAL_DERIVED_SEQNUM_INCREMENTAL_BUILD_ONLY', 'derived build-only verdict')
    patch = verify_patch_identity(support, built, actual['derived_patch_identity'])
    support.fixed(plan['initializer_contract_manifest'])
    initial_read(CONTRACT_PIN)
    binary = actual['new_backend_binary']
    require(binary['path'] == B + '/bin/verilator_bin' and set(binary) == {'path', 'bytes', 'sha256', 'mode'}, 'binary pin shape/path')
    require(support.identity(binary['path'], 64 * 1024**2) == {k: binary[k] for k in ('bytes', 'sha256', 'mode')}, 'new optimized binary identity')
    require(int(binary['mode'], 8) & 0o111, 'new binary executable')
    runtime = actual['configured_runtime_inputs']
    require(set(runtime) == {'include_inventory', 'wrappers'}, 'runtime closure binding shape')
    saved = json.loads(support.fixed(runtime['include_inventory']))
    require(saved['root'] == B + '/include', 'fixed include root')
    current = support.tree_inventory(B + '/include', 32 * 1024**2, 256, 512, 4 * 1024**2)
    require(current == saved, 'configured include subtree identity drift')
    require(set(runtime['wrappers']) == {'verilator', 'verilator_includer'}, 'fixed runtime wrappers')
    for name, pin in runtime['wrappers'].items():
        require(pin['path'] == B + '/bin/' + name, 'wrapper path')
        support.fixed(pin)
    programs = actual['host_program_identities']
    require(set(programs) == {'/usr/bin/make', '/usr/bin/g++', '/usr/bin/ar', '/usr/bin/perl', '/bin/sh'}, 'fixed direct host tools')
    for invoked, pin in programs.items():
        require(os.path.realpath(invoked) == pin['path'], 'host executable resolution changed')
        require(support.identity(pin['path'], 64 * 1024**2) ==
                {k: pin[k] for k in ('bytes', 'sha256', 'mode')}, 'host executable identity changed')
    return {'backend': binary, 'derived_patch_identity': patch,
            'runtime_inventory': runtime['include_inventory'], 'direct_host_tools': programs}


def verify_previous(support, plan, phase, compare_tree):
    last = None
    for name in PHASES[:PHASES.index(phase)]:
        previous = plan['previous_actual'][name]
        require(set(previous) == {'review', 'inventory', 'result'}, 'previous actual binding shape')
        reviewed = accepted_review(support, previous['review'], name)
        raw = support.fixed(previous['inventory'])
        result = json.loads(support.fixed(previous['result']))
        require(reviewed.get('work_tree_inventory_sha256') == previous['inventory']['sha256'] and
                result.get('work_tree_inventory_sha256') == previous['inventory']['sha256'] and
                result.get('phase') == name and result.get('native_exit') == 0 and
                result.get('cleanup_confirmed') is True, 'prior inventory/result/review binding')
        last = json.loads(raw)
    if compare_tree and last is not None:
        c = plan['phases'][PHASES[PHASES.index(phase) - 1]]
        current = support.tree_inventory(W, c['tree_bytes'], c['file_count'], c['entry_count'], c['fsize_bytes'])
        require(current == last, 'previous accepted work tree drift')
    return last


def projected_runner(support, plan, phase, evidence):
    supervisor, observer = support.projected_sources(plan, phase)
    pins = plan['projection_pins'][phase]
    for name, raw in (('supervisor', supervisor), ('observation', observer)):
        require(len(raw) == pins[name]['bytes'] and digest(raw) == pins[name]['sha256'], 'projected raw identity before compile')
    namespace = {'__builtins__': __builtins__, 'os': os, 'resource': resource, 'signal': signal,
                 'subprocess': subprocess, 'time': time, 'json': json, 'require': require,
                 'AS_LIMIT': plan['phases'][phase]['as_bytes'], 'BUILD_ENV': dict(plan['environment'])}
    exec(compile(observer, 'fixed_four_micro_observers', 'exec', dont_inherit=True), namespace)
    sampler = namespace['sample_leader']
    state = {'path': evidence / 'leader_samples.jsonl', 'identity': None, 'count': 0, 'next': None, 'start': None}
    namespace['sample_leader'] = lambda child: sampler(child, state)
    exec(compile(supervisor, 'fixed_five_micro_WNOWAIT', 'exec', dont_inherit=True), namespace)
    return namespace


def inventory_text(support, tree, relative):
    row = tree['entries'].get(relative)
    require(row is not None and row['kind'] == 'regular' and 0 < row['bytes'] <= 4 * 1024**2, 'small generated text missing: ' + relative)
    return support.checked_read(Path(tree['root']) / relative, row['bytes'], row['sha256']).decode('utf-8')


def hierarchy_witness(support, tree, compiled):
    names = tree['entries']
    candidates = [n for n in names if re.fullmatch(r'obj/Vmicro_leaf[A-Za-z0-9_]*__hierMkArgs\.f', n)]
    require(len(candidates) == 1, 'exactly one separately generated specialized leaf')
    tokens = shlex.split(inventory_text(support, tree, candidates[0]))
    def option(flag):
        require(tokens.count(flag) == 1 and tokens.index(flag) + 1 < len(tokens), 'unique child option ' + flag)
        return tokens[tokens.index(flag) + 1]
    leaf = option('--lib-create')
    require(re.fullmatch(r'micro_leaf[A-Za-z0-9_]*', leaf) is not None, 'bounded specialized leaf name')
    require(option('--hierarchical-child') == '1' and option('--top-module-encoded') == leaf, 'real child command')
    params = [v[len('-GSTEP='):] for v in tokens if v.startswith('-GSTEP=')]
    require(len(params) == 1, 'single STEP specialization')
    parsed = re.fullmatch(r"32'[sS]?([hHdD])([0-9a-fA-F_]+)", params[0])
    unsized_signed_hex = re.fullmatch(r"'[sS][hH]([0-9a-fA-F]+)", params[0])
    require(params[0] == '3' or (parsed is not None and int(parsed[2].replace('_', ''), 16 if parsed[1].lower() == 'h' else 10) == 3) or (unsized_signed_hex is not None and int(unsized_signed_hex[1], 16) == 3), 'STEP must be 3')
    child = 'V' + leaf
    wrapper_rel = child + '/' + leaf + '.sv'
    archive_rel = child + '/lib' + leaf + '.a'
    top_args = shlex.split(inventory_text(support, tree, 'obj/Vmicro_top__hierMkArgs.f'))
    require(wrapper_rel in top_args and F + '/tiny.sv' in top_args and
            top_args.index(wrapper_rel) < top_args.index(F + '/tiny.sv'), 'wrapper precedes original SV')
    top_mk = inventory_text(support, tree, 'obj/Vmicro_top.mk')
    hier_mk = inventory_text(support, tree, 'obj/Vmicro_top_hier.mk')
    require('include Vmicro_top_hier.mk' in top_mk and 'VM_HIER_LIBS' in hier_mk and
            archive_rel in hier_mk and child + '.mk' in hier_mk, 'separate library build graph')
    sv = inventory_text(support, tree, 'obj/' + wrapper_rel)
    cpp = inventory_text(support, tree, 'obj/' + child + '/' + leaf + '.cpp')
    initializer = contract_module().initialized_container(cpp.encode('utf-8'), leaf)
    require('chandle handle__V' in sv and 'handle__V = ' + leaf + '_protectlib_create' in sv,
            'instance-specific generated protected handle')
    boundary_names = [leaf + '_protectlib_' + suffix for suffix in ('create', 'combo_update', 'seq_update', 'final')]
    for name in boundary_names:
        require(name in sv and name in cpp, 'protected boundary source missing ' + name)
    require('new V' + leaf + '_container' in cpp and 'handlep__V->eval()' in cpp and
            'delete handlep__V' in cpp, 'generated handle allocation/evaluation/deletion')
    top_cpp = [n for n in names if re.fullmatch(r'obj/Vmicro_top[^/]*\.cpp', n)]
    require(0 < len(top_cpp) <= 48, 'bounded top C++ set')
    top_text = '\n'.join(inventory_text(support, tree, n) for n in top_cpp)
    require(len(top_text) <= 4 * 1024**2, 'bounded generated top inspection')
    for name in boundary_names:
        require(name in top_text, 'top invokes real boundary ' + name)
    for name in ('hm_read_count', 'hm_read_delta', 'hm_set_delta'):
        require(name in inventory_text(support, tree, 'obj/Vmicro_top__Dpi.h') and name in top_text,
                'top export declaration/implementation missing')
    require('Verilated::dpiScope()' in top_text and 'exportFind' in top_text and 'exportInsert' in top_text,
            'top DPI scope dispatch and registration')
    child_cpp = [n for n in names if n.startswith('obj/' + child + '/V' + leaf) and n.endswith('.cpp')]
    require(0 < len(child_cpp) <= 48, 'separate child implementation units')
    if compiled:
        row = names.get('obj/' + archive_rel)
        require(row is not None and row['kind'] == 'regular' and row['bytes'] > 0, 'child static archive missing')
        require(names.get('obj/Vmicro_top__ALL.a', {}).get('bytes', 0) > 0 and
                names.get('obj/Vmicro_top', {}).get('bytes', 0) > 0, 'linked model artifacts missing')
    return {'status': 'STRUCTURAL_WITNESS_REQUIRES_INDEPENDENT_REVIEW', 'specialized_leaf': leaf,
            'child_args': candidates[0], 'wrapper': 'obj/' + wrapper_rel, 'child_archive': 'obj/' + archive_rel,
            'top_cpp': top_cpp, 'child_cpp': child_cpp, 'protected_boundary_names': boundary_names,
            'dpi_scope': 'dual.micro_top', 'compiled_artifacts_present': compiled,
            'derived_initializer_contract': initializer,
            'original_uninitialized_failure_preserved': True,
            'not_general_undefined_behavior_clearance': True,
            'does_not_claim_direct_leaf_memory_dpi': True}


def check_log(plan, phase, raw, witness=None):
    require(len(raw) <= plan['phases'][phase]['log_bytes'], 'phase aggregate log cap')
    text = raw.decode('utf-8')
    if phase == 'version':
        require(len(raw) <= 4096 and len(text.splitlines()) == 1 and text.startswith('Verilator '), 'new binary version output')
    elif phase == 'generate':
        require(re.search(r'(^|\n)[^\n]*(?:g\+\+|gcc|clang\+\+|clang)\s[^\n]*\s-c\s', text) is None,
                'generation unexpectedly compiled native C++')
    elif phase == 'compile':
        leaf = witness['specialized_leaf']
        require(leaf + '.cpp' in text and 'Vmicro_top__ALL.a' in text and
                re.search(r'-o\s+Vmicro_top(?:\s|$)', text),
                'separate child compile and actual top link log required')
    elif phase == 'run':
        expected = '\n'.join(plan['expected_run_stdout']) + '\n'
        require(text == expected, 'exact runtime scope/state/lifetime evidence')


def arm(deadline, label):
    global DEADLINE_PHASE
    DEADLINE_PHASE = label
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'absolute stage deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL, remaining)


def expired(_sig, _frame):
    raise TimeoutError(DEADLINE_PHASE + ' deadline')


def execute(plan, phase, entry):
    pending_gate(plan, phase)  # Before loading support, enumerating inputs, mkdir or native launch.
    require(sys.platform == 'linux', 'Linux WNOWAIT and rusage units required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []) and
            signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'fresh unblocked phase timer')
    c = plan['phases'][phase]
    total_stop = entry + c['total_seconds']
    pre_stop = entry + c['preflight_seconds']
    old_handler = signal.signal(signal.SIGALRM, expired)
    old_umask = os.umask(0o077)
    made = False
    runner = None
    evidence = Path(c['evidence_root'])
    try:
        arm(pre_stop, phase + '_preflight')
        support = support_module()
        immutable = verify_inputs(support, plan)
        prior = verify_previous(support, plan, phase, True)
        runner = projected_runner(support, plan, phase, evidence)
        before = runner['usage']()
        require(before['user_cpu_seconds'] == before['system_cpu_seconds'] == before['maxrss_kib'] == 0,
                'dedicated phase already has child usage')
        require(not os.path.lexists(evidence), 'fresh evidence directory required')
        if phase == 'version':
            require(not os.path.lexists(W), 'fresh micro work root required')
            support.fresh_directory(W)
            for name in ('obj', 'home', 'tmp'):
                support.fresh_directory(Path(W) / name)
        support.fresh_directory(evidence)
        made = True
        runner['save'](evidence / 'INPUTS.json', {'status': 'PREPARED_NOT_EXECUTED', 'phase': phase,
            'argv': c['argv'], 'cwd': c['cwd'], 'environment': plan['environment'], 'limits': c,
            'plan_sha256': PLAN_SHA, 'immutable_inputs': immutable, 'projection_pins': plan['projection_pins'][phase]})
        require(time.monotonic() < pre_stop, 'preflight exhausted; no late spawn')
        work_stop = min(entry + c['work_stop_absolute_offset_seconds'], time.monotonic() + c['work_max_seconds'])
        arm(work_stop, phase + '_work')
        failure = None
        record = None
        raw = None
        try:
            record, raw = runner['bounded']('native', c['argv'], Path(c['cwd']), evidence,
                                             work_stop - time.monotonic(), c['cpu_seconds'])
        except BaseException as error:
            failure = error
        after = runner['usage']()
        arm(total_stop, phase + '_postflight')
        runner['save'](evidence / 'CHILD_USAGE.json', {'before': before, 'after': after,
            'status': 'OBSERVATION_NOT_CORRECTNESS_PASS', 'failure_type': None if failure is None else type(failure).__name__,
            'scope': 'Dedicated process RUSAGE_CHILDREN after bounded cleanup attempt; inspect native.json cleanup_confirmed.',
            'leader_scope': 'One original PID/starttime; not descendants or sampled subtree peak.',
            'maxrss_cumulative_peak_not_difference': True, 'linux_maxrss_unit': 'KiB'})
        if failure is not None:
            raise failure
        require(record['cleanup_confirmed'] is True, 'owned process group cleanup required')
        require(verify_inputs(support, plan) == immutable, 'immutable prerequisite drift')
        verify_previous(support, plan, phase, False)
        retained_file_cap = 32 * 1024**2 if phase == 'run' else c['fsize_bytes']
        tree = support.tree_inventory(W, c['tree_bytes'], c['file_count'], c['entry_count'], retained_file_cap)
        witness = hierarchy_witness(support, tree, phase in ('compile', 'run')) if phase != 'version' else {'status': 'VERSION_ONLY'}
        check_log(plan, phase, raw, witness)
        if phase == 'run':
            require(tree == prior, 'runtime mutated accepted compiled work tree')
        sample_pin = support.identity(evidence / 'leader_samples.jsonl', c['sample_rows'] * 2048)
        require(sample_pin['bytes'] > 0, 'leader sample receipt required')
        runner['save'](evidence / 'WORK_TREE.json', tree)
        inventory_pin = support.identity(evidence / 'WORK_TREE.json', 4 * 1024**2)
        runner['save'](evidence / 'WITNESS.json', witness)
        result = {'status': 'MICRO_PHASE_EVIDENCE_PENDING_INDEPENDENT_ACCEPTANCE', 'terminal_success': False,
            'phase': phase, 'native_exit': record['exit_code'], 'cleanup_confirmed': True,
            'work_tree_inventory_sha256': inventory_pin['sha256'], 'argv': c['argv'],
            'entry_to_postflight_seconds': time.monotonic() - entry, 'host93_input_touched': False,
            'original_uninitialized_failure_preserved': True,
            'derived_initializer_scope': 'PENDING_GENERATION' if phase == 'version' else 'FINITE_TARGET_CONTAINER_ONLY',
            'not_general_undefined_behavior_clearance': True,
            'acceptance_requires': 'Exact-stage independent review plus separate observed outer exit0 and total wall receipt.'}
        runner['save'](evidence / 'RESULT.json', result)
        wanted = {'INPUTS.json', 'native.json', 'native.log', 'CHILD_USAGE.json', 'leader_samples.jsonl',
                  'WORK_TREE.json', 'WITNESS.json', 'RESULT.json'}
        require({p.name for p in evidence.iterdir()} == wanted, 'exact successful evidence set')
        if phase == 'run':
            support.tree_inventory(evidence, 1024**2, 16, 32, 4 * 1024**2)
        require(time.monotonic() < total_stop, 'final total receipt deadline')
        return result
    except BaseException as error:
        if made and runner is not None:
            try:
                arm(total_stop, phase + '_failure_record')
                runner['save'](evidence / 'FAILURE.json', {'status': 'FAILED_MICRO_PHASE', 'phase': phase,
                    'error_type': type(error).__name__, 'message': str(error), 'terminal_success': False})
            except BaseException:
                pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        os.umask(old_umask)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, choices=PHASES)
    parser.add_argument('--execute-reviewed', action='store_true')
    args = parser.parse_args()
    plan = load_plan()
    validate_contract(plan, args.phase)
    if args.execute_reviewed:
        result = execute(plan, args.phase, globals()['__entry_monotonic__'])
    else:
        support = support_module()
        sup, obs = support.projected_sources(plan, args.phase)
        pins = {'supervisor': {'bytes': len(sup), 'sha256': digest(sup)},
                'observation': {'bytes': len(obs), 'sha256': digest(obs)}}
        require(pins == plan['projection_pins'][args.phase], 'source-only projection pins')
        result = {'status': 'SOURCE_ONLY_NO_NATIVE_OR_OUTPUT_CREATION', 'phase': args.phase,
                  'actual_bindings': 'PENDING', 'projection_pins': pins}
    print(json.dumps(result, sort_keys=True))
