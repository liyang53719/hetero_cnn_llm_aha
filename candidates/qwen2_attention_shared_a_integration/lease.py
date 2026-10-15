"""Actual producer completion and shared-owner quiescence admission gates."""
from collections import Counter
import hashlib
from candidates.qwen2_attention_resident_candidate.scratch import ReadonlyKVIdentity
from .banks import LoanDenseOwner,BankByteView,need

class SyntheticKvPublication:
    """Seal real KvAppend owner/Bus ACKs; explicitly not public21 completion."""
    def __init__(self,prefix,harness,job,result):
        self.prefix,self.harness,self.job,self.result=prefix,harness,job,result
        self._validate_completion()
        need(harness.bus.pending is None,'producer seal before DDR drain')
        self.digest=hashlib.sha256(harness.bus.raw(job.dst)).hexdigest()
        self.generation=(job.tag,prefix.counts['owner_results'])
    def _validate_completion(self):
        p,h,j,r=self.prefix,self.harness,self.job,self.result
        need(h.owner is p and p.job is j and j.kind=='KvAppend' and p.state=='idle' and not p.poison and
          p.counts['owner_results']==1 and
          r.status is None and r.tag==j.tag and r.write_bytes==p.ack_bytes==j.write_bytes,
          'real accepted synthetic KvAppend terminal/ACK required')
        extent=set(range(j.dst,j.dst+j.write_bytes,64))
        need(h.bus.outputs[j.dst]==extent and extent<=h.bus.acked and extent<=h.bus.readable,
             'KvAppend exact ACK/publication required')
    def validate(self,attention_job):
        self._validate_completion();j=self.job
        need((attention_job.b,attention_job.c,attention_job.m)==(j.dst,j.dst+j.write_bytes//2,j.m),
             'Attention must consume this same published KV parent/views')
        need(hashlib.sha256(self.harness.bus.raw(j.dst)).hexdigest()==self.digest,'published KV mutation')
        need(self.generation==(j.tag,self.prefix.counts['owner_results']),'KvAppend generation changed')
        return ReadonlyKVIdentity(id(self.harness.bus.outputs[j.dst]),id(self.harness.bus.outputs[j.dst]),j.tag,j.tag)
    def pending(self):return self.harness.bus.pending

class PublicKvPublication:
    """Read live original checkpoint state; never accept a caller success bool.

    This route is source-defined but not exercised by the synthetic small gate.
    It requires the original physical parent allocation and accepted pc9.
    """
    def __init__(self,x,physical,job):
        from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import PublicExecution
        from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory
        need(isinstance(x,PublicExecution) and type(physical) is PhysicalMemory,'actual public execution and physical memory required')
        self.x,self.physical,self.job=x,physical,job
        need(physical.pending is None,'public prefix DDR must drain before producer seal')
        need(getattr(x.frontend.memory,'physical_memory',None) is physical and physical.fixture is x.policy_fixture,
             'same live frontend/fixture/physical identity')
        need(x.ports()['ordinary_request'] is job and job.kind=='Attention' and (job.tag&0xffff)==12,
             'actual fused pc12 owner request')
        need(len(x.host.program)==21 and x.host.completed==x.host.jobs==10 and
          [c['pc'] for c in x.completions]==list(range(10)) and
          x.counts['completion_fire']==x.counts['owner_result_fire']==10 and
          x.host.status is None and x.launch_result is None,'ten actual public prefix completions required')
        need(x.completions[-1]['pc']==9 and x.completions[-1]['status'] is None,'accepted successful pc9')
        self.epoch=physical.fixture.config.epoch
        _,r=physical.region(job.b,job.m*1024);_,v=physical.region(job.c,job.m*1024)
        need(r is v and r is physical.regions['kv'] and r['base']==job.b and job.c==job.b+job.m*1024 and
          r['extent']==job.m*2048 and r['dtype']==7,'same FP32 KV parent and exact two views')
        self.region=r;self.digest=physical.published_hashes.get('kv');self.validate(job)
    def validate(self,job):
        x,p,r=self.x,self.physical,self.region
        need(job is self.job and p.fixture.config.epoch==self.epoch and
          r['terminal'] and r['published'] and self.digest is not None and p.published_hashes.get('kv')==self.digest,
          'KV publication/generation changed')
        expected=set(range(r['base'],r['base']+r['extent'],64))
        need(r['acked']==r['written']==expected and
          (r['base'],r['base']+r['extent']) in x.host.published and
          hashlib.sha256(r['data'][64:-64]).hexdigest()==self.digest,'exact live KV ACK and immutable published data')
        return ReadonlyKVIdentity(id(r),id(r),(self.epoch<<32)|9,(self.epoch<<32)|9)
    def pending(self):return self.physical.pending

class SharedALoanRouter:
    def __init__(self,dense,prefix,attention,publication):
        need(type(dense) is LoanDenseOwner and dense.tiles.banks is dense.a_banks,'one actual Dense/Tile A bank allocation')
        need(type(attention.scratch.storage) is BankByteView and attention.scratch.storage.banks is dense.a_banks,
             'Attention cache must view those exact banks')
        need(prefix.scalar is attention.scalar,'same actual prefix/Attention scalar service')
        need(type(publication) in (SyntheticKvPublication,PublicKvPublication),'checked producer publication authority')
        self.dense,self.prefix,self.attention,self.publication=dense,prefix,attention,publication
        self.guard=dense.a_banks;self.active=False;self.job=None;self.counts=Counter()
        self.bank_identity=self.guard.payload_identity
    def quiescent(self):
        d,p,a=self.dense,self.prefix,self.attention
        need(d.state=='idle' and d.lease is None and d.tiles.idle and not d.tiles.leased and not d.tiles.poison and
          d.ports()['response'] is None and d.pending is None and d.read_active is None and d.a_hold is None and d.a_rmw_pending is None and d.accepted_write is None and
          not d.fifo and d.final_value is None and d.write_state=='idle' and not d.seed_outstanding,
          'Dense/window/tile/DMA/seed obligations are not drained')
        need(p.state=='idle' and not p.poison and p.ports()['response'] is None and
          a.state=='idle' and not a.poison and a.matrix.owner is None and not a.matrix.reset_required and
          a.scalar.client is None and not a.memory_pending and not a.abort_pending and
          a.matrix_client is None and a.matrix_request is None and a.matrix.lib.matrix_state()==0 and
          self.publication.pending() is None,'prefix/DDR/Matrix/Scalar not drained')
        need(a.scratch.owner is None and a.scratch.pending is None and not a.local_pending,'local cache not drained')
    def arm(self,job):
        need(not self.active and self.guard.lease is None,'one A loan at a time');self.quiescent()
        identity=self.publication.validate(job)
        need(self.attention.kv_identity==identity,'cache identity differs from actual producer publication')
        self.guard.lease=self;self.active=True;self.job=job;self.counts['loans']+=1
    def _assert_exclusive(self):
        d=self.dense
        need(self.guard.lease is self and self.guard.payload_identity==self.bank_identity and d.tiles.banks is d.a_banks and
          d.state=='idle' and d.lease is None and d.tiles.idle and not d.tiles.leased and not d.tiles.poison and
          d.pending is None and d.read_active is None and d.a_hold is None and d.a_rmw_pending is None and d.accepted_write is None and not d.fifo and d.final_value is None,
          'A lease escaped or concurrent owner work became live')
    def tick(self,**inputs):
        if 'job' in inputs:
            need(not self.active,'duplicate Attention launch');self.arm(inputs['job'])
        need(self.active,'Attention edge without checked A loan');self._assert_exclusive()
        # Publication is immutable during the lease. Failure revokes supply and
        # lets the original owner drain its accepted obligations, not release A.
        try:self.publication.validate(self.job)
        except ValueError:
            self.attention.scratch.revoke()
        with self.guard.edge():
            self.guard.clock_only=True
            self.dense.tick()
            self.guard.clock_only=False
            try:
                with self.guard.scope('cache'):edge=self.attention.tick(**inputs)
            except (ValueError,AssertionError):
                # A bank-port/model fault never restores admission. Preserve
                # accepted debts, enter original poison/drain, and propagate
                # the exception so the caller cannot count this as success.
                self.attention._fault('Protocol','shared A route fault requires drain')
                self.counts['route_faults']+=1
                raise
            need(self.guard.begins==1,'exactly one physical bank edge required')
            self.counts['edges']+=1
        self._assert_exclusive()
        if edge['response_fire']:
            a=self.attention
            need(a.state in ('idle','locked') and a.matrix.owner is None and a.scalar.client is None and
              a.matrix_client is None and not a.memory_pending and a.scratch.owner is None and
              a.scratch.pending is None and not a.local_pending and self.publication.pending() is None,
              'A release before local/DDR/Matrix/Scalar drain and terminal consume')
            self.guard.lease=None;self.active=False;self.counts['releases']+=1
        return edge
    def ports(self):return self.attention.ports()
    def report(self):
        return dict(active=self.active,shared_payload_identity_unchanged=self.guard.payload_identity==self.bank_identity,
          same_dense_tile_attention_banks=self.dense.tiles.banks is self.dense.a_banks is self.attention.scratch.storage.banks,
          bank_events=dict(self.guard.counts),loan_events=dict(self.counts),blocked_offers=dict(self.dense.loan_denials),
          payload_bytearray_allocated=False,production_public_checkpoint_executed=False,
          authority='REAL_SYNTHETIC_KVAPPEND' if type(self.publication) is SyntheticKvPublication else 'PUBLIC_PREFIX_STATE_VALIDATED_ONLY',
          rtl_executed=False,model_edges_are_hardware_cycles=False)
