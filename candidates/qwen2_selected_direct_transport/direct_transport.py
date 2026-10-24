"""Selected QK16 model: reuse the original uncached public Attention driver.

Installed only in the fresh resident runtime overlay. This metadata binding
owns no payload/cache/banks/service and does not admit a full numerical run.
"""
from dataclasses import asdict
from .entry import install as install_schedule
from .routing import Qk16LegacyPvClient
from ..ffn_public.fullgraph_execution import execute_attention_owner


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dense_retired(o):
    # Exact original ParentLoan.debts owner fields, without allocating a loan.
    return (o.state == 'idle' and o.error is None and o.read_active is None and
        o.a_hold is None and o.a_rmw_pending is None and o.pending is None and not o.fifo and
        not o.seed_outstanding and o.seed_state == 'idle' and
        not (o.group_started and not o.group_done) and o.write_state == 'idle' and
        o.window_request is None and o.window_result is None and
        o.drain_request is None and o.drain_result is None and o.drain_expected is None and
        o.lease is None and not o.drain_poison and o.tiles.idle and
        not o.tiles.leased and not o.tiles.poison and o.ports()['response'] is None and
        not o.ports()['reset_required'])


def no_scratch(o):
    return (o.scratch_request is None and o.scratch_pending is False and
        o.scratch_leased is False and o.scratch_last is None and o.scratch_write_tag is None and
        o.packed_memory_tag is None)


class DirectBinding:
    """Identity/debt guard around existing direct memory and owner handshakes."""
    def __init__(self, x, physical, job, schedule):
        self.execution, self.physical, self.job, self.schedule = x, physical, job, schedule
        self.identities = self.current_identities(x)
        self.regions = self.region_identity(physical)
        self.resource_address = x.matrix_service.resource_address
        self.client = None

    @staticmethod
    def region_identity(physical):
        return tuple((name, id(region), id(region.get('data')), id(region.get('provider')),
                      region.get('base'), region.get('extent'), region.get('reserved'), region.get('dtype'),
                      len(region['data']) if region.get('data') is not None else None,
                      region.get('readonly'), region.get('virtual'))
                     for name, region in physical.regions.items())

    @staticmethod
    def current_identities(x):
        return (x.owner, x.owner.a_banks, x.owner.b_banks, x.owner.tiles.banks,
                x.attention_owner, x.matrix_service, x.prefix_owner, x.prefix_owner.scalar,
                x.frontend.memory, x.frontend.port.memory,
                getattr(x.frontend.memory, 'physical_memory', None))

    def check(self, x):
        require(x is self.execution and getattr(x, 'selected_direct_binding', None) is self,
                'selected direct binding replaced')
        require(all(a is b for a, b in zip(self.identities, self.current_identities(x))) and
                x.matrix_service.resource_address == self.resource_address,
                'selected direct owner/bank/service/physical identity changed')
        require(x.frontend.memory is x.frontend.port.memory and
                x.frontend.memory.physical_memory is self.physical and
                x.bank_ids == tuple(id(value) for value in self.identities[:4]),
                'selected direct original physical map/banks required')
        require(self.regions == self.region_identity(self.physical),
                'selected direct physical allocation replaced')
        require(x.attention_transport is None and x.attention_transport_binding is None and
                x._checked_attention_transport() is None,
                'selected direct route cannot attach raw KV cache/transport')
        owner = x.attention_owner
        require(owner.packed_schedule is self.schedule and no_scratch(owner),
                'selected direct schedule/scratch debt changed')
        require(owner.matrix is x.matrix_service and owner.scalar is x.prefix_owner.scalar,
                'selected direct original shared services required')
        client = owner.matrix_client
        require(client is not None or (owner.state == 'idle' and x.matrix_service.owner is None
                                      and owner.scalar.client is None),
                'selected direct active Matrix client detached')
        if client is not None:
            require(type(client) is Qk16LegacyPvClient and client.owner is owner and
                    client.service is x.matrix_service and client.packed.owner is owner and
                    client.legacy.owner is owner and client.packed.service is x.matrix_service and
                    client.legacy.service is x.matrix_service,
                    'selected direct original shared clients required')
            require(self.client is None or client is self.client,
                    'selected direct Matrix client replaced')
            self.client = client
        require(dense_retired(x.owner) and x.prefix_owner.state == 'idle' and
                not x.prefix_owner.ports()['reset_required'],
                'selected direct Attention conflicts with Dense/prefix obligations')


def bind(x, physical, job):
    require(getattr(x, 'selected_direct_binding', None) is None,
            'selected direct route is single-bound')
    require(x.attention_transport is None and x.attention_transport_binding is None and
            x._checked_attention_transport() is None,
            'selected direct route cannot bind an existing raw KV transport')
    ports, owner = x.ports(), x.attention_owner
    require(ports['ordinary_request'] is job and ports['group_request'] is None and
            job.kind == 'Attention', 'selected direct requires the dispatched public Attention job')
    require(dense_retired(x.owner) and x.prefix_owner.state == 'idle' and
            not x.prefix_owner.ports()['reset_required'] and no_scratch(owner),
            'selected direct binding requires fully retired original owners')
    require(physical.pending is None and x.frontend.memory is x.frontend.port.memory and
            x.frontend.memory.physical_memory is physical,
            'selected direct binding requires retired identical physical memory')
    require(owner.matrix is x.matrix_service and owner.scalar is x.prefix_owner.scalar and
            not x.matrix_service.reset_required and
            x.bank_ids == (id(x.owner), id(x.owner.a_banks), id(x.owner.b_banks), id(x.owner.tiles.banks)),
            'selected direct binding replaced banks or shared services')
    if hasattr(x, 'policy_jobs'):
        require(x.policy_jobs.get(job.tag & 0xffff) == asdict(job),
                'selected direct binding precedes original official role validation')
    require(type(job.m) is int and 1 <= job.m <= 128, 'selected direct M1..128 required')
    owner._validate(job)
    schedule = install_schedule(owner)
    binding = DirectBinding(x, physical, job, schedule)
    x.selected_direct_binding = binding
    binding.check(x)
    return binding


def run(x, physical, job, *, final_ack_stall=5):
    require(type(final_ack_stall) is int and final_ack_stall > 0,
            'Attention final ACK must have a positive bounded stall')
    binding = bind(x, physical, job)
    report = execute_attention_owner(x, physical, job, final_ack_stall=final_ack_stall,
                                     enable_raw_kv=False)
    binding.check(x)
    require(physical.pending is None and x.matrix_service.owner is None,
            'selected direct terminal before physical/service retirement')
    return report
