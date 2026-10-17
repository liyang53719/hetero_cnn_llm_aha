"""Separate owned composition, admission, and full-M128 child processes.

Cold import is stdlib-only. Source-only tests never invoke native admission or
entry.run. The parent authenticates process ownership and terminal acceptance;
these children neither create their own authority nor inherit a historical PASS.
"""
import argparse
import importlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
OWN = 'candidates/qwen2_resident_matrix/portable_same_host_m128_launch/'
ENTRY = 'candidates/qwen2_resident_matrix/attention_packed_m128_same_host/'
PACKAGE = 'candidates.qwen2_resident_matrix.attention_packed_m128_same_host'
PRODUCER = 'candidates/qwen2_resident_matrix/portable_official_producer/'
PRODUCER_M128 = 'candidates/qwen2_resident_matrix/portable_official_producer_m128/'
CLAIMS = ('actual_chain_executed', 'full_public_admission', 'full_29_node_acceptance',
          'rtl_execution', 'hardware_recipe_acceptance', 'old_pass_inherited')
SOURCE_CONTRACT = ENTRY + 'SOURCE_CONTRACT.json'
PROFILE = 'qwen2-public-pv16-packed-m128-same-host-v1'


def need(value, reason):
    if not value:
        raise ValueError('same-host M128 worker: ' + reason)


def directory(path):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts and
         not any(p.is_symlink() for p in (path, *path.parents)) and path.is_dir(),
         'absolute existing non-symlink directory')
    need(path == path.resolve(strict=True), 'canonical directory')
    return path


