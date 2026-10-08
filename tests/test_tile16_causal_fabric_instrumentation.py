"""Small source contracts for the causal tile16 fabric and opt-in observations.

These tests need no weights, vectors, simulator, or generated arithmetic RTL.
The full real-source Verilator lint/run belongs to the hardware runner.
"""
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
TB = ROOT / 'tb/tb_qwen35_matrix_norm_rope_tile16.sv'
SOURCE = TB.read_text()


def _body(name, kind='task'):
    pattern = rf'  {kind} automatic[^\n]*\b{re.escape(name)}\b[^\n]*\n(.*?)  end{kind}'
    match = re.search(pattern, SOURCE, re.S)
    assert match, name
    return match[1]


def _compact(text):
    return re.sub(r'\s+', '', text)


def test_default_is_legacy_random_and_observation_requires_explicit_metrics():
    assert "parameter bit READ_LOOKAHEAD=1'b0" in SOURCE
    assert '.CANDIDATE_READ_LOOKAHEAD(READ_LOOKAHEAD)' in SOURCE
    assert 'fabric_mode="random"' in SOURCE
    assert 'fabric_profile=FAB_RANDOM,metrics_fd=0' in SOURCE
    assert 'if($value$plusargs("metrics=%s",metrics_path))begin' in SOURCE
    assert 'if(metrics_path==trace_path)$fatal' in SOURCE
    # No automatic metrics destination or unconditional new trace events.
    assert 'metrics_path={trace_path' not in SOURCE
    assert 'if(metrics_fd)$fdisplay(trace_fd,"{\\"event\\":\\"matrix_input' in SOURCE
    assert 'if(metrics_fd&&active&&accepted_cycle!=0&&!metrics_emitted)sample_metrics();' in SOURCE
    assert 'if(metrics_fd)emit_metrics(1);' in SOURCE
    assert 'if(metrics_fd)emit_metrics(0);rst_n=0' in SOURCE


def test_random_profile_retains_each_legacy_delay_and_force_block():
    compact = _compact(SOURCE)
    for old in (
        'force_read_block==0&&(!random_stalls||lfsr[2]||lfsr[9])',
        'force_write_block==0&&(!random_stalls||lfsr[3]||lfsr[10])',
        'force_dma_block==0&&(!random_stalls||lfsr[1]||lfsr[8])',
        '(!random_stalls||lfsr[0]||lfsr[7])',
        "ddelay<=fabric_profile==FAB_RANDOM?(random_stalls?integer'(lfsr[13:11])+1:1)",
        "adelay<=fabric_profile==FAB_RANDOM?((ak==3&&regid==2)?512:(random_stalls?integer'(lfsr[18:15])+3:3))",
        "rdelay<=fabric_profile==FAB_RANDOM?(random_stalls?integer'(lfsr[22:20])+1:1)",
        "wdelay<=fabric_profile==FAB_RANDOM?11+integer'(lfsr[26:23])",
    ):
        assert old in compact
    assert 'fabric_profile==FAB_RANDOM||dma_transfer_done' in compact


def test_unstalled_has_no_artificial_delays_and_keeps_real_fabric_handshakes():
    for channel in ('READ', 'WRITE', 'DESC', 'DMA'):
        assert f'fabric_profile==FAB_UNSTALLED||replay_admit(CH_{channel})' in SOURCE
        assert f'fabric_profile==FAB_REPLAY?response_budget(CH_{channel}):0' in SOURCE
    assert 'fabric_profile==FAB_UNSTALLED||(fabric_profile==FAB_REPLAY?' in SOURCE
    for real_gate in (
        'assign rr=!host_mode&&request_gate&&frr[0];',
        'assign rsv=!host_mode&&response_gate&&frsv[0];',
        'assign rd=frd[511:0];',
        'assign wr=!host_mode&&!dma_write_valid&&write_gate&&fwr;',
        'assign asv=rst_n&&ap&&dma_transfer_done&&adelay==0;',
    ):
        assert real_gate in SOURCE


