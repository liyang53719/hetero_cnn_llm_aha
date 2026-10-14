"""Additive profile0 PV32 owner with a borrowed, unretired Legacy reply.

QK and softmax retain the original OfficialAttentionOwner AST. PV stages two
accepted V16 reads in bv/packet, forms the existing B256 request, and selects
one16word output beat at a time from the original client's held wide reply.
No32word accumulator or post-retirement MatrixValue cache is allocated.
"""
from dataclasses import dataclass
from collections import Counter
from itertools import chain

from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import LegacyRequest
from candidates.qwen2_resident_matrix.ffn_attention.scalar_recipe import exp_negative
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ArithmeticFault,finite
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import MemoryRequest,PrefixFault,FULL_MASK


def require(ok,message):
    if not ok:raise ValueError(message)


@dataclass(frozen=True)
class RetirePV32Reply:
    destination: int


class OfficialPV32AttentionOwner(OfficialAttentionOwner):
    """Existing services; explicit new PV32 sequencing, no complete-chain claim."""
    def __init__(self,matrix,scalar=None,*,max_tokens=1024):
        super().__init__(matrix,scalar,max_tokens=max_tokens)
        self.pv32_last_pending=False
        self.pv32_borrowed=False
        self.pv32_retire_ready=False
        self.pv32_reply_identity=None
        self.pv32_ack_at_borrow=0
        self.pv32_borrow_hash=None
        self.functional_state_ticks=Counter()

    def _attention(self, j):
        for token in range(j.m):
            for head in range(12):
                kv_head = head // 6
                q = []
                for depth in range(0, 128, 16):
                    q.extend((yield from self._read(j.a + (token * 1536 + head * 128 + depth) * 4)))
                self.row_words = len(q)
                self.peak_row_words = max(self.peak_row_words, len(q))
                scores, maximum = [], 0xff800000
                for key in range(token + 1):
                    for depth in range(0, 128, 16):
                        k = yield from self._read(j.b + (key * 256 + kv_head * 128 + depth) * 4)
                        lanes = yield from self._matrix_step(0x23, q[depth:depth + 16], k,
                            clear=depth == 0, last=depth == 112, steps=8)
                    total = 0
                    for lane in lanes:
                        total = self._op('add', total, lane)
                    dot = self._op('bf', total)
                    score = self._op('bf', self._op('mul', dot, 0x3db504f3))
                    scores.append(score)
                    if self._less(maximum, score):
                        maximum = score
                self.peak_score_words = max(self.peak_score_words, len(scores))
                probabilities, total = [], 0
                for score in scores:
                    difference = self._op('add', score, maximum ^ 0x80000000)
                    probability = exp_negative(self.scalar, self, difference)
                    self.counts['exp_negative_requests'] += 1
                    probabilities.append(probability)
                    total = self._op('add', total, probability)
                self.peak_probability_words = max(self.peak_probability_words, len(probabilities))
                inverse = self._op('div', 0x3f800000, total)
                for col in range(0, 128, 32):
                    for key, probability in enumerate(probabilities):
                        probability = self._op('mul', probability, inverse)
                        bv = yield from self._read(j.c + (key * 256 + kv_head * 128 + col) * 4)
                        packet = yield from self._read(j.c + (key * 256 + kv_head * 128 + col + 16) * 4)
                        yield from self._pv32_step((probability,) + (0,) * 15,bv,packet,
                            clear=key == 0,last=key == token,steps=token + 1,
                            destination=j.dst + (token * 1536 + head * 128 + col) * 4)
                self.row_words = 0

    def _pv32_step(self,a,bv,packet,*,clear,last,steps,destination):
        require(len(a)==len(bv)==len(packet)==16,'PV32 requires existing three16word operand holds')
        a=tuple(self._op('bf',x)>>16 for x in a)
        b=tuple(self._op('bf',x)>>16 for x in chain(bv,packet))+(0,)*224
        result=yield LegacyRequest(0x24,a,b,clear,last,steps)
        if result.value is None or result.error:
            raise PrefixFault('Protocol','PV32 received an invalid Matrix reply')
        # Last replies arrive by an explicit borrow. Other replies arrive only
        # after the original accepted result_fire. Count all selected returned
        # work even if a later selected finite check rejects the packet.
        self.useful_macs+=32
        self.counts['pv32_selected_lane_results']+=32
        if any(not finite(result.value[0][i]) for i in range(32)):
            raise PrefixFault('Numerical','nonfinite selected PV32 Matrix output lane')
        if last:
            require(self.pv32_borrowed and id(result)==self.pv32_reply_identity,'final PV32 reply was not borrowed')
            for half in (0,16):
                # Only this existing acc16-sized beat is materialized. The raw
                # other half remains in the client's real held wide response.
                output=tuple(self._op('bf',result.value[0][half+i]) for i in range(16))
                if any(not finite(v) for v in output):
                    raise PrefixFault('Numerical','nonfinite terminal BF16 PV32 output beat')
                yield from self._write(destination+half*4,output)
                self.counts['pv32_output_half_ack']+=1
            retired=yield RetirePV32Reply(destination)
            require(retired is result,'PV32 retired a different borrowed reply')
            self.pv32_borrowed=self.pv32_retire_ready=False
            self.pv32_reply_identity=self.pv32_borrow_hash=None
            self.counts['pv32_borrow_retired']+=1

    def _advance(self,response=None):
        """Original action dispatcher plus one two-ACK retirement marker."""
        try:
            action=self.program.send(response)
            if isinstance(action,LegacyRequest):
                self.pv32_last_pending=action.opcode==0x24 and action.last
                self.matrix_request,self.state=action,'matrix_issue'
                return
            if isinstance(action,RetirePV32Reply):
                require(self.pv32_borrowed and self.matrix_client is not None and
                    self.matrix_client.ports()['result'] is not None and
                    id(self.matrix_client.ports()['result'])==self.pv32_reply_identity and
                    not self.memory_pending and self.ack_bytes==self.pv32_ack_at_borrow+128,
                    'PV32 reply cannot retire before both output ACKs')
                self.pv32_retire_ready=True;self.state='matrix_wait';return
            address,data=action
            if self.serial==1<<32:
                raise PrefixFault('Protocol','Attention memory request sequence exhausted')
            self.request=MemoryRequest(address,(self.tag_prefix<<32)|self.serial,
                data is not None,data,FULL_MASK if data is not None else 0)
            self.serial+=1;self.state='issue'
        except StopIteration:
            if self.ack_bytes!=self.job.write_bytes:
                self._fault('Protocol','Attention terminal before exact write ACK fence')
            elif self.matrix_client is None or not self.matrix_client.ports()['drained']:
                self._fault('Protocol','Attention terminal before Matrix obligations retire')
            else:self._finish()
        except PrefixFault as error:self._fault(error.status,error.detail)
        except ArithmeticFault as error:self._fault('Numerical',str(error))

    def tick(self,**inputs):
        # Pre-edge mutually exclusive owner/client states, software events only.
        self.functional_state_ticks['owner:'+self.state]+=1
        self.functional_state_ticks['matrix_owned' if self.matrix.owner is self else 'matrix_not_owned']+=1
        self.functional_state_ticks['scalar_owned' if self.scalar.client is self else 'scalar_not_owned']+=1
        if self.matrix_client is not None:
            self.functional_state_ticks['legacy:'+self.matrix_client.state]+=1
        if self.memory_pending and self.request is not None:
            self.functional_state_ticks['write_ack_wait' if self.request.write else 'read_response_wait']+=1
        if self.state=='issue' and not inputs.get('memory_ready',False):
            self.functional_state_ticks['memory_request_backpressure']+=1
        if self.state=='matrix_issue' and not inputs.get('matrix_request_ready',True):
            self.functional_state_ticks['matrix_request_backpressure']+=1
        if self.pv32_borrowed:self.functional_state_ticks['pv32_borrowed_reply_held']+=1
        held=None
        # Peek only a visible, ready-to-borrow FINAL PV reply. Do not fabricate
        # a result_fire: the original reply remains the resource/debt authority.
        borrow=(self.state=='matrix_wait' and self.pv32_last_pending and not self.pv32_borrowed and
            self.matrix_client is not None and inputs.get('matrix_result_ready',True) and
            not any(inputs.get(k,False) for k in ('abort','local_reset','reset')) and not self.poison)
        if borrow:
            candidate=self.matrix_client.ports()['result']
            if candidate is not None and not candidate.error and candidate.value is not None:held=candidate
        if held is not None:inputs=dict(inputs,matrix_result_ready=False)
        edge=super().tick(**inputs)
        edge['pv32_reply_borrow_fire']=False
        if held is not None and self.state=='matrix_wait' and not self.poison:
            require(self.matrix_client.ports()['result'] is held,'PV32 reply changed before borrow')
            self.pv32_borrowed=True;self.pv32_retire_ready=False
            self.pv32_reply_identity=id(held);self.pv32_ack_at_borrow=self.ack_bytes
            self.pv32_borrow_hash=held.value.sha256
            self.counts['pv32_reply_borrows']+=1;edge['pv32_reply_borrow_fire']=True
            self.matrix_request=None
            self._advance(held)
        if self.pv32_borrowed and self.state not in ('drain','locked','finish') and not self.poison:
            require(self.matrix_client is not None and self.matrix_client.ports()['result'] is not None and
                id(self.matrix_client.ports()['result'])==self.pv32_reply_identity and
                self.matrix_client.ports()['result'].value.sha256==self.pv32_borrow_hash,
                'PV32 borrowed reply disappeared before both ACKs and retirement')
        if self.matrix_client is None and self.state in ('idle','locked'):
            self.pv32_borrowed=self.pv32_retire_ready=False
            self.pv32_reply_identity=self.pv32_borrow_hash=None
        return edge

    def report(self):
        report=super().report()
        report.update(candidate='profile0_pv32_held_reply_v1',pv32_borrowed=self.pv32_borrowed,
            pv32_retire_ready=self.pv32_retire_ready,pv32_no_private_wide_result=True,
            explicit_output_hold_words=16,input_staging_words=dict(bv=16,packet=16),
            qk_and_softmax_policy='original OfficialAttentionOwner unchanged AST',
            fullchunk_acceptance=False,functional_state_ticks=dict(self.functional_state_ticks),
            counter_scope='pre-edge software owner/client/ownership states; no hardware timing or utilization')
        return report
