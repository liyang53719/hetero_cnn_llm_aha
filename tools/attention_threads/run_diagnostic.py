#!/usr/bin/env python3
"""Same-SV threads=2 diagnostic, consuming one trusted production build archive.

Dormant unless explicitly invoked with the trusted successful build's identity.
No Scala emission, baseline rebuild, state injection or numerical acceptance.
Upload only the two compact JSON receipts and the nine explicitly allowlisted
candidate identity/ELF/SV files. Fixtures, weights and raw events stay local.
"""
from pathlib import Path, PurePosixPath
import argparse
import contextlib
import hashlib
import importlib
import json
import os
import re
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import time
from types import MappingProxyType

PIN = '98c7d80f65c5f05b55726c5239a6e9ec15d1b53f'
RTL_SHA256 = 'e8b6ab6640ef0b932a0fc976b00b64998094d692698b4f8e134ead0911611510'
HEADER_SHA256 = '3618a544538abb20d850d24afac11b3479443e4b5f7155f7ecb0680f6c42ea0a'
BUILDER_SHA256 = 'bfd6f528fe036c38113f5316361258c54a1975dd733a97ae9f0d139c72157951'
BUDGET_SECONDS, BUILD_SECONDS, RESERVE_SECONDS = 9000, 6300, 180
WINDOWS = (('norm_prefix', 4096, 60), ('reset_to_matrix_prefix', 65536, 240))
ORDER = ('baseline', 'threads2', 'threads2', 'baseline')
EVENT_MAX_BYTES = 256 * 1024 * 1024
HERE = Path(__file__).resolve().parent
DIAGNOSTIC_ROOT = HERE.parents[1]
BUILD_SCRIPT = 'chisel/continuous_prefill/scripts/run_host_bf16_attention_block_gate.sh'
PREFIX_HEADER = 'chisel/continuous_prefill/tests/host_attention_block_prefix.h'
SOURCE_STAGES = ('capture', 'projection', 'attention', 'block', 'fixture')
REFERENCE_ONLY_PATHS = frozenset(('scripts/rebuild_qk_norm256_corpora.py',
    'scripts/run_qwen35_bf16_audit.py', 'scripts/run_qwen35_prefix_chain.py'))
COMPACT_FILES = ('compact/summary.json', 'compact/source_input_hashes.json')
CANDIDATE_FILES = ('candidate_identity.json', 'build_threads2.sh', 'verilator_argv.json',
    'obj/VHostBlockTop', 'obj/VHostBlockTop.cpp', 'generated/HostBlockTop.sv',
    'generated/SCOPE.json', 'idma_identity.json', 'idma.f')
TIMING_SCOPE = ('elapsed PhysicalAxi.step calls including capture overhead; excludes event '
                'serialization, final memory digest and report; not isolated eval timing')
HEADER = dict(schema='HOST_ATTENTION_BLOCK_PREFIX_EVENTS_V1', numerical_acceptance=False,
              payload_encoding='le_u32x16_hex', timing_excluded=True)
COUNTERS = ('cycles', 'reset_cycles', 'active_cycles', 'ar_handshakes', 'aw_handshakes',
            'w_handshakes', 'r_handshakes', 'b_handshakes')
PAYLOAD_KEYS = {'pre_w_payload_le_hex', 'pre_r_payload_le_hex'}
# Exact original Recorder field inventory. Unknown fields fail closed, including
# anything that might accidentally introduce raw data into a compact report.
EVENT_INTS = set('''pre_reset pre_run pre_running pre_pc pre_launch_valid pre_launch_ready
pre_completion_valid pre_completion_ready pre_completion_word pre_result_valid pre_result_ready
pre_w_mask pre_w_last pre_w_data_fnv1a64 pre_r_id pre_r_resp pre_r_last pre_r_data_fnv1a64
pre_b_id pre_b_resp cycle end_rng end_read_beats end_read_acks end_write_beats end_write_acks
end_read_bursts end_write_bursts end_pending_valid end_pending_write end_pending_error
end_pending_address end_pending_id end_pending_total end_pending_remaining end_pending_delay
end_pending_final end_aw_valid end_collected_beats end_committing_beats end_ar_held end_aw_held
end_w_held end_pc end_issued_jobs end_pipeline_issues end_pipeline_stalls end_idma_transfers
end_idma_read_bursts end_idma_read_beats end_idma_cache_hits end_idma_streamed_beats
end_idma_streamed_write_beats end_memory_accepted_0 end_memory_returned_0 end_memory_accepted_1
end_memory_returned_1 end_useful_macs end_executed_macs end_write_bytes end_reset_required
end_completion_valid end_result_valid end_run end_running end_completions end_successful
end_metadata_reads end_ack_bytes end_physical_bytes end_inferred_length end_inferred_generation'''.split())
EVENT_INTS.update('pre_'+channel+'_'+field for channel in ('ar', 'aw', 'w', 'r', 'b')
                  for field in ('valid', 'ready'))
EVENT_INTS.update('pre_'+channel+'_'+field for channel in ('ar', 'aw')
                  for field in ('address', 'id', 'len', 'size', 'burst'))
REPORT_KEYS = {'schema', 'status', 'numerical_acceptance', 'prefix_reached', 'cycles', 'cycle_limit',
               'constructor_cycles', 'step_elapsed_ns', 'timing_scope', 'event_file', 'event_bytes',
               'prefix_fnv1a64', 'prefix_hash_is_noncryptographic', 'memory_hash_is_noncryptographic',
               'sha256_input', 'deterministic'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda value: require(False, 'nonfinite JSON value'))


def regular(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'regular nonsymlink evidence file required')
    return path


def read_json(path, limit=1024*1024):
    path = regular(path)
    require(0 < path.stat().st_size <= limit, 'JSON exceeds byte bound')
    return decode(path.read_bytes())


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=30).strip()


def parse_cpus(value):
    require(isinstance(value, str) and re.fullmatch(r'\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*', value),
            'invalid CPU list')
    result = set()
    for item in value.split(','):
        ends = list(map(int, item.split('-')))
        first, last = (ends[0], ends[-1])
        require(0 <= first <= last <= 1048576, 'CPU range outside bound')
        result.update(range(first, last+1))
    return result


