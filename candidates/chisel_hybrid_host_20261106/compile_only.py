"""TEMP: compile the exact source selection; never invoke a hardware/helper main.

No elaboration, FIR/RTL emission, native-library load, reference acquisition,
profile execution, result comparison, or artifact upload is implemented here.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
import urllib.request

D = Path(__file__).resolve().parent
REPO = D.parents[1]
PHASES = ('original162', 'modulecache', 'graph', 'helpers')
COUNTS = (162, 2, 10, 30)
CLASS_COUNTS = (896, 11, 174, 135)


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(raw):
    value = PurePosixPath(raw)
    need(type(raw) is str and not value.is_absolute() and '..' not in value.parts and str(value) == raw, 'canonical source-relative path')
    return value


def exact(path, row):
    need(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path, 'canonical regular input')
    before = path.stat()
    need(before.st_size == row['bytes'], 'input size')
    data = path.read_bytes()
    after = path.stat()
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(stamp(before) == stamp(after) and digest(data) == row['sha256'], 'stable exact source bytes')
    return data


def selection():
    sources = json.loads((D / 'SOURCES.json').read_bytes())
    need(sources['schema'] == 'TEMP_HYBRID_SOURCE_ONLY_SELECTION_V1' and sources['source_count'] == 204, 'source-only catalog')
    rows = sources['sources']
    need(len(rows) == len({r['path'] for r in rows}) == 204, 'unique complete source set')
    for row in rows:
        need(set(row) == {'path', 'bytes', 'sha256', 'phase'} and row['phase'] in PHASES, 'source schema')
        need(str(relative(row['path'])).endswith('.scala'), 'Scala sources only')
        exact(REPO / row['path'], row)
    for phase, count in zip(PHASES, COUNTS):
        need(sum(row['phase'] == phase for row in rows) == count, 'exact per-phase source closure')
    jars = json.loads((D / 'MAVEN_INPUTS.json').read_bytes())
    need(jars['schema'] == 'EXACT_PUBLIC_MAVEN_INPUTS_V1', 'Maven schema')
    jars = jars['jars']
    need(len(jars) == 107 and len({r['maven_path'] for r in jars}) == 106, '107 exact Maven roles,106 unique artifacts')
    catalog = {}
    for row in jars:
        need(set(row) == {'maven_path', 'bytes', 'sha256', 'role', 'url'}, 'portable Maven fields')
        rel = str(relative(row['maven_path']))
        identity = {k: v for k, v in row.items() if k != 'role'}
        need(rel not in catalog or catalog[rel] == identity, 'duplicate role has identical artifact bytes')
        catalog[rel] = identity
        need(row['url'] in ('https://repo.maven.apache.org/maven2/' + rel, 'https://repo1.maven.org/maven2/' + rel), 'exact public Maven origin')
        need(type(row['bytes']) is int and 0 < row['bytes'] <= 70_000_000 and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'finite pinned Maven artifact')
    need(sum(r['role'] == 'plugin' for r in jars) == 1 and sum(r['role'] == 'classpath' for r in jars) == 106, 'exact compiler plugin and classpath roles')
    plugin = next(r for r in jars if r['role'] == 'plugin')
    need(sum(r['maven_path'] == plugin['maven_path'] for r in jars) == 2, 'only the same plugin also appears on the original classpath')
    return rows, jars


def fetch_jars(rows, output):
    files = []
    for row in rows:
        target = output / 'maven' / relative(row['maven_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            exact(target, row)
            files.append((row, str(target)))
            continue
        with urllib.request.urlopen(row['url'], timeout=45) as response:
            raw = response.read(row['bytes'] + 1)
        need(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'downloaded Maven artifact identity')
        with target.open('xb') as stream:
            stream.write(raw)
        exact(target, row)
        files.append((row, str(target)))
    return files


def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 << 20, 16 << 20))


def compile_sources(rows, jars, output, java):
    need(java.is_file() and os.access(java, os.X_OK), 'explicit installed JDK executable')
    version = subprocess.run([str(java), '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, check=True).stdout
    need(re.search(rb'version "21[.\"]', version) is not None, 'JDK21 compile toolchain')
    inputs = fetch_jars(jars, output)
    plugin = next(path for row, path in inputs if row['role'] == 'plugin')
    cp_jars = [path for row, path in inputs if row['role'] != 'plugin']
    need(len(cp_jars) == 106, 'complete compiler/runtime jar classpath')
    roots = {}
    combined = {}
    reports = []
    for phase, expected_classes in zip(PHASES, CLASS_COUNTS):
        root = output / phase
        root.mkdir()
        prior = [str(roots[x]) for x in ('modulecache', 'graph', 'original162') if x in roots]
        classpath = ':'.join(prior + cp_jars)
        selected = [REPO / row['path'] for row in rows if row['phase'] == phase]
        compiler = [str(java), '-XX:-UsePerfData', '-XX:ActiveProcessorCount=1', '-XX:ReservedCodeCacheSize=128m', '-Xss4m', '-Xmx2g', '-XX:-HeapDumpOnOutOfMemoryError', '-XX:ErrorFile=' + str(output / 'compiler_error.log'), '-cp', ':'.join(cp_jars), 'scala.tools.nsc.Main', '-classpath', classpath, '-language:reflectiveCalls', '-d', str(root)]
        if phase in ('original162', 'helpers'):
            compiler.append('-Xplugin:' + plugin)
        compiler += list(map(str, selected))
        log = output / (phase + '.log')
        with log.open('xb') as stream:
            result = subprocess.run(compiler, cwd=root, stdout=stream, stderr=subprocess.STDOUT, timeout=300, preexec_fn=child_limits, check=False)
        if result.returncode:
            print(log.read_bytes()[:20000].decode('utf-8', errors='replace'))
        need(result.returncode == 0, 'Scala compilation failed: ' + phase)
        classes = {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob('*.class')}
        need(len(classes) == expected_classes and not (set(classes) & set(combined)), 'complete exclusive class families: ' + phase)
        combined.update(classes)
        roots[phase] = root
        reports.append(dict(phase=phase, source_count=len(selected), class_count=len(classes), diagnostics_bytes=log.stat().st_size))
    need(len(combined) == 1216, 'complete newly compiled exclusive class set')
    # Repeat source identity verification; these are new CI classes, not the old local binary receipt.
    selection()
    print(json.dumps(dict(status='TEMP_SOURCE_COMPILE_ONLY', source_count=204, class_count=1216, phases=reports,
                          elaboration_run=False, native_loaded=False, profiles_run=False, numerical_acceptance=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--java', type=Path)
    args = parser.parse_args()
    rows, jars = selection()
    if args.check_only:
        need(args.output is None and args.java is None, 'read-only selection check')
        print(json.dumps(dict(status='TEMP_SOURCE_SELECTION_ONLY', sources=len(rows), public_maven_roles=len(jars), unique_maven_artifacts=len({r['maven_path'] for r in jars}), execution=False)))
        return
    need(args.output is not None and args.java is not None, 'explicit fresh output and JDK for compile-only mode')
    output = args.output.absolute()
    need(not output.exists() and not output.is_symlink() and output.parent.resolve(strict=True) == output.parent, 'new canonical compile-only output')
    need(not output.is_relative_to(REPO), 'build outputs stay outside source checkout')
    need(not any(os.environ.get(key) for key in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH', 'LD_PRELOAD', 'LD_AUDIT', 'LD_LIBRARY_PATH')), 'no ambient compiler/runtime injection')
    output.mkdir()
    compile_sources(rows, jars, output, args.java.resolve(strict=True))


if __name__ == '__main__':
    main()
