"""Full32-head cold chunk on the caller's actual published Prep region.

A successful terminal is a private staging receipt, never a block commit.
"""
import time
from .chunk_budget import closed_counts
from ..qwen35_gdn_prefill.chunk import model as c

class ChunkInterrupted(RuntimeError):
    def __init__(self, error, driver, snapshot):
        super().__init__(str(error))
        self.snapshot = snapshot
        self.raw = {name: getattr(driver,name).raw() for name in ('output','state_out','scratch')}


def execute_chunk(memory, scalar, vector, producer, allocate, *, tokens, deadline,
                  controls=None, progress=None, stall_budget=1024, on_interrupt=None):
    c.require(type(tokens) is int and tokens in (16,128), 'full35 M16/M128')
    c.require(type(deadline) in (int,float) and deadline>time.monotonic(),'future wall deadline')
    c.require(controls is None or callable(controls),'optional controls')
    c.require(progress is None or callable(progress),'optional progress observer')
    c.require(on_interrupt is None or callable(on_interrupt),'optional execution alarm cancellation')
    c.require(type(stall_budget) is int and 0 <= stall_budget <= 1000000, 'finite stall budget')
    c.require(memory.exact(producer.base,tokens*c.GROUPED_35B.core_row_bytes,readable=True) is producer,
              'actual Prep MemoryRegion identity')
    expected = closed_counts(tokens,128,128)
    state_bytes=32*128*128*4
    state_in=allocate(size=state_bytes)
    state_out=allocate(size=state_bytes)
    output=allocate(size=tokens*32*128*2)
    scratch=allocate(size=expected['scratch_ddr_bytes'])
    owner=c.ChunkOwner(scalar,vector,heads=32,key_dim=128,value_dim=128,host_batch=True,
        layout=c.GROUPED_35B,cumsum_policy=c.GUARDED_CUMSUM,exp_policy=c.ep.IEEE_EXP)
    job=c.ChunkJob(35301,producer.base,state_in,state_out,output,scratch,tokens,
        heads=32,layout=c.GROUPED_35B,cumsum_policy=c.GUARDED_CUMSUM,exp_policy=c.ep.IEEE_EXP)
    driver=c.TypedChunkDriver(owner,memory,job)
    c.require(driver.input is producer and owner.scalar is scalar and owner.vector is vector,'shared producer/resources')
    limit=expected['driver_ticks_no_stall']+stall_budget
    started=time.monotonic()
    def request_identity(q):
        return None if q is None else dict(address=q.address,tag=q.tag,write=q.write,nbytes=64,data_bytes=0 if q.data is None else len(q.data))
    def snapshot():
        return dict(owner=driver.report(),owner_state=owner.state,sequence=owner.sequence,
            held_request=request_identity(owner.request),accepted_request=request_identity(driver.pending_request),
            pending_write=None if driver.pending_write is None else dict(command=vars(driver.pending_write[1][0])),position=dict(owner.position),context=dict(owner.context),
            pending_response=driver.pending is not None,physical_write_pending=memory.pending is not None,
            terminal_accepted=driver.response is not None,automatically_drained=False,resumable_checkpoint=False,
            span_coverage={name:dict(bytes=getattr(driver,name).extent,written_beats=len(getattr(driver,name).written),
                acknowledged_beats=len(getattr(driver,name).acknowledged),published=getattr(driver,name).published)
                for name in ('output','state_out','scratch')})
    try:
        for tick in range(limit):
            c.require(time.monotonic()<deadline,'bounded chunk wall deadline')
            driver.tick(**({} if controls is None else controls('chunk',tick,driver)))
            if progress is not None and tick%1000000==0:
                progress(dict(ticks=tick+1,limit=limit,context=dict(owner.context),position=dict(owner.position),
                              host_seconds=time.monotonic()-started,counts=dict(driver.counts)))
            if driver.response is not None:break
        c.require(driver.response is not None,'bounded chunk transport watchdog')
        details=driver.report()
        c.require(not any(getattr(driver,name).published for name in ('output','state_out','scratch')),'staging published early')
        details.update(transport_prediction=expected,transport_watchdog=limit,stall_budget=stall_budget,
            same_actual_prep_region=True,same_scalar=True,same_vector=True,host_seconds=time.monotonic()-started,
            hardware_cycles=None,hardware_utilization=None,busy_duty=None,native_acceptance=False)
        if driver.response.status is None:
            c.require(driver.response.staging_complete,'missing complete staging receipt')
            for name in ('read_bytes','write_bytes','source_read_bytes','scratch_read_bytes'):
                c.require(driver.counts[name]==expected[name],'transport prediction mismatch '+name)
            if controls is None:
                c.require(driver.counts['ticks']==expected['driver_ticks_no_stall'],'no-stall tick prediction')
    except BaseException as error:
        if on_interrupt is not None:on_interrupt()
        raise ChunkInterrupted(error,driver,snapshot()) from error
    return driver,details