def cgroup_directories(proc=Path('/proc'), root=Path('/')):
    """Resolve self cgroups against mounted controller roots, including parents."""
    memberships = []
    for line in (proc/'self/cgroup').read_text().splitlines():
        _, controllers, relative = line.split(':', 2)
        memberships.append((set(controllers.split(',')) if controllers else set(), relative))
    result = []
    for line in (proc/'self/mountinfo').read_text().splitlines():
        before, after = line.split(' - ', 1)
        fields, tail = before.split(), after.split()
        kind = tail[0]
        if kind not in ('cgroup', 'cgroup2'):
            continue
        mount_root, mount_at = fields[3:5]
        require('\\' not in mount_at+mount_root, 'escaped cgroup mount unsupported')
        controllers = set(tail[2].split(',')) if kind == 'cgroup' else set()
        for member_controllers, membership in memberships:
            if (kind == 'cgroup2' and member_controllers) or (kind == 'cgroup' and not controllers & member_controllers):
                continue
            require('..' not in PurePosixPath(membership).parts, 'unresolved cgroup namespace path')
            try:
                relative = PurePosixPath(membership).relative_to(mount_root)
            except ValueError:
                continue
            mounted = root / mount_at.lstrip('/')
            current = mounted / str(relative)
            require(current.is_dir(), 'self cgroup not visible')
            while True:
                result.append((kind, controllers, current))
                if current == mounted:
                    break
                current = current.parent
    require(result, 'no visible self cgroup controller hierarchy')
    return result


def resource_snapshot(proc=Path('/proc'), root=Path('/'), affinity=None, command=subprocess.check_output):
    """Admission uses the narrowest visible ancestor quota and effective cpuset."""
    allowed = set(os.sched_getaffinity(0) if affinity is None else affinity)
    status = (proc/'self/status').read_text()
    match = re.search(r'^Cpus_allowed_list:\s*(\S+)\s*$', status, re.M)
    require(match is not None, 'Cpus_allowed_list missing')
    status_cpus = parse_cpus(match[1]); allowed &= status_cpus
    rows, quotas, cpu_seen, cpuset_seen = [], [], False, False
    for kind, controllers, path in cgroup_directories(proc, root):
        row = dict(version=kind, path=str(path), files={})
        names = ('cpu.max', 'cpu.stat', 'cpuset.cpus.effective', 'cpuset.cpus') if kind == 'cgroup2' else (
            'cpu.cfs_quota_us', 'cpu.cfs_period_us', 'cpu.stat', 'cpuacct.usage', 'cpuset.effective_cpus', 'cpuset.cpus')
        for name in names:
            file = path/name
            if file.is_file():
                value = file.read_text().strip(); row['files'][name] = value
                if name in ('cpuset.cpus.effective', 'cpuset.effective_cpus', 'cpuset.cpus') and value:
                    allowed &= parse_cpus(value); cpuset_seen = True
        values = row['files']
        if 'cpu.max' in values:
            quota, period = values['cpu.max'].split(); period = int(period)
            require(period > 0, 'invalid cgroup CPU period'); cpu_seen = True
            if quota != 'max':
                require(int(quota) > 0, 'invalid cgroup CPU quota'); quotas.append(int(quota)/period)
        elif 'cpu.cfs_quota_us' in values and 'cpu.cfs_period_us' in values:
            quota, period = int(values['cpu.cfs_quota_us']), int(values['cpu.cfs_period_us'])
            require(period > 0 and (quota == -1 or quota > 0), 'invalid v1 CPU quota'); cpu_seen = True
            if quota > 0:
                quotas.append(quota/period)
        rows.append(row)
    require(cpu_seen and cpuset_seen, 'CPU quota/cpuset admission evidence incomplete')
    details = {}
    for argv in (['nproc'], ['lscpu']):
        raw = command(argv, text=True, timeout=10)
        require(len(raw) <= 65536, 'CPU inventory exceeds bound')
        details[argv[0]] = raw.strip()
    require(re.fullmatch(r'[1-9]\d*', details['nproc']), 'invalid nproc inventory')
    effective = min([len(allowed), *quotas])
    return dict(sched_getaffinity=sorted(os.sched_getaffinity(0) if affinity is None else affinity),
                cpus_allowed_list=match[1], permitted_cpus=sorted(allowed),
                quota_cpu_limits=quotas, effective_cpu_count=effective,
                selected_affinity=sorted(allowed)[:2] if effective >= 2 else [],
                cgroups=rows, **details)


def cpu_delta(before, after, elapsed, usage_before, usage_after):
    require(elapsed > 0, 'positive runtime required')
    user = usage_after.ru_utime-usage_before.ru_utime
    system = usage_after.ru_stime-usage_before.ru_stime
    result = dict(user_seconds=user, system_seconds=system, cpu_seconds=user+system,
                  mean_cpu_cores=(user+system)/elapsed, cgroup_delta={})
    by_path = {row['path']: row for row in before['cgroups']}
    for row in after['cgroups']:
        prior = by_path.get(row['path'])
        require(prior is not None, 'cgroup changed during execution')
        for filename in ('cpu.stat', 'cpuacct.usage'):
            old, new = prior['files'].get(filename), row['files'].get(filename)
            require((old is None) == (new is None), 'CPU accounting availability drift')
            if old is None:
                continue
            parse = lambda value: ({'usage_ns': int(value)} if filename == 'cpuacct.usage' else
                                   {line.split()[0]: int(line.split()[1]) for line in value.splitlines()})
            left, right = parse(old), parse(new)
            require(left.keys() == right.keys(), 'CPU accounting fields drift')
            diff = {key: right[key]-left[key] for key in left}
            require(all(value >= 0 for value in diff.values()), 'CPU accounting regressed')
            result['cgroup_delta'][row['path']+'/'+filename] = diff
    result['cgroup_scope'] = 'shared cgroup accounting; may include unrelated processes'
    return result


def same_admission(before, after):
    for key in ('sched_getaffinity', 'cpus_allowed_list', 'permitted_cpus', 'quota_cpu_limits',
                'effective_cpu_count', 'selected_affinity'):
        require(before[key] == after[key], 'CPU resource admission drift: '+key)


