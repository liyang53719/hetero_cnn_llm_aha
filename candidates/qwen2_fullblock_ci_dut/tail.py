"""Fresh pc12-held continuation using the original pc13..20 driver body.

No restore/resume path, arithmetic edits, private output provider, injected
job, manual Host state change, narrowed window, or reduced Down chunk exists.
"""
from array import array
from dataclasses import asdict
from pathlib import Path
from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as execution
from candidates.qwen2_resident_matrix.ffn_public import prefix_execution as prefix
from candidates.qwen2_resident_matrix.ffn_public.fullgraph_execution import _request, _dense
from candidates.qwen2_live_attention_model_m128 import boundary
from . import statistics
require = execution.require


def execute_tail(x, physical, lib, output, *, memory, attention_job, stage):
    boundary.held_checkpoint(x, physical, pc=12, completed=12, jobs=11, output='att')
    require(attention_job is x.host.bound and attention_job is x.attention_owner.job and
            attention_job.kind == 'Attention' and attention_job.tag & 0xffff == 12,
            'continuation requires this live accepted pc12 job, never a copied job')
    require(memory.physical_memory is physical and memory.act.data is physical.regions['act']['data'] and
            memory.workspace.physical_memory is physical and memory.workspace.job is None and
            not memory.workspace.finished and memory.workspace.extent == 786432,
            'initial single physical act/workspace view required before launch')
    require(set(n for n,r in physical.regions.items() if n in physical.fixture.allocations and r['readonly'] and r['provider'] is not None) ==
            {'x','gamma0','wq','wk','wv','bq','bk','bv','rope','wo','gamma1','wg','wu','wd'},
            'all fourteen initial readonly roles required')
    require(lib.sf_entrypoint == 'sf_vector_bf16_v1' and lib.calls == 0 and
            int(lib.sf_calls()) == int(lib.sf_failures()) == 0, 'fresh selected original BF16 SiLU ABI required')
    out = Path(output)
    require(out.is_dir(), 'fresh fullblock output directory required')
    identities = (id(x.owner), id(x.prefix_owner), id(x.attention_owner), id(x.matrix_service),
                  id(x.prefix_owner.scalar), id(physical), id(memory.act.data), id(memory.workspace.data))
    identities_full = statistics.identity(x,physical,memory)
    reports = []
    stage('pc12_release')
    x.publish_completions((12,))
    physical.publish(attention_job,x.host)
    require(x.host.pc == x.host.completed == 13 and x.host.jobs == 11 and x.host.state == 'decode' and
            [c['pc'] for c in x.completions] == list(range(13)), 'pc12 did not genuinely retire')

    for pc, kind in ((13, 'Dense'), (14, 'Add'), (15, 'Norm')):
        stage("pc"+str(pc)+"_"+kind)
        job = _request(x, pc, kind)
        report = (_dense(x, physical, memory, lib, job, out / 'pc13_dense_o') if kind == 'Dense'
                  else prefix.execute_prefix_owner(x, physical, job))
        x.publish_completions((pc,))
        physical.publish(job, x.host)
        if kind == 'Dense':
            x.retire_ordinary_bookkeeping()
        reports.append(dict(pcs=[pc], kind=kind, report=report))

    stage("pc16_18_resident_ffn")
    ports = x.advance_to_request()
    call = ports['group_request']
    require(call is not None and ports['ordinary_request'] is None and
            tuple(getattr(call, role).tag & 0xffff for role in ('gate', 'up', 'act')) == (16, 17, 18),
            'fullgraph requires the original Gate/Up/SiLU public group')
    h = x.start_group()
    group_out = out / 'pc16_18_ffn'
    group_out.mkdir()
    outputs = {role: array('I', [execution.numeric.drain_check.SENTINEL_WORD]) *
               (h.call.gate.m * execution.numeric.WIDTH) for role in ('gate', 'up')}
    group_report = execution.execute_windows(x, lib, memory, outputs, group_out)
    for _ in range(16):
        if h.terminal is not None:
            break
        h.tick()
    require(h.terminal is not None and h.terminal.status is None and
            h.c.state == 'idle' and x.owner.lease is None and x.matrix_service.owner is None,
            'actual fullgraph FFN group did not retire')
    _, act_report = memory.act.validate_full()
    require(h.terminal.write_bytes == memory.act.ack_bytes and
            h.terminal.useful_macs == sum(r['useful_macs'] for r in h.window_reports) and
            h.terminal.executed_macs == sum(r['executed_macs'] for r in h.window_reports),
            'fullgraph FFN terminal differs from actual accepted traffic')
    physical.terminal(h.call.act, h.terminal)
    x.publish_completions((16, 17, 18))
    physical.publish(h.call.act, x.host)
    group_report.update(act_ddr=act_report, coordinator=dict(accepted=dict(h.counts),
        terminal=asdict(h.terminal), window_terminals=h.window_reports,
        drain_terminals=h.drain_reports, handoffs=h.handoffs))
    reports.append(dict(pcs=[16, 17, 18], kind='FFN', report=group_report))

    stage("pc19_down")
    job = _request(x, 19, 'Dense')
    report = _dense(x, physical, memory, lib, job, out / 'pc19_down', down=True)
    x.publish_completions((19,))
    physical.publish(job, x.host)
    x.retire_ordinary_bookkeeping()
    reports.append(dict(pcs=[19], kind='Dense', report=report))

    stage("pc20_residual")
    job = _request(x, 20, 'Add')
    report = prefix.execute_prefix_owner(x, physical, job)
    x.publish_completions((20,))
    physical.publish(job, x.host)
    reports.append(dict(pcs=[20], kind='Add', report=report))
    stage("launch_result_hold_retire")
    result = x.finish()
    require(result['status'] is None and result['completed'] == 21 and result['jobs'] == 17 and
            [c['pc'] for c in x.completions] == list(range(21)) and
            all(c['status'] is None for c in x.completions) and
            x.counts['completion_fire'] == 21 and x.counts['request_fire'] == x.counts['owner_result_fire'] == 17 and
            x.counts['result_fire'] == 1 and x.host.events == set(range(22)),
            'whole public21 terminal lacks exactly 21 completions and 17 actual owner jobs')
    require(identities == (id(x.owner), id(x.prefix_owner), id(x.attention_owner), id(x.matrix_service),
            id(x.prefix_owner.scalar), id(physical), id(memory.act.data), id(memory.workspace.data)) and
            x.owner.state == x.prefix_owner.state == x.attention_owner.state == 'idle' and
            x.matrix_service.owner is None and x.prefix_owner.scalar.client is None and
            x.owner.lease is None and x.owner.tiles.idle and not x.owner.tiles.leased and
            not x.reset_required() and physical.pending is None and memory.workspace.finished,
            'whole public21 terminal changed resources or left obligations outstanding')
    require(not any(statistics.debts(x, physical, memory).values()),
            "whole block has outstanding tail obligations")
    require(identities_full == statistics.identity(x, physical, memory), "live physical buffer/resource replacement")
    physical.check_coexistence()
    virtual_spans = set(x.host.virtual)
    # Gate/Up are ordinary reservations in the original public manifest. The
    # actual Host's accepted FFN group gives them their virtual lifetime; do
    # not mistake their untouched DDR reservations for missing output jobs.
    require(all((physical.regions[name]['base'], physical.regions[name]['base'] +
                 physical.regions[name]['extent']) in virtual_spans
                for name in ('scores', 'probabilities', 'gate', 'up')),
            'whole public21 terminal lost original Attention/FFN virtual reservations')
    for name, region in physical.regions.items():
        if region['readonly'] or name == 'workspace':
            continue
        if (region['base'], region['base'] + region['extent']) in virtual_spans:
            require(not region['written'] and not region['acked'] and not region['terminal'] and
                    not region['published'] and
                    region['data'][64:-64] == prefix.SENTINEL * (region['extent'] // 4),
                    'virtual intermediate became a physical output: ' + name)
            continue
        require(region['terminal'] and region['published'], 'unexecuted fullgraph output: ' + name)
        words = array('I')
        words.frombytes(physical.raw(region['base'], region['extent']))
        outputs[name] = words
    require(result['write_bytes'] == sum(len(r['acked']) * 64 for name, r in physical.regions.items()
            if not r['readonly'] and not r['virtual'] and name != 'workspace'),
            'whole public21 written total differs from actual physical output ACK coverage')
    for name, words in outputs.items():
        (out / ('actual_' + name + '.f32le')).write_bytes(words.tobytes())
    return outputs, dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED', reports=reports,
        host=x.report(), memory=physical.report(), matrix=x.matrix_service.report(),
        virtual_outputs=memory.check_virtual(), same_owner_and_banks=True,
        same_physical_memory_and_services=True, full_block_executed=True,
        full_block_software_model_executed=True, attention_suffix_executed=True,
        public_host_python_model_executed=True, scala_host_executed=False,
        rtl_executed=False, actual_idma=False, hardware_cycles=None,
        protocol_model_ticks_are_hardware_cycles=False, full_wall_mac_utilization=None,
        reference_arithmetic_executed=False, native_acceptance='NOT_EVALUATED_BY_EXECUTION_SEE_COMPARISON')
