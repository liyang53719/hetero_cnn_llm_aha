"""Two existing clients, one exclusively acquired MatrixService, no new backend."""
from ..attention_packed_owner.client import PackedClient, PackedRequest, PackedConsumerAck
from ..ffn_attention.matrix_service import LegacyMatrixClient, require


class Qk16LegacyPvClient:
    def __init__(self, service, owner):
        self.service, self.owner = service, owner
        self.resource_address = service.resource_address
        self.acquisition = service.counts.get('owner_acquires', 0)
        self.owner_tag, self.epoch = service.owner_tag, service.epoch
        # The existing owner may use its generated profile module's exact ABI
        # types. Reuse its real legacy client, not a shadow Matrix service.
        method = getattr(getattr(owner, '_matrix_step', None), '__func__', None)
        legacy_type = (method.__globals__.get('LegacyMatrixClient', LegacyMatrixClient)
                       if method is not None else LegacyMatrixClient)
        self._legacy_request_type = legacy_type.__init__.__globals__['LegacyRequest']
        self._legacy_result_type = legacy_type.__init__.__globals__['LegacyResult']
        self.packed = PackedClient(service, owner)
        self.legacy = legacy_type(service, owner)
        self.active = self.packed
        self._qk_keys = 0

    @property
    def state(self):
        return ('qk:' if self.active is self.packed else 'pv:') + self.active.state

    @property
    def drained(self):
        return self.packed.drained and self.legacy.drained

    @property
    def held_tag(self):
        return self.packed.held_tag if self.active is self.packed else None

    @property
    def write_debts(self):
        return self.packed.write_debts

    def ports(self):
        ports = self.active.ports()
        ports.update(drained=self.drained, held_tag=self.held_tag,
                     write_debts=self.write_debts,
                     reset_required=ports['reset_required'] or self.packed.poison or self.legacy.poison)
        return ports

    def is_legacy_result(self, result):
        return type(result) is self._legacy_result_type

    def register_write(self, tag):
        require(self.active is self.packed, 'packed write on legacy PV client')
        return self.packed.register_write(tag)

    def commit_write(self, ack):
        require(self.active is self.packed, 'packed write ACK on legacy PV client')
        return self.packed.commit_write(ack)

    def tick(self, *, request=None, result_ready=False, service_result_ready=True,
             service_done_ready=True, abort=False, done_override=None):
        self.service._check_owner(self.owner, 'normal')
        require(self.service.resource_address == self.resource_address and
                self.service.counts.get('owner_acquires', 0) == self.acquisition and
                self.service.owner_tag == self.owner_tag and self.service.epoch == self.epoch,
                'selected scheduling Matrix acquisition/resource changed')
        desired = self.active
        if type(request) is PackedRequest:
            require(request.opcode == 0x23, 'selected production mode packs QK only')
            desired = self.packed
        elif type(request) is PackedConsumerAck:
            desired = self.packed
        elif type(request) is self._legacy_request_type:
            require(request.opcode == 0x24 and request.slice_mask == 1,
                    'selected production mode requires legacy PV mask1')
            desired = self.legacy
        else:
            require(request is None, 'unsupported selected scheduling request')
        if desired is not self.active:
            require(not abort and not self.ports()['reset_required'] and self.drained,
                    'client switch before all previous result/done/reply debts drain')
            self.active = desired
        if type(request) is PackedRequest and request.clear and self.packed.drained:
            count = self.owner.packed_schedule.active_qk_keys
            require(type(count) is int and 1 <= count <= 16, 'selected QK active key count')
            self._qk_keys = count
        prior_state, prior_index = self.packed.state, self.packed.index
        ports = self.active.tick(request=request, result_ready=result_ready,
            service_result_ready=service_result_ready, service_done_ready=service_done_ready,
            abort=abort, done_override=done_override)
        # PackedClient advances index only on the actual accept_step edge.
        # Count accepted useful QK work even if a later result/Scalar edge fails.
        if self.active is self.packed and prior_state == 'issue' and self.packed.index == prior_index + 1:
            require(1 <= self._qk_keys <= 16, 'accepted QK step without bound key count')
            self.owner.useful_macs += self._qk_keys * 16
        return ports
