"""Same serialized Matrix with a checked raw QKV partial-only binding.

The adapter changes no arithmetic, buffer, or resource lifecycle. It verifies
that each independent local Matrix group corresponds to the active full-job
K-window metadata. The actual bank owner supplies its pair-ordered operands.
Bias and BF16 materialization remain the following public Bias command.
"""
from dataclasses import asdict
from ..official_bf16.dense_silu import OfficialMatrixService, JOB_FIELDS
from ..ffn_attention.matrix_service import DenseLibraryAdapter, require
from .k_window_model import KWindowRequest
from .profile import ReductionProfile


class ProfiledMatrixService(OfficialMatrixService):
    def __init__(self, library, profile):
        require(type(profile) is ReductionProfile,'explicit typed numerical profile')
        self.profile=profile
        super().__init__(library)

    def bind_dense_job(self, job, role):
        binding=super().bind_dense_job(job,role)
        if role in ('q_raw','k_raw','v_raw'):
            require(job.m in (16,128),'profile M16/M128 domain')
            self.profile.validate(job.k)
        return binding

    def dense_library(self, owner):
        self._check_owner(owner,'dense')
        binding=self.bindings[self.owner_tag]
        if binding.role not in ('q_raw','k_raw','v_raw'):
            return super().dense_library(owner)
        if self._dense is None:
            self._dense=ProfiledDenseAdapter(self,owner,binding,self.profile)
        require(isinstance(self._dense,ProfiledDenseAdapter),'mixed Dense policy in one acquisition')
        return self._dense

    def report(self):
        r=super().report()
        r.update(qkv_reduction_profile=asdict(self.profile),
                 qkv_partial_rounding='unmodified FP32 Matrix results; shared-vector add then public Bias/BF16')
        return r


class ProfiledDenseAdapter(DenseLibraryAdapter):
    def __init__(self,service,owner,binding,profile):
        super().__init__(service,owner)
        self.binding,self.profile,self.active_window=binding,profile,None

    def td_group(self,start,end,contexts):
        self._check()
        q=self.owner.window_request
        require(isinstance(q,KWindowRequest),'QKV profiled Matrix requires real K-window owner')
        q.validate();self.profile.validate(q.job.k)
        fields=tuple((name,getattr(q.job,name)) for name in JOB_FIELDS)
        require(fields==self.binding.job_fields,'partial full Job differs from public source/dtype/stride binding')
        require((q.k_begin,q.k_end) in self.profile.ranges and
                q.block_id==self.profile.ranges.index((q.k_begin,q.k_end))+1 and
                q.pair_reverse==self.profile.pair_reverse,'active partial does not match immutable K profile')
        require((start,end,contexts)==(0,q.k_end-q.k_begin,q.cols//32),
                'independent partial Matrix group must use accepted local K ordinals')
        result=super().td_group(start,end,contexts)
        if result==0:self.active_window=q
        return result

    def td_step(self,k,context,clear,last,finish,emit,a,b,output):
        require(self.active_window is not None and self.owner.window_request==self.active_window,
                'active full-job K window changed while Matrix was owned')
        return super().td_step(k,context,clear,last,finish,emit,a,b,output)

    def td_seed_begin(self,*args):
        raise ValueError('independent QKV partials do not accept injected/restored accumulator seeds')