def read_prefix(output, cycles):
    """Read exact unchanged Recorder schema, bounded streaming full-cycle evidence."""
    require(type(cycles) is int and 37 <= cycles <= 65536, 'prefix cycles outside original driver contract')
    output = Path(output); report = read_json(output/'prefix.json')
    require(type(report) is dict and set(report) == REPORT_KEYS, 'unexpected prefix report schema')
    require(report['schema'] == 'HOST_ATTENTION_BLOCK_PREFIX_V1' and
            report['status'] == 'BOUNDED_DIAGNOSTIC_PREFIX' and
            report['numerical_acceptance'] is False and report['prefix_reached'] is True,
            'prefix cannot award numerical acceptance')
    require(type(report['cycles']) is type(report['cycle_limit']) is int and
            report['cycles'] == report['cycle_limit'] == cycles and report['constructor_cycles'] == 36 and
            report['event_file'] == 'prefix_events.jsonl' and report['timing_scope'] == TIMING_SCOPE,
            'prefix cycle/timing scope drift')
    require(type(report['step_elapsed_ns']) is int and report['step_elapsed_ns'] > 0,
            'missing completed-step timing')
    for key in ('prefix_fnv1a64',):
        require(isinstance(report[key], str) and re.fullmatch('[0-9a-f]{16}', report[key]), 'invalid FNV digest')
    require(report['prefix_hash_is_noncryptographic'] is report['memory_hash_is_noncryptographic'] is True and
            report['sha256_input'] == 'exact prefix_events.jsonl bytes; no timings or output paths', 'digest scope drift')
    path = regular(output/'prefix_events.jsonl'); size = path.stat().st_size
    require(type(report['event_bytes']) is int and report['event_bytes'] == size and
            0 < size <= EVENT_MAX_BYTES, 'prefix event byte bound/count')
    deterministic = report['deterministic']
    require(type(deterministic) is dict and set(deterministic) == set(COUNTERS) | {
        'memory_bytes', 'memory_fnv1a64', 'terminal_event'}, 'unexpected deterministic schema')
    require(all(type(deterministic.get(key)) is int and 0 <= deterministic[key] <= cycles for key in COUNTERS),
            'invalid prefix counters')
    observed = dict.fromkeys(COUNTERS, 0); digest = hashlib.sha256()
    previous_issues = previous_useful = previous_executed = 0
    activity = dict(matrix_pipeline_issue_delta=0, matrix_issue_cycles=0, first_matrix_issue_cycle=None,
                    useful_macs_delta=0, executed_macs_delta=0, pcs_seen=[],
                    norm_completion_cycle=None, norm_completion_before_matrix=False,
                    norm_acked_bytes=0, norm_physical_bytes=0, norm_write_ack_beats=0)
    pcs = set(); event = None; consumed = 0
    with path.open('rb') as stream:
        line = stream.readline(8193); consumed += len(line); digest.update(line)
        header = decode(line)
        require(len(line) <= 8192 and line.endswith(b'\n') and type(header) is dict and
                header == HEADER and all(type(header[key]) is type(value) for key, value in HEADER.items()),
                'wrong event header')
        for index in range(1, cycles+1):
            line = stream.readline(8193); consumed += len(line); digest.update(line)
            require(consumed <= EVENT_MAX_BYTES and 0 < len(line) <= 8192 and line.endswith(b'\n'),
                    'missing or oversized cycle event')
            event = decode(line)
            require(type(event) is dict and set(event) == EVENT_INTS | PAYLOAD_KEYS, 'event field inventory drift')
            require(all(type(event[key]) is int and 0 <= event[key] < 2**64 for key in EVENT_INTS),
                    'event fields must be unsigned integers')
            require(event['cycle'] == index, 'one complete ordered event per cycle required')
            for channel in ('w', 'r'):
                payload = event['pre_'+channel+'_payload_le_hex']
                require(isinstance(payload, str) and
                        (re.fullmatch('[0-9a-f]{128}', payload) is not None if event['pre_'+channel+'_valid'] else payload == ''),
                        'actual valid AXI payload encoding')
            require(all(event[key] in (0, 1) for key in EVENT_INTS if key.endswith(('_valid', '_ready')))
                    and event['pre_reset'] in (0, 1) and event['pre_running'] in (0, 1), 'invalid event boolean pin')
            observed['cycles'] += 1; observed['reset_cycles'] += event['pre_reset']
            observed['active_cycles'] += event['pre_running']
            for channel in ('ar', 'aw', 'w', 'r', 'b'):
                observed[channel+'_handshakes'] += event['pre_'+channel+'_valid'] * event['pre_'+channel+'_ready']
            require(event['end_reset_required'] == 0, 'DUT requested reset during prefix')
            if event['pre_completion_valid'] and event['pre_completion_ready'] and event['pre_pc'] == 0:
                word = event['pre_completion_word']
                require(word == (3 << 29) | (1 << 40) and
                        event['end_completions'] == event['end_successful'] == 1 and
                        event['end_ack_bytes'] == event['end_physical_bytes'] == 2048 and
                        event['end_write_acks'] == observed['w_handshakes'] == 32 and
                        observed['b_handshakes'] > 0 and activity['norm_completion_cycle'] is None,
                        'pc0 Norm completion lacks actual 2048-byte write publication')
                activity.update(norm_completion_cycle=index, norm_acked_bytes=event['end_ack_bytes'],
                                norm_physical_bytes=event['end_physical_bytes'],
                                norm_write_ack_beats=event['end_write_acks'])
            pcs.update((event['pre_pc'], event['end_pc']))
            issues, useful, executed = (event[key] for key in ('end_pipeline_issues', 'end_useful_macs', 'end_executed_macs'))
            require(issues >= previous_issues and useful >= previous_useful and executed >= previous_executed,
                    'execution counters regressed')
            delta = issues-previous_issues
            # At pc=1 Q Dense is using MatrixPipeline.wideSteps. MAC receipt
            # counters can remain zero until owner completion; never require >0.
            if delta and event['pre_pc'] == event['end_pc'] == 1:
                require(event['end_run'] == 0 and event['end_running'] == 1, 'unhealthy Matrix activity')
                activity['matrix_pipeline_issue_delta'] += delta
                activity['matrix_issue_cycles'] += 1
                if activity['first_matrix_issue_cycle'] is None:
                    require(activity['norm_completion_cycle'] is not None and
                            activity['norm_completion_cycle'] < index and
                            event['end_completions'] == event['end_successful'] == 1 and
                            event['end_ack_bytes'] == event['end_physical_bytes'] == 2048 and
                            event['end_write_acks'] == 32,
                            'first Matrix issue requires prior successful Norm publication')
                    activity['first_matrix_issue_cycle'] = index
                    activity['norm_completion_before_matrix'] = True
            previous_issues, previous_useful, previous_executed = issues, useful, executed
        require(stream.read(1) == b'', 'excess prefix events')
    require(consumed == size and path.stat().st_size == size, 'event file changed during read')
    terminal = {key: value for key, value in event.items() if key not in PAYLOAD_KEYS}
    require(deterministic['terminal_event'] == terminal and all(deterministic[key] == observed[key] for key in COUNTERS),
            'actual events differ from deterministic report')
    require(observed['reset_cycles'] == 6 and observed['active_cycles'] == cycles-36 and
            observed['ar_handshakes'] > 0 and observed['r_handshakes'] > 0 and
            terminal['end_running'] == 1 and terminal['end_idma_read_beats'] > 0, 'prefix reset/AXI/activity scope')
    require(type(deterministic['memory_bytes']) is int and deterministic['memory_bytes'] > 0 and
            deterministic['memory_bytes'] % 4 == 0 and isinstance(deterministic['memory_fnv1a64'], str) and
            re.fullmatch('[0-9a-f]{16}', deterministic['memory_fnv1a64']), 'memory digest scope')
    activity.update(useful_macs_delta=previous_useful, executed_macs_delta=previous_executed, pcs_seen=sorted(pcs),
                    final_pc=terminal['end_pc'], final_pipeline_issues=previous_issues,
                    write_acknowledgements=terminal['end_write_acks'],
                    matrix_activity_proven=activity['matrix_pipeline_issue_delta'] > 0)
    return dict(report_sha256=sha(output/'prefix.json'), event_sha256=digest.hexdigest(), event_bytes=size,
                deterministic_sha256=object_sha(deterministic), terminal_event_sha256=object_sha(terminal),
                counters=observed, activity=activity, step_elapsed_ns=report['step_elapsed_ns'],
                memory_bytes=deterministic['memory_bytes'], memory_fnv1a64=deterministic['memory_fnv1a64'],
                memory_hash_is_noncryptographic=True)


