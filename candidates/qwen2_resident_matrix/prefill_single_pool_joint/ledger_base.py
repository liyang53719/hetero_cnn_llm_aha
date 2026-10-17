"""Bounded metadata ledger; consumes external events, never generates operands/time."""
from dataclasses import dataclass
from pathlib import Path
import hashlib, json

INTERFACES = {
    'matrix': 'actual-Chisel',
    'tile_rmw': 'actual-Chisel',
    'scratch_raw': 'source-candidate-not-wired',
    'attention_vector': 'proposed',
    'attention_sfu': 'proposed',
    'silu_loan_legacy_held': 'actual-Chisel',
}
UNRESOLVED = (
    'Q128 Python staging is one head/query; physical register mapping unproved',
    'K256 input packet mapping and bank gather/transpose unproved',
    'V256 packet and 96-word PV panel physical aliases unproved',
    'Attention Add/Mul/Exp/Div borrower mux and flags not wired',
    'Matrix leaf return timing and readiness not supplied by RTL observations',
    'DDR operand producer transactions and complete Host final ACK not connected',
    'Selected production enableBinaryAdd=true private abort drain not modeled; held SiLU loan is false-profile only',
)

class Violation(ValueError): pass

@dataclass(frozen=True)
class PublicationTicket:
    serial: int
    def __bool__(self):
        raise Violation('publication is deferred until the edge closes; call resolve_publication')

@dataclass
class BankDebt:
    kind: str
    banks: tuple
    word: int
    line: int | None
    accepted_edge: int
    committed: bool=False
    returned: bool=False
    returned_edge: int | None=None