def load_parent(origin):
    """Bootstrap the already parent-pinned cold API without a .pyc import."""
    need(origin / OWN == HERE, 'worker belongs to original launch source')
    path = HERE / 'run.py'
    need(not path.is_symlink() and path.is_file(), 'cold parent source')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 8*1024*1024,
         'cold parent source type/size')
    raw = path.read_bytes()
    need(len(raw) == info.st_size, 'cold parent source size drift')
    spec = importlib.util.spec_from_file_location('same_host_worker_parent', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    # load_pins revalidates both this file and run.py before any source import.
    return module


def runtime(out):
    need(sys.version_info[:3] == (3, 12, 15) and sys.flags.isolated and
         not sys.flags.optimize and sys.dont_write_bytecode and sys.pycache_prefix is None,
         'exact Python 3.12.15 isolated-B normal interpreter')
    need(Path(sys.executable).absolute() == out / 'm16/setup/venv/bin/python' and
         Path(sys.prefix).absolute() == out / 'm16/setup/venv' and sys.prefix != sys.base_prefix,
         'same private setup virtual environment')


def context_check(api, L, args, origin, out):
    value = api.read_context(L, args.context, args.context_sha256)
    expected_profile = 'same-host-m128-run-v1' if args.mode == 'run' else 'same-host-m128-prepare-v1'
    expected_name = 'M128_RUN_CONTEXT.json' if args.mode == 'run' else 'M128_PREPARE_CONTEXT.json'
    need(Path(args.context) == out / expected_name and value['profile'] == expected_profile,
         'exact mode-specific parent context')
    need(value['parent_pid'] == os.getppid() and value['parent_pid'] > 1,
         'same live owning parent')
    need(value['origin'] == str(origin) and value['out'] == str(out), 'parent paths differ')
    need(value['ci']['commit'] == args.commit and
         L.encoded(value['host']) == L.encoded(L.host()), 'same triggering commit/host')
    need(os.environ.get('GITHUB_SHA') == args.commit and
         os.environ.get('GITHUB_RUN_ID') == value['ci']['run_id'] and
         os.environ.get('GITHUB_RUN_ATTEMPT') == value['ci']['run_attempt'] == '1',
         'same first-attempt triggering environment')
    receipt = out / 'M128_QUALIFICATION.json'
    raw = L.safe(receipt)
    need(L.sha(raw) == value['producer_receipt_sha256'], 'own parent qualification bytes')
    qualified = L.strict(raw)
    qualification_keys = {'schema', 'profile', 'status', 'attempt_nonce', 'ci', 'host_sha256',
        'runtime_identity_sha256', 'producer_manifest_sha256', 'producer_source_manifest_sha256',
        'parent_context_sha256', 'verifier_receipt_sha256', 'child_pid', 'child_exit_code',
        'owned_group_cleanup_complete', 'original_array_gate_revalidated', 'claims'}
    need(type(qualified) is dict and set(qualified) == qualification_keys and
         type(qualified.get('schema')) is int and qualified['schema'] == 1 and
         qualified.get('profile') == 'qwen2-fresh-same-host-m128-producer-qualified-v1' and
         qualified.get('status') == 'PASS_FRESH_M128_PRODUCER' and
         qualified.get('attempt_nonce') == value['attempt_nonce'] and
         L.encoded(qualified.get('ci')) == L.encoded(value['ci']) and
         qualified.get('host_sha256') == L.sha(L.encoded(value['host'])) and
         type(qualified.get('child_pid')) is int and qualified['child_pid'] > 1 and
         type(qualified.get('child_exit_code')) is int and qualified['child_exit_code'] == 0 and
         qualified.get('owned_group_cleanup_complete') is True and
         qualified.get('original_array_gate_revalidated') is True and
         all(L.digest(qualified.get(key)) for key in ('runtime_identity_sha256',
             'producer_manifest_sha256', 'producer_source_manifest_sha256',
             'parent_context_sha256', 'verifier_receipt_sha256')) and
         type(qualified.get('claims')) is dict and set(qualified['claims']) == set(CLAIMS) and
         all(item is False for item in qualified['claims'].values()),
         'own same-host single-attempt producer qualification')
    producer_context = read_bound(L, out / 'M128_CONTEXT.json', value['producer_context_sha256'])
    need(qualified['parent_context_sha256'] == value['producer_context_sha256'] and
         producer_context.get('profile') == 'qwen2-fresh-same-host-m128-context-v1' and
         type(producer_context.get('parent_pid')) is int and
         producer_context['parent_pid'] == value['parent_pid'] and
         producer_context.get('root') == str(origin) and
         producer_context.get('workspace') == str(out / 'producer128') and
         producer_context.get('upstream_workspace') == str(out / 'm16/setup/producer') and
         producer_context.get('python') == str(out / 'm16/setup/venv/bin/python') and
         producer_context.get('attempt_nonce') == value['attempt_nonce'] and
         L.encoded(producer_context.get('ci')) == L.encoded(value['ci']) and
         L.encoded(producer_context.get('host')) == L.encoded(value['host']) and
         producer_context.get('upstream', {}).get('m16_prerequisite') ==
             dict(path=str(out / 'M16_PREREQUISITE.json'), sha256=value['m16_prerequisite_sha256']),
         'same live parent producer context and current M16 prerequisite')
    m16 = read_bound(L, out / 'M16_PREREQUISITE.json', value['m16_prerequisite_sha256'])
    observed = m16.get('observed_full')
    need(type(m16.get('schema')) is int and m16['schema'] == 1 and
         m16.get('profile') == 'qwen2-fresh-same-host-m16-prerequisite-v1' and
         m16.get('status') == 'VERIFIED_CURRENT_JOB_FULL_M16_SAME_ELF' and
         type(m16.get('parent_pid')) is int and m16['parent_pid'] == value['parent_pid'] and
         m16.get('m16_root') == str(out / 'm16') and m16.get('ci') == value['ci'] and
         m16.get('attempt_nonce') == value['attempt_nonce'] and
         m16.get('host_sha256') == qualified['host_sha256'] and
         m16.get('runtime_identity_sha256') == qualified['runtime_identity_sha256'] and
         type(observed) is dict and set(observed) == {'pid', 'observed_exit_code',
             'final_exit_code', 'owned_group_cleanup_complete'} and
         type(observed['pid']) is int and observed['pid'] > 1 and
         all(type(observed[key]) is int and observed[key] == 0
             for key in ('observed_exit_code', 'final_exit_code')) and
         observed['owned_group_cleanup_complete'] is True and
         all(m16.get(key) is False for key in ('full_29_node_acceptance',
             'm128_verdict_inherited', 'old_pass_inherited')),
         'current-job full M16 zero exit, cleanup, host/runtime and limited scope')
    return value, qualified


def read_bound(L, path, expected):
    """Read only original parent-hashed bytes, before importing source modules."""
    need(L.digest(expected), 'metadata digest')
    raw = L.safe(path)
    need(L.sha(raw) == expected, 'parent-bound metadata bytes')
    value = L.strict(raw)
    need(type(value) is dict, 'parent-bound metadata object')
    return value


def import_root(L, root, sources):
    """One numerical source tree per fresh interpreter, including namespaces."""
    need(not any(name in ('candidates', 'scripts') or name.startswith(('candidates.', 'scripts.'))
                 for name in sys.modules), 'source tree was already imported')
    L.import_path_guard(root, sources)
    need(str(root) not in sys.path, 'source root already on import path')
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()


def imported_sources(L, root, sources):
    """Reject a namespace fallback or any unpinned Python source actually used."""
    for name, module in tuple(sys.modules.items()):
        if not (name in ('candidates', 'scripts') or name.startswith(('candidates.', 'scripts.'))):
            continue
        path = getattr(module, '__file__', None)
        if path is not None:
            path = Path(path)
            need(path.is_relative_to(root), 'foreign source module: ' + name)
            relative = path.relative_to(root).as_posix()
            need(relative in sources and L.sha(L.safe(path, 8*1024*1024)) == sources[relative],
                 'unreviewed imported source: ' + name)
        for location in getattr(module, '__path__', ()):
            location = Path(location)
            need(location.is_relative_to(root), 'foreign namespace source: ' + name)


def composition_value(L, sources, commit):
    return dict(profile=PROFILE, git_head=commit, source_sha256=sources,
                source_manifest_sha256=L.sha(L.encoded(sources)),
                source_contract_sha256=sources[SOURCE_CONTRACT],
                actual_chain_executed=False, full_public_admission=False)


def read_composition(api, L, pins, out, commit):
    sources = api.validate_composition(L, pins, out / 'source128', commit)
    expected = composition_value(L, sources, commit)
    value = L.strict(L.safe(out / 'M128_COMPOSED.json'))
    need(L.encoded(value) == L.encoded(expected), 'exact current composed receipt')
    return sources


def copy_overlay(L, overlay, target, sources):
    """Copy reviewed bytes only; never replace the caller-owned worktree .git."""
    directory(overlay)
    directory(target)
    git_path = target / '.git'
    git_raw = L.safe(git_path, 65536)
    need(git_raw.startswith(b'gitdir: ') and b'\n' in git_raw, 'genuine linked-worktree marker')
    found = {}
    for path in sorted(overlay.rglob('*')):
        need(not path.is_symlink(), 'composition symlink')
        if path.is_dir():
            continue
        name = path.relative_to(overlay).as_posix()
        need(name in sources and '.git' not in Path(name).parts, 'unexpected composition output')
        raw = L.safe(path, 8*1024*1024)
        need(L.sha(raw) == sources[name], 'composition output drift')
        found[name] = raw
    need(set(found) == set(sources), 'complete exact composition output inventory')
    for name in found:
        path = target / name
        need(not any(p.is_symlink() for p in (path, *path.parents)), 'worktree source symlink')
        if path.exists():
            info = path.stat()
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'worktree source type/alias')
    for name, raw in found.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            info = os.fstat(descriptor)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'opened worktree source type/alias')
            with os.fdopen(descriptor, 'wb', closefd=False) as stream:
                stream.truncate(0)
                stream.write(raw)
                stream.flush()
        finally:
            os.close(descriptor)
        need(L.safe(path, 8*1024*1024) == raw, 'copied source bytes differ')
    need(L.safe(git_path, 65536) == git_raw, 'worktree Git identity was changed')