def test_replay_hash_has_no_wall_clock_or_lfsr_dependency():
    body = _body('replay_hash', 'function')
    for forbidden in ('lfsr', 'cycle', 'transaction', 'head', 'random'):
        assert forbidden not in body
    for constant in ('9e3779b9', '85ebca6b', '7feb352d', '846ca68b'):
        assert constant in body
    assert 'REPLAY_SALT' in body
    assert "REPLAY_SALT=32'h3c6ef372" in SOURCE
    assert 'request_ordinal[channel],channel,0' in _body('admission_budget', 'function')
    assert 'request_ordinal[channel],channel,1' in _body('response_budget', 'function')
    assert 'replay_hash(request_ordinal[CH_WRITE],CH_WRITE,2)' in SOURCE


def test_admission_is_request_relative_and_ordinals_reset_per_command():
    launch = _body('launch')
    assert 'request_ordinal[ch]=0;admit_remaining[ch]=0;admit_started[ch]=0;' in launch
    transport = SOURCE.split('begin : transport', 1)[1].split('norm_boundary_scoreboard', 1)[0]
    assert 'if(channel_fire[ch])begin' in transport
    assert 'request_ordinal[ch]<=request_ordinal[ch]+1;' in transport
    assert 'else if(fabric_profile==FAB_REPLAY&&channel_valid[ch])begin' in transport
    assert 'if(!admit_started[ch])begin' in transport
    assert 'admission_budget(ch)>0?admission_budget(ch)-1:0' in transport
    assert 'else if(admit_remaining[ch]>0)admit_remaining[ch]<=admit_remaining[ch]-1;' in transport
    assert 'admit_started[channel]?admit_remaining[channel]==0:admission_budget(channel)==0' in SOURCE


def _sv_formats(task):
    """Read literal output fragments without interpreting simulator state."""
    return [json.loads('"' + match + '"') for match in re.findall(
        r'\$f(?:write|display)\(metrics_fd,"((?:\\.|[^"\\])*)"', task)]


def _format_sample(fmt, string_value='sample'):
    def substitute(match):
        width, kind = match.groups()
        if kind == 's':
            return string_value
        return '0' * (int(width or 1) if kind == 'h' else 1)
    return re.sub(r'%0?(\d*)([dhs])', substitute, fmt)


def test_metrics_format_is_valid_json_with_exact_nested_channel_schema():
    fragments = _sv_formats(_body('emit_metrics'))
    assert len(fragments) == 7
    # Four prefix fragments, a loop comma, the loop channel object, final }}.
    rendered = ''.join(_format_sample(f) for f in fragments[:4])
    rendered += ','.join(_format_sample(fragments[5], name)
                         for name in ('descriptor', 'dma', 'read', 'write'))
    rendered += fragments[6]
    metrics = json.loads(rendered)
    assert metrics['event'] == 'command_metrics'
    assert metrics['schema_version'] == 1
    assert set(metrics['operand_wait_cycles']) == {'arq', 'arp', 'wrq', 'wrp'}
    assert set(metrics['matrix_input_ii']) == {'count', 'sum', 'min', 'max'}
    assert set(metrics['scheduler_stall_cycles']) == {
        'endpoint_inactive', 'context_busy', 'fifo_full', 'array_admission'}
    assert set(metrics['channels']) == {'descriptor', 'dma', 'read', 'write'}
    fields = {'requests', 'responses', 'request_stall_cycles', 'response_hold_cycles',
              'pending_cycles', 'latency_count', 'latency_sum', 'latency_max',
              'admission_budget_sum', 'response_budget_sum', 'schedule_hash'}
    for channel in metrics['channels'].values():
        assert set(channel) == fields
        assert re.fullmatch('[0-9a-f]{16}', channel['schedule_hash'])
    assert set(metrics['overlap_cycles']) == {
        'matrix_stall_read_pending', 'matrix_input_read_pending',
        'read_request_matrix_input', 'read_response_matrix_output',
        'read_pending_context_busy'}
    for field in ('fabric', 'read_lookahead', 'completed', 'status', 'transaction',
                  'name', 'kind', 'start_cycle', 'end_cycle', 'command_cycles',
                  'matrix_input_fires', 'matrix_input_stall_cycles',
                  'prefetch_occupancy_cycles', 'prefetch_accepts',
                  'context_busy_raw_cycles', 'fabric_read_response_hold_cycles',
                  'read_artificial_response_hold_cycles', 'same_cycle_write_acks'):
        assert field in metrics