def compare_window(rows, cycles):
    require(len(rows) == 4 and tuple(row['variant'] for row in rows) == ORDER, 'complete A/B/B/A order required')
    if any(row['status'] == 'PENDING_TIMEOUT' for row in rows):
        return dict(status='PENDING', reason='prefix timeout', prefix_equivalence=False, ratios_available=False)
    require(all(row['status'] == 'COMPLETE' for row in rows), 'invalid A/B/B/A execution status')
    first = rows[0]['prefix']
    if cycles == 4096:
        require(all(row['prefix']['activity']['pcs_seen'] == [0] and
                    row['prefix']['activity']['final_pipeline_issues'] == 0 for row in rows),
                '4096 smoke prefix is no longer the original pc0 Norm scope')
    for row in rows[1:]:
        for key in ('event_sha256', 'event_bytes', 'deterministic_sha256', 'terminal_event_sha256'):
            require(row['prefix'][key] == first[key], 'A/B/B/A deterministic prefix mismatch: '+key)
        require(row['log_sha256'] == rows[0]['log_sha256'], 'A/B/B/A visible driver log mismatch')
    base = [row['prefix']['step_elapsed_ns'] for row in rows if row['variant'] == 'baseline']
    candidate = [row['prefix']['step_elapsed_ns'] for row in rows if row['variant'] == 'threads2']
    matrix = all(row['prefix']['activity']['matrix_activity_proven'] for row in rows)
    status = 'COMPLETE_PREFIX_EQUIVALENCE_ONLY' if cycles == 4096 or matrix else 'PENDING'
    return dict(status=status, reason=None if status != 'PENDING' else 'no observed pc1 Matrix issue',
                prefix_equivalence=True, ratios_available=True,
                baseline_step_elapsed_ns=base, threads2_step_elapsed_ns=candidate,
                baseline_over_threads2_mean_step=sum(base)/sum(candidate),
                matrix_activity_proven=matrix,
                measured_scope='reset-to-'+str(cycles)+'-cycle prefix including capture overhead',
                isolated_eval_timing=False, isolated_matrix_timing=False,
                whole_layer_speedup_claimed=False, numerical_acceptance=False)


def candidate_recipe(raw, source, output):
    """Extract frozen Verilator/C++ portion verbatim; add only --threads 2."""
    require(hashlib.sha256(raw).hexdigest() == BUILDER_SHA256, 'frozen builder identity drift')
    text = raw.decode()
    start = 'python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"\n'
    end = 'python3 "$P/scripts/host_bf16_v_toolchain.py" after "$OUT"\n'
    require(text.count(start) == text.count(end) == 1, 'frozen build recipe anchors changed')
    body = text[text.index(start):text.index(end)]
    anchor = 'verilator --cc --exe --assert '
    require(body.count(anchor) == 1 and '--threads' not in body, 'unexpected original threading policy')
    body = body.replace(anchor, 'verilator --threads 2 --cc --exe --assert ', 1)
    require('MAKEFLAGS=-n' in body and 'hier_verilation' in body and 'build_host_hierarchy_bounded.py' in body and
            '-ffp-contract=off -fno-fast-math' in body, 'incomplete production C++ recipe')
    command_line = next(line for line in body.splitlines() if 'MAKEFLAGS=-n verilator ' in line)
    actual_arguments = command_line.split('MAKEFLAGS=-n verilator ', 1)[1].split(' >"$OUT/build.log"', 1)[0]
    record = ('python3 - "$OUT/verilator_argv.json" "$(command -v verilator)" '+actual_arguments+
              " <<'PY_THREADS_ARGV'\nimport json,sys\nfrom pathlib import Path\n"
              "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:])+'\\n')\nPY_THREADS_ARGV\n")
    body = body.replace(command_line+'\n', record+command_line+'\n', 1)
    makeflags = next(line for line in text.splitlines() if line.startswith('export MAKEFLAGS='))
    prefix = ('#!/usr/bin/env bash\nset -euo pipefail\nROOT='+shlex.quote(str(source))+
              '\nP="$ROOT/chisel/continuous_prefill"\nOUT='+shlex.quote(str(output))+
              '\nexport BUILD_JOBS=1\n'+makeflags+'\n')
    return prefix+body


def worker_children():
    """All live members of this isolated worker group, including reparented ones."""
    leader = os.getpid()
    require(os.getpgrp() == os.getsid(0) == leader, 'isolated supervised worker session required')
    result = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            raw = path.read_text(); fields = raw[raw.rfind(')')+2:].split()
            pid = int(path.parent.name)
            if pid != leader and fields[0] != 'Z' and int(fields[2]) == leader:
                require(int(fields[3]) == leader, 'foreign process entered worker group')
                result.append(pid)
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


def cleanup_worker_children(process, grace=2):
    """Keep descendants in the outer supervisor's group even on worker SIGKILL.

    Operations are serial. The worker itself is the only group member retained
    between them; no new session/group is ever created for build or simulator.
    """
    def terminate(sig):
        members = worker_children()
        for pid in members:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        return members
    for sig in (signal.SIGTERM, signal.SIGKILL):
        end = time.monotonic()+grace
        while terminate(sig) and time.monotonic() < end:
            process.poll()
            time.sleep(0.02)
    process.wait(timeout=grace)
    require(not worker_children(), 'owned operation descendants survived cleanup')


def run_logged(argv, log, *, cwd, timeout, affinity, env=None):
    """Bound and reap descendants on success, timeout, cancellation or failure."""
    require(timeout > 0 and len(set(affinity)) == 2, 'bounded process with explicit two-CPU affinity required')
    require(os.getpgrp() == os.getsid(0) == os.getpid(), 'isolated supervised worker session required')
    require(not Path(log).exists(), 'fresh process log required')
    process = None; started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    timed_out = False
    cancellation = (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)
    def child_setup():
        os.sched_setaffinity(0, affinity)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, cancellation)
    with Path(log).open('x') as stream:
        try:
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, cancellation)
            try:
                process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                           preexec_fn=child_setup)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True; code = None
        finally:
            if process is not None:
                previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, cancellation)
                try:
                    cleanup_worker_children(process)
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    elapsed = time.monotonic()-started
    return dict(returncode=code, timed_out=timed_out, elapsed_seconds=elapsed,
                argv=argv, affinity=list(affinity), log_sha256=sha(log),
                process_group_cleaned=True), before, after


