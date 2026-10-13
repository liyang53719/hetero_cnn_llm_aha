"""K2048 internal profile using the original actual Matrix/Vector/DMA driver.

The explicit numerical profile remains a synthetic/diagnostic choice until a
fixed official 35B backend has been checked. Capacity or a successful fixed
recipe never implies native 35B acceptance. No alternate numerical top exists:
all accepted requests use the inherited driver, same MatrixService, Vector16,
TypedMemory, result queue and actual write ACK/publication path.
"""
from ..qwen35_gdn_prefill import projection_driver as base
from .projection_owner import (LargeKProjectionOwner, LargeKWindowRequest,
    LargeKReductionRequest, LargeKReductionCoordinator)
from .sum_tiles import InplaceSumController, owner_tile_edge
from .partial_tiles import resource_ledger

FAMILY = 'candidate_k2048_two_partials_v1'
SOURCE_FILES = base.SOURCE_FILES + tuple('candidates/qwen35_35b_prefill/' + f for f in (
    'partial_tiles.py', 'sum_tiles.py', 'projection_owner.py', 'projection_driver.py'))


class TypedLargeKProjectionDriver(base.TypedProjectionDriver):
    OWNER_TYPE = LargeKProjectionOwner
    WINDOW_REQUEST_TYPE = LargeKWindowRequest

    def __init__(self, owner, matrix_service, memory, job, *, vector, profile,
                 sum_identity, role='synthetic'):
        base.require(type(sum_identity) is int and 0 < sum_identity < 1 << 32 and
                     sum_identity != (job.tag or 1), 'distinct typed sum lease identity required')
        self.sum_identity = sum_identity
        super().__init__(owner, matrix_service, memory, job, vector=vector,
                         role=role, profile=profile, family=FAMILY)

    def _validate_family(self, job, role, profile, family):
        base.require(family == FAMILY and role == 'synthetic',
                     'large-K candidate has no accepted official model profile yet')
        base.require(0 < job.k <= 2048, 'K2048 physical A region exceeded')
        base.require(profile not in (base.GDN_PROJECTION_PROFILE, base.ATTENTION_PROJECTION_PROFILE),
                     'an old K1024 model profile cannot authorize a new model')

    def _make_call(self, typed_job, profile):
        return LargeKReductionRequest(typed_job, typed_job.tag or 1,
            profile.ranges, profile.pair_reverse, sum_identity=self.sum_identity)

    def _make_sum(self, owner):
        return InplaceSumController(owner.tiles,
            bank_tick=lambda **p: owner_tile_edge(owner, **p))

    def _make_coordinator(self):
        return LargeKReductionCoordinator()

    def _binding_identity(self):
        return super()._binding_identity() + (self.sum_identity,)

    def _report(self):
        report = super()._report()
        report.update(scope='K2048_TWO_PARTIAL_DESTRUCTIVE_BF16_SOFTWARE_OWNER',
                      sum_identity=self.sum_identity, resource_ledger=resource_ledger(),
                      official_35b_profile_accepted=False, native_acceptance=False,
                      physical_sum_slot=0, explicit_destructive_lease=True)
        return report
