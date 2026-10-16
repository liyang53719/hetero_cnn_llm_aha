"""Finite metadata-only, conservative scheduling proposal; no arithmetic/RTL."""
from dataclasses import dataclass

OWNERS = ('attention', 'dense', 'norm', 'rope', 'bias', 'ffn')
POOLS = ('vector16', 'sfu16')


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('canonical integer')
    return value


@dataclass(frozen=True)
class Operation:
    pool: str
    opcode: str
    # Acceptance to NEXT acceptance with immediate ACK, not arithmetic latency.
    spacing: int

    def __post_init__(self):
        if type(self.pool) is not str or type(self.opcode) is not str or self.pool not in POOLS or self.opcode not in ('add', 'mul', 'exp', 'div'):
            raise ValueError('operation')
        integer(self.spacing, 2, 1000000)
        if self.pool == 'vector16':
            if self.opcode not in ('add', 'mul') or self.spacing != 2:
                raise ValueError('proposed capture then ACK; no vector SFU')
        elif self.opcode in ('add', 'mul') and self.spacing != 3:
            raise ValueError('original scalar spacing')
        elif self.opcode == 'exp' and self.spacing not in (3, 20):
            raise ValueError('original exp branch spacing')
        elif self.opcode == 'div' and self.spacing < 3:
            raise ValueError('explicit divider observation required')


def fold_plan():
    # Each output keeps all sixteen additions in order, then one scale multiply.
    return (Operation('vector16', 'add', 2),) * 16 + (Operation('vector16', 'mul', 2),)


def softmax_plan(keys, divider_spacing, full_exp):
    integer(keys, 1, 128)
    if type(full_exp) is not tuple or len(full_exp) != keys or any(type(x) is not bool for x in full_exp):
        raise ValueError('explicit per-key exp branch')
    if not any(full_exp):
        raise ValueError('finite nonempty row has a full-path exp(0)')
    # Original subtract, exp, sequential sum; reciprocal then ascending-key norm.
    operations = []
    for full in full_exp:
        operations.extend((Operation('sfu16', 'add', 3), Operation('sfu16', 'exp', 20 if full else 3), Operation('sfu16', 'add', 3)))
    operations.append(Operation('sfu16', 'div', divider_spacing))
    operations.extend((Operation('sfu16', 'mul', 3),) * keys)
    return tuple(operations)


def silu_plan(divider_spacing, full_exp):
    if type(full_exp) is not bool:
        raise ValueError('exp branch')
    return (Operation('sfu16', 'exp', 20 if full_exp else 3), Operation('sfu16', 'add', 3), Operation('sfu16', 'div', divider_spacing), * ((Operation('sfu16', 'mul', 3),) * 3))


@dataclass(frozen=True)
class Offer:
    owner: str
    lanes: tuple  # chain identities; each lane executes its next ordered operation


@dataclass(frozen=True)
class Response:
    packet: int
    owner: str
    pool: str
    opcode: str
    lanes: tuple
    indices: tuple


class Schedule:
    """One global owner and at most one packet: intentionally no pool overlap.

    Chain storage and responses are host metadata. No physical payload buffer or
    bank port is supplied. feed_ready is an explicit external prerequisite only.
    """
    def __init__(self, plans):
        if type(plans) is not dict or not plans or len(plans) > 16:
            raise ValueError('bounded chain inventory')
        for name, plan in plans.items():
            integer(name, 0, 15)
            if type(plan) is not tuple or not plan or len(plan) > 1024 or any(type(op) is not Operation for op in plan):
                raise ValueError('plan')
        self.plans = dict(plans)
        self.indices = {name: 0 for name in plans}
        self.owner = None
        self.pending = None
        self.poison = False
        self.cycle = 0
        self.serial = 0
        self.accepted = 0
        self.retired = 0

    def tick(self, *, acquire=None, release=None, offer=None, ack=None,
             feed_ready=False, abort=False, soft_reset=False):
        for value in (feed_ready, abort, soft_reset):
            if type(value) is not bool:
                raise ValueError('canonical control')
        for owner in (acquire, release):
            if owner is not None and (type(owner) is not str or owner not in OWNERS):
                raise ValueError('owner')
        if ack is not None:
            integer(ack, 0, 1000000000)
        if offer is not None:
            if type(offer) is not Offer or type(offer.owner) is not str or offer.owner not in OWNERS or type(offer.lanes) is not tuple or not 1 <= len(offer.lanes) <= 16:
                raise ValueError('offer')
            if any(type(x) is not int or x not in self.plans for x in offer.lanes) or len(set(offer.lanes)) != len(offer.lanes):
                raise ValueError('lane identities')
        old_owner, old_pending = self.owner, self.pending
        fault = self.poison or abort or soft_reset
        response = old_pending[0] if old_pending and self.cycle >= old_pending[1] else None
        ack_fire = response is not None and ack == response.packet
        release_fire = release is not None and release == old_owner and old_pending is None
        # Release offers take priority; acquisition and ordinary issue cannot
        # use ownership freed on this edge. Fault is sticky through release.
        acquire_fire = acquire is not None and release is None and old_owner is None and old_pending is None and not fault
        offer_fire = False
        if offer is not None and old_owner == offer.owner and old_pending is None and release is None and acquire is None and feed_ready and not fault:
            if any(self.indices[x] >= len(self.plans[x]) for x in offer.lanes):
                raise ValueError('completed dependency chain')
            ops = tuple(self.plans[x][self.indices[x]] for x in offer.lanes)
            if len({(op.pool, op.opcode) for op in ops}) != 1:
                raise ValueError('one shared opcode per lockstep packet')
            self.serial += 1
            result = Response(self.serial, old_owner, ops[0].pool, ops[0].opcode, offer.lanes, tuple(self.indices[x] for x in offer.lanes))
            # Faster lanes hold until the slowest; no independent lane reissue.
            self.pending = (result, self.cycle + max(op.spacing for op in ops) - 1)
            self.accepted += 1
            offer_fire = True
        if ack_fire:
            for name in response.lanes:
                self.indices[name] += 1
            self.pending = None
            self.retired += 1
        if release_fire:
            self.owner = None
        if acquire_fire:
            self.owner = acquire
        self.poison = fault
        self.cycle += 1
        return dict(response=response, ack_fire=ack_fire, publish=ack_fire and not fault,
                    offer_fire=offer_fire, acquire_fire=acquire_fire, release_fire=release_fire,
                    reset_required=fault, debt=int(self.pending is not None))


def workload(tokens):
    integer(tokens, 1, 128)
    pairs = 12 * tokens * (tokens + 1) // 2
    groups = 12 * sum((n + 15) // 16 for n in range(1, tokens + 1))
    vectors = tokens * 8960 // 16
    return dict(tokens=tokens, qk_fold_adds=16*pairs, qk_vector_fold_packets=16*groups,
                qk_vector_scale_packets=groups, softmax_subtractions=pairs,
                softmax_ordered_sum_adds=pairs, softmax_exp=pairs,
                softmax_divisions=12*tokens, softmax_normalizations=pairs,
                legacy_pv_normalization_calls=8*pairs,
                silu_elements=tokens*8960, silu_vectors=vectors,
                silu_lane_operations=6*16*vectors, silu_divisions=16*vectors,
                silu_service_floor_excluding_division=15*vectors,
                silu_all_full_exp_service_excluding_division=32*vectors,
                actual_hardware_cycles=None, accepted_80=False, accepted_90=False,
                bank_feasibility_proven=False, implemented_borrower=False)
