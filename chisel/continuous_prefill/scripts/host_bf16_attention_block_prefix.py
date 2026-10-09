"""Two bounded diagnostics on the real full-block ELF, outside numerical cases."""
from pathlib import Path
import json
import hashlib
import re
import subprocess
import time

import host_bf16_attention_block_live_gate as live

CYCLES = 4096
STATUS = 'PASS_PRODUCTION_BLOCK_PREFIX_DETERMINISM_ONLY'
COUNTERS = ('cycles', 'reset_cycles', 'active_cycles', 'ar_handshakes',
            'aw_handshakes', 'w_handshakes', 'r_handshakes', 'b_handshakes')


def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_prefix(output):
    output = Path(output)
    profile_path = live.fixture.safe_file(output, 'prefix.json')
    live.require(profile_path.stat().st_size <= 1024 * 1024, 'prefix report exceeds bound')
    value = json.loads(profile_path.read_text())
    live.require(value.get('schema') == 'HOST_ATTENTION_BLOCK_PREFIX_V1' and
                 value.get('status') == 'BOUNDED_DIAGNOSTIC_PREFIX' and
                 value.get('numerical_acceptance') is False and value.get('prefix_reached') is True,
                 'prefix result cannot award numerical acceptance')
    live.require(value.get('cycles') == value.get('cycle_limit') == CYCLES and
                 value.get('constructor_cycles') == 36 and
                 value.get('event_file') == 'prefix_events.jsonl', 'wrong bounded prefix scope')
    events = live.fixture.safe_file(output, value['event_file'])
    live.require(0 < events.stat().st_size <= 64 * 1024 * 1024 and
                 value.get('event_bytes') == events.stat().st_size, 'prefix event byte count')
    with events.open('rb') as stream:
        header = json.loads(next(stream))
        live.require(header == dict(schema='HOST_ATTENTION_BLOCK_PREFIX_EVENTS_V1',
            numerical_acceptance=False, payload_encoding='le_u32x16_hex', timing_excluded=True),
            'wrong prefix event schema')
        count = 0
        for count, line in enumerate(stream, 1):
            event = json.loads(line)
            live.require(event.get('cycle') == count and count <= CYCLES,
                         'one complete ordered event per prefix cycle required')
        live.require(count == CYCLES, 'incomplete prefix events')
    deterministic = value.get('deterministic')
    live.require(type(deterministic) is dict and deterministic.get('cycles') == CYCLES and
                 type(deterministic.get('terminal_event')) is dict,
                 'missing actual deterministic prefix state')
    live.require(all(type(deterministic.get(key)) is int and 0 <= deterministic[key] <= CYCLES
                     for key in COUNTERS), 'invalid prefix counters')
    live.require(deterministic['reset_cycles'] == 6 and
                 deterministic['active_cycles'] == CYCLES - 36, 'wrong reset/active cycle scope')
    live.require(deterministic['ar_handshakes'] > 0 and deterministic['r_handshakes'] > 0,
                 'prefix did not exercise actual AXI reads')
    live.require(type(deterministic.get('memory_bytes')) is int and deterministic['memory_bytes'] > 0 and
                 deterministic['memory_bytes'] % 4 == 0 and
                 type(deterministic.get('memory_fnv1a64')) is str and
                 re.fullmatch('[0-9a-f]{16}', deterministic['memory_fnv1a64']) is not None and
                 value.get('memory_hash_is_noncryptographic') is True,
                 'missing actual memory diagnostic digest')
    # The terminal event is compared against the last actual trace record, but
    # never returned to the uploadable report. Only hashes and counter scalars
    # cross that boundary; even unexpected future fields cannot upload payloads.
    terminal = {key: value for key, value in event.items()
                if key not in ('pre_w_payload_le_hex', 'pre_r_payload_le_hex')}
    live.require(terminal == deterministic['terminal_event'], 'prefix terminal event mismatch')
    live.require(terminal.get('end_reset_required') == 0 and terminal.get('end_running') == 1 and
                 terminal.get('end_idma_read_beats', 0) > 0,
                 'prefix did not remain in healthy active execution')
    live.require(type(value.get('step_elapsed_ns')) is int and value['step_elapsed_ns'] > 0,
                 'missing measured completed-step time')
    return dict(report_sha256=live.sha(profile_path), deterministic_sha256=object_sha(deterministic),
                counters={key: deterministic[key] for key in COUNTERS},
                terminal_event_sha256=object_sha(terminal), step_elapsed_ns=value['step_elapsed_ns'],
                memory_bytes=deterministic['memory_bytes'],
                memory_fnv1a64=deterministic['memory_fnv1a64'], memory_hash_is_noncryptographic=True,
                event_sha256=live.sha(events), event_bytes=events.stat().st_size)