def compiler_evidence(build):
    groups = {}; driver_seen = False
    for path in sorted((build/'bounded_build').glob('*.log')):
        for line in path.read_text(errors='replace').splitlines():
            if not re.search(r'(?:^|\s)(?:\S*/)?(?:g\+\+|c\+\+)(?:\s|$)', line) or ' -c ' not in line:
                continue
            argv = shlex.split(line)
            source = next((value for value in reversed(argv) if value.endswith('.cpp')), None)
            if not source:
                continue
            flags = [value for value in argv if re.fullmatch(r'-O(?:[0123sgz]|fast)', value)]
            require(flags and flags[-1] in ('-O0', '-O2') and '-fno-fast-math' in argv and
                    '-ffp-contract=off' in argv, 'actual strict FP/O2/O0 compiler flags changed')
            if source.endswith('host_bf16_attention_block.cpp'):
                driver_seen = True
            key = (flags[-1], '__Slow.cpp' in source)
            groups[key] = groups.get(key, 0)+1
    require(driver_seen, 'original block driver compile absent')
    result = read_json(build/'bounded_build/result.json')
    require(result['status'] == 'PASS' and result['jobs'] == 1 and result['generated_inputs_unchanged'] is True,
            'serial bounded build did not complete')
    return dict(commands=[dict(effective_optimization=key[0], generated_slow=key[1], count=value)
                          for key, value in sorted(groups.items())], bounded_build=result)


def build_candidate(source, baseline, output, *, timeout, affinity, launch=run_logged):
    require(0 < timeout <= BUILD_SECONDS and not output.exists(), 'fresh bounded candidate build required')
    output.mkdir(); (output/'generated').mkdir()
    for name in ('HostBlockTop.sv', 'SCOPE.json'):
        shutil.copyfile(regular(baseline/'generated'/name), output/'generated'/name)
    require(sha(output/'generated/HostBlockTop.sv') == RTL_SHA256, 'same immutable RTL required')
    builder = output/'build_threads2.sh'
    builder.write_text(candidate_recipe(regular(source/BUILD_SCRIPT).read_bytes(), source, output))
    result, _, _ = launch(['bash', str(builder)], output/'candidate_build.log', cwd=source,
                          timeout=timeout, affinity=affinity, env=os.environ.copy())
    require(not result['timed_out'] and result['returncode'] == 0, 'candidate Verilator/C++ build failed or timed out')
    binary = regular(output/'obj/VHostBlockTop')
    with binary.open('rb') as stream:
        require(stream.read(4) == b'\x7fELF' and os.access(binary, os.X_OK), 'new candidate executable ELF required')
    # Generated model threads() is the actual runtime policy, independent of argv.
    generated = regular(output/'obj/VHostBlockTop.cpp').read_text()
    require(re.search(r'unsigned\s+VHostBlockTop::threads\(\)\s+const\s*\{\s*return\s+2;\s*\}', generated),
            'actual generated top is not threads=2')
    require(not (output/'build_ready.json').exists(), 'candidate must never impersonate production build_ready')
    receipt = dict(status='BUILT_THREADS2_PREFIX_DIAGNOSTIC_ONLY', threads=2, numerical_acceptance=False,
                   source_commit=PIN, binary_sha256=sha(binary), rtl_sha256=sha(output/'generated/HostBlockTop.sv'),
                   driver_sha256=sha(source/'chisel/continuous_prefill/tests/host_bf16_attention_block.cpp'),
                   prefix_header_sha256=sha(source/PREFIX_HEADER), builder_sha256=sha(builder),
                   original_builder_sha256=sha(source/BUILD_SCRIPT), process=result,
                   verilator_argv=read_json(output/'verilator_argv.json'),
                   compile=compiler_evidence(output), generated_top_sha256=sha(output/'obj/VHostBlockTop.cpp'),
                   hierarchy_configuration_sha256=sha(source/'chisel/continuous_prefill/tests/native_weight_hierarchy.vlt'),
                   rtl_changed=False, baseline_rebuilt=False, scala_executed=False,
                   dpi_thread_safety_forced=False)
    require(receipt['rtl_sha256'] == RTL_SHA256 and receipt['prefix_header_sha256'] == HEADER_SHA256,
            'candidate source/RTL changed during build')
    (output/'candidate_identity.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


def candidate_identity(output):
    require(not (output/'build_ready.json').exists(), 'candidate production receipt forbidden')
    return {name: sha(regular(output/name)) for name in CANDIDATE_FILES}


def selected_tools(baseline):
    """Bind the tools selected by PATH/root, not merely files at receipt paths."""
    toolchain = importlib.import_module('host_bf16_v_toolchain')
    identity = importlib.import_module('real2_ci').verilator_backend_identity
    tools = toolchain.tool_identity()
    require(tools == read_json(baseline/'toolchain.json')['tools'], 'selected compiler/toolchain differs from baseline')
    entry, backend = identity(shutil.which('verilator'), Path(os.environ['VERILATOR_ROOT']))
    actual = dict(entrypoint=entry, actual_elf=backend)
    require(actual == read_json(baseline/'actual_verilator_after.json'), 'selected actual Verilator ELF differs')
    return dict(tools=tools, actual_verilator=actual)


def imports(source):
    sys.path[:0] = [str(source/'chisel/continuous_prefill/scripts'), str(source/'src')]
    frozen = importlib.import_module('run_host_bf16_attention_block_fresh_gate')
    require(frozen.ROOT.resolve() == source, 'live authorities imported from wrong checkout')
    return frozen, importlib.import_module('host_bf16_attention_block_build_artifact')


def checked_paths(args):
    source = args.source_root
    require(source.is_absolute() and not source.is_symlink(), 'absolute frozen source root required')
    source = source.resolve()
    require(args.expected_commit == PIN and git(source, 'rev-parse', 'HEAD') == PIN and
            git(source, 'rev-parse', '--show-toplevel') == str(source), 'exact frozen production checkout required')
    require(not git(source, 'status', '--porcelain', '--untracked-files=normal'), 'frozen source checkout must be clean')
    require(DIAGNOSTIC_ROOT != source and git(DIAGNOSTIC_ROOT, 'rev-parse', '--show-toplevel') == str(DIAGNOSTIC_ROOT),
            'separate diagnostic checkout required')
    diagnostic_commit = git(DIAGNOSTIC_ROOT, 'rev-parse', 'HEAD')
    require(not git(DIAGNOSTIC_ROOT, 'status', '--porcelain', '--untracked-files=normal'), 'diagnostic checkout must be clean')
    require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == diagnostic_commit,
            'diagnostic checkout differs from triggering GITHUB_SHA')
    require(re.fullmatch('[0-9a-f]{64}', args.expected_sha256) and
            re.fullmatch('[1-9][0-9]*', args.baseline_run_id), 'trusted successful archive SHA/run identity required')
    require(sha(regular(args.archive)) == args.expected_sha256, 'trusted baseline archive hash mismatch')
    require(sha(source/PREFIX_HEADER) == HEADER_SHA256 and sha(source/BUILD_SCRIPT) == BUILDER_SHA256,
            'frozen diagnostic recorder/build recipe drift')
    require(args.output.is_absolute() and not args.output.is_symlink(), 'absolute new output required')
    output = args.output.resolve()
    require(output.is_relative_to(source/'work') and output != source/'work' and not output.exists() and
            not output.is_relative_to(DIAGNOSTIC_ROOT), 'fresh output under frozen source/work required')
    return source, output, diagnostic_commit


