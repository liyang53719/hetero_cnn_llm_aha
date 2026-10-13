"""Four bounded K slabs with three left-fold sums; real terminals own credit.

Control metadata only. Original two-range coordinator remains untouched.
Each partial/sum has a distinct identity and all old retirement, abort,
held-terminal and actual-byte fences are inherited. No output arithmetic here.
"""
from dataclasses import dataclass
from ..qwen2_resident_matrix.dense_block_reduce.public_coordinator import (
    DenseReductionRequest, DenseReductionCoordinator, Services, uint)
from .streaming_owner import StreamingWindowRequest, StreamingDrainRequest, validate_full_job
from .chained_sum import SumInvocation

RANGES=((0,1024),(1024,2048),(2048,3072),(3072,4096))

@dataclass(frozen=True)
class FourReductionRequest(DenseReductionRequest):
    partial_ids: tuple = ()
    sum_ids: tuple = ()

    def validate(self):
        validate_full_job(self.job)
        if self.k_ranges!=RANGES or self.pair_reverse is not True:
            raise ValueError('explicit four contiguous K1024 high-first ranges required')
        if (type(self.partial_ids) is not tuple or len(self.partial_ids)!=4 or
            type(self.sum_ids) is not tuple or len(self.sum_ids)!=3):
            raise ValueError('exact immutable four partial/three sum identity tuples')
        ids=(self.identity,)+self.partial_ids+self.sum_ids
        if any(not uint(x,32) or not x for x in ids) or len(set(ids))!=8:
            raise ValueError('distinct public/four partial/three sum identities')
        for block in range(4):
            StreamingWindowRequest.from_full(self.job,self.partial_ids[block],0,min(160,self.job.n),block).validate()
        StreamingDrainRequest(self.job,self.sum_ids[-1],0,min(160,self.job.n)).validate()

class FourReductionCoordinator(DenseReductionCoordinator):
    def ports(self,services=Services(),*,abort=False):
        p=super().ports(services,abort=abort)
        if p['window_request'] is not None:
            p['window_request']=StreamingWindowRequest.from_full(
                self.call.job,self.call.partial_ids[self.block],self.ng,self.cols,self.block)
        if p['sum_request'] is not None:
            block=self.block
            p['sum_request']=SumInvocation(identity=self.call.sum_ids[block-1],
                lhs_identity=self.call.partial_ids[0] if block==1 else self.call.sum_ids[block-2],
                rhs_identity=self.call.partial_ids[block],ng=self.ng,rows=self.call.job.m,
                cols=self.cols,lhs_phase='partial' if block==1 else 'sum')
        if p['drain_request'] is not None:
            p['drain_request']=StreamingDrainRequest(self.call.job,self.call.sum_ids[-1],self.ng,self.cols)
        return p

    def _window_exact(self,r,services):
        try:
            fields=((r.tag,32),(r.identity,32),(r.ng,16),(r.rows,8),(r.cols,8),
                    (r.slot,2),(r.k_begin,16),(r.k_end,16),(r.block_id,32),(r.produced_beats,11))
            return (all(uint(v,b) for v,b in fields) and r.pair_reverse is True and
                (r.tag,r.identity,r.ng,r.rows,r.cols,r.slot,r.k_begin,r.k_end,r.block_id)==
                (self.call.job.tag,self.call.partial_ids[self.block],self.ng,self.call.job.m,self.cols,
                 0 if self.block==0 else 1,*RANGES[self.block],self.block+1) and
                r.committed is True and r.produced_beats==self.call.job.m//16*self.cols and
                r.ddr_write_bytes==0 and services.lease_valid)
        except (AttributeError,TypeError):return False

    def _drain_exact(self,r,services):
        try:
            fields=((r.tag,32),(r.identity,32),(r.ng,16),(r.rows,8),(r.cols,8),(r.consumed_beats,11))
            return (all(uint(v,b) for v,b in fields) and
                (r.tag,r.identity,r.ng,r.rows,r.cols)==
                (self.call.job.tag,self.call.sum_ids[-1],self.ng,self.call.job.m,self.cols) and
                r.committed is True and r.consumed_beats==self.call.job.m//16*self.cols and
                r.ddr_write_bytes==self.call.job.m*self.cols*2 and
                not services.tiles_leased and services.tiles_drained)
        except (AttributeError,TypeError):return False

    def tick(self,**kwargs):
        previous=self.state
        edge=super().tick(**kwargs)
        # The inherited fence has verified bank, Vector and owner retirement.
        # A subsequent producer may now overwrite ONLY the retired rhs slot.
        if (previous=='sumWait' and kwargs.get('sum_complete') and
            self.state=='drainFlush' and not self.poison and self.block<3):
            self.block+=1
            self.state='partialFlush'
        return edge