def run_pair(build, path, *, block_session, session, projection_session, attention_session,
             timeout_seconds=240):
    live.require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 240, 'bounded prefix timeout required')
    build, path = Path(build), Path(path)
    authorities = dict(block_session=block_session, session=session,
                       projection_session=projection_session, attention_session=attention_session)
    admitted = live.admit_fixture(path, **authorities)
    identity = live.build_identity(build, admitted['source_sha256'])
    live.verify_all_build_sources(build, 'prefix_initial_source_verify.log')
    prefixes = []
    for index in range(2):
        output, log = build/f'diagnostic_prefix{index}', build/f'diagnostic_prefix{index}.log'
        live.require(not output.exists() and not log.exists(), 'fresh prefix evidence required')
        live.require(live.admit_fixture(path, **authorities) == admitted and
                     live.build_identity(build, admitted['source_sha256']) == identity,
                     'prefix input or actual DUT identity changed')
        started = time.monotonic()
        try:
            with log.open('w') as stream:
                result = subprocess.run([str(build/'obj/VHostBlockTop'), str(path), str(output),
                                         'pass', f'--diagnostic-prefix={CYCLES}'],
                    cwd=live.ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            (build/f'diagnostic_prefix{index}.exit').write_text('TIMEOUT\n')
            raise ValueError('actual full-block prefix timed out') from error
        (build/f'diagnostic_prefix{index}.exit').write_text(str(result.returncode) + '\n')
        live.require(result.returncode == 0, 'actual full-block prefix execution failed')
        prefix = read_prefix(output)
        live.require('HOST_ATTN_BLOCK_PAIR ' not in log.read_text(),
                     'prefix cannot claim completed numerical pair')
        prefix.update(elapsed_seconds=time.monotonic()-started, log_sha256=live.sha(log))
        prefixes.append(prefix)
    first, second = prefixes
    live.require(first['event_sha256'] == second['event_sha256'] and
                 first['event_bytes'] == second['event_bytes'] and
                 first['deterministic_sha256'] == second['deterministic_sha256'] and
                 first['log_sha256'] == second['log_sha256'], 'actual full-block prefixes are not deterministic')
    live.require(live.admit_fixture(path, **authorities) == admitted and
                 live.build_identity(build, admitted['source_sha256']) == identity,
                 'prefix input or actual DUT identity changed after execution')
    live.verify_all_build_sources(build, 'prefix_final_source_verify.log')
    result = dict(status=STATUS, numerical_acceptance=False, full_block_m1_executed=False,
                  actual_dut_identity_verified=True, live_authorities_verified=True,
                  binary_sha256=identity['obj/VHostBlockTop'],
                  rtl_sha256=identity['generated/HostBlockTop.sv'],
                  build_ready_sha256=identity['build_ready.json'],
                  input_sha256=admitted['input_sha256'], cycles_per_prefix=CYCLES,
                  timeout_seconds_per_prefix=timeout_seconds, prefixes=prefixes,
                  step_timing_scope='PhysicalAxi.step including capture overhead, excluding event serialization; not isolated eval timing',
                  scope='raw-hidden full-block prefix only; GQA activity is not required or inferred',
                  raw_prefix_events_upload_allowed=False)
    (build/'diagnostic_prefix_pair.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
