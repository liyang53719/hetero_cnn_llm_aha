"""Atomic-edge contract for the existing VectorSiluOwner tile loan only."""
from dataclasses import dataclass
from enum import Enum

class Profile(Enum):
    LEGACY_HELD='enableBinaryAdd_false'
    PRODUCTION_PRIVATE='enableBinaryAdd_true'

class ContractError(ValueError):pass

@dataclass(frozen=True)
class Request:
    tag: int
    mode: str='silu'
    lane_count: int=16

class LoanContract:
    """One physical SFU16 pool; no proposed Attention primitive interface.

    Ready/result/divider events are externally supplied observations or synthetic
    test events, not predicted arithmetic/memory timing. A single tick contains
    all same-edge signals, so abort/result ordering cannot depend on Python calls.
    """
    def __init__(self, profile):
        if type(profile) is not Profile:raise ContractError('explicit profile enum required')
        self._profile=profile;self.active=None;self.poison=False;self.cancelled=False
        self.edge=-1;self.pending_pulses=0;self.division_seen=False
        self.held_result=None;self.used_tags=set();self.trace=[]

    @property
    def profile(self):
        return self._profile

    @staticmethod
    def _check(ok, message):
        if not ok:raise ContractError(message)

    def tick(self, edge, *, request=None, ordinary_idle=False,
             vector_request_ready=False, vector_result_valid=False,
             result_token=None, result_error=False, external_result_ready=False,
             abort=False, divider_accept_mask=0, divider_pulse_mask=0):
        # Validate the entire edge before mutating persistent state.
        self._check(type(edge) is int and edge==self.edge+1,'one atomic monotonic edge')
        for flag in (ordinary_idle,vector_request_ready,vector_result_valid,result_error,external_result_ready,abort):
            self._check(type(flag) is bool,'canonical boolean signal')
        for mask in (divider_accept_mask,divider_pulse_mask):
            self._check(type(mask) is int and 0<=mask<=0xffff,'bounded 16-lane mask')
        if request is not None:
            self._check(type(request) is Request and type(request.tag) is int and request.tag>0 and
                        request.tag not in self.used_tags and request.lane_count==16 and type(request.lane_count) is int,
                        'existing fixed16 loan request identity/shape')
            self._check(type(request.mode) is str and (request.mode=='silu' or (request.mode=='binary_add' and self.profile is Profile.PRODUCTION_PRIVATE)),
                        'only original SiLU or enabled BinaryAdd loan; no standalone Exp/Div/masked primitive')
        if vector_result_valid:
            self._check(self.active is not None,'result without accepted loan')
            self._check(type(result_token) is int and result_token>0,'opaque result identity required, not numeric payload')
            self._check(self.pending_pulses==0,'result before all previously accepted divider pulses retired')
            self._check(result_error or self.active.mode=='binary_add' or self.division_seen,
                        'successful full SiLU cannot omit its accepted internal division')
        else:
            self._check(result_token is None and not result_error,'result metadata without valid')
        if self.held_result is not None:
            self._check(vector_result_valid and (result_token,result_error)==self.held_result,
                        'held vector result identity/error must remain stable until consumed')
        if divider_accept_mask:
            self._check(self.active is not None and self.active.mode=='silu' and not self.division_seen and
                        divider_accept_mask==0xffff and not vector_result_valid,
                        'only one existing all16 internal SiLU divider phase')
        if divider_pulse_mask:
            self._check(self.active is not None and divider_pulse_mask & ~self.pending_pulses==0,
                        'unreserved/duplicate divider pulse; current-edge accept cannot return')
        # Division remains internal to an already accepted SiLU even after abort.
        # No external new request is accepted on an abort edge.
        production=self.profile is Profile.PRODUCTION_PRIVATE
        active=self.active is not None
        ready=(ordinary_idle and not active and not self.poison and not abort and vector_request_ready)
        request_fire=request is not None and ready
        external_valid=active and vector_result_valid and (not self.poison and not abort if production else True)
        external_fire=external_valid and external_result_ready
        vector_ready=active and (external_result_ready or (production and (self.poison or abort)))
        vector_fire=active and vector_result_valid and vector_ready
        private_drain=vector_fire and not external_fire
        publish=external_fire and not result_error and not self.poison and not self.cancelled and not abort
        result=dict(edge=edge,profile=self.profile.value,request_ready=ready,request_fire=request_fire,
                    external_result_valid=external_valid,external_result_fire=external_fire,
                    internal_vector_result_fire=vector_fire,private_drain=private_drain,
                    publication_allowed=publish,drained_pre=not active,
                    busy_pre=active or self.poison or (abort if production else False),
                    reset_required_pre=self.poison)
        # Commit after checks and combinational evaluation.
        self.edge=edge
        self.pending_pulses=(self.pending_pulses | divider_accept_mask) & ~divider_pulse_mask
        if divider_accept_mask:self.division_seen=True
        if request_fire:
            self.active=request;self.used_tags.add(request.tag);self.cancelled=False
            self.pending_pulses=0;self.division_seen=False
        if vector_result_valid:self.held_result=(result_token,result_error)
        if vector_fire:
            self.active=None;self.held_result=None
            if result_error:self.poison=True
        if abort:self.poison=True;self.cancelled=True
        result.update(drained_post=self.active is None,busy_post=self.active is not None or self.poison,
                      reset_required_post=self.poison,divider_pulse_debt_post=self.pending_pulses)
        self.trace.append(result)
        return result

    def report(self):
        return dict(kind='atomic_existing_SFU_loan_metadata_contract',profile=self.profile.value,
                    physical_sfu_lanes=16,new_fpu_instances=0,
                    interface_status='actual-Chisel contract, externally supplied synthetic/unverified events',
                    unresolved=['arithmetic FP32/BF16 values and flags', 'actual operation/return latency',
                                'bank operand supply and physical staging', 'full Host completion',
                                'integration with shared resource ledger'],
                    event_provenance='synthetic_or_observed_external_unverified',
                    numerical_execution=False,rtl_measured=False,accepted_80=False,accepted_90=False)
