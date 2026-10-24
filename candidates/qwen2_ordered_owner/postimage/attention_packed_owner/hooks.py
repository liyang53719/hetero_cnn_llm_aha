"""Narrow optional owner hooks; all parent-bank edges belong to the outer driver."""
from .protocol import ScratchAction,ScratchResponse
from .schedule import PackedSchedule
from .client import PackedClient,PackedRequest,PackedConsumerAck,PackedWriteTag,PackedWriteAck
from ..ffn_public.prefix_owners import PrefixFault
from ..production_qk16_model.schedule import ProductionQk16Schedule
from ..production_qk16_model.routing import Qk16LegacyPvClient
from ..production_qk16_model import ordered_owner

def install(owner,schedule):
    if schedule is not None and type(schedule) not in (PackedSchedule,ProductionQk16Schedule):raise ValueError('exact packed schedule required')
    if schedule is not None:schedule.bind(owner)
    owner.packed_schedule=schedule;owner.scratch_request=None;owner.scratch_pending=False;owner.scratch_write_tag=None;owner.scratch_leased=False;owner.scratch_last=None;owner.packed_memory_tag=None
    ordered_owner.initialize(owner)

def ports(o,p):
    p.update(scratch=o.scratch_request if not o.scratch_pending else None,scratch_response_ready=o.scratch_pending)
    return p

def validate(o,j):
    if type(o.packed_schedule) is ProductionQk16Schedule:
        o.packed_schedule.validate_length(j.m)

def client(o):
    return (Qk16LegacyPvClient(o.matrix,o) if type(o.packed_schedule) is ProductionQk16Schedule
            else PackedClient(o.matrix,o))
def fault(o):
    ordered_owner.fault(o)
    if not o.scratch_pending:o.scratch_request=None
    queue_release(o)

def action(o,a):
    if o.packed_schedule is None:return False
    if ordered_owner.action(o,a):return True
    if type(a) in (PackedRequest,PackedConsumerAck):
        o.matrix_request=a;o.state='matrix_issue';return True
    if type(a) is ScratchAction:
        if not a.valid():raise PrefixFault('Protocol','malformed scratch action')
        o.scratch_request=a;o.state='scratch_issue';return True
    return False

def edge(o,p,ready,response):
    p.update(scratch_fire=False,scratch_response_fire=False)
    if o.packed_schedule is None:
        if response is not None:raise ValueError('scratch response while default profile selected')
        return
    queue_release(o)
    if p.get('scratch') is not None and p['scratch'] is o.scratch_request and ready and (not o.poison or o.scratch_request.operation=='release'):
        a=o.scratch_request
        if a.operation=='write' and o.matrix_client.held_tag is not None:
            tag=PackedWriteTag(o.matrix_client.held_tag,'scratch',a.line,a.generation,a.serial)
            o.matrix_client.register_write(tag);o.scratch_write_tag=tag
        o.scratch_pending=True;o.scratch_last=a
        if not o.poison:o.state='scratch_wait'
        p['scratch_fire']=True
    if p.get('scratch_response_ready') and response is not None:
        a=o.scratch_request
        if type(response) is not ScratchResponse or type(response.action) is not ScratchAction or not response.action.valid() or response.action!=a:
            o._fault('Protocol','foreign scratch response; debt retained');return
        malformed=type(response.error) is not bool or type(response.words) is not tuple or any(type(x) is not int or not 0<=x<1<<32 for x in response.words) or len(response.words)!=(16 if a.operation=='read' else 0)
        if malformed:response=ScratchResponse(a,(),True)
        o.scratch_pending=False;o.scratch_request=None;p['scratch_response_fire']=True
        if a.operation=='acquire' and not response.error:o.scratch_leased=True
        if a.operation=='release' and not response.error:o.scratch_leased=False
        if o.scratch_write_tag is not None:
            o.matrix_client.commit_write(PackedWriteAck(o.scratch_write_tag,response.error or o.poison));o.scratch_write_tag=None
        if response.error:o._fault('Memory','scratch operation failed')
        elif o.state!='drain':o._advance(response)
        queue_release(o)

def queue_release(o):
    if (o.poison and o.scratch_leased and not o.scratch_pending and o.scratch_request is None
            and not o.memory_pending and (o.matrix_client is None or o.matrix_client.ports()['drained'])):
        a=o.scratch_last
        o.scratch_request=o.packed_schedule.scratch('release',a.generation,a.query,a.kv_head)


def memory_accept(o,q):
    if o.packed_schedule is not None and q.write and o.matrix_client.held_tag is not None:
        if o.packed_memory_tag is not None:raise PrefixFault('Protocol','two packed output write debts')
        tag=PackedWriteTag(o.matrix_client.held_tag,'output',q.address,0,q.tag)
        o.matrix_client.register_write(tag);o.packed_memory_tag=tag

def memory_ack(o,q,r):
    if o.packed_memory_tag is not None:
        bad=o.poison or type(r.error) is not bool or r.error or type(r.nbytes) is not int or r.nbytes!=64
        o.matrix_client.commit_write(PackedWriteAck(o.packed_memory_tag,bool(bad)));o.packed_memory_tag=None


def record_result(o,result):
    from .client import PackedResult,PackedStepAccepted,PackedRetired
    if o.packed_schedule is None or type(result) is PackedResult:o.counts['matrix_results']+=1
    elif type(o.packed_schedule) is ProductionQk16Schedule and o.matrix_client.is_legacy_result(result):o.counts['matrix_results']+=1
    elif type(result) is PackedStepAccepted:o.counts['packed_nonfinal_accept_completions']+=1
    elif type(result) is PackedRetired:o.counts['packed_consumer_retirements']+=1
    else:raise PrefixFault('Protocol','unknown packed client completion')


def ordered_pre_client(o,p,done_override):
    ordered_owner.pre_client(o,p,done_override)

def ordered_post_client(o,p):
    ordered_owner.post_client(o,p)

def ordered_result_error(o,result):
    return ordered_owner.result_error(o,result)