def compose(api, L, pins, args, origin, out, context, qualified):
    overlay, source = out / 'overlay128', directory(out / 'source128')
    need(not overlay.exists() and not overlay.is_symlink(), 'fresh source overlay')
    import_root(L, origin, pins['inputs'])
    prepare = importlib.import_module(PACKAGE + '.prepare')
    need(prepare.ROOT == origin, 'original composition source root')
    result = prepare.compose(overlay, git_head=args.commit, producer_package=origin / PRODUCER,
                             producer_m128_package=origin / PRODUCER_M128)
    need(type(result) is dict and set(result) == set(composition_value(L, result['source_sha256'], args.commit)),
         'exact original composition result')
    sources = result['source_sha256']
    need(type(sources) is dict and
         {k: v for k, v in sources.items() if k != SOURCE_CONTRACT} == pins['composed_sources'],
         'reviewed static full-M128 composition')
    need(L.encoded(result) == L.encoded(composition_value(L, sources, args.commit)),
         'original composition metadata')
    copy_overlay(L, overlay, source, sources)
    need(api.validate_composition(L, pins, source, args.commit) == sources,
         'copied dynamic composition binding')
    imported_sources(L, origin, pins['inputs'])
    api.load_pins(origin)
    after, after_qualified = context_check(api, L, args, origin, out)
    need(after == context and after_qualified == qualified, 'composition context drift')
    L.write_new(out / 'M128_COMPOSED.json', result)


