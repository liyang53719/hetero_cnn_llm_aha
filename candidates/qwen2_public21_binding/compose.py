#!/usr/bin/env python3
"""Fail-closed portable public21 SOURCE_COMPOSITION_ONLY gate.

No source, patch, pin, fixture, or toolchain refresh. No compiler, simulation,
network, or historical composer invocation. The execution HEAD is provenance,
not a semantic-equivalence certificate. All consumed Git and working bytes must
still match their fixed reviewed identities.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BASE_COMMIT = '8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689'
MANIFEST_SHA256 = '75caad6c8db95ba5470a5d97b6d691f96af17e0bfe58f2ca207693c92097864c'
OVERLAY_MANIFEST_SHA256 = 'e1a77d673be3eaa69508cdfd4650f06a8d2998834e42c35c2a27c3a4e7380e2c'
HOST = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala'
HARNESS = 'Public21DispatchHarness.scala'
SPEC = 'Public21ReductionDispatchControlSpec.scala'
DEFAULT_SPEC = 'candidates/qwen2_resident_matrix/public_dispatch/Qwen2Public21DispatchControlSpec.scala'
SCOPE = 'SOURCE_COMPOSITION_ONLY'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, digest, label):
    require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'invalid fixed digest: ' + label)
    require(sha(data) == digest, 'identity drift: ' + label)
    return data


def relative(name):
    require(isinstance(name, str) and bool(re.fullmatch('[A-Za-z0-9_./+-]+', name)), 'unsafe path: ' + repr(name))
    path = PurePosixPath(name)
    require(bool(path.parts) and not path.is_absolute() and str(path) == name and all(p not in ('.', '..') for p in path.parts),
            'unsafe path: ' + name)
    return path


def read_regular(root, name):
    relative(name)
    target = root / name
    for part in (target, *target.parents):
        if part == root:
            break
        require(not part.is_symlink(), 'symlink input: ' + name)
    require(target.is_file() and target.resolve().is_relative_to(root.resolve()), 'missing or escaped input: ' + name)
    return target.read_bytes()


def git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(repo), *args], env=env)


def load_inputs(candidate=HERE):
    raw = read_regular(candidate, 'pinned_source_manifest.json')
    manifest = json.loads(checked(raw, MANIFEST_SHA256, 'pinned source manifest'))
    require(manifest['schema'] == 'qwen2-public21-binding-source-v1', 'manifest schema')
    require(manifest['source_base_commit'] == BASE_COMMIT, 'fixed source base changed')
    assets = {name: checked(read_regular(candidate, name), digest, 'candidate ' + name)
              for name, digest in manifest['asset_sha256'].items()}
    for name in ('current_overlay.patch', 'attention_preflight.patch', 'dispatch_abort.patch', 'source_audit.py',
                 'evidence/overlay_manifest.json', 'explicit_resolutions.json',
                 'evidence/compile_inputs.json', 'evidence/attention_preflight_adapter.py', HARNESS, SPEC):
        require(name in assets, 'missing mandatory candidate asset: ' + name)
    overlay = json.loads(checked(assets['evidence/overlay_manifest.json'], OVERLAY_MANIFEST_SHA256, 'original overlay manifest'))
    require(overlay['base_commit'] == BASE_COMMIT, 'overlay fixed source base')
    before = overlay['before_sha256']; post = overlay['post_sha256']
    require(set(before) == set(post) == set(manifest['final_post_sha256']), 'source identity sets differ')
    require(len(before) == 76 and sum(p.endswith('.scala') for p in before) == 70 and
            sum(p.endswith('.sv') for p in before) == 6, 'exact 70 Scala + 6 SV source inventory')
    require(len(overlay['changed_sources']) == 20, 'overlay change inventory')
    require(overlay['original_patch_order'] and len(overlay['original_patch_order']) == 15 and
            set(overlay['original_patch_order']) == set(overlay['original_patch_sha256']), 'full historical patch provenance')
    for name in before:
        relative(name)
    checked(assets['current_overlay.patch'], overlay['effective_patch']['sha256'], 'original effective overlay patch')
    checked(assets['explicit_resolutions.json'], overlay['documented_resolutions_sha256'], 'original conflict resolutions')
    require(manifest['attention_changed_sources'] == [HOST], 'attention patch must target only actual parser')
    require(set(post) == set(manifest['attention_post_sha256']), 'attention identity set')
    require([p for p in post if post[p] != manifest['attention_post_sha256'][p]] == [HOST], 'attention postimage scope')
    require(manifest['dispatch_abort_changed_sources'] == [HOST], 'dispatch abort patch must target only actual parser')
    require([p for p in post if manifest['attention_post_sha256'][p] != manifest['final_post_sha256'][p]] == [HOST], 'dispatch abort postimage scope')
    compile_evidence = json.loads(assets['evidence/compile_inputs.json'])
    require(compile_evidence['manifest_sha256'] == OVERLAY_MANIFEST_SHA256, 'compile evidence overlay identity')
    require(compile_evidence['repo_scala_sha256'] == {p: h for p, h in post.items() if p.endswith('.scala')},
            'compile evidence source set')
    require(len(compile_evidence['hardfloat_sha256']) == 20, 'HardFloat inventory')
    return manifest, overlay, assets, compile_evidence


def repo_inputs(manifest, overlay, compile_evidence):
    baseline = {}
    for pins in (overlay['before_sha256'], overlay['original_patch_sha256'], overlay['composition_helper_sha256'],
                 manifest['fixture_dependency_sha256'],
                 {compile_evidence['hardfloat_repo_pins_path']: compile_evidence['hardfloat_repo_pins_sha256']}):
        for name, digest in pins.items():
            relative(name)
            require(name not in baseline or baseline[name] == digest, 'conflicting source/provenance pins: ' + name)
            baseline[name] = digest
    groups = [(BASE_COMMIT, baseline)]
    for group in manifest['additional_repo_inputs']:
        require(bool(re.fullmatch('[0-9a-f]{40}', group['commit'])), 'fixed additional commit required')
        groups.append((group['commit'], group['sha256']))
    return groups


def verify_repo(repo, groups, execution_head):
    frozen = {}
    identities = {}
    for commit, pins in groups:
        for name, digest in sorted(pins.items()):
            relative(name)
            require(name not in identities or identities[name] == digest, 'conflicting consumed pin: ' + name)
            data = checked(git(repo, 'show', commit + ':' + name), digest, 'fixed Git source ' + name)
            checked(git(repo, 'show', execution_head + ':' + name), digest, 'execution HEAD source ' + name)
            checked(read_regular(repo, name), digest, 'current working source ' + name)
            frozen[name] = data
            identities[name] = digest
    return frozen, identities


def strict_patch(sources, patch, expected_targets):
    """Apply only exact unified hunks at declared line positions; never fuzz/offset."""
    lines = patch.decode('utf-8').splitlines(keepends=True)
    result = dict(sources); targets = []; i = 0
    while i < len(lines):
        require(lines[i].startswith('--- a/') and lines[i].endswith('\n'), 'unsupported patch header')
        name = lines[i][6:-1]; relative(name); i += 1
        require(i < len(lines) and lines[i] == '+++ b/' + name + '\n', 'patch rename/create/path mismatch'); i += 1
        require(name in sources and name not in targets, 'patch target missing or duplicated: ' + name)
        targets.append(name); original = sources[name].decode('utf-8').splitlines(keepends=True); output = []; cursor = 0; hunks = 0
        while i < len(lines) and not lines[i].startswith('--- a/'):
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[i])
            require(match is not None, 'unsupported or missing unified hunk: ' + name)
            old_start, old_count, new_start, new_count = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            i += 1; hunks += 1
            offset = old_start - 1 if old_count else old_start
            require(cursor <= offset <= len(original), 'overlapping/out-of-range hunk: ' + name)
            output.extend(original[cursor:offset]); cursor = offset
            new_offset = new_start - 1 if new_count else new_start
            require(len(output) == new_offset, 'new hunk position mismatch: ' + name)
            old_seen = new_seen = 0
            while i < len(lines) and lines[i][:1] in (' ', '+', '-') and not lines[i].startswith('--- a/'):
                line = lines[i]; i += 1; tag = line[0]; content = line[1:]
                if tag in (' ', '-'):
                    require(cursor < len(original) and original[cursor] == content, 'exact patch context mismatch: ' + name)
                    cursor += 1; old_seen += 1
                if tag in (' ', '+'):
                    output.append(content); new_seen += 1
            require((old_seen, new_seen) == (old_count, new_count), 'hunk line count mismatch: ' + name)
        require(hunks > 0, 'empty patch file entry: ' + name)
        output.extend(original[cursor:]); result[name] = ''.join(output).encode('utf-8')
    require(targets and len(targets) == len(set(targets)) and set(targets) == set(expected_targets), 'patch target scope')
    return result


def verify_map(sources, pins, label):
    require(set(sources) == set(pins), label + ' inventory drift')
    for name, digest in pins.items():
        checked(sources[name], digest, label + ' ' + name)


def output_path(repo, out):
    require('..' not in out.parts, 'unsafe output traversal')
    out = Path(os.path.abspath(out))
    work = repo / 'work'
    require(out != work and out.is_relative_to(work), 'output must be a fresh child of repo/work')
    for part in (out, *out.parents):
        require(not part.is_symlink(), 'symlink output path')
        if part == repo:
            break
    require(not out.exists(), 'fresh output directory required')
    require(out.parent.is_dir(), 'output parent must already exist')
    require(subprocess.run(['git', '-C', str(repo), 'check-ignore', '-q', '--no-index', '--', str(out)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0, 'output must be ignored')
    return out


def compose(repo, out, hardfloat_source=None, candidate=HERE):
    repo = repo.resolve(strict=True)
    require(Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == repo, 'repo must be Git root')
    out = output_path(repo, out)
    manifest, overlay, assets, compile_evidence = load_inputs(candidate)
    execution_head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    require(bool(re.fullmatch('[0-9a-f]{40}', execution_head)), 'invalid execution HEAD')
    groups = repo_inputs(manifest, overlay, compile_evidence)
    frozen, consumed = verify_repo(repo, groups, execution_head)
    require(json.loads(frozen[compile_evidence['hardfloat_repo_pins_path']]) == compile_evidence['hardfloat_sha256'],
            'HardFloat existing repository pins differ from compile inventory')
    baseline = {name: frozen[name] for name in overlay['before_sha256']}
    first = strict_patch(baseline, assets['current_overlay.patch'], overlay['changed_sources'])
    verify_map(first, overlay['post_sha256'], 'overlay postimage')
    attention = strict_patch(first, assets['attention_preflight.patch'], [HOST])
    verify_map(attention, manifest['attention_post_sha256'], 'attention postimage')
    final = strict_patch(attention, assets['dispatch_abort.patch'], [HOST])
    verify_map(final, manifest['final_post_sha256'], 'dispatch abort postimage')
    hf = {}
    if hardfloat_source is not None:
        root = hardfloat_source.resolve(strict=True)
        expected = compile_evidence['hardfloat_sha256']
        found = {str(p.relative_to(root)) for p in (root / 'hardfloat/src/main/scala').rglob('*.scala')}
        require(found == set(expected), 'external HardFloat source set drift')
        hf = {name: checked(read_regular(root, name), digest, 'external HardFloat ' + name) for name, digest in expected.items()}
    with tempfile.TemporaryDirectory(prefix='.public21-compose-', dir=repo / 'work') as temporary:
        staged = Path(temporary) / 'result'; staged.mkdir()
        source = staged / 'source'
        for name, data in final.items():
            target = source / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        namespace = {}
        exec(compile(assets['source_audit.py'], str(candidate / 'source_audit.py'), 'exec'), namespace)
        audit = namespace['source_audit'](baseline, overlay, source)
        require('scanAttention=if(enableResidentFfn && officialBf16)' in final[HOST].decode(), 'official-only attention preflight guard')
        harness_rel = 'candidates/qwen2_public21_binding/' + HARNESS
        target = source / harness_rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(assets[HARNESS])
        tests = staged / 'test'; tests.mkdir()
        (tests / SPEC).write_bytes(assets[SPEC]); (tests / Path(DEFAULT_SPEC).name).write_bytes(frozen[DEFAULT_SPEC])
        for name, data in hf.items():
            target = staged / 'hardfloat_snapshot' / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        compile_sources = ['source/' + p for p in sorted(final) if p.endswith('.scala')]
        compile_sources += ['hardfloat_snapshot/' + p for p in sorted(compile_evidence['hardfloat_sha256'])]
        compile_sources += ['source/' + harness_rel]
        test_sources = ['test/' + Path(DEFAULT_SPEC).name, 'test/' + SPEC]
        require(len(compile_sources) == len(set(compile_sources)) == 91 and len(test_sources) == 2, 'compile/test source counts')
        contract = dict(scope=SCOPE, compile_sources=compile_sources, test_sources=test_sources,
            compile_source_count=91, repository_scala_count=70, harness_scala_count=1, hardfloat_scala_count=20,
            compile_inputs_ready=bool(hf), missing_external_hardfloat=not bool(hf),
            hardfloat_commit=compile_evidence['hardfloat_commit'], hardfloat_sha256=compile_evidence['hardfloat_sha256'],
            compiler_versions=compile_evidence['compiler_versions'],
            test_classes=['heteronpu.continuous.Qwen2Public21DispatchControlSpec', 'heteronpu.continuous.Public21ReductionDispatchControlSpec'],
            fixture_generator='candidates/qwen2_resident_matrix/public_dispatch/generate_contract.py',
            fixture_requirement='Generate fresh metadata fixtures from the verified current generator in a new work directory; hash gate.json, every fixture manifest and table before and after control simulation.',
            fixture_generated=False, compiled=False, elaborated=False, rtl_simulated=False, arithmetic_executed=False,
            owner_completion_mock=True, full_block_numerical_acceptance=False)
        (staged / 'compile_inputs.json').write_text(json.dumps(contract, indent=2) + '\n')
        (staged / 'compile_sources_91.list').write_text('\n'.join(compile_sources) + '\n')
        (staged / 'test_sources_2.list').write_text('\n'.join(test_sources) + '\n')
        # A changed source, candidate, external dependency or HEAD during composition is fatal.
        require(git(repo, 'rev-parse', 'HEAD').decode().strip() == execution_head, 'execution HEAD changed during composition')
        for name, digest in consumed.items():
            checked(read_regular(repo, name), digest, 'final current working source ' + name)
        load_inputs(candidate)
        for name, data in hf.items():
            checked(read_regular(hardfloat_source.resolve(), name), sha(data), 'final external HardFloat ' + name)
        output_files = {str(p.relative_to(staged)): sha(p.read_bytes()) for p in sorted(staged.rglob('*')) if p.is_file()}
        report = dict(status='PASS_SOURCE_COMPOSITION_ONLY', scope=SCOPE, source_base_commit=BASE_COMMIT,
            execution_head=execution_head, execution_head_is_semantic_proof=False, consumed_source_drift=False,
            consumed_sha256=consumed, manifest_sha256=MANIFEST_SHA256, compose_sha256=sha(Path(__file__).read_bytes()),
            asset_sha256=manifest['asset_sha256'], source_count=76, scala_source_count=70, sv_source_count=6,
            binding_harness_count=1, test_class_count=2, overlay_changed_sources=overlay['changed_sources'],
            attention_changed_sources=[HOST], dispatch_abort_changed_sources=[HOST], separate_binding_harness_included=True, final_post_sha256=manifest['final_post_sha256'],
            output_sha256=output_files, compile_inputs_ready=bool(hf), audit=audit,
            no_historical_kernel_file_copied=True, h2048_borrower_default=False, elementwise_loan_default=False,
            source_composition_only=True, compiled=False, elaborated=False, rtl_simulated=False,
            arithmetic_executed=False, owner_completion_mock=True, full_block_numerical_acceptance=False)
        receipt_bytes = (json.dumps(report, indent=2) + '\n').encode('utf-8')
        output_path(repo, out)
        # mkdir reserves the fresh destination; copytree must never reuse old evidence.
        out.mkdir()
        shutil.copytree(staged, out, dirs_exist_ok=True)
        for name, digest in output_files.items():
            checked(read_regular(out, name), digest, 'published source output ' + name)
        # A PASS receipt appears only after every destination byte was verified.
        with (out / 'source_receipt.json').open('xb') as receipt:
            receipt.write(receipt_bytes)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=HERE.parents[1])
    parser.add_argument('--out', type=Path, required=True, help='new ignored repo/work child; existing parent required')
    parser.add_argument('--hardfloat-source', type=Path, help='optional caller-fetched root containing hardfloat/src/main/scala')
    parser.add_argument('--run-rtl', action='store_true', help='reserved; this source-only gate does not run RTL')
    args = parser.parse_args()
    require(not args.run_rtl, 'RTL execution is not part of this SOURCE_COMPOSITION_ONLY gate; use a separately authorized control runner with explicit toolchain and freshly hashed fixtures')
    report = compose(args.repo, args.out, args.hardfloat_source)
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'source_base_commit', 'execution_head', 'manifest_sha256',
                                                 'source_count', 'scala_source_count', 'binding_harness_count', 'test_class_count', 'compile_inputs_ready')}, indent=2))


if __name__ == '__main__':
    main()