def write_compact(out, summary, hashes):
    compact = out/'compact'; compact.mkdir(exist_ok=True)
    for name, value in (('summary.json', summary), ('source_input_hashes.json', hashes)):
        temporary = compact/(name+'.tmp')
        require(not temporary.is_symlink() and not (compact/name).is_symlink(), 'compact evidence symlink')
        temporary.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n'); temporary.replace(compact/name)


def upload_allowlists():
    compact = list(COMPACT_FILES)
    candidate = ['threads2/'+name for name in CANDIDATE_FILES]
    return dict(compact_artifact_upload_allowlist=compact,
                candidate_artifact_upload_allowlist=candidate,
                artifact_upload_allowlist=compact+candidate)


def source_map(value):
    require(type(value) is dict and value, 'nonempty complete source map required')
    require(all(type(name) is str and not PurePosixPath(name).is_absolute() and
                '..' not in PurePosixPath(name).parts and type(digest) is str and
                re.fullmatch('[0-9a-f]{64}', digest) for name, digest in value.items()),
            'invalid source map path/digest')
    return dict(value)


def source_union(*maps):
    result = {}
    for mapping in maps:
        for name, digest in mapping.items():
            require(name not in result or result[name] == digest, 'source union hash conflict: '+name)
            result[name] = digest
    return result


def source_stage_snapshots(source, build_sources):
    """Read frozen factories' entire source inventories before running any factory."""
    names = dict(capture=('heteronpu.qk_norm256_materialization', 'src/heteronpu/qk_norm256_materialization.py'),
        projection=('host_bf16_qkv_reference', 'chisel/continuous_prefill/scripts/host_bf16_qkv_reference.py'),
        attention=('host_bf16_qk_rope_reference', 'chisel/continuous_prefill/scripts/host_bf16_qk_rope_reference.py'),
        block=('host_bf16_attention_block_reference', 'chisel/continuous_prefill/scripts/host_bf16_attention_block_reference.py'),
        fixture=('host_bf16_attention_block_fixture', 'chisel/continuous_prefill/scripts/host_bf16_attention_block_fixture.py'))
    modules = {stage: importlib.import_module(name) for stage, (name, _) in names.items()}
    require(all(Path(modules[stage].__file__).resolve() == source/path for stage, (_, path) in names.items()),
            'reference source inventory imported from wrong frozen checkout')
    capture = modules['capture']
    snapshots = dict(capture=capture._source_hashes(source, capture._contract(source)),
        projection=modules['projection']._source_identity(), attention=modules['attention']._source_identity(),
        block=modules['block'].source_identity(), fixture=modules['fixture'].source_identity())
    snapshots = {stage: source_map(value) for stage, value in snapshots.items()}
    union = source_union(*snapshots.values())
    require(set(union)-set(build_sources) == REFERENCE_ONLY_PATHS,
            'frozen reference-only source inventory changed')
    # These three files have no entry in the build manifest. Bind them directly
    # to the exact frozen Git objects, independently of a live factory receipt.
    for name in sorted(REFERENCE_ONLY_PATHS):
        raw = subprocess.check_output(['git', '-C', str(source), 'show', PIN+':'+name], timeout=30)
        require(hashlib.sha256(raw).hexdigest() == union[name] == sha(regular(source/name)),
                'reference-only source differs from frozen commit: '+name)
    return snapshots


class SourceInventory:
    """Separate immutable build closure from strictly staged reference unions."""
    def __init__(self, frozen, build_sources, stage_sources, hashes):
        require(type(stage_sources) is dict and set(stage_sources) == set(SOURCE_STAGES),
                'complete reference stage inventory required')
        self.frozen = frozen
        self.build = MappingProxyType(source_map(build_sources))
        self.stages = MappingProxyType({stage: MappingProxyType(source_map(stage_sources[stage]))
                                       for stage in SOURCE_STAGES})
        self.completed = []
        self.full = MappingProxyType(source_union(self.build, *self.stages.values()))
        require(hashes['source_sha256'] == {} and 'build_source_sha256' not in hashes and
                'reference_source_sha256' not in hashes and 'source_inventory' not in hashes,
                'fresh source inventory required')
        # Full future reference inventory is checked before capture/reference
        # execution, but only completed stages enter the current aggregate.
        frozen.verify_checkout(PIN, dict(self.full))
        frozen.merge_sources(hashes['source_sha256'], dict(self.build))
        hashes.update(build_source_sha256=dict(self.build), reference_source_sha256={},
                      source_inventory=self.receipt())
        self.verify(hashes)

    def references(self):
        return source_union(*(self.stages[stage] for stage in self.completed))

    def receipt(self):
        references = self.references()
        return dict(completed_stages=list(self.completed), build_files=len(self.build),
                    build_source_map_sha256=object_sha(dict(self.build)),
                    reference_files=len(references), reference_source_map_sha256=object_sha(references),
                    aggregate_files=len(source_union(self.build, references)),
                    stages={stage: dict(files=len(self.stages[stage]),
                                       source_map_sha256=object_sha(dict(self.stages[stage])))
                            for stage in SOURCE_STAGES})

    def verify(self, hashes, current_build=None):
        if current_build is not None:
            require(current_build == dict(self.build), 'immutable complete build source inventory drift')
        references = self.references()
        require(hashes['build_source_sha256'] == dict(self.build) and
                hashes['reference_source_sha256'] == references and
                hashes['source_sha256'] == source_union(self.build, references) and
                hashes['source_inventory'] == self.receipt(), 'staged source union inventory drift')
        self.frozen.verify_checkout(PIN, dict(self.full))

    def admit(self, stage, actual, hashes):
        self.verify(hashes)
        require(len(self.completed) < len(SOURCE_STAGES) and stage == SOURCE_STAGES[len(self.completed)],
                'reference source stage order changed')
        require(source_map(actual) == dict(self.stages[stage]), 'complete '+stage+' source inventory drift')
        self.frozen.merge_sources(hashes['source_sha256'], actual)
        self.completed.append(stage)
        hashes['reference_source_sha256'] = self.references()
        hashes['source_inventory'] = self.receipt()
        self.verify(hashes)

    def require_complete(self, hashes):
        self.verify(hashes)
        require(tuple(self.completed) == SOURCE_STAGES, 'incomplete reference source stage inventory')


