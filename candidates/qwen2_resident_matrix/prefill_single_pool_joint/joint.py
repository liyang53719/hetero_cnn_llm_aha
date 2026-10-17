"""Candidate atomic metadata adapter, not a cycle simulator or operand supplier."""
from copy import deepcopy
from inspect import signature
from ledger_base import Ledger, Violation
from loan import LoanContract, Profile

ALLOWED=frozenset(('begin_scratch','release_scratch','raw_accept','rmw_accept',
    'external_bank_access','bank_return','bank_ack','matrix_begin',
    'matrix_command_accepted','matrix_completion_accepted','matrix_step_accepted',
    'matrix_return','matrix_result_ack','matrix_done_ack'))

class Joint:
    def __init__(self):
        self._ledger=Ledger();self._loan=LoanContract(Profile.PRODUCTION_PRIVATE)

    def snapshot(self):
        return deepcopy(dict(ledger=self._ledger.__dict__,loan=self._loan.__dict__))

    def tick(self, edge, *, abort=False, loan_signals=None, events=()):
        # No caller-owned object is retained; failed validation never commits.
        if type(abort) is not bool or type(events) is not tuple:
            raise Violation('canonical complete edge inputs required')
        if loan_signals is None:loan_signals={}
        if type(loan_signals) is not dict or any(type(k) is not str for k in loan_signals):
            raise Violation('canonical loan signal mapping required')
        if 'abort' in loan_signals or 'edge' in loan_signals:
            raise Violation('one parent edge and abort source only')
        for event in events:
            if type(event) is not tuple or len(event)!=3:
                raise Violation('event is (method, args tuple, kwargs dict)')
            name,args,kwargs=event
            if type(name) is not str or name not in ALLOWED or type(args) is not tuple or type(kwargs) is not dict:
                raise Violation('old SFU/ALU/abort/tick APIs disabled')
            if any(type(k) is not str for k in kwargs) or 'abort' in kwargs:
                raise Violation('abort must be declared for the entire edge')
            bound=signature(getattr(Ledger,name)).bind(None,*args,**kwargs)
            if 'request_id' in bound.arguments:
                identity=bound.arguments['request_id']
                if type(identity) is not int or identity<=0:
                    raise Violation('canonical positive integer request identity required')
            if 'abort' in bound.arguments:
                raise Violation('positional abort also forbidden; declare whole-edge abort')
        ledger,loan=deepcopy((self._ledger,self._loan))
        signals=deepcopy(loan_signals);batch=deepcopy(events)
        result=loan.tick(edge,abort=abort or ledger.poison,**signals)
        # A consumed error poisons publication on this edge; this is a
        # conservative candidate integration rule, not a new measured RTL path.
        ledger.advance(edge,abort=abort or loan.poison)
        ledger.parent_tick()
        results=[]
        for name,args,kwargs in batch:
            results.append(getattr(ledger,name)(*args,**kwargs))
        if result['request_fire']:
            ledger._identity(loan.active.tag)
            ledger.ids.add(loan.active.tag)
        # No legacy SFU state is populated. LoanContract is the sole SFU debt.
        if ledger.sfu is not None or ledger.alu is not None:
            raise Violation('duplicate SFU or unimplemented ALU resource')
        self._ledger,self._loan=ledger,loan
        return deepcopy(dict(loan=result,events=results))

    def resolve_publication(self,ticket):
        return self._ledger.resolve_publication(ticket)

    def can_supply(self,staging):
        return False

    def report(self):
        base=self._ledger.report();base['debts']['sfu']=int(self._loan.active is not None)
        base['interfaces']['integrated_loan_adapter']='candidate'
        base['interfaces']['production_loan_contract']='actual_chisel_contract_external_events_unverified'
        base['unresolved_prerequisites']=[x for x in base['unresolved_prerequisites'] if 'private abort drain not modeled' not in x]
        base['unresolved_prerequisites']+=['Joint integration has no RTL wiring or numerical validation','Event list ordering is candidate, not a proven simultaneous hardware schedule']
        base['loan']=self._loan.report();base['physical_sfu_pools']=1
        base['attention_primitive_enabled']=False;base['proposed_alu_enabled']=False
        return base
