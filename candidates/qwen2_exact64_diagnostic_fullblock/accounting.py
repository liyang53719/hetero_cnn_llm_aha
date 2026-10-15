"""Separate actual software exact64 work from original MatrixStream events.

Predictions are checked against accepted reports. They never manufacture an
issue, cycle, utilization, launch terminal, or successful numerical verdict.
"""
from collections import Counter

SCOPE='DIAGNOSTIC_SOFTWARE_OWNER'
V_EXPECTED=dict(partials=4,drains=2,wide_matrix_steps=12288,useful_macs=50331648,
    executed_macs=50331648,actual_c_fma_calls=50331648,vector_add_requests=2048,
    raw_qkv_ack_bytes=131072)
EXACT_EXPECTED=dict(fmas=352321536,adds=14680064,write_bytes=917504,tiles=3584)
WHOLE_EXPECTED=dict(dense_steps=1376256,normal_steps=1188864,dense_fma=5637144576,
    normal_fma=608698368,whole_useful_macs=6014828544,whole_executed_macs=6598164480,
    opportunities=10506731520,silu_calls=71680,tail_dense_steps=1363968,
    tail_dense_fma=5586812928,tail_dense_groups=162,tail_dense_results=800,tail_matrix_leases=114)


def need(ok,message):
    if not ok:raise ValueError(message)


def v_totals(records):
    need(len(records)==1 and records[0]['original_public_job']['tag']&0xffff==7,
        'only actual original pc7 V remains in Matrix reduction reports')
    totals=Counter()
    for r in records:
        totals['partials']+=len(r['partials']);totals['drains']+=len(r['drains'])
        totals['wide_matrix_steps']+=r['accepted']['backend_step_fire']
        totals['useful_macs']+=r['terminal']['useful_macs']
        totals['executed_macs']+=r['terminal']['executed_macs']
        totals['actual_c_fma_calls']+=r['actual_dense_fma_calls_delta']
        totals['vector_add_requests']+=r['shared_vector']['add_requests']
        totals['raw_qkv_ack_bytes']+=r['terminal']['write_bytes']
    need(dict(totals)==V_EXPECTED,'actual V accepted/FMA/reduction schedule differs')
    return dict(totals)