def fresh_fixture(frozen, args, out, summary, hashes, inventory):
    """Exactly one original baseline/AVX2 capture; retain all live factories."""
    session = frozen.rebuild_session(out/'official_capture', args.payload_layer0, args.payload_layer3, args.payload_extra)
    summary.update(session.evidence())
    require(session.fresh and summary['fresh_official_executions'] == 2 and
            summary['reused_official_executions'] == 0, 'one fresh baseline/AVX2 execution required')
    hashes['official_capture_manifest_sha256'] = session.manifest_sha256
    inventory.admit('capture', session.verify()['source_sha256'], hashes)
    summary['native_full_block_failures'] = frozen._native_failure_evidence(session)
    projection = frozen.generate_projection_references(session, out/'projection_reference', variants=('baseline',), windows=frozen.WINDOWS)
    projected = projection.verify(session=session)
    require(projected['requested_windows'] == [list(window) for window in frozen.WINDOWS] and
            projected['head_jobs'] == 24 and projected['matrix_accumulator_steps'] == 10485760 and
            projected['native_operator_gate_pass'] is True, 'original projection gate/inventory')
    inventory.admit('projection', projected['source_sha256'], hashes)
    attention = frozen.generate_attention_references(session, projection, out/'attention_reference', variants=('baseline',))
    attended = attention.verify(session=session, projection_reference_session=projection)
    require(attended['original_operator_gate_pass'] is True, 'original Norm/RoPE operator gate')
    inventory.admit('attention', attended['source_sha256'], hashes)
    block = frozen.generate_block_reference(session, projection, attention, out/'block_reference')
    authorities = dict(block_session=block, session=session, projection_session=projection, attention_session=attention)
    receipt = block.verify(session=session, projection_session=projection, attention_session=attention)
    inventory.admit('block', receipt['source_sha256_after'], hashes)
    admitted = frozen.pack_fixture(out/'pair_fixture', **authorities)
    require(admitted['live_authorities_verified'] is True, 'live fixture admission required')
    inventory.admit('fixture', admitted['source_sha256'], hashes)
    inventory.require_complete(hashes)
    hashes['input_sha256'] = admitted['input_sha256']
    hashes.update(projection_reference_receipt_sha256=projection.receipt_sha256,
                  attention_reference_receipt_sha256=attention.receipt_sha256,
                  block_reference_receipt_sha256=block.receipt_sha256)
    return authorities, admitted


