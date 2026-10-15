"""One existing Banks allocation, guarded edge/actor routes, no payload copy."""
from contextlib import contextmanager
from collections import Counter
from candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseReductionOwner
from candidates.qwen2_attention_resident_candidate.scratch import SharedAScratch

class LoanFault(ValueError):pass

def need(ok,message):
    if not ok:raise LoanFault(message)

class GuardedBanks:
    def __init__(self,banks):
        need(banks.depth==1376 and len(banks.words)==16,'actual A Banks capacity')
        self.__banks=banks;self.depth=banks.depth;self.actor=None;self.in_edge=False
        self.begins=0;self.lease=None;self.clock_only=False;self.counts=Counter()
    @property
    def reads(self):return dict(self.__banks.reads)
    @property
    def writes(self):return dict(self.__banks.writes)
    @property
    def words(self):
        # Read-only host inspection. It cannot mutate bank cells.
        return tuple(tuple(row) for row in self.__banks.words)
    @property
    def payload_identity(self):return id(self.__banks),id(self.__banks.words)
    @contextmanager
    def edge(self):
        need(not self.in_edge,'nested/shared A edge reset forbidden')
        self.in_edge=True;self.begins=0
        try:yield
        finally:self.actor=None;self.in_edge=False;self.clock_only=False
    @contextmanager
    def scope(self,actor):
        need(self.in_edge and self.actor is None and actor in ('owner','cache'),'exclusive bank actor')
        self.actor=actor
        try:yield
        finally:self.actor=None
    def begin_cycle(self):
        need(self.in_edge and self.actor=='owner' and self.begins==0,'one owner-driven begin_cycle per edge')
        self.__banks.begin_cycle();self.begins+=1;self.counts['bank_edges']+=1
    def _access(self):
        need(self.in_edge and self.begins==1,'bank access outside accepted shared edge')
        need(self.actor==('cache' if self.lease is not None else 'owner'),'bank actor conflicts with A lease')
    def read(self,bank,word):
        self._access()
        need(type(bank) is int and 0<=bank<16 and type(word) is int and 0<=word<self.depth,'canonical physical read address')
        need(bank not in self.__banks.reads,'second physical bank read port')
        result=self.__banks.read(bank,word);self.counts['read_accesses']+=1;return result
    def write(self,bank,word,data):
        self._access()
        need(type(bank) is int and 0<=bank<16 and type(word) is int and 0<=word<self.depth and
          type(data) is int and 0<=data<1<<256,'canonical physical write address/data')
        need(bank not in self.__banks.writes,'second physical bank write port')
        self.__banks.write(bank,word,data);self.counts['write_accesses']+=1

class GuardedTiles:
    def __init__(self,tiles,banks):
        object.__setattr__(self,'_delegate',tiles);object.__setattr__(self,'_banks',banks)
        tiles.banks=banks
    def __getattr__(self,name):return getattr(self._delegate,name)
    def __setattr__(self,name,value):setattr(self._delegate,name,value)
    def tick(self,**inputs):
        g=self._banks
        need(g.in_edge and g.actor=='owner','direct TileBank tick outside shared owner edge')
        if g.lease is not None:
            need(g.clock_only and not any(inputs.get(k) for k in ('control','write','read','dense_reads','dense_writes','abort','coordinated_reset')),
                 'tile admission/access during Attention A loan')
        return self._delegate.tick(**inputs)

class LoanDenseOwner(DenseReductionOwner):
    """Existing Dense/window/tile engines with a guarded A-owner boundary."""
    def __init__(self,*args,**kwargs):
        self.bank_guard=None
        super().__init__(*args,**kwargs)
        self.bank_guard=GuardedBanks(self.a_banks)
        self.a_banks=self.bank_guard;self.tiles=GuardedTiles(self.tiles,self.bank_guard)
        self.loan_denials=Counter()
    def ports(self):
        p=super().ports()
        if self.bank_guard is not None and self.bank_guard.lease is not None:
            for k in ('job_ready','window_ready','k_window_ready','drain_ready'):p[k]=False
        return p
    def tick(self,**inputs):
        g=self.bank_guard
        if g is None:return super().tick(**inputs)
        if g.lease is not None and not g.clock_only:
            for k,v in inputs.items():
                if v is not None and v is not False:self.loan_denials[k]+=1
            p=self.ports();p.update(loan_blocked=True,job_fire=False,window_fire=False,k_window_fire=False,
                response_fire=False,window_result_fire=False,read_fire=False,read_command_fire=False,
                group_fire=False,step_fire=False,result_fire=False,a_reads={},a_writes={},b_reads={},b_writes={})
            return p
        if g.in_edge:
            need(g.clock_only and g.lease is not None,'only router clock may reuse current edge')
            need(not inputs,'router shared clock accepts no external business/reset/loan inputs')
            with g.scope('owner'):return super().tick(**dict(inputs,loan_busy=True,loan_request=True,invalidate_lease=True))
        with g.edge(),g.scope('owner'):return super().tick(**inputs)

class BankByteView:
    """32-byte-only view used by the frozen scratch's two-bank packet route."""
    def __init__(self,banks):self.banks=banks
    def __len__(self):return 16*1376*32
    @staticmethod
    def locate(key):
        need(type(key) is slice and key.step is None and type(key.start) is int and type(key.stop) is int and
             0<=key.start<key.stop<=16*1376*32 and key.stop-key.start==32 and key.start%32==0,'one aligned physical bank word')
        return divmod(key.start//32,1376)
    def __getitem__(self,key):return self.banks.read(*self.locate(key)).to_bytes(32,'little')
    def __setitem__(self,key,value):
        need(type(value) is bytes and len(value)==32,'exact physical write word')
        self.banks.write(*self.locate(key),int.from_bytes(value,'little'))

def banked_scratch(banks):
    """Initialize frozen scratch control only; payload is original bank cells."""
    need(type(banks) is GuardedBanks,'actual guarded A allocation required')
    s=SharedAScratch.__new__(SharedAScratch)
    s.storage=BankByteView(banks);s.valid=bytearray(512)
    s.owner=None;s.epoch=0;s.binding=None;s.identity=None
    s.pending=None;s.held=None;s.ready_at=0;s.clock=0
    s.revoked=False;s.counts=Counter();s.accepted_at=0;s.last_serial=0
    return s
