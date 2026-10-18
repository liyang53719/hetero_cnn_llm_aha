"""Fixed canonical16 file-to-same-RAM gate. Default is source check only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
AS_LIMIT = 256 * 1024 * 1024


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def group_state(pgid):
    try:
        os.killpg(pgid, 0)
        return 'present'
    except ProcessLookupError:
        return 'absent'
    except BaseException:
        return 'unknown'


def observe_exit(child, command, wall_seconds):
    # Linux only. Never poll()/wait() here: WNOWAIT keeps the original leader
    # unreaped, so its PID/PGID cannot be reused before group cleanup.
    deadline = time.monotonic() + wall_seconds
    while True:
        event = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if event is not None:
            require(event.si_pid == child.pid, 'unexpected waitid child identity')
            return dict(pid=event.si_pid, code=event.si_code, status=event.si_status)
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(command, wall_seconds)
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))


def bounded(label, command, directory, output, wall_seconds, cpu_seconds, as_limit=AS_LIMIT):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_limit))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    record = dict(stage=label, argv=command, cwd=str(directory), status='STARTING',
                  wall_limit_seconds=wall_seconds, cpu_limit_seconds=cpu_seconds,
                  address_space_limit_bytes=as_limit, spawn_handle_acquired=False,
                  pid=None, pgid=None, timed_out=False, parent_exception=None,
                  exit_observed_while_unreaped=None, anchor_confirmed=False,
                  kill_attempted=False, kill_result='not_requested', reaped=False,
                  group_state='unknown', cleanup_confirmed=False, exit_code=None,
                  cleanup_budget_seconds=5)
    receipt = output / (label + '.json')
    log_path = output / (label + '.log')
    save(receipt, record)
    started = time.monotonic()
    child = None
    failure = None
    with log_path.open('wb') as log:
        try:
            child = subprocess.Popen(command, cwd=directory, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            record.update(spawn_handle_acquired=True, pid=child.pid, pgid=child.pid)
            save(receipt, record)
            record['exit_observed_while_unreaped'] = observe_exit(child, command, wall_seconds)
        except BaseException as error:
            failure = error
            record['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
            record['parent_exception'] = dict(type=type(error).__name__, message=str(error))
        finally:
            if child is not None:
                deadline = time.monotonic() + 5
                # Verify this is still OUR unreaped child, alive or zombie.
                # ECHILD/other errors mean no identity proof and prohibit kill.
                try:
                    event = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    require(event is None or event.si_pid == child.pid, 'cleanup anchor mismatch')
                    record['anchor_confirmed'] = True
                except BaseException as error:
                    record['anchor_error'] = dict(type=type(error).__name__, message=str(error))
                    if failure is None:
                        failure = error
                if record['anchor_confirmed']:
                    record['group_before_reap'] = group_state(child.pid)
                    if record['group_before_reap'] != 'absent':
                        record['kill_attempted'] = True
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                            record['kill_result'] = 'signal_sent_before_reap'
                        except ProcessLookupError:
                            record['kill_result'] = 'group_already_absent'
                        except BaseException as error:
                            record['kill_result'] = type(error).__name__ + ': ' + str(error)
                            if failure is None:
                                failure = error
                    try:
                        child.wait(timeout=max(0, deadline - time.monotonic()))
                    except BaseException as error:
                        record['reap_error'] = dict(type=type(error).__name__, message=str(error))
                        if failure is None:
                            failure = error
                    record['exit_code'] = child.returncode
                    record['reaped'] = child.returncode is not None
                # A zombie leader itself keeps the group present. Only AFTER
                # final reap can absence be required. All probes here are read
                # only: never signal a potentially recycled PGID after reap.
                record['group_state'] = group_state(child.pid)
                try:
                    while record['group_state'] != 'absent' and time.monotonic() < deadline:
                        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
                        record['group_state'] = group_state(child.pid)
                except BaseException as error:
                    record['cleanup_probe_error'] = dict(type=type(error).__name__, message=str(error))
                    record['group_state'] = 'unknown'
                    if failure is None:
                        failure = error
                record['cleanup_confirmed'] = record['reaped'] and record['group_state'] == 'absent'
            record['seconds'] = round(time.monotonic() - started, 6)
            record['status'] = ('PASS' if failure is None and record['exit_code'] == 0
                                and record['cleanup_confirmed'] else 'FAIL')
            save(receipt, record)
    record['log_bytes'] = log_path.stat().st_size
    if record['log_bytes'] > 65536:
        record['status'] = 'FAIL'
        record['output_limit_exceeded'] = True
    save(receipt, record)
    if failure is not None:
        raise failure
    require(record['status'] == 'PASS', label + ' failed; retained ' + receipt.name)
    return record, log_path.read_bytes()

def no_symlinks(path):
    path = Path(os.path.abspath(path))
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'symlink path refused')
    return path


def prepare_inputs(root):
    names = {'initialization_ram.hpp','sha256.hpp','same_buffer_loader.hpp',
             'canonical16_binding.hpp','consume_canonical16.cpp','replay_metadata.py',
             'SOURCE_PIN.json','EXPECTED_LAYOUT.json','INPUT_SPEC.json'}
    pins = json.loads((HERE/'BUILD_INPUT_PINS.json').read_text())
    require(set(pins['files']) == names, 'exact nine source inputs required')
    copied, verified = {}, {}
    for name, pin in pins['files'].items():
        path = no_symlinks(root/name)
        require(path.is_file() and path.stat().st_size == pin['bytes'] < 100000,
                'source input extent differs: '+name)
        raw = path.read_bytes()
        require(digest(raw) == pin, 'source input drift: '+name)
        copied[name] = raw; verified[name] = digest(raw)
    return copied, verified


def check_providers(path, spec):
    # Receipt is provenance, not a substitute for the child's stream/RAM hashes.
    receipt = no_symlinks(path/'PROVIDERS.json')
    pin = spec['provider_receipt']
    require(receipt.is_file() and receipt.stat().st_size == pin['bytes'] < 65536,
            'provider receipt type/size differs')
    with receipt.open('rb') as stream:
        raw = stream.read(pin['bytes']+1)
        require(stream.read(1) == b'', 'provider receipt trailing bytes')
    require(digest(raw) == pin, 'fixed provider receipt drift')
    actual = json.loads(raw)
    require(actual['status'] == 'FIXED_PROVIDER14_BYTES_VERIFIED' and
            actual['provider_payload_bytes'] == 94916608, 'provider receipt not complete')
    wanted = [{'name':r['name'],'file':r['name']+'.bin','bytes':r['bytes'],'sha256':r['sha256']}
              for r in spec['inputs'][2:]]
    require(actual['providers'] == wanted, 'provider receipt identity/order differs')
    require({p.name for p in path.iterdir()} == {'PROVIDERS.json'} | {p['file'] for p in wanted},
            'unexpected provider directory entries')
    for row in wanted:
        p = no_symlinks(path/row['file'])
        require(p.is_file() and p.stat().st_size == row['bytes'], 'provider file type/size differs')
    return digest(raw)


def validate_metadata(directory, log, spec):
    record = json.loads(log)
    require(record['status'] == 'EXACT_SOURCE_METADATA_REPLAY_ONLY' and
            record['tensor_payload_bytes_written'] == 0, 'unexpected metadata replay result')
    require(set(record['files']) == {'metadata.json','metadata_layout.hpp',
                                    'host_commands.bin','host_descriptors.bin'}, 'metadata output set differs')
    actual = {}
    for row in spec['inputs'][:2]:
        name = 'host_'+row['name']+'.bin'
        path = no_symlinks(directory/name)
        require(path.is_file() and path.stat().st_size == row['bytes'] < 4096, 'table size differs')
        data = path.read_bytes()
        pin = {'bytes':row['bytes'],'sha256':row['sha256']}
        require(digest(data) == pin == record['files'][name], 'actual metadata table SHA256 differs')
        actual[name] = digest(data)
    return actual


def validate_behavior(actual, spec):
    fields = {'status','inputs','ram_base','ram_bytes','declared_coverage_bytes',
              'same_ram_offsets_verified','coverage_sealed','token_redeemed_once',
              'sha256_passes','sha256_total_bytes','full_host_ready','launch_ready','eda_executed'}
    require(type(actual) is dict and set(actual) == fields, 'unexpected canonical result fields')
    require(actual['status'] == 'CANONICAL16_SAME_RAM_VERIFIED', 'canonical load did not complete')
    require(type(actual['inputs']) is list and len(actual['inputs']) == 16, 'exact 16 actual inputs required')
    for index, (row, fixed) in enumerate(zip(actual['inputs'],spec['inputs'])):
        require(type(row) is dict and set(row) == {'index','name','base','bytes','actual_sha256'},
                'actual input schema differs')
        require(all(type(row[k]) is int for k in ('index','base','bytes')), 'actual input integers required')
        require(row == {'index':index,'name':fixed['name'],'base':fixed['base'],
                        'bytes':fixed['bytes'],'actual_sha256':fixed['sha256']}, 'actual RAM identity differs')
    for key, value in (('ram_base',spec['ram_base']),('ram_bytes',spec['ram_bytes']),
                       ('declared_coverage_bytes',spec['coverage_bytes']),('sha256_passes',4),
                       ('sha256_total_bytes',379681792)):
        require(type(actual[key]) is int and actual[key] == value, 'actual RAM accounting differs: '+key)
    require(all(actual[k] is True for k in ('same_ram_offsets_verified','coverage_sealed','token_redeemed_once')),
            'actual RAM proof flag missing')
    require(all(actual[k] is False for k in ('full_host_ready','launch_ready','eda_executed')),
            'initialization must not claim Host/launch/EDA')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='c++')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--providers', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    copied, verified = prepare_inputs(HERE)
    spec = json.loads(copied['INPUT_SPEC.json'])
    if not args.execute:
        print(json.dumps({'status':'SOURCE_CHECK_ONLY','source_files':len(copied),
                          'native_executed':False,'real_payload_read':False}))
        return 0
    require(args.repo is not None and args.providers is not None and args.output is not None,
            'execute requires repo, providers and fresh output')
    repo = no_symlinks(args.repo).resolve(strict=True)
    providers = no_symlinks(args.providers).resolve(strict=True)
    output = no_symlinks(args.output)
    require(not output.exists() and output.parent.is_dir(), 'fresh output with existing parent required')
    require(not any(output.is_relative_to(p) for p in (repo,providers,HERE)), 'output overlaps input/source tree')
    receipt = check_providers(providers,spec)
    output.mkdir(mode=0o700,exist_ok=False)
    report = dict(status='STARTED',input_hashes=verified,provider_receipt=receipt,stages={},
                  canonical_input_sha_verified=False,full_host_ready=False,launch_ready=False,
                  eda_executed=False,build_and_logs_retained=True)
    save(output/'RESULT.json',report)
    try:
        work = output/'build'; work.mkdir(exist_ok=False)
        for name, raw in copied.items(): (work/name).write_bytes(raw)
        selected = shutil.which(args.compiler)
        require(selected is not None, 'existing requested compiler not found')
        compiler = Path(selected).resolve(strict=True)
        require(compiler.is_file(), 'existing compiler missing')
        report['compiler'] = dict(requested=args.compiler,resolved=str(compiler),**digest(compiler.read_bytes()))
        save(output/'RESULT.json',report)
        version, log = bounded('compiler_version',[str(compiler),'--version'],work,output,5,2)
        report['stages']['compiler_version'] = version
        report['compiler']['version'] = log.decode('utf-8',errors='replace')
        save(output/'RESULT.json',report)
        command = [str(compiler),'-std=c++17','-O0','-Wall','-Wextra','-Werror','-pedantic',
                   '-I',str(work),str(work/'consume_canonical16.cpp'),'-o',str(work/'canonical16_consumer')]
        compilation,_ = bounded('compile',command,work,output,30,30)
        report['stages']['compile'] = compilation; save(output/'RESULT.json',report)
        metadata,log = bounded('metadata',[sys.executable,'-I','-S','-B',str(work/'replay_metadata.py'),
                    '--repository',str(repo),'--output',str(output/'metadata')],work,output,10,5)
        report['stages']['metadata'] = metadata
        report['metadata_tables'] = validate_metadata(output/'metadata',log,spec)
        save(output/'RESULT.json',report)
        execution,log = bounded('run',[str(work/'canonical16_consumer'),str(output/'metadata'),str(providers)],
                                work,output,120,120,as_limit=1024*1024*1024)
        report['stages']['run'] = execution
        actual = validate_behavior(json.loads(log),spec)
        report.update(status='BOUNDED_CANONICAL16_SAME_RAM_PASS',behavior=actual,
                      canonical_input_sha_verified=True,scope='fixed canonical16 input initialization only')
    except BaseException as error:
        report['status'] = 'FAIL'
        report['exception'] = dict(type=type(error).__name__,message=str(error))
    finally:
        for label in ('compiler_version','compile','metadata','run'):
            path = output/(label+'.json')
            if path.exists(): report['stages'][label] = json.loads(path.read_text())
        save(output/'RESULT.json',report)
    print(json.dumps(report,sort_keys=True))
    return 0 if report['status'] == 'BOUNDED_CANONICAL16_SAME_RAM_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