def exact64_totals(records):
    """Driver report schema is explicit; no fallback to shape-derived counters."""
    need(len(records)==2,'two actual exact64 projection owner terminals required')
    totals=Counter()
    for (pc,width),r in zip(((1,1536),(4,256)),records):
        need(r['scope']==SCOPE and r['performance']=='NO_GO' and
            r['hardware_mapping']=='NOT_IMPLEMENTED','exact64 diagnostic scope')
        need(r['job']['tag']&0xffff==pc and r['terminal']['status'] is None,
            'ordered genuine pc1/pc4 exact64 terminals')
        need((r['job']['m'],r['job']['n'],r['job']['k'])==(128,width,1536),
            'original full M128 projection geometry')
        counts=r['kernel_delta']
        need(all(type(counts[n]) is int and counts[n]>=0 for n in ('fmas','adds','tiles_started')),
            'canonical nonnegative exact64 actual counters')
        output_elements=128*width
        need(counts['fmas']==output_elements*1536 and counts['adds']==output_elements*64 and
            counts['tiles_started']==r['tiles_output_acked']==output_elements//64 and
            r['terminal']['write_bytes']==output_elements*4,
            'each exact64 projection must complete its full actual arithmetic/tile/ACK coverage')
        memory=r['memory'];reads=128*(96+width//64*3072);writes=output_elements//16
        need(memory==dict(read_bytes=reads*64,write_bytes=writes*64,read_requests=reads,write_requests=writes,acks=writes),
            'exact64 accepted memory traffic differs from bounded row/tile schedule')
        need(r['terminal']['useful_macs']==r['terminal']['executed_macs']==counts['fmas'],
            'actual exact64 kernel FMA/Host terminal disagreement')
        need(r['matrix_counter_delta'].get('dense_steps',0)==0 and
            r['matrix_counter_delta'].get('normal_steps',0)==0 and
            r['actual_dense_fma_calls_delta']==0 and r['actual_normal_fma_calls_delta']==0,
            'exact64 software work must not invent MatrixStream issue/FMA')
        need(r['partial_bytes']==16384 and r['final_ack_fence']['terminal_strictly_after_final_ack'] is True and
            r['final_ack_fence']['held_ticks']==5,
            'bounded partials and actual final-ACK terminal fence')
        totals['fmas']+=counts['fmas'];totals['adds']+=counts['adds']
        totals['tiles']+=counts['tiles_started'];totals['write_bytes']+=r['terminal']['write_bytes']
    need(dict(totals)==EXACT_EXPECTED,'actual exact64 M128 FMA/Add/ACK/tile totals differ')
    return dict(totals)


def whole(matrix,statistics,launch,silu,intervals,exact):
    expected=WHOLE_EXPECTED;c=matrix['counters']
    need(exact==EXACT_EXPECTED,'fullblock requires validated actual exact64 totals')
    need(c['dense_steps']==expected['dense_steps'] and c['normal_steps']==expected['normal_steps'] and
        matrix['dense_fma_calls']==expected['dense_fma'] and matrix['normal_fma_calls']==expected['normal_fma'] and
        launch['useful_macs']==expected['whole_useful_macs'] and
        launch['executed_macs']==expected['whole_executed_macs'] and
        statistics['full_fixed_array_issued_cell_opportunities']==expected['opportunities'] and
        silu.calls==int(silu.sf_calls())==expected['silu_calls'] and int(silu.sf_failures())==0,
        'actual mixed software/Matrix fullblock schedule differs')
    tail=Counter()
    for r in intervals:
        if r['name'] in ('pc13_Dense','pc16_18_resident_ffn','pc19_down'):
            tail.update(r['accepted_counter_delta']['matrix'])
    need(tuple(tail[n] for n in ('dense_steps','dense_groups','dense_results','owner_acquires','owner_releases','dense_seed_acks'))==
        (1363968,162,800,114,114,144),'actual original tail schedule differs')
    need(matrix['dense_fma_calls']+matrix['normal_fma_calls']+exact['fmas']==launch['executed_macs'],
        'separate actual C kernels must account for every launch FMA')
    return dict(predicted=expected,observed_tail=dict(tail),exact64_software=dict(exact),
        actual_useful_macs=launch['useful_macs'],actual_executed_macs=launch['executed_macs'],
        exact64_matrix_stream_steps=0,full_fixed_array_opportunities_scope='ORIGINAL_MATRIX_EVENTS_ONLY',
        exact64_tree_adds_are_macs=False,hardware_cycles=None,hardware_utilization=None,
        performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',scope=SCOPE)


def identity(x,projection):
    """Additional local object identities; never a public artifact projection."""
    return dict(projection=id(projection),kernel=id(projection.kernel),
        partial=id(projection.kernel.partial),n0_row=id(projection.row),weights=id(projection.weights),
        original_a_payload=list(x.owner.bank_guard.payload_identity),
        resident_scratch=id(x.attention_owner.scratch),
        resident_storage=id(x.attention_owner.scratch.storage))


def debts(x,projection):
    route=x.attention_router;scratch=x.attention_owner.scratch
    return dict(exact64_active=getattr(x,'exact64_projection',None) is not None,
        exact64_not_idle=projection.state!='idle',exact64_poison=projection.poison,
        exact64_request=projection.request is not None,exact64_result=projection.result is not None,
        exact64_kernel_not_idle=projection.kernel.state!='idle',
        shared_a_guard_lease=x.owner.bank_guard.lease is not None,
        shared_a_route_active=route is not None and route.active,
        shared_a_route_fault=route is not None and route.fault is not None,
        shared_a_owner=scratch.owner is not None,shared_a_pending=scratch.pending is not None,
        shared_a_hold=scratch.held is not None,shared_a_valid_lines=any(scratch.valid),
        attention_local_pending=x.attention_owner.local_pending,
        attention_local_request=x.attention_owner.local_request is not None,
        attention_deferred_finish=x.attention_owner.deferred_finish is not None)