def sealed_value(L, context, sources, manifest_sha, terminal_identity):
    need(type(terminal_identity) is dict and set(terminal_identity) == {
        'native_result_sha256', 'origin_identity', 'm16_prerequisite', 'library', 'entry_manifest_sha256'} and
        terminal_identity['entry_manifest_sha256'] == manifest_sha, 'exact terminal identity projection')
    return dict(schema=1, profile=PROFILE, entry_manifest_sha256=manifest_sha,
                producer_receipt_sha256=context['producer_receipt_sha256'],
                producer_context_sha256=context['producer_context_sha256'],
                m16_prerequisite_sha256=context['m16_prerequisite_sha256'],
                source_manifest_sha256=L.sha(L.encoded(sources)),
                attempt_nonce=context['attempt_nonce'], ci=context['ci'],
                terminal_identity=terminal_identity,
                terminal_identity_sha256=L.sha(L.encoded(terminal_identity)))


def manifest_bindings(L, A, out, origin, context, qualified, sources, manifest_sha):
    manifest = A.read_manifest(out / 'M128_ENTRY_MANIFEST.json', manifest_sha)
    need(manifest['source_sha256'] == sources and
         manifest['source_manifest_sha256'] == L.sha(L.encoded(sources)) and
         manifest['producer_origin'] == str(origin) and
         manifest['producer_workspace'] == str(out / 'producer128') and
         manifest['producer_manifest'] == dict(path=str(out / 'producer128/PRODUCER_M128.json'),
              sha256=qualified['producer_manifest_sha256']) and
         manifest['producer_receipt'] == dict(path=str(out / 'M128_QUALIFICATION.json'),
              sha256=context['producer_receipt_sha256']) and
         manifest['producer_context'] == dict(path=str(out / 'M128_CONTEXT.json'),
              sha256=context['producer_context_sha256']) and
         manifest['m16_prerequisite'] == dict(path=str(out / 'M16_PREREQUISITE.json'),
              sha256=context['m16_prerequisite_sha256']), 'manifest source and current parent pointers')
    m16 = read_bound(L, out / 'M16_PREREQUISITE.json', context['m16_prerequisite_sha256'])
    need(manifest['library'] == m16['library'] and
         manifest['library']['origin_root'] == str(out / 'm16/setup/tiny/source') and
         manifest['library']['receipt']['path'] == str(out / 'm16/setup/tiny/build/official_bf16_compile.json') and
         manifest['library']['binary']['path'] == str(out / 'm16/setup/tiny/build/official_bf16_matrix_silu.so'),
         'exact same-job full M16 compile receipt and ELF')
    return manifest


def terminal_identity(L, A, out, context, qualified, manifest, manifest_sha):
    """Pure projection of authenticated inputs; never infer it from a result."""
    producer = read_bound(L, out / 'producer128/PRODUCER_M128.json', qualified['producer_manifest_sha256'])
    m16 = read_bound(L, out / 'M16_PREREQUISITE.json', context['m16_prerequisite_sha256'])
    need(type(producer.get('rows')) is int and producer['rows'] == 128 and
         type(producer.get('past_tokens')) is int and producer['past_tokens'] == 0 and
         producer.get('attempt_nonce') == context['attempt_nonce'] and producer.get('ci') == context['ci'] and
         producer.get('source_manifest_sha256') == qualified['producer_source_manifest_sha256'] and
         producer.get('parent_context_sha256') == context['producer_context_sha256'] and
         L.sha(L.encoded(producer.get('host'))) == qualified['host_sha256'] and
         L.sha(L.encoded(producer.get('runtime_identity'))) == qualified['runtime_identity_sha256'] and
         producer.get('upstream', {}).get('m16_prerequisite') == manifest['m16_prerequisite'],
         'true M128 producer bytes and current-job identity')
    return A.terminal_identity(manifest, producer, qualified, m16, manifest_sha)


