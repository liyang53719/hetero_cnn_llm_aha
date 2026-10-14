"""Narrow host/physical obligations and causal coverage; no arithmetic changes."""
from dataclasses import asdict
import hashlib


def require(ok,message):
    if not ok:raise ValueError(message)


def debts(x,physical):
    owner=x.owner;service=x.matrix_service;attention=x.attention_owner
    return dict(matrix_owned=service.owner is not None,scalar_owned=x.prefix_owner.scalar.client is not None,
        dma_pending=physical.pending is not None,owner_pending=owner.pending is not None,
        owner_fifo=len(owner.fifo),owner_read=owner.read_active is not None,
        owner_a_hold=owner.a_hold is not None,owner_a_rmw=owner.a_rmw_pending is not None,
        accepted_write=owner.accepted_write is not None,tile_lease=owner.tiles.leased,
        tile_busy=not owner.tiles.idle,a_lease=owner.lease is not None,
        reduction_active=x.reduction is not None,reset_required=x.reset_required(),
        prefix_not_idle=x.prefix_owner.state!='idle',attention_not_idle=attention.state!='idle',
        attention_memory_pending=attention.memory_pending,attention_abort_pending=attention.abort_pending,
        attention_client_live=attention.matrix_client is not None,
        attention_matrix_request=attention.matrix_request is not None,
        matrix_c_state=int(service.lib.matrix_state()))


def identity(x,physical):
    return dict(execution=id(x),host=id(x.host),physical=id(physical),metadata=id(x.frontend.memory),
        owner=id(x.owner),a_banks=id(x.owner.a_banks),b_banks=id(x.owner.b_banks),
        tile_banks=id(x.owner.tiles.banks),prefix_owner=id(x.prefix_owner),attention_owner=id(x.attention_owner),
        matrix=id(x.matrix_service),scalar=id(x.prefix_owner.scalar),
        accumulator_address=x.matrix_service.resource_address)


def held_checkpoint(x,physical,*,pc,completed,jobs,output):
    held=x.ports()['completion'];region=physical.regions[output]
    require(x.host.pc==pc and x.host.completed==completed and x.host.jobs==jobs and
        x.host.state=='complete' and x.host.status is None and x.launch_result is None,
        'held host boundary identity')
    require(held is not None and held.pc==pc and held.signal==pc+1 and held.status is None,
        'held completion identity/status')
    require(x.counts['request_fire']==x.counts['owner_result_fire']==jobs and
        x.counts['completion_fire']==completed and x.counts['result_fire']==0 and
        [c['pc'] for c in x.completions]==list(range(completed)) and
        x.host.events==set(range(completed+1)), 'held boundary actual accepted counts/events')
    require(region['terminal'] and not region['published'] and
        len(region['written'])*64==len(region['acked'])*64==region['extent'] and
        (region['base'],region['base']+region['extent']) not in x.host.published,
        'held physical output missing ACK/terminal or already visible')
    outstanding=debts(x,physical)
    require(not any(outstanding.values()),'accepted backend obligations outstanding: '+str(outstanding))
    return dict(pc=pc,completed=completed,jobs=jobs,completion=asdict(held),
        launch_result=None,finalfence=False,output=output,output_published=False,backend_debts=outstanding)


def stable_hold(x,physical,*,pc,completed,jobs,output,ticks=5):
    before=held_checkpoint(x,physical,pc=pc,completed=completed,jobs=jobs,output=output)
    hashes={n:hashlib.sha256(r['data'][64:-64]).hexdigest() for n,r in physical.regions.items() if not r['readonly']}
    events=set(x.host.events);published=list(x.host.published)
    for _ in range(ticks):
        x.idle_edge()
        require(held_checkpoint(x,physical,pc=pc,completed=completed,jobs=jobs,output=output)==before,
            'held completion changed')
        require(x.host.events==events and list(x.host.published)==published,'held event/publication changed')
        require(hashes=={n:hashlib.sha256(r['data'][64:-64]).hexdigest() for n,r in physical.regions.items() if not r['readonly']},
            'held output/suffix bytes changed')
    return dict(before,stability_ticks=ticks,all_physical_output_hashes=hashes)


def pristine_suffix(physical,prefix):
    from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import SENTINEL
    result={}
    for name,r in physical.regions.items():
        if r['readonly'] or name in prefix:continue
        require(not r['written'] and not r['acked'] and not r['terminal'] and not r['published'] and
            r['data'][64:-64]==SENTINEL*(r['extent']//4),'unexecuted suffix/virtual output changed: '+name)
        result[name]=dict(status='NOT_EXECUTED',written_bytes=0,ack_bytes=0,published=False)
    return result
