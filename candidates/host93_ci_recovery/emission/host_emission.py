"""Portable Host93 reconstruction. SOURCE-only unless an authorized caller calls run.

All child execution belongs to call_phase; this module has no subprocess runner.
Published recipes are raw-byte pinned, frozen, then consumed from that snapshot.
Historical audit paths/receipts and historical generated outputs are never inputs.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Require Python -I -S -B before any project load.')

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import types

HERE = Path(__file__).resolve().parent
MIB = 1024 * 1024
BASE = 'candidates/qwen2_resident_matrix/host93_source_recovery/'
ASSEMBLER = BASE + 'assemble_host93.py'
REPLAY = BASE + 'SOURCE_REPLAY_PLAN.json'
ACQUIRER = BASE + 'acquisition/acquire.py'
CLASS_HELPER = 'development_snapshots/canonical_host93_observation_source_20261018/calibration/run_class_gate.py'
CHIRRTL_HELPER = 'development_snapshots/canonical_host93_chirrtl_source_20261018/run_chirrtl_gate.py'
SV_HELPER = 'development_snapshots/canonical_host93_sv_calibration_source_20261018/run_sv_gate.py'
MEMBER_HELPER = 'development_snapshots/canonical_host93_firtool_acquisition_source_20261018/acquire_firtool_member.py'
PINS_PIN = {'bytes': 24660, 'sha256': '45831ad171ce04c62d746325b3afb90abb4e2e7467e0e8510034529917603f8e'}
FIR_PIN = {'bytes': 42417256, 'sha256': '264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'}
SV_PIN = {'bytes': 76366612, 'sha256': '2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'}
FIRTOOL_PIN = {'bytes': 25009456, 'sha256': '7f52d2a3782d09736895f66e7eb0e5cc4b3b1b18aa1ad0d04fca4cd6e42cd2ee'}

# This child bootstrap hashes and compiles the identical bounded source buffer.
# The script is not passed to Python's import/pyc loader.
BOOTSTRAP = '''import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
 raise SystemExit('Require Python -I -S -B before source load')
import hashlib,os,stat
from pathlib import Path
def need(ok,reason):
 if not ok: raise ValueError(reason)
def stamp(s):
 return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
need(len(sys.argv)>=4,'fixed source arguments required')
p,size,pin=sys.argv[1:4]; size=int(size); path=Path(p)
need(path.is_absolute() and '..' not in path.parts and str(path)==p,'normalized absolute source path')
need(0<size<=2*1024*1024 and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'fixed source bounds')
parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
 for part in path.parent.parts[1:]:
  nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
  os.close(parent); parent=nxt
 fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
 try:
  before=os.fstat(fd)
  need(stat.S_ISREG(before.st_mode) and before.st_size==size,'fixed source regular size')
  chunks=[]; count=0
  while count<=size:
   block=os.read(fd,min(65536,size+1-count))
   if not block: break
   chunks.append(block); count+=len(block)
  raw=b''.join(chunks)
  need(len(raw)==size and hashlib.sha256(raw).hexdigest()==pin,'fixed source bytes before compile')
  need(stamp(before)==stamp(os.fstat(fd))==stamp(os.stat(path.name,dir_fd=parent,follow_symlinks=False)),'fixed source identity changed')
 finally:
  os.close(fd)
finally:
 os.close(parent)
sys.argv=[p]+sys.argv[4:]
ns={'__name__':'__main__','__file__':p,'__package__':None}
exec(compile(raw,p,'exec',dont_inherit=True),ns)
'''


def need(condition, message):
    if not condition:
        raise ValueError(message)


def unique_json(raw):
    def pairs(entries):
        value = {}
        for key, item in entries:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs)


def relative(name):
    need(type(name) is str and 0 < len(name) <= 4096, 'relative name length')
    path = PurePosixPath(name)
    need(not path.is_absolute() and str(path) == name and
         all(x not in ('', '.', '..') for x in name.split('/')) and
         not any(x in name for x in ('\\', '\x00', '\r', '\n')), 'unsafe relative path')
    return name


def clean(path):
    path = Path(path).absolute()
    need('..' not in path.parts and all(not p.is_symlink() for p in (path, *path.parents)), 'unsafe path')
    return path


def _stamp(info):
    return tuple(getattr(info, 'st_' + k) for k in ('dev', 'ino', 'mode', 'size', 'mtime_ns', 'ctime_ns'))


def read_bytes(path, cap, expected=None):
    path = clean(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap, 'regular bounded file required')
        if expected is not None:
            need(before.st_size == expected['bytes'], 'fixed input byte count')
        raw = handle.read(cap + 1)
        need(len(raw) == before.st_size and _stamp(before) == _stamp(os.fstat(handle.fileno())), 'input changed during read')
    need(_stamp(before) == _stamp(path.stat(follow_symlinks=False)), 'input replaced during read')
    if expected is not None:
        need(byte_identity(raw) == expected, 'fixed input SHA-256 or size mismatch')
    return raw


def byte_identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def file_identity(path, cap):
    path = clean(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap, 'regular bounded identity input required')
        count, digest = 0, hashlib.sha256()
        while True:
            raw = handle.read(min(65536, cap - count + 1))
            if not raw:
                break
            count += len(raw)
            need(count <= cap, 'identity input byte cap')
            digest.update(raw)
        need(count == before.st_size and _stamp(before) == _stamp(os.fstat(handle.fileno())), 'identity input changed')
    need(_stamp(before) == _stamp(path.stat(follow_symlinks=False)), 'identity input replaced')
    return {'bytes': count, 'sha256': digest.hexdigest()}


def inventory(root, tree_cap, file_cap, entry_cap=20000, file_count_cap=10000):
    """Complete finite inventory: all entries, directories, regular files, no links."""
    root = clean(root)
    need(root.is_dir(), 'inventory root missing')
    pending, directories, files, entries, total = [root], [], {}, 0, 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as scan:
            for entry in scan:
                entries += 1
                need(entries <= entry_cap, 'inventory entry cap')
                name = relative(Path(entry.path).relative_to(root).as_posix())
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    directories.append(name)
                    pending.append(Path(entry.path))
                else:
                    need(stat.S_ISREG(mode), 'nonregular inventory entry')
                    need(len(files) < file_count_cap, 'inventory file count cap')
                    pin = file_identity(entry.path, min(file_cap, tree_cap - total))
                    total += pin['bytes']
                    need(total <= tree_cap, 'inventory tree byte cap')
                    files[name] = pin
    return {'complete': True, 'entries': entries, 'directories': sorted(directories),
            'files': dict(sorted(files.items())), 'file_count': len(files), 'bytes': total}


def exact_files(actual, expected):
    need(set(actual['files']) == set(expected), 'complete file inventory differs')
    for name, pin in expected.items():
        need(actual['files'][name] == pin, 'actual bytes differ: ' + name)


def write_new(path, raw, mode=0o600):
    path = clean(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)


def save(path, value):
    write_new(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


def source_pins():
    value = unique_json(read_bytes(HERE / 'SOURCE_PINS.json', PINS_PIN['bytes'], PINS_PIN))
    need(value['schema'] == 'host93-portable-ci-source-pins-v1' and value['project_input_count'] == 111,
         'source pin schema')
    need(len(value['files']) == 121, 'fixed source pin count')
    for name, pin in value['files'].items():
        relative(name)
        need(set(pin) == {'bytes', 'sha256'} and type(pin['bytes']) is int and 0 < pin['bytes'] <= 2*MIB and
             re.fullmatch('[a-f0-9]{64}', pin['sha256']), 'invalid source pin')
    return value['files']


def static_check(repo):
    """Read source identities only. No project Python is compiled or executed."""
    repo, pins = clean(repo), source_pins()
    for name, pin in pins.items():
        read_bytes(repo / name, pin['bytes'], pin)
    return {'status': 'SOURCE_STATIC_PINS_ONLY', 'source_file_count': len(pins),
            'project_input_count': 111, 'source_assembled': False, 'tools_acquired': False,
            'java_started': False, 'firtool_started': False, 'rtl_generated': False}


def load_source(path, raw, pin):
    """Compile only the already fixed byte buffer; never reopen for execution."""
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'require Python -I -S -B before source compile')
    need(type(raw) is bytes and byte_identity(raw) == pin, 'same-buffer source identity mismatch')
    module = types.ModuleType('_host93_pinned_' + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def limits(total, work, cpu, address, fsize, sample_rows=None):
    return {'total_seconds': total, 'work_seconds': work, 'cpu_seconds': cpu,
            'as_bytes': address, 'fsize_bytes': fsize, 'log_bytes': 2*MIB,
            'sample_rows': total + 10 if sample_rows is None else sample_rows}


LIMITS = {
    'java_version': limits(30, 10, 10, 4*1024*MIB, 2*MIB),
    'acquire_jar87': limits(1200, 1185, 300, 512*MIB, 64*MIB),
    'acquire_hardfloat20': limits(300, 285, 120, 512*MIB, 2*MIB),
    'assemble': limits(60, 45, 40, 512*MIB, 2*MIB),
    'class': limits(330, 300, 300, 4*1024*MIB, 48*MIB),
    'chirrtl': limits(90, 60, 60, 4*1024*MIB, 48*MIB),
    'acquire_firtool': limits(180, 165, 120, 512*MIB, 64*MIB),
    'sv': limits(390, 360, 360, 2*1024*MIB, 128*MIB, 400),
}


def _accept_phase(value):
    need(type(value) is dict and set(('record', 'raw_log', 'usage', 'evidence_root')) <= set(value), 'phase result contract')
    need(type(value['record']) is dict and value['record'].get('exit_code') == 0 and
         value['record'].get('cleanup_confirmed') is True, 'phase exit/cleanup not confirmed')
    need(type(value['raw_log']) is bytes and len(value['raw_log']) <= 2*MIB, 'bounded raw phase log required')
    return {'record': value['record'], 'usage': value['usage'],
            'evidence_root': str(value['evidence_root']), 'raw_log_identity': byte_identity(value['raw_log'])}


ACQUISITION_PHASES = ('acquire_jar87', 'acquire_hardfloat20', 'acquire_firtool')

TRANSPORT_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                  'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
                  'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE')


def phase_environment(name, base):
    """Only fixed acquisition phases inherit existing platform transport settings.

    Values are forwarded as-is, never written into a receipt or public evidence.
    Native/build phases retain their original clean environment. No proxy or CA
    is created and no direct-network fallback is attempted.
    """
    result = dict(base)
    if name in ACQUISITION_PHASES:
        for key in TRANSPORT_KEYS:
            if key in os.environ:
                result[key] = os.environ[key]
    return result


def _acquired(root, plan, extras, tree_cap):
    actual = inventory(root, tree_cap, 64*MIB)
    want = {a['relative_destination'] for a in plan['artifacts']} | set(extras)
    need(set(actual['files']) == want, 'acquisition output inventory differs')
    for artifact in plan['artifacts']:
        pin = actual['files'][artifact['relative_destination']]
        need(pin['sha256'] == artifact['sha256'] and pin['bytes'] < artifact['max_transfer_bytes'], 'acquired bytes differ')
        need(artifact['known_size_bytes'] in (None, pin['bytes']), 'acquired size differs')
    return actual


def _java21():
    chosen = 'JAVA_HOME_21_X64' if os.environ.get('JAVA_HOME_21_X64') else 'JAVA_HOME'
    need(os.environ.get(chosen), 'Java 21 must already be supplied by the CI runner')
    # Standard runner JAVA_HOME may be a symlink; pin its resolved official installation.
    home = clean(Path(os.environ[chosen]).resolve(strict=True))
    java = clean((home / 'bin/java').resolve(strict=True))
    need(java.is_relative_to(home) and os.access(java, os.X_OK), 'Java binary missing or outside selected JDK')
    release = read_bytes(home / 'release', MIB)
    need(re.search(rb'^JAVA_VERSION="21(?:[.\-+"])[^\r\n]*', release, re.M), 'selected release is not Java 21')
    return home, java, {'environment_key': chosen, 'java': file_identity(java, 64*MIB),
                        'release': byte_identity(release)}


def run(repo: Path, work: Path, call_phase):
    """Reconstruct once using a caller's bounded CPU1 runner and shared 6600s deadline.

    call_phase(name, argv, cwd, environment, limits) must return original bounded
    record, raw_log bytes, child usage, and evidence_root; failures must raise.
    This function never retries and never treats old artifacts as fresh evidence.
    work must not exist. Results contain measured runtime paths, not source pins
    tied to one machine. The caller owns retaining all evidence, including failure.
    """
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'use Python -I -S -B')
    repo, work = clean(repo), clean(work)
    need(repo.is_dir() and (repo / '.git').exists(), 'existing repository checkout required')
    need(work.parent.is_dir() and not work.exists(), 'fresh work directory required')
    need(not work.is_relative_to(repo) and not repo.is_relative_to(work), 'work must be disjoint from repository')
    need(callable(call_phase), 'bounded phase callback required')
    work.mkdir(mode=0o700)
    result = {'status': 'INCOMPLETE_HOST93_FRESH_EMISSION', 'phases': {}, 'inventories': {}, 'identities': {},
              'paths': {}, 'historical95_identity_inherited': False, 'host_executed': False,
              'numerical_qualification': False, 'full_block_rtl_passes': 0}
    try:
        pins = source_pins()
        frozen = work / 'frozen_repo'
        frozen.mkdir()
        source_raw = {}
        for name, pin in pins.items():
            raw = read_bytes(repo / name, pin['bytes'], pin)
            source_raw[name] = raw
            write_new(frozen / name, raw)
        frozen_inventory = inventory(frozen, 4*MIB, 2*MIB)
        exact_files(frozen_inventory, pins)
        result['inventories']['fixed_source_inputs'] = frozen_inventory
        plan = unique_json(source_raw[REPLAY])
        need(len(plan['input_sha256']) == 111 and len(plan['expected93']) == 93, 'Host93 input/source cardinality')
        for name, sha in plan['input_sha256'].items():
            need(pins[name]['sha256'] == sha, 'replay/source pins disagree')
        jplan, hplan, fplan = [unique_json(source_raw[BASE + 'acquisition/plans/' + group + '.json'])
                               for group in ('jar87', 'hardfloat20', 'firtool')]
        class_helper = load_source(frozen / CLASS_HELPER, source_raw[CLASS_HELPER], pins[CLASS_HELPER])
        chirrtl_helper = load_source(frozen / CHIRRTL_HELPER, source_raw[CHIRRTL_HELPER], pins[CHIRRTL_HELPER])
        sv_helper = load_source(frozen / SV_HELPER, source_raw[SV_HELPER], pins[SV_HELPER])
        java_home, java, java_pin = _java21()
        python = clean(Path(sys.executable).resolve(strict=True))
        python_pin = file_identity(python, 64*MIB)
        result['identities'].update({'java21': java_pin, 'python': python_pin})
        for name in ('home', 'tmp', 'phases'):
            (work / name).mkdir()
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
               'JAVA_HOME': str(java_home), 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'PYTHONHASHSEED': '0'}

        def phase(name, argv, cwd):
            phase_cwd = work / 'phases' / name
            phase_cwd.mkdir()
            need(file_identity(python, 64*MIB) == python_pin, 'Python changed before phase')
            start = time.monotonic()
            value = call_phase('host93_' + name, list(map(str, argv)), phase_cwd, phase_environment(name, env), dict(LIMITS[name]))
            result['phases'][name] = _accept_phase(value)
            result['inventories']['phase_cwd_' + name] = inventory(phase_cwd, 64*MIB, 48*MIB)
            need(time.monotonic() - start <= LIMITS[name]['total_seconds'], 'phase total deadline exceeded')
            need(file_identity(python, 64*MIB) == python_pin, 'Python changed after phase')
            return value['raw_log']

        def script(name, source, argv):
            raw = read_bytes(frozen / source, pins[source]['bytes'], pins[source])
            need(raw == source_raw[source], 'script snapshot changed')
            return phase(name, [python, '-I', '-S', '-B', '-c', BOOTSTRAP, frozen / source,
                                pins[source]['bytes'], pins[source]['sha256'], *argv], work)

        def stable_inputs():
            exact_files(inventory(frozen, 4*MIB, 2*MIB), pins)
            need(file_identity(java, 64*MIB) == java_pin['java'] and
                 file_identity(java_home / 'release', MIB) == java_pin['release'], 'Java inputs changed')

        log = phase('java_version', [java, '-Xmx64m', '-XX:ActiveProcessorCount=1', '-version'], work)
        need(re.search(rb'(?:openjdk|java) version "21(?:[.\-+"])', log), 'Java 21 version probe failed')
        stable_inputs()
        acquired = work / 'acquired'
        acquired.mkdir()
        jars, hf, ft = (acquired / name for name in ('jar87', 'hardfloat20', 'firtool'))
        for group, destination, ap, cap in (('jar87', jars, jplan, 514*MIB), ('hardfloat20', hf, hplan, 3*MIB)):
            script('acquire_' + group, ACQUIRER, ['fetch', group, '--repository', repo,
                   '--output-root', destination, '--execute-acquisition'])
            actual = _acquired(destination, ap, {'ACQUISITION.json'}, cap)
            result['inventories'][group] = actual
            stable_inputs()

        assembled = work / 'assembled'
        exact_files(inventory(hf, 3*MIB, 2*MIB), result['inventories']['hardfloat20']['files'])
        script('assemble', ASSEMBLER, ['--repo', frozen, '--assemble-reviewed-source',
               '--hardfloat-scala', hf / 'hardfloat/src/main/scala', '--output', assembled])
        assembly = inventory(assembled, 16*MIB, 2*MIB)
        expected_names = {'scala/' + name for name in plan['expected93']} | {'SOURCE_RECEIPT.json'}
        result['inventories']['assembled'] = assembly
        need(set(assembly['files']) == expected_names, 'fresh assembly complete inventory')
        for name, sha in plan['expected93'].items():
            need(assembly['files']['scala/' + name]['sha256'] == sha, 'assembled93 source mismatch')
        exact_files(inventory(hf, 3*MIB, 2*MIB), result['inventories']['hardfloat20']['files'])
        stable_inputs()
        classes = work / 'classes'
        classes.mkdir()
        source = assembled / 'scala'
        exact_files(inventory(jars, 514*MIB, 64*MIB), result['inventories']['jar87']['files'])
        exact_files(inventory(assembled, 16*MIB, 2*MIB), assembly['files'])
        phase('class', class_helper.command(java, jars, classes, source, plan['expected93'], jplan), work)
        class_inventory = inventory(classes, 64*MIB, 48*MIB)
        result['inventories']['classes'] = class_inventory
        need(class_inventory['files'] and all(name.endswith('.class') for name in class_inventory['files']), 'nonempty class-only output required')
        need('heteronpu/continuous/EmitCanonicalHost93.class' in class_inventory['files'], 'Host93 emitter class missing')
        exact_files(inventory(assembled, 16*MIB, 2*MIB), assembly['files'])
        exact_files(inventory(jars, 514*MIB, 64*MIB), result['inventories']['jar87']['files'])
        stable_inputs()

        structure = work / 'structure'
        exact_files(inventory(classes, 64*MIB, 48*MIB), class_inventory['files'])
        exact_files(inventory(jars, 514*MIB, 64*MIB), result['inventories']['jar87']['files'])
        log = phase('chirrtl', chirrtl_helper.command(java, classes, jars, jplan, structure), work)
        structure_inventory = inventory(structure, 64*MIB, 48*MIB, 16, 8)
        result['inventories']['chirrtl'] = structure_inventory
        fir = structure / 'HostBlockCollection.fir'
        need(set(structure_inventory['files']) == {'HostBlockCollection.fir'}, 'exact fresh FIR output')
        result['identities']['fir'] = structure_inventory['files']['HostBlockCollection.fir']
        need(result['identities']['fir'] == FIR_PIN, 'fresh FIR deterministic identity mismatch')
        need(log.count(b'CANONICAL_HOST93_CHIRRTL_BEGIN ') == 1 and
             log.count(b'CANONICAL_HOST93_CHIRRTL_WRITTEN ') == 1, 'exact Host93 emitter markers required')
        exact_files(inventory(classes, 64*MIB, 48*MIB), class_inventory['files'])
        exact_files(inventory(jars, 514*MIB, 64*MIB), result['inventories']['jar87']['files'])
        stable_inputs()

        script('acquire_firtool', MEMBER_HELPER, ['--acquisition-source', frozen / (BASE + 'acquisition'),
               '--repository', repo, '--output-root', ft, '--execute-reviewed-acquisition'])
        tool_inventory = _acquired(ft, fplan, {'firtool', 'ACQUISITION.json', 'MEMBER.json'}, 100*MIB)
        result['inventories']['firtool_acquisition'] = tool_inventory
        need(tool_inventory['files']['firtool'] == FIRTOOL_PIN, 'official firtool member identity mismatch')
        need(stat.S_IMODE((ft / 'firtool').stat().st_mode) == 0o600, 'acquired member must remain mode0600')
        member_receipt = unique_json(read_bytes(ft / 'MEMBER.json', MIB))
        need(member_receipt['extracted_member_count'] == 1 and member_receipt['binary_executed'] is False and
             member_receipt['member_name'] == 'org.chipsalliance/llvm-firtool/linux-x64/bin/firtool', 'single-member extraction receipt')
        tool = work / 'tool/firtool'
        write_new(tool, read_bytes(ft / 'firtool', FIRTOOL_PIN['bytes'], FIRTOOL_PIN), 0o700)
        need(file_identity(tool, 32*MIB) == FIRTOOL_PIN, 'execution snapshot identity')
        rtl = work / 'rtl'
        rtl.mkdir()
        stable_inputs()
        need(file_identity(fir, 48*MIB) == FIR_PIN and file_identity(tool, 32*MIB) == FIRTOOL_PIN, 'SV preflight inputs differ')
        phase('sv', sv_helper.command(tool, fir, rtl), work)
        rtl_inventory = inventory(rtl, 256*MIB, 128*MIB, 64, 32)
        result['inventories']['rtl'] = rtl_inventory
        need({'HostBlockCollection.sv'} <= set(rtl_inventory['files']) <= {'HostBlockCollection.sv', 'circt.anno.json'}, 'unexpected SV output files')
        result['identities']['sv'] = rtl_inventory['files']['HostBlockCollection.sv']
        need(result['identities']['sv'] == SV_PIN, 'fresh SV deterministic identity mismatch')
        if 'circt.anno.json' in rtl_inventory['files']:
            need(rtl_inventory['files']['circt.anno.json']['bytes'] <= 32*MIB, 'annotation byte cap')
        need(file_identity(fir, 48*MIB) == FIR_PIN and file_identity(tool, 32*MIB) == FIRTOOL_PIN, 'SV inputs changed')
        exact_files(inventory(ft, 100*MIB, 64*MIB), tool_inventory['files'])
        stable_inputs()
        result['paths'] = {name: str(path) for name, path in {
            'source': source, 'classes': classes, 'jars': jars, 'hardfloat': hf,
            'fir': fir, 'sv': rtl / 'HostBlockCollection.sv', 'firtool': tool,
            'frozen_repo': frozen}.items()}
        result['inventories']['complete_work_before_result_receipt'] = inventory(work, 1024*MIB, 128*MIB, 40000, 20000)
        result['status'] = 'PASS_HOST93_FRESH_EMISSION_ONLY'
        result['identities']['firtool'] = file_identity(tool, 32*MIB)
        for name, path in (('fir', fir), ('sv', rtl / 'HostBlockCollection.sv'), ('firtool', tool)):
            result[name] = {'path': str(path), **result['identities'][name],
                            'mode': format(stat.S_IMODE(path.stat().st_mode), '04o')}
        save(work / 'HOST_EMISSION_RESULT.json', result)
        return result
    except BaseException as error:
        result['status'] = 'INCOMPLETE_HOST93_FRESH_EMISSION'
        result['error_type'] = type(error).__name__
        result['error'] = str(error)[:4000]
        try:
            result['inventories']['failure_work_before_receipt'] = inventory(work, 1024*MIB, 128*MIB, 40000, 20000)
        except BaseException as inventory_error:
            result['failure_inventory'] = {'complete': False, 'error_type': type(inventory_error).__name__,
                                           'error': str(inventory_error)[:1000]}
        try:
            save(work / 'HOST_EMISSION_FAILED.json', result)
        except BaseException as receipt_error:
            if hasattr(error, 'add_note'):
                error.add_note('Failure receipt error: ' + type(receipt_error).__name__)
        raise


def main():
    parser = argparse.ArgumentParser(description='Source-only static identity checks; no execution CLI.')
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(static_check(args.repo), sort_keys=True))


if __name__ == '__main__':
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'use Python -I -S -B')
    main()