def run_worker(args):
    source, out, diagnostic_commit = checked_paths(args)
    frozen, artifact = imports(source)
    out.mkdir(parents=True)
    trigger = os.environ.get('GITHUB_SHA')
    os.environ['GITHUB_SHA'] = PIN  # Only after both independent clean checkouts were verified.
    summary = dict(status='RUNNING_THREADS2_PREFIX_DIAGNOSTIC', stage='resource_admission',
                   production_source_commit=PIN, diagnostic_source_commit=diagnostic_commit,
                   github_trigger_sha=trigger, trusted_baseline_run_id=args.baseline_run_id,
                   numerical_acceptance=False, native_full_block_acceptance=False, full_layer_executed=False,
                   whole_layer_speedup_claimed=False, overall_pass=False, timing_signoff=False, qor_signoff=False,
                   reference_injection=False, state_injection=False, same_fresh_fixture=True,
                   baseline_rebuilt=False, scala_executed=False, candidate_builds=0,
                   runner_budget_seconds=BUDGET_SECONDS, failure_reserve_seconds=RESERVE_SECONDS,
                   windows={}, raw_prefix_events_upload_allowed=False,
                   step_timing_scope=TIMING_SCOPE,
                   **upload_allowlists())
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={},
                  diagnostic_source_sha256={str(Path(__file__).relative_to(DIAGNOSTIC_ROOT)): sha(__file__)},
                  baseline_archive_sha256=args.expected_sha256)
    started = time.monotonic(); deadline = started+BUDGET_SECONDS-RESERVE_SECONDS
    baseline, candidate = out/'baseline', out/'threads2'
    authorities = admitted = initial_baseline = initial_candidate = admission = inventory = None
    code = 1

    def remaining(cap):
        seconds = deadline-time.monotonic()
        require(seconds > 0, 'total diagnostic budget exhausted')
        return min(cap, seconds)

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=time.monotonic()-started)
        write_compact(out, summary, hashes)

    def postcheck():
        require(git(DIAGNOSTIC_ROOT, 'rev-parse', 'HEAD') == diagnostic_commit and
                not git(DIAGNOSTIC_ROOT, 'status', '--porcelain', '--untracked-files=normal') and
                all(sha(DIAGNOSTIC_ROOT/name) == digest for name, digest in hashes['diagnostic_source_sha256'].items()),
                'diagnostic source identity drift')
        require(sha(args.archive) == args.expected_sha256, 'baseline archive changed')
        frozen.verify_checkout(PIN, hashes['source_sha256'])
        if inventory is not None:
            inventory.verify(hashes, read_json(baseline/'sources.sha256.json'))
        if initial_baseline is not None:
            frozen.verify_all_build_sources(baseline, 'threads_final_source_verify.log')
            require(frozen.build_identity(baseline, dict(inventory.build)) == initial_baseline,
                    'baseline/source/tool identity drift')
        if initial_candidate is not None:
            require(candidate_identity(candidate) == initial_candidate, 'candidate ELF/RTL/argv identity drift')
        if authorities is not None:
            require(frozen.admit_fixture(out/'pair_fixture', **authorities) == admitted, 'fresh live fixture drift')
            summary.update(authorities['session'].evidence())
            summary['native_full_block_failures'] = frozen._native_failure_evidence(authorities['session'])
        for name, rows in summary['windows'].items():
            for row in rows['runs']:
                if row['status'] == 'COMPLETE':
                    require(read_prefix(out/row['output'], rows['cycles']) == row['prefix'] and
                            sha(out/row['log']) == row['log_sha256'], 'prefix evidence drift')

    try:
        with frozen.total_budget(BUDGET_SECONDS-RESERVE_SECONDS):
            try:
                admission = resource_snapshot()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                summary.update(status='NOT_RUN', reason='resource admission unavailable: '+str(error))
                code = 0
                return code
            summary['resource_admission'] = admission
            if admission['effective_cpu_count'] < 2:
                summary.update(status='NOT_RUN', reason='effective CPU count is below two')
                code = 0
                return code
            affinity = admission['selected_affinity']
            checkpoint('restore_trusted_baseline')
            require(os.environ.get('OFFLINE_TOOLS'), 'original compiler JAR receipt runtime required')
            summary['compiler_jars'] = artifact.prepare_compiler_jars(args.archive, Path(os.environ['OFFLINE_TOOLS']), args.expected_sha256, PIN)
            summary['build_transfer'] = artifact.restore(args.archive, baseline, args.expected_sha256, PIN)
            build_sources = read_json(baseline/'sources.sha256.json')
            inventory = SourceInventory(frozen, build_sources, source_stage_snapshots(source, build_sources), hashes)
            initial_baseline = frozen.build_identity(baseline, dict(inventory.build))
            require(initial_baseline['generated/HostBlockTop.sv'] == RTL_SHA256, 'trusted baseline RTL differs')
            hashes['baseline_identity'] = initial_baseline
            summary['selected_tools_before'] = selected_tools(baseline)
            checkpoint('one_candidate_verilator_cpp_build')
            current = resource_snapshot(); same_admission(admission, current)
            summary['candidate_builds'] = 1
            summary['candidate'] = build_candidate(source, baseline, candidate, timeout=remaining(BUILD_SECONDS), affinity=affinity)
            initial_candidate = candidate_identity(candidate); hashes['candidate_identity'] = initial_candidate
            require(summary['candidate']['binary_sha256'] != initial_baseline['obj/VHostBlockTop'], 'candidate ELF equals baseline')
            require(read_json(candidate/'idma_identity.json') == read_json(baseline/'idma_identity.json'), 'candidate iDMA identity differs')
            postcheck()
            summary['selected_tools_after'] = selected_tools(baseline)
            require(summary['selected_tools_after'] == summary['selected_tools_before'], 'selected tools drift')
            checkpoint('one_fresh_capture_and_live_fixture')
            with (out/'pipeline.log').open('x') as pipeline, contextlib.redirect_stdout(pipeline):
                authorities, admitted = fresh_fixture(frozen, args, out, summary, hashes, inventory)
            inventory.require_complete(hashes)
            for name, cycles, timeout in WINDOWS:
                window = dict(cycles=cycles, timeout_seconds=timeout, runs=[], comparison=dict(status='PENDING'))
                summary['windows'][name] = window
                for index, variant in enumerate(ORDER):
                    postcheck()
                    before = resource_snapshot(); same_admission(admission, before)
                    output_name = name+'_'+str(index)+'_'+variant
                    log_name = output_name+'.log'
                    build = baseline if variant == 'baseline' else candidate
                    checkpoint(output_name)
                    process, usage_before, usage_after = run_logged(
                        [str(build/'obj/VHostBlockTop'), str(out/'pair_fixture'), str(out/output_name),
                         'pass', '--diagnostic-prefix='+str(cycles)], out/log_name,
                        cwd=source, timeout=remaining(timeout), affinity=affinity)
                    after = resource_snapshot(); same_admission(admission, after)
                    row = dict(variant=variant, output=output_name, log=log_name,
                               status='PENDING_TIMEOUT' if process['timed_out'] else 'COMPLETE',
                               process=process, log_sha256=sha(out/log_name),
                               runtime_cpu=cpu_delta(before, after, process['elapsed_seconds'], usage_before, usage_after),
                               cgroup_before=before['cgroups'], cgroup_after=after['cgroups'])
                    window['runs'].append(row)
                    if not process['timed_out']:
                        require(process['returncode'] == 0, 'actual unchanged driver prefix failed')
                        require('HOST_ATTN_BLOCK_PAIR ' not in (out/log_name).read_text(), 'prefix claimed completed numerical pair')
                        row['prefix'] = read_prefix(out/output_name, cycles)
                        hashes['output_sha256'][output_name] = {key: value for key, value in row['prefix'].items() if key.endswith('_sha256')}
                    checkpoint('completed_'+output_name)
                window['comparison'] = compare_window(window['runs'], cycles)
                checkpoint('completed_'+name)
            postcheck()
            require(selected_tools(baseline) == summary['selected_tools_before'], 'final selected tools drift')
            summary['resource_after'] = resource_snapshot(); same_admission(admission, summary['resource_after'])
            summary.update(status=('COMPLETE_PREFIX_DIAGNOSTIC_ONLY' if all(
                item['comparison']['status'] == 'COMPLETE_PREFIX_EQUIVALENCE_ONLY' for item in summary['windows'].values())
                else 'PENDING'), live_authorities_verified=True, source_tool_identity_verified=True)
            code = 0
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status='FAILED_DIAGNOSTIC', error=dict(type=type(error).__name__, message=str(error)))
        try:
            postcheck()
            summary['post_failure_identity_verified'] = True
        except Exception as drift:
            summary['post_failure_identity_error'] = str(drift)
    finally:
        checkpoint('complete' if code == 0 else summary['stage'])
    return code


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--baseline-run-id', required=True)
    for name in ('layer0', 'layer3', 'extra'):
        parser.add_argument('--payload-'+name, type=Path, required=True)
    return parser.parse_args(argv)


def worker_entry():
    signal.pthread_sigmask(signal.SIG_UNBLOCK, (signal.SIGINT, signal.SIGTERM))
    def interrupted(signum, frame):
        raise KeyboardInterrupt('supervisor cancellation '+str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(run_worker(arguments()))


def finalize_supervision(out, outcome):
    out.mkdir(parents=True, exist_ok=True)
    try:
        summary, hashes = read_json(out/'compact/summary.json', 8*1024*1024), read_json(out/'compact/source_input_hashes.json', 8*1024*1024)
    except (ValueError, OSError):
        summary, hashes = {}, {}
        outcome = dict(outcome, returncode=1, missing_or_invalid_worker_evidence=True)
    summary.update(supervisor=outcome, numerical_acceptance=False, native_full_block_acceptance=False,
                   overall_pass=False, whole_layer_speedup_claimed=False,
                   **upload_allowlists())
    if outcome['forced_shutdown'] or outcome['returncode']:
        summary['status'] = 'FAILED_DIAGNOSTIC'
    write_compact(out, summary, hashes)
    # CI artifact storage can be unavailable. Preserve the complete compact
    # receipts in Actions logs, never raw fixture/trace/tensor files.
    for name in COMPACT_FILES:
        print('BEGIN_ATTENTION_THREADS_COMPACT '+name, flush=True)
        print((out/name).read_text(), end='', flush=True)
        print('END_ATTENTION_THREADS_COMPACT '+name, flush=True)
    return outcome['returncode']


def main():
    args = arguments()
    source, out, _ = checked_paths(args)
    frozen, _ = imports(source)
    entry = 'import sys;sys.path.insert(0,sys.argv.pop(1));from run_diagnostic import worker_entry;worker_entry()'
    argv = [sys.executable, '-c', entry, str(HERE)]
    for name, value in vars(args).items():
        argv.extend(('--'+name.replace('_', '-'), str(value.resolve() if isinstance(value, Path) else value)))
    outcome = frozen.supervise_process(argv, timeout_seconds=BUDGET_SECONDS-10)
    raise SystemExit(finalize_supervision(out, outcome))


if __name__ == '__main__':
    main()