def seal(api, L, pins, args, origin, out, context, qualified):
    source = directory(out / 'source128')
    sources = read_composition(api, L, pins, out, args.commit)
    import_root(L, source, sources)
    C = importlib.import_module(PACKAGE + '.contract')
    A = importlib.import_module(PACKAGE + '.admission')
    need(C.ROOT == source and C.snapshot() == sources and C.git_context()['commit'] == args.commit,
         'sealed actual composed Git/source identity')
    manifest, manifest_sha, admitted = A.seal_manifest(out / 'M128_ENTRY_MANIFEST.json',
        producer_origin=origin, producer_workspace=out / 'producer128',
        producer_manifest_sha256=qualified['producer_manifest_sha256'],
        producer_receipt=out / 'M128_QUALIFICATION.json',
        producer_receipt_sha256=context['producer_receipt_sha256'],
        producer_context=out / 'M128_CONTEXT.json', producer_context_sha256=context['producer_context_sha256'],
        m16_prerequisite=out / 'M16_PREREQUISITE.json', m16_prerequisite_sha256=context['m16_prerequisite_sha256'])
    need(manifest == out / 'M128_ENTRY_MANIFEST.json' and
         manifest_sha == L.sha(L.safe(manifest)), 'fresh sealed manifest identity')
    value = manifest_bindings(L, A, out, origin, context, qualified, sources, manifest_sha)
    identity = terminal_identity(L, A, out, context, qualified, value, manifest_sha)
    need(type(admitted) is dict and admitted.get('terminal_identity') == identity,
         'independently admitted terminal identity differs')
    need(C.snapshot() == sources and C.git_context()['commit'] == args.commit, 'sealed source postflight')
    imported_sources(L, source, sources)
    api.load_pins(origin)
    after, after_qualified = context_check(api, L, args, origin, out)
    need(after == context and after_qualified == qualified, 'seal context drift')
    L.write_new(out / 'M128_SEALED.json', sealed_value(L, context, sources, manifest_sha, identity))


def run(api, L, pins, args, origin, out, context, qualified):
    source = directory(out / 'source128')
    sources = read_composition(api, L, pins, out, args.commit)
    need(context['source_manifest_sha256'] == L.sha(L.encoded(sources)), 'parent-pinned full source')
    manifest_sha = context['entry_manifest_sha256']
    need(L.sha(L.safe(out / 'M128_ENTRY_MANIFEST.json')) == manifest_sha, 'parent-pinned entry manifest')
    sealed = L.strict(L.safe(out / 'M128_SEALED.json'))
    need(type(sealed) is dict and 'terminal_identity' in sealed and
         L.encoded(sealed) == L.encoded(sealed_value(L, context, sources, manifest_sha, sealed['terminal_identity'])),
         'same parent-qualified seal')
    import_root(L, source, sources)
    C = importlib.import_module(PACKAGE + '.contract')
    A = importlib.import_module(PACKAGE + '.admission')
    entry = importlib.import_module(PACKAGE + '.entry')
    need(C.ROOT == source and C.snapshot() == sources and C.git_context()['commit'] == args.commit,
         'actual full-M128 composed Git/source identity')
    manifest = manifest_bindings(L, A, out, origin, context, qualified, sources, manifest_sha)
    identity = terminal_identity(L, A, out, context, qualified, manifest, manifest_sha)
    need(identity == sealed['terminal_identity'], 'current parent-authorized terminal identity')
    run_context = dict(profile=PROFILE, attempt=1, pid=os.getpid(), parent_pid=os.getppid(),
        started=context['started'], work_deadline=context['started']+2424,
        outer_deadline=context['started']+2430, source_manifest_sha256=context['source_manifest_sha256'],
        producer_receipt_sha256=context['producer_receipt_sha256'], attempt_nonce=context['attempt_nonce'],
        m16_prerequisite_sha256=context['m16_prerequisite_sha256'])
    need(run_context['work_deadline'] == context['work_deadline'] and
         run_context['outer_deadline'] == context['outer_deadline'], 'unmodified original execution envelope')
    C.authorize_run(run_context)
    after, after_qualified = context_check(api, L, args, origin, out)
    need(after == context and after_qualified == qualified, 'pre-run parent context drift')
    imported_sources(L, source, sources)
    entry.configure_backend()  # Exactly once, only in this new numeric child.
    entry.run(out / 'full_m128', manifest=out / 'M128_ENTRY_MANIFEST.json',
              manifest_sha256=manifest_sha, run_context=run_context)
    need(C.snapshot() == sources and C.git_context()['commit'] == args.commit, 'full source postflight')
    imported_sources(L, source, sources)
    api.load_pins(origin)
    after, after_qualified = context_check(api, L, args, origin, out)
    need(after == context and after_qualified == qualified, 'post-run parent context drift')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('compose', 'seal', 'run'))
    for name in ('origin', 'out', 'context'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('commit', 'context-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    origin, out = directory(args.origin), directory(args.out)
    need(not out.is_relative_to(origin) and not origin.is_relative_to(out), 'source and output disjoint')
    runtime(out)
    api = load_parent(origin)
    pins = api.load_pins(origin)
    L = api.load_launcher(origin, pins)
    need(L.digest(args.commit, 40), 'exact triggering commit')
    context, qualified = context_check(api, L, args, origin, out)
    return {'compose': compose, 'seal': seal, 'run': run}[args.mode](
        api, L, pins, args, origin, out, context, qualified)


if __name__ == '__main__':
    main()
