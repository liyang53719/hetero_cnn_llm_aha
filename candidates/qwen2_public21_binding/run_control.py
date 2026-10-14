#!/usr/bin/env python3
"""Opt-in portable public21 parser/reduction CONTROL RTL gate; mocked backends.

Default: NOT_EXECUTED. Toolchain and HardFloat must already be fetched by the
caller. No numeric payload, weight, or historical simulation is reused.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import compose as c

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCOPE = 'ACTUAL_PUBLIC21_PARSER_REDUCTION_CONTROL_ONLY'
FAULTS = {
    'window_tag', 'drain_short', 'held_reset', 'abort_pending', 'future_score', 'future_probability',
    'abort_fetch', 'abort_typed', 'abort_scan', 'abort_ordinary_issue', 'abort_resident_issue',
    'stray_resident_during_reduction', 'idle_ordinary_stray', 'idle_resident_stray',
}
ARCHIVES = {
    'downloads/sbt-launch-1.10.2.jar': 'cdd6963b622f42690cb2e3154bde3f3257a03839f216e1b5d7420000d6a71817',
    'downloads/llvm-firtool-1.62.1-linux-x64.jar': '63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039',
    'downloads/verilator_5.032-1+b2_amd64.deb': '238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2',
}


def record(path):
    path = Path(path).resolve(strict=True)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=c.sha(path.read_bytes()))


def snapshot(paths):
    return {str(Path(p).resolve(strict=True)): c.sha(Path(p).read_bytes()) for p in sorted(set(paths))}


def rehash(before):
    return {name: c.sha(Path(name).read_bytes()) if Path(name).is_file() else 'MISSING' for name in before}


def toolchain_inputs(root):
    root = root.resolve(strict=True)
    for name, digest in ARCHIVES.items():
        c.checked(c.read_regular(root, name), digest, 'fixed caller toolchain archive ' + name)
    required = ['bin/sbt-chiseltest', 'bin/sbt', 'bin/verilator', 'env.sh', 'repositories',
                'deps/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin/firtool',
                'deps/verilator_debian/usr/bin/verilator', 'deps/verilator_debian/usr/bin/verilator_bin']
    files = {root / name for name in (*ARCHIVES, *required)}
    for name in required:
        c.read_regular(root, name)
    for directory in ('coursier', 'sbt/boot'):
        jars = list((root / directory).rglob('*.jar'))
        c.require(jars, 'caller must prefetch ' + directory + ' JARs')
        files.update(jars)
    # Host tools are observed identities, not claimed vendor checksum pins.
    for name in ('java', 'g++', 'make', 'perl'):
        executable = shutil.which(name)
        c.require(executable, 'caller toolchain missing ' + name)
        files.add(Path(executable).resolve())
    c.require(os.access(root / 'bin/sbt-chiseltest', os.X_OK), 'toolchain wrapper must be executable')
    return root / 'bin/sbt-chiseltest', snapshot(files)


def fixture_inputs(repo, root, expected_sources):
    gate_bytes = c.read_regular(root, 'gate.json'); gate = json.loads(gate_bytes)
    c.require(gate['scope'] == 'METADATA_CONTROL_ONLY' and gate['arithmetic_executed'] is False, 'fixture gate scope')
    c.require(gate['source_sha256'] == expected_sources, 'fixture generator consumed unpinned or changed sources')
    c.require([v['directory'] for v in gate['fixtures']] == ['m16', 'm128', 'm16_relocated'], 'exact fresh fixture set')
    c.require(gate['current_owner_count'] == 19 and gate['candidate_owner_count'] == 17, 'fixture owner counts')
    paths = {root / 'gate.json'}
    for entry, rows, epoch in zip(gate['fixtures'], (16, 128, 16), (7, 8, 9)):
        folder = root / entry['directory']; name = entry['directory'] + '/manifest.json'
        data = json.loads(c.checked(c.read_regular(root, name), entry['manifest_sha256'], 'fresh fixture manifest ' + name))
        paths.add(root / name)
        c.require(data['rows'] == rows and data['epoch'] == epoch, 'fixture rows/epoch')
        c.require(data['arithmetic_executed'] is False and data['weights_materialized'] is False and
                  data['full_block_numerical_pass'] is False, 'fixture contains numeric execution claim')
        c.require(len(data['accepted_jobs']) == 19 and len(data['expected_completions']) == 21 and
                  len(data['historical_candidate17']['accepted_jobs']) == 17, 'fixture dispatch counts')
        c.require(set(data['tables']) == {'command', 'descriptor'}, 'metadata tables only')
        for table in data['tables'].values():
            c.relative(table['file'])
            raw = c.checked(c.read_regular(folder, table['file']), table['sha256'], 'fresh metadata table')
            c.require(len(raw) == table['bytes'] == ((table['count'] * 16 + 63) // 64) * 64, 'metadata length')
            paths.add(folder / table['file'])
    found = {p for p in root.rglob('*') if p.is_file()}
    c.require(found == paths, 'unexpected fixture payload/file')
    for name, digest in expected_sources.items():
        c.checked(c.read_regular(repo, name), digest, 'fresh fixture current source ' + name)
    return snapshot(paths)


def checked_markers(text):
    lines = [line for line in text.splitlines() if line.startswith(('PUBLIC21_CURRENT_', 'PUBLIC21_REDUCTION_DISPATCH_'))]
    current = [line for line in lines if line.startswith('PUBLIC21_CURRENT_PARSER_CONTROL_PASS ')]
    current_reject = [line for line in lines if line.startswith('PUBLIC21_CURRENT_PARSER_REJECTION_PASS ')]
    reduction = [line for line in lines if line.startswith('PUBLIC21_REDUCTION_DISPATCH_CONTROL_PASS ')]
    rejected = [line for line in lines if line.startswith('PUBLIC21_REDUCTION_DISPATCH_REJECT_PASS ')]
    cases = [re.search(r'\bfault=([^ ]+)', line) for line in rejected]
    fault_names = [m[1] for m in cases if m is not None]
    ok = (len(lines) == 22 and len(current) == 4 and len(current_reject) == 1 and len(reduction) == 3 and
          len(rejected) == len(fault_names) == 14 and set(fault_names) == FAULTS and
          all('arithmetic=false' in line for line in lines))
    return ok, lines



def execution_flags(text, accepted=False):
    """Separate attempted tools, evidenced RTL activity, and aggregate acceptance.

    A missing testbench PASS marker means RTL execution is not established; an
    emitted source or a launched compiler alone is not execution evidence.
    """
    prefixes = ('PUBLIC21_CURRENT_PARSER_CONTROL_PASS ', 'PUBLIC21_CURRENT_PARSER_REJECTION_PASS ',
                'PUBLIC21_REDUCTION_DISPATCH_CONTROL_PASS ', 'PUBLIC21_REDUCTION_DISPATCH_REJECT_PASS ')
    evidenced = any(line.startswith(prefixes) and 'arithmetic=false' in line for line in text.splitlines())
    c.require(not accepted or evidenced, 'cannot accept control RTL without testbench execution evidence')
    return dict(rtl_executed=evidenced, rtl_simulated=evidenced, control_acceptance_passed=accepted,
                rtl_execution_evidence='TESTBENCH_PASS_MARKER' if evidenced else 'NOT_ESTABLISHED')


def run_group(command, project, env, log, timeout=600):
    """One bounded process group; inherited children are terminated on timeout."""
    with log.open('w') as stream:
        process = subprocess.Popen(command, cwd=project, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
            # The leader can exit on TERM while a grandchild ignores TERM.
            # Reaping the leader is not proof that its process group drained.
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            stream.write('\nTIMEOUT: 600-second RTL process group terminated\n')
            return 124


def run(repo, out, toolchain_root, hardfloat_source):
    repo = repo.resolve(strict=True)
    out = c.output_path(repo, out)
    manifest, overlay, assets, compile_evidence = c.load_inputs()
    wrapper, tools_before = toolchain_inputs(toolchain_root)
    out.mkdir()
    summary = dict(status='RUNNING', scope=SCOPE, started_from_fresh_output=True,
        arithmetic_executed=False, owner_completion_mock=True, backend_responses_mock=True,
        full_block_rtl=False, full_block_numerical_acceptance=False, hardware_performance_measured=False,
        tb_inputs='COMMAND_AND_DESCRIPTOR_METADATA_ONLY; BACKEND_ARITHMETIC_RETURNS_MOCK_ZERO',
        actual_modules=['HostBlockCommands', 'DenseBlockReductionCoordinator', 'DenseTileSumBridge'],
        rtl_execution_attempted=False, watchdog_seconds=600, wrapper=record(wrapper), toolchain_before=tools_before,
        **execution_flags(''))
    dest = out / 'summary.json'
    def save():
        dest.write_text(json.dumps(summary, indent=2) + '\n')
    save(); started = time.monotonic()
    try:
        source_root = out / 'sources'
        receipt = c.compose(repo, source_root, hardfloat_source)
        contract = json.loads((source_root / 'compile_inputs.json').read_bytes())
        c.require(contract['compile_inputs_ready'] and len(contract['compile_sources']) == 91 and
                  len(contract['test_sources']) == 2, 'exact complete 70+20+1 Compile and two Test inputs')
        expected_fixture_sources = dict(manifest['fixture_dependency_sha256'])
        for group in manifest['additional_repo_inputs']:
            for name, digest in group['sha256'].items():
                if name.endswith(('/generate_contract.py', '/source_pins.json')):
                    expected_fixture_sources[name] = digest
        fixture = out / 'fixtures'
        fixture_command = [sys.executable, str(repo / contract['fixture_generator']), '--out', str(fixture)]
        fixture_env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        with (out / 'fixture_generation.log').open('w') as log:
            subprocess.run(fixture_command, cwd=repo, env=fixture_env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=60, check=True)
        metadata_before = fixture_inputs(repo, fixture, expected_fixture_sources)
        compile_files = [source_root / name for name in contract['compile_sources']]
        test_files = [source_root / name for name in contract['test_sources']]
        project = out / 'project'; (project / 'project').mkdir(parents=True)
        # Exact source lists, no inherited live-tree directories, no stale target.
        def scala_file(path):
            return 'file(' + json.dumps(str(path.resolve())) + ')'
        build = '''ThisBuild / scalaVersion := "2.13.16"
ThisBuild / organization := "org.heteronpu"
ThisBuild / version := "0.1.0"
ThisBuild / offline := true
val verifyPinnedSources = taskKey[Unit]("Verify exact reviewed source inventory")
lazy val root = (project in file(".")).settings(
  name := "qwen2-public21-binding-control",
  libraryDependencies ++= Seq("org.chipsalliance" %% "chisel" % "6.7.0", "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test, "org.scalatest" %% "scalatest" % "3.2.19" % Test),
  addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full),
  Compile / unmanagedSourceDirectories := Seq.empty,
  Test / unmanagedSourceDirectories := Seq.empty,
  Compile / unmanagedSources := Seq(COMPILE_FILES),
  Test / unmanagedSources := Seq(TEST_FILES),
  scalacOptions ++= Seq("-deprecation", "-feature", "-unchecked", "-language:reflectiveCalls"),
  Test / parallelExecution := false,
  verifyPinnedSources := {
    val actualCompile = (Compile / sources).value.map(_.getCanonicalPath)
    val actualTest = (Test / sources).value.map(_.getCanonicalPath)
    val expectedCompile = Seq(COMPILE_FILES).map(_.getCanonicalPath)
    val expectedTest = Seq(TEST_FILES).map(_.getCanonicalPath)
    require(actualCompile.size == 91 && actualCompile.toSet == expectedCompile.toSet, "Compile source drift")
    require(actualTest.size == 2 && actualTest.toSet == expectedTest.toSet, "Test source drift")
    println("PUBLIC21_SOURCE_LIST_PASS compile=91 tests=2")
  }
)
'''.replace('COMPILE_FILES', ','.join(map(scala_file, compile_files))).replace('TEST_FILES', ','.join(map(scala_file, test_files)))
        (project / 'build.sbt').write_text(build)
        (project / 'project/build.properties').write_text('sbt.version=1.10.2\n')
        source_paths = [source_root / name for name in receipt['output_sha256']]
        source_paths += [source_root / 'source_receipt.json', project / 'build.sbt', project / 'project/build.properties',
                         HERE / 'compose.py', HERE / 'pinned_source_manifest.json', Path(__file__).resolve()]
        source_paths += [HERE / name for name in manifest['asset_sha256']]
        source_paths += [repo / name for name in receipt['consumed_sha256']]
        source_before = snapshot(source_paths)
        command = [str(wrapper), 'verifyPinnedSources', 'testOnly ' + ' '.join(contract['test_classes'])]
        env = dict(os.environ, HETERO_PUBLIC21_FIXTURE_ROOT=str(fixture), COURSIER_MODE='offline')
        summary.update(source_base_commit=receipt['source_base_commit'], execution_head=receipt['execution_head'],
            source_manifest_sha256=receipt['manifest_sha256'], source_before=source_before,
            metadata_before=metadata_before, fixture_command=fixture_command,
            gate_sha256=metadata_before[str((fixture / 'gate.json').resolve())],
            compile_sources=[str(p) for p in compile_files], test_sources=[str(p) for p in test_files],
            test_classes=contract['test_classes'], command=command)
        summary['rtl_execution_attempted'] = True
        save()
        code = run_group(command, project, env, out / 'test.log')
        text = (out / 'test.log').read_text()
        after = rehash(source_before); metadata_after = rehash(metadata_before); tools_after = rehash(tools_before)
        marker_ok, markers = checked_markers(text)
        count = sum(int(n) for n in re.findall(r'Total number of tests run: (\d+)', text))
        zero_skips = bool(re.search(r'canceled 0, ignored 0, pending 0', text))
        generated = [record(p) for p in sorted(project.rglob('*')) if p.is_file() and p.suffix in ('.sv', '.fir', '.so')]
        summary.update(returncode=code, source_after=after, sources_unchanged=source_before == after,
            metadata_after=metadata_after, metadata_unchanged=metadata_before == metadata_after,
            toolchain_after=tools_after, toolchain_unchanged=tools_before == tools_after,
            test_count=count, zero_skips=zero_skips, markers=markers, marker_contract_passed=marker_ok,
            generated_records=generated, log=record(out / 'test.log'), **execution_flags(text))
        rtl_copies = []
        for top in ('HostBlockCommands', 'Public21DispatchHarness'):
            for suffix in ('.sv', '.lo.fir'):
                matches = list((project / 'test_run_dir').rglob(top + suffix))
                c.require(len(matches) == 1 and not matches[0].is_symlink(), 'fresh generated RTL inventory: ' + top + suffix)
                target = out / 'rtl' / top / (top + suffix)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(matches[0], target)
                c.require(record(matches[0])['sha256'] == record(target)['sha256'], 'generated artifact copy identity')
                rtl_copies.append(record(target))
        success = (code == 0 and count == 2 and zero_skips and marker_ok and 'All tests passed.' in text and
                   source_before == after and metadata_before == metadata_after and tools_before == tools_after and bool(generated) and text.count('PUBLIC21_SOURCE_LIST_PASS compile=91 tests=2') == 1)
        summary.update(status='PASS_PUBLIC21_BINDING_CONTROL_ONLY' if success else 'FAILED', returncode=code,
            source_after=after, sources_unchanged=source_before == after,
            metadata_after=metadata_after, metadata_unchanged=metadata_before == metadata_after,
            toolchain_after=tools_after, toolchain_unchanged=tools_before == tools_after,
            test_count=count, zero_skips=zero_skips, markers=markers, marker_contract_passed=marker_ok,
            generated_records=generated, preserved_rtl=rtl_copies, **execution_flags(text, success),
            generated_records_scope='FRESH_ISOLATED_PROJECT_ONLY', log=record(out / 'test.log'))
    except Exception as error:
        summary.update(status='FAILED', control_acceptance_passed=False, error=type(error).__name__ + ': ' + str(error))
        success = False
    summary['host_seconds'] = time.monotonic() - started
    save()
    return summary, success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-rtl', action='store_true')
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--toolchain-root', type=Path)
    parser.add_argument('--hardfloat-source', type=Path)
    args = parser.parse_args()
    if not args.run_rtl:
        print(json.dumps(dict(status='NOT_EXECUTED', scope=SCOPE, rtl_execution_attempted=False,
            arithmetic_executed=False, owner_completion_mock=True, full_block_numerical_acceptance=False, **execution_flags(''))))
        return
    c.require(args.out is not None and args.toolchain_root is not None and args.hardfloat_source is not None,
              '--run-rtl requires explicit --out, --toolchain-root and --hardfloat-source')
    summary, passed = run(args.repo, args.out, args.toolchain_root, args.hardfloat_source)
    print(json.dumps({key: summary[key] for key in ('status', 'scope', 'rtl_executed', 'host_seconds')}, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