class Ledger:
    """Single six-row scratch context; external accepted events are assertions.

    No event here creates operand_ready. can_supply always reports unresolved
    for unproven staging. Credit tests may replay synthetic accepted events,
    but that does not close the supply prerequisite or predict a runnable trace.
    """
    def __init__(self, trace_origin='synthetic_external'):
        if trace_origin not in ('synthetic_external','observed_external_unverified'):
            raise Violation('explicit synthetic or unverified observed provenance only')
        self.trace_origin=trace_origin
        self.edge=-1; self.last_parent_edge=-1; self.parent_ticks=0
        self.reads={}; self.writes={}; self.used_ports=set(); self.reserved={}; self.bank_debts={}
        self.context=None; self.scratch_active=False;self.generation=0; self.written=set()
        self.matrix_group=None; self.matrix_steps={}; self.matrix_results={}
        self.matrix_closed=False;self.matrix_state_edge=-1;self.command_edge=None;self.completion_edge=None
        self.sfu=None; self.alu=None; self.poison=False
        self.sfu_retired_edge=-1;self.alu_retired_edge=-1;self.bank_retired_edge=-1;self.lease_edge=-1
        self.tile_active_edge=-1;self.dense_access_kind=None
        self.accepts_this_edge=set();self.drain_ready_edge=None;self.abort_edge=None
        self.history=[]; self.ids=set();self.publications={};self.aborted_edges=set()

    def _require(self, condition, reason):
        if not condition: raise Violation(reason)

    def _identity(self, request_id):
        self._require(type(request_id) is int and request_id>0 and request_id not in self.ids,
                      'request identity must be positive and never reused')

    def _live(self):
        self._require(self.edge>=0,'explicit edge required')
        self._require(not self.poison,'abort blocks all new accepted work')

    def _record(self, event, **fields):
        self.history.append(dict(edge=self.edge,event=event,**fields))

    def advance(self, edge, abort=False):
        self._require(type(edge) is int and edge==self.edge+1 and type(abort) is bool,'one monotonic edge at a time')
        for decision in self.publications.values():
            if decision['edge']==self.edge and decision['line'] is not None and decision['eligible'] and self.edge not in self.aborted_edges:
                self.written.add(decision['line'])
        self.edge=edge;self.reads={};self.writes={};self.used_ports=set();self.accepts_this_edge=set();self.dense_access_kind=None
        if abort:self.abort()
        committed_ids=set()
        for bank,word,request_id in self.reserved.pop(edge,[]):
            self._require(bank not in self.writes,'reserved writes collide')
            self.writes[bank]=word
            self.bank_debts[request_id].committed=True
            self._record('reserved_RMW_write_commit',bank=bank,request_id=request_id)
            committed_ids.add(request_id);self.tile_active_edge=self.edge
        for request_id in committed_ids:
            del self.bank_debts[request_id];self.bank_retired_edge=self.edge
            self._record('tile_write_retired_without_response_ACK',request_id=request_id,physical_commit=True)

    def _single_fire(self, port):
        self._require(port not in self.used_ports,'single physical port cannot fire twice per edge: '+port)
        self.used_ports.add(port)

    def parent_tick(self):
        self._require(self.edge>=0 and self.last_parent_edge!=self.edge,'parent may advance once per outer edge')
        self.last_parent_edge=self.edge;self.parent_ticks+=1
        self._record('parent_tick')

    def begin_scratch(self, generation, query, kv_head):
        self._live()
        self._require(self.context is None and not self.bank_debts and not self.reads and not self.writes and not self.reserved and self.edge>self.lease_edge and self.edge>self.bank_retired_edge,'scratch begin needs pre-edge released lease and no debts')
        self._require(type(generation) is int and self.generation<generation<2**32 and
                      type(query) is int and 0<=query<128 and type(kv_head) is int and kv_head in (0,1),
                      'bounded scratch context')
        self.generation=generation;self.context=(generation,query,kv_head);self.scratch_active=True;self.written=set();self.lease_edge=self.edge;self.accepts_this_edge.add("scratch_begin")
        self._record('scratch_begin',generation=generation,query=query,kv_head=kv_head)

    def release_scratch(self):
        self._require(self.context is not None and not self.bank_debts and self.edge>self.bank_retired_edge and self.edge>self.lease_edge,'lease release requires pre-edge bank drain')
        self.context=None;self.scratch_active=False;self.written=set();self.lease_edge=self.edge;self._record('scratch_release')

    def _check_ports(self, banks, word, kind):
        own=self.reads if kind=='read' else self.writes
        other=self.writes if kind=='read' else self.reads
        for bank in banks:
            self._require(bank not in own,'same bank port oversubscribed')
            self._require(other.get(bank)!=word,'same-address read/write hazard')

    def raw_accept(self, request_id, line, write, context):
        self._live();self._identity(request_id)
        self._require(type(line) is int and 4096<=line<4192 and type(write) is bool,'scratch raw line/op')
        self._require(context==self.context and context is not None and self.edge>self.lease_edge,'stale context or scratchBegin/request same edge')
        self._require(not self.bank_debts and self.edge>self.bank_retired_edge,'original raw port has one accepted/held debt and no ACK-edge reuse')
        self._require(write or line in self.written,'scratch read before clean write ACK')
        banks=(2*(line%8),2*(line%8)+1);word=line>>3
        self._check_ports(banks,word,'write' if write else 'read')
        ports=self.writes if write else self.reads
        for bank in banks:ports[bank]=word
        self.ids.add(request_id);self.accepts_this_edge.add(request_id)
        self.bank_debts[request_id]=BankDebt('raw_write' if write else 'raw_read',banks,word,line,self.edge,committed=write)
        self._record('raw_accept',request_id=request_id,write=write,banks=banks,word=word)

    def rmw_accept(self, request_id, word):
        self._live();self._identity(request_id)
        self._require(self.context is None and self.edge>self.lease_edge,'raw scratch lease/pre-edge release blocks all Dense/tile ports')
        self._require(type(word) is int and 768<=word<1248,'bounded existing tile storage word')
        self._require(not self.bank_debts and self.edge>self.bank_retired_edge and not self.reads and not self.writes,'tile service requires quiet bank sites and no outstanding debt')
        banks=tuple(range(16));self._check_ports(banks,word,'read')
        reserved=self.reserved.get(self.edge+1,[])
        self._require(not reserved,'RMW next-write reservation conflict')
        for bank in banks:self.reads[bank]=word
        self.reserved[self.edge+1]=[(bank,word,request_id) for bank in banks];self.tile_active_edge=self.edge
        self.ids.add(request_id);self.accepts_this_edge.add(request_id);self.bank_debts[request_id]=BankDebt('tile_rmw',banks,word,None,self.edge)
        self._record('tile_RMW_read_accept',request_id=request_id)

    def external_bank_access(self, bank, word, write):
        """One actual competing Dense-port event, not a supply generator."""
        self._live()
        self._require(self.context is None and self.edge>self.lease_edge,'raw scratch lease/pre-edge release blocks all Dense/tile ports')
        self._require(self.edge!=self.tile_active_edge and not self.bank_debts,'tile accept/commit/outstanding blocks all Dense services')
        self._require(self.dense_access_kind is None or self.dense_access_kind==write,'one Dense access service kind per edge')
        self._require(type(bank) is int and 0<=bank<16 and type(word) is int and 0<=word<1376 and type(write) is bool,'bank event shape')
        self._check_ports((bank,),word,'write' if write else 'read')
        (self.writes if write else self.reads)[bank]=word;self.dense_access_kind=write
        self.accepts_this_edge.add(('bank',bank,write))
        self._record('competing_bank_access',bank=bank,word=word,write=write)

    def bank_return(self, request_id):
        self._require(request_id in self.bank_debts,'foreign bank return')
        debt=self.bank_debts[request_id]
        self._require(not debt.returned and self.edge>debt.accepted_edge,'early or duplicate bank return')
        self._require(debt.kind!='tile_rmw' or debt.committed,'RMW return before reserved write')
        debt.returned=True;debt.returned_edge=self.edge;self._record('bank_return',request_id=request_id)

    def bank_ack(self, request_id, abort=False):
        if abort:self.abort()
        self._require(request_id in self.bank_debts,'foreign bank ACK')
        debt=self.bank_debts[request_id]
        self._require(debt.returned and self.edge>debt.returned_edge,'ACK requires previously visible held response')
        ticket=self._publication(debt.line if debt.kind=='raw_write' else None)
        del self.bank_debts[request_id];self.bank_retired_edge=self.edge;self._record('bank_ACK',request_id=request_id,ticket=ticket.serial)
        return ticket

    def matrix_begin(self, tag):
        self._live();self._identity(tag)
        self._require(self.matrix_group is None and not self.matrix_steps and not self.matrix_results,'group/result lease still held')
        self._require(self.edge>self.matrix_state_edge,'group cannot reaccept on retirement edge')
        self._single_fire('matrix_group')
        self.ids.add(tag);self.accepts_this_edge.add(tag);self.matrix_group=tag;self.matrix_group_edge=self.edge;self.matrix_closed=False;self.command_edge=None;self.completion_edge=None;self._record('matrix_group_accept',tag=tag)

    def _matrix_draining(self):
        # Actual state enters draining after the first abort edge, not
        # combinationally with poison/abort on that same edge.
        return self.abort_edge is not None and self.edge>self.abort_edge

    def matrix_command_accepted(self):
        self._require(self.edge>=0 and not self._matrix_draining(),'command return belongs to pre-existing non-draining group')
        self._require(self.matrix_group is not None and self.command_edge is None and self.edge>self.matrix_group_edge,'leaf command handshake must follow group acceptance')
        self.command_edge=self.edge;self._record('external_all_leaf_command_accept')

    def matrix_completion_accepted(self):
        self._require(self.matrix_group is not None and self.matrix_closed and not self.matrix_steps and not self._matrix_draining() and self.completion_edge is None and self.edge>self.matrix_state_edge,'external leaf completion requires prior ending state')
        self.completion_edge=self.edge;self._record('external_all_leaf_completion_accept')

    def matrix_step_accepted(self, request_id, last=False, emit=False, context=0):
        """Replay an external accepted fire; no assertion of operand feasibility."""
        self._live();self._identity(request_id)
        self._require(self.matrix_group is not None and not self.matrix_closed and self.edge>self.matrix_group_edge,'no pre-existing open Matrix group')
        self._require(self.command_edge is not None and self.edge>self.command_edge,'step requires prior leaf command acceptance')
        self._require(type(context) is int and context==0,'narrow slice uses only existing context0')
        self._require(type(last) is bool and type(emit) is bool,'canonical flags')
        self._require(len(self.matrix_steps)<8,'Matrix metadata credit exhausted')
        self._require(not any(s['last'] for s in self.matrix_steps.values()),'last already accepted')
        self._single_fire('matrix_step')
        self.ids.add(request_id);self.accepts_this_edge.add(request_id);self.matrix_steps[request_id]=dict(last=last,emit=emit,edge=self.edge)
        self._record('external_matrix_step_accept',request_id=request_id,operand_feasibility='unresolved')

    def matrix_return(self, request_id):
        self._require(request_id in self.matrix_steps,'foreign Matrix return')
        self._require(request_id==next(iter(self.matrix_steps)),'source metadata FIFO return order')
        step=self.matrix_steps[request_id]
        self._require(self.edge>step['edge'],'no fabricated zero-edge Matrix latency')
        self._require(self._matrix_draining() or not step['emit'] or len(self.matrix_results)<2,'held result credit exhausted')
        self._single_fire('matrix_return')
        del self.matrix_steps[request_id]
        if step['emit'] and not self._matrix_draining():self.matrix_results[request_id]=self.edge
        if step['last']:self.matrix_closed=True
        if self.poison:self.drain_ready_edge=self.edge+2
        self.matrix_state_edge=self.edge
        self._record('matrix_return',request_id=request_id)

    def matrix_result_ack(self, request_id, abort=False):
        if abort:self.abort()
        self._require(request_id in self.matrix_results,'foreign Matrix result ACK')
        self._require(request_id==next(iter(self.matrix_results)),'result FIFO order')
        self._require(self.edge>self.matrix_results[request_id],'result must be held before ACK')
        self._single_fire('matrix_result_ACK')
        del self.matrix_results[request_id];self.matrix_state_edge=self.edge;self._record('matrix_result_ACK',request_id=request_id)
        return self._publication()

    def matrix_done_ack(self):
        self._require(self.matrix_group is not None and (self.matrix_closed or self.poison) and not self.matrix_steps and not self.matrix_results,'done before last/result retirement')
        self._require(self.edge>self.matrix_state_edge,'done requires pre-edge drained result state')
        self._require(not self.poison or (self.drain_ready_edge is not None and self.edge>=self.drain_ready_edge),'error done must observe draining then finish edges')
        self._require(self.poison or (self.completion_edge is not None and self.edge>self.completion_edge),'successful done requires external leaf completion on prior edge')
        self.matrix_group=None;self.matrix_state_edge=self.edge;self._record('matrix_done_ACK')
        return self._publication()

    def sfu_accept(self, request_id, owner, lane_mask, division=False):
        self._live();self._identity(request_id)
        self._require(owner in ('attention','silu') and type(lane_mask) is int and 0<lane_mask<2**16 and type(division) is bool,'SFU packet shape')
        self._require(self.sfu is None and self.edge>self.sfu_retired_edge,'one SFU pool; no held or same-ACK-edge reuse')
        self.ids.add(request_id);self.accepts_this_edge.add(request_id)
        self.sfu=dict(id=request_id,owner=owner,mask=lane_mask,division=division,
                      reserved=lane_mask if division else 0,pulses=0,pulse_edge=-1,accepted=self.edge,returned=None)
        self._record('sfu_accept',request_id=request_id,loan_profile='legacy_enableBinaryAdd_false' if owner=='silu' and lane_mask==65535 and not division else 'proposed_primitive',interface=(INTERFACES['silu_loan_legacy_held'] if owner=='silu' and lane_mask==65535 and not division else 'proposed'))

    def divider_pulse(self, request_id, lane):
        self._require(self.sfu is not None and self.sfu['id']==request_id and type(lane) is int and 0<=lane<16,'foreign divider pulse')
        p=self.sfu;bit=1<<lane
        self._require(p['division'] and p['reserved']&bit and not p['pulses']&bit,'unreserved or duplicate pulse')
        self._require(self.edge>p['accepted'],'divider cannot return same edge as accept')
        p['pulses']|=bit;p['pulse_edge']=self.edge;self._record('divider_pulse_capture',request_id=request_id,lane=lane)

    def sfu_return(self, request_id):
        self._require(self.sfu is not None and self.sfu['id']==request_id,'foreign SFU return')
        p=self.sfu
        self._require(p['returned'] is None and self.edge>p['accepted'],'early/duplicate SFU return')
        self._require(not p['division'] or (p['pulses']==p['mask'] and self.edge>p['pulse_edge']),'all active pulses must be captured on prior edges')
        p['returned']=self.edge;self._record('sfu_return',request_id=request_id)

    def sfu_ack(self, request_id, abort=False):
        if abort:self.abort()
        self._require(self.sfu is not None and self.sfu['id']==request_id and self.sfu['returned'] is not None and self.edge>self.sfu['returned'],'SFU ACK before held matching response')
        self.sfu=None;self.sfu_retired_edge=self.edge;self._record('sfu_ACK',request_id=request_id)
        return self._publication()

    def alu_accept(self, request_id, opcode, lane_mask):
        self._live();self._identity(request_id)
        self._require(self.alu is None and self.edge>self.alu_retired_edge and opcode in ('add','mul') and type(lane_mask) is int and 0<lane_mask<2**16,'bounded proposed ALU packet')
        self.ids.add(request_id);self.accepts_this_edge.add(request_id);self.alu=dict(id=request_id,accepted=self.edge,returned=None)
        self._record('alu_accept',request_id=request_id,interface=INTERFACES['attention_vector'])

    def alu_return(self, request_id):
        self._require(self.alu is not None and self.alu['id']==request_id and self.alu['returned'] is None and self.edge>self.alu['accepted'],'ALU return requires accepted packet on prior edge')
        self.alu['returned']=self.edge;self._record('alu_return',request_id=request_id)

    def alu_ack(self, request_id, abort=False):
        if abort:self.abort()
        self._require(self.alu is not None and self.alu['id']==request_id and self.alu['returned'] is not None and self.edge>self.alu['returned'],'ALU ACK requires held matching response')
        self.alu=None;self.alu_retired_edge=self.edge;self._record('alu_ACK',request_id=request_id)
        return self._publication()

    def can_supply(self, staging):
        self._record('operand_mapping_unresolved',staging=staging)
        return False

    def _publication(self, line=None):
        serial=len(self.publications)+1
        self.publications[serial]=dict(edge=self.edge,eligible=not self.poison,line=line)
        return PublicationTicket(serial)

    def resolve_publication(self, ticket):
        self._require(type(ticket) is PublicationTicket and ticket.serial in self.publications,'foreign publication ticket')
        decision=self.publications[ticket.serial]
        self._require(self.edge>decision['edge'],'edge not closed: a coincident abort can still arrive')
        return decision['eligible'] and decision['edge'] not in self.aborted_edges

    def abort(self):
        self._require(not self.accepts_this_edge,'abort and new accepted work cannot share an edge; predeclare abort on advance')
        if not self.poison:self.drain_ready_edge=self.edge+2;self.abort_edge=self.edge
        self.poison=True;self.aborted_edges.add(self.edge);self.scratch_active=False;self.written.clear();self._record('abort_seen')

    def report(self):
        pins=Path(__file__).with_name('SOURCE_PINS.json')
        return dict(kind='metadata_event_constraints_only',interfaces=dict(INTERFACES),
                    source_evidence=json.loads(pins.read_text()),
                    source_manifest_sha256=hashlib.sha256(pins.read_bytes()).hexdigest(),
                    event_provenance=self.trace_origin,latency_provenance='external annotations; no measured latency certified',
                    unresolved_prerequisites=list(UNRESOLVED),
                    debts=dict(bank=len(self.bank_debts),matrix_steps=len(self.matrix_steps),
                               matrix_results=len(self.matrix_results),sfu=int(self.sfu is not None),alu=int(self.alu is not None)),
                    poisoned=self.poison,parent_ticks=self.parent_ticks,events=len(self.history),
                    numerical_execution=False,rtl_measured=False,accepted_80=False,accepted_90=False)