def test_matrix_input_trace_is_exact_width_actual_operands_before_increment():
    block = SOURCE.split('      if(matrix_accept)begin', 1)[1].split('      if(matrix_output)', 1)[0]
    fmt = re.search(r'\$fdisplay\(trace_fd,"((?:\\.|[^"\\])*)"', block)[1]
    decoded = json.loads('"' + fmt + '"')
    event = json.loads(_format_sample(decoded))
    assert set(event) == {'event', 'transaction', 'cycle', 'head', 'batch_start',
                          'rows', 'tile', 'index', 'last', 'context', 'clear', 'a', 'b'}
    assert event['event'] == 'matrix_input'
    assert len(event['a']) == 64 and len(event['b']) == 128
    assert 'matrix_inputs/1024,matrix_inputs,`CHAIN.ml,`CHAIN.mctx,`CHAIN.mc,`CHAIN.ma,`CHAIN.mb' in block
    assert block.index('$fdisplay') < block.index('matrix_inputs=matrix_inputs+1')


def test_metrics_probe_real_scheduler_and_preserve_single_pending_read():
    sample = _body('sample_metrics')
    for probe in ('`SCHED.busy_o', '`SCHED.context_available', '`SCHED.fifo_not_full',
                  '`SCHED.array_in_ready_i', '`CHAIN.matrix.active_q',
                  '`CHAIN.payload.next_a_pending_q', '`CHAIN.payload.next_a_request'):
        assert probe in sample
    assert 'matrix.matrix.g_production.front_control.scheduler' in SOURCE
    assert 'strict_read_pending!=integer\'(rp)' in SOURCE
    assert 'if(strict_read_pending!=0)$fatal(1,"more than one pending read")' in SOURCE
    assert 'if(frsv[0]&&!rp)$fatal(1,"fabric read response without pending owner")' in SOURCE
    assert 'held_matrix&&(!`CHAIN.mpv||' in SOURCE
    assert '{`CHAIN.mctx,`CHAIN.mc,`CHAIN.ml,`CHAIN.ma,`CHAIN.mb}!==old_matrix_operands' in SOURCE
    assert "schedule_word={32'(request_ordinal[ch]),16'(admission),16'(response)}" in sample


def test_metrics_sample_once_per_command_cycle_and_measure_within_tile_ii():
    sample = _body('sample_metrics')
    assert 'metric_cycles=metric_cycles+1;' in sample
    assert 'metric_last_input_cycle=`CHAIN.ml?0:cycle;' in sample
    assert 'metric_last_input_cycle=0;' in _body('reset_metrics')
    assert "metric_cycles!=64'(cycle-accepted_cycle+1)" in _body('emit_metrics')
    assert 'metrics_emitted=1;' in _body('emit_metrics')
    assert 'if(metrics_emitted)$fatal' in _body('emit_metrics')


@pytest.mark.parametrize('budget', range(4))
@pytest.mark.parametrize('physical_ready_cycle', (0, 2, 7))
def test_request_relative_countdown_contract(budget, physical_ready_cycle):
    """Executable contract for the implemented first-valid/held-ready algorithm."""
    def accepted(start):
        started, remaining = False, 0
        for elapsed in range(20):
            gate = remaining == 0 if started else budget == 0
            if gate and elapsed >= physical_ready_cycle:
                return start + elapsed
            if not started:
                started, remaining = True, max(0, budget - 1)
            elif remaining:
                remaining -= 1
        raise AssertionError('request never accepted')
    assert accepted(0) == max(budget, physical_ready_cycle)
    assert accepted(937) - 937 == accepted(0)
