"""Independent stdlib synthetic tests only: no archive, CLI, native or DUT access.

Expected packets/events come from nested test data and this file's own serializer;
never from checker.group_cursor, ActualWords.qk_packet or ActualWords.pv_packet.
"""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('independent_packet_checker', HERE / 'check_packets.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
OWNER = 0x7182
SENTINEL = 0xa5963cc3


def words32(values):
    return b''.join(int(v).to_bytes(4, 'little') for v in values)


def packet16(a, b, byteorder='little'):
    if len(a) != 16 or len(b) != 256:
        raise ValueError('test packet extent')
    return b''.join(int(v).to_bytes(2, byteorder) for v in a + b)


def synthetic(rows):
    # Deliberately unequal head/row/depth fields expose wrong addressing rather
    # than using all-zero, broadcast-identical, or head-identical fixtures.
    q = [[[0x3e00 + (t * 61 + h * 17 + d) % 128 for d in range(128)]
          for h in range(12)] for t in range(rows)]
    kv = [[[[0x4000 + (role * 149 + t * 43 + h * 97 + d) % 4096
              for d in range(128)] for h in range(2)] for t in range(rows)]
          for role in range(2)]
    p = [[[0x3d00 + (h * 31 + t * 7 + k) % 512 if k <= t else None
           for k in range(rows)] for t in range(rows)] for h in range(12)]
    qp = [v << 16 for token in q for head in token for v in head]
    kvp = [v << 16 for role in kv for token in role for head in token for v in head]
    pp = [v << 16 if v is not None else SENTINEL for head in p for row in head for v in row]
    present = [int(v is not None) for head in p for row in head for v in row]
    raw = dict(q=words32(qp), kv=words32(kvp), probability=words32(pp),
               presence=bytes(present), frequency=b''.join((8 if v else 0).to_bytes(2, 'little') for v in present))
    return dict(rows=rows, q=q, kv=kv, p=p, raw=raw)


def expected_stream(data):
    """Separate nested-list producer, never delegates expected scheduling."""
    events, packets, groups = [], [], []
    def add(name, values):
        index = len(events)
        events.append([name, index * 3, values])
        return index
    add('acquire', ['normal', OWNER])
    def group(op, profile, mask, payloads, context):
        number = len(groups)
        tag, ticket, epoch = 0x200 + number, 0x10000 + number, 19
        groups.append((add('accept_group', [op, len(payloads), tag, mask, profile]), context))
        for i, payload in enumerate(payloads):
            final = i == len(payloads) - 1
            emit = profile == 0 or final
            at = add('accept_step', [i, 0, i == 0, final, final, emit, hashlib.sha256(payload).hexdigest()])
            packets.append(dict(event=at, raw=payload, step=i, **context))
            if emit:
                add('retire_result', [0, final, False, ticket, epoch, hashlib.sha256(b'synthetic-result-' + str(at).encode()).hexdigest()])
                if final:
                    add('retire_done', [tag, False, ticket, epoch])
                if profile == 0:
                    add('retire_legacy_reply', [ticket, epoch])
    for t in range(data['rows']):
        for h, qhead in enumerate(data['q'][t]):
            shared_head = h // 6
            keys = data['kv'][0][:t + 1]
            for start in range(0, len(keys), 16):
                chosen = keys[start:start + 16]
                payloads = []
                for depth in range(0, len(qhead), 16):
                    a = qhead[depth:depth + 16]
                    b = [v for key in chosen for v in key[shared_head][depth:depth + 16]]
                    b += [0] * (256 - len(b))
                    payloads.append(packet16(a, b))
                group(0x23, 2, 255, payloads, dict(kind='qk', query=t, head=h, coordinate=start, active=len(chosen)))
            for col in range(0, 128, 16):
                payloads = []
                for k, probability in enumerate(data['p'][h][t][:t + 1]):
                    payloads.append(packet16([probability] + [0] * 15,
                        data['kv'][1][k][shared_head][col:col + 16] + [0] * 240))
                group(0x24, 0, 1, payloads, dict(kind='pv', query=t, head=h, coordinate=col, active=None))
    add('retire_owner_response', [])
    add('release', [])
    return events, packets, groups


def frame(events, *, raw_override=None, count_delta=0, corrupt_footer=False, trailing=b''):
    records = []
    for i, e in enumerate(events):
        raw = raw_override[i] if raw_override and i in raw_override else json.dumps(e, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
        records.append(len(raw).to_bytes(4, 'little') + raw)
    body = b''.join(records)
    digest = hashlib.sha256(body).digest()
    if corrupt_footer:
        digest = bytes([digest[0] ^ 1]) + digest[1:]
    return b'Q2EVT1\r\n' + body + b'\xff' * 4 + (len(events) + count_delta).to_bytes(8, 'little') + digest + trailing


def reader(blob, count, **kwargs):
    return checker.FramedEvents(io.BytesIO(blob), expected_bytes=len(blob),
        expected_sha256=kwargs.pop('expected_sha256', hashlib.sha256(blob).hexdigest()),
        expected_events=count, **kwargs)


class IndependentPackets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m1, cls.m2 = synthetic(1), synthetic(2)
        cls.e1, cls.p1, cls.g1 = expected_stream(cls.m1)
        cls.e2, cls.p2, cls.g2 = expected_stream(cls.m2)

    def audit(self, events, data=None, blob=None, **kw):
        data = data or self.m2
        blob = frame(events) if blob is None else blob
        return checker.audit(reader(blob, len(events), **kw), checker.ActualWords(data['rows'], **data['raw']), OWNER)

    def reject_events(self, mutate, pattern=None):
        events = copy.deepcopy(self.e2)
        mutate(events)
        with self.assertRaisesRegex(ValueError, pattern or '.'):
            self.audit(events)

    def mutate_packet(self, choose, transform):
        p = next(p for p in self.p2 if choose(p))
        def change(events):
            events[p['event']][2][6] = hashlib.sha256(transform(p['raw'])).hexdigest()
        self.reject_events(change, 'operand digest mismatch')

    def test_m1_m2_positive_and_scope(self):
        for data, events, packets, groups in ((self.m1,self.e1,self.p1,self.g1),(self.m2,self.e2,self.p2,self.g2)):
            with self.subTest(rows=data['rows']):
                result = self.audit(events, data)
                self.assertEqual(result['observed']['groups'], len(groups))
                self.assertEqual(result['expected']['packets'], len(packets))
                self.assertEqual(result['expected']['events'], len(events))
                for name in ('ddr_address_handshake_trace_verified','complete_result_tile_verified','numerical_kernel_executed','official_reference_executed','rtl_pass','full29_numeric_pass'):
                    self.assertIs(result['scope'][name], False)

    def test_decoder_positive_budget_and_footer_latch(self):
        blob = frame(self.e2)
        budget = []
        r = reader(blob, len(self.e2), budget_check=lambda: budget.append(1))
        got = []
        while True:
            e = r.next()
            if e is None:
                break
            got.append(e)
        self.assertEqual(got, self.e2)
        self.assertTrue(r.finished)
        self.assertEqual(len(budget), len(self.e2)//1024)
        with self.assertRaisesRegex(ValueError, 'event after footer'):
            r.next()

    def test_wrong_a(self):
        self.mutate_packet(lambda p:p['kind']=='qk', lambda raw: bytes([raw[0]^1])+raw[1:])

    def test_wrong_b(self):
        self.mutate_packet(lambda p:p['kind']=='qk', lambda raw: raw[:32]+bytes([raw[32]^1])+raw[33:])

    def test_qk_inactive_padding(self):
        self.mutate_packet(lambda p:p['kind']=='qk' and p['active']==1, lambda raw:raw[:64]+b'\x01'+raw[65:])

    def test_pv_a_padding(self):
        self.mutate_packet(lambda p:p['kind']=='pv', lambda raw:raw[:2]+b'\x01'+raw[3:])

    def test_pv_b_padding(self):
        self.mutate_packet(lambda p:p['kind']=='pv', lambda raw:raw[:64]+b'\x01'+raw[65:])

    def test_little_endian_packet(self):
        self.mutate_packet(lambda p:p['kind']=='qk', lambda raw:b''.join(raw[i:i+2][::-1] for i in range(0,len(raw),2)))

    def test_head6_gqa_wrong_k_and_v(self):
        for kind in ('qk','pv'):
            with self.subTest(kind=kind):
                p = next(p for p in self.p2 if p['kind']==kind and p['head']==6 and p['query']==1)
                # Keep Q/P unchanged but substitute head0's complete B side.
                wrong = next(x for x in self.p2 if x['kind']==kind and x['head']==0 and x['query']==p['query'] and x['coordinate']==p['coordinate'] and x['step']==p['step'])
                self.mutate_packet(lambda x:x is p, lambda raw:raw[:32]+wrong['raw'][32:])

    def test_wrong_probability_and_v_parent_offset(self):
        p = next(p for p in self.p2 if p['kind']=='pv')
        for raw in (b'\x01\x3f'+p['raw'][2:], p['raw'][:32]+self.p2[0]['raw'][32:64]+p['raw'][64:]):
            with self.subTest(packet=raw[:34]):
                self.mutate_packet(lambda x:x is p, lambda unused:raw)

    def test_step_order(self):
        p, q = self.p2[:2]
        self.reject_events(lambda e:(e.__setitem__(p['event'],copy.deepcopy(e[q['event']])), e.__setitem__(q['event'],copy.deepcopy(self.e2[p['event']]))), 'step control|edge')

    def test_control_metadata_fields(self):
        for at,val in ((0,1),(1,1),(2,False),(3,True),(4,True),(5,True)):
            with self.subTest(field=at):
                self.reject_events(lambda e:e[self.p2[0]['event']][2].__setitem__(at,val), 'step control')

    def test_bool_integer_separation(self):
        self.reject_events(lambda e:e[self.p2[0]['event']][2].__setitem__(0,False), 'step field')
        self.reject_events(lambda e:e[self.p2[0]['event']][2].__setitem__(2,1), 'step field')

    def test_group_metadata(self):
        gi=self.g2[0][0]
        for at,val in ((0,0x24),(1,7),(3,1),(4,0)):
            with self.subTest(field=at):
                self.reject_events(lambda e:e[gi][2].__setitem__(at,val), 'group order')

    def test_result_done_epoch_ticket_metadata(self):
        result = next(i for i,e in enumerate(self.e2) if e[0]=='retire_result')
        done = next(i for i,e in enumerate(self.e2) if e[0]=='retire_done')
        for i,field,value in ((result,0,1),(result,1,False),(result,2,True),(result,3,0),(done,0,999),(done,2,999),(done,3,999)):
            with self.subTest(event=i,field=field):
                self.reject_events(lambda e:e[i][2].__setitem__(field,value))
        later = next(i for i,e in enumerate(self.e2) if e[0]=='retire_result' and i>result)
        self.reject_events(lambda e:e[later][2].__setitem__(4,20), 'epoch changed')
        self.reject_events(lambda e:e[later][2].__setitem__(3,self.e2[result][2][3]), 'monotone.*ticket')

    def test_owner_acquire_terminal_extra_missing(self):
        self.reject_events(lambda e:e[0][2].__setitem__(1,OWNER+1),'owner acquisition')
        self.reject_events(lambda e:e.__delitem__(-2),'retire_owner_response')
        self.reject_events(lambda e:e.append(['abort',len(e)*3,[]]),'extra event')

    def test_invalid_payload_archives(self):
        # These are generated in-memory bytes only, never actual archive files.
        cases=[]
        def change(name,index,width,value):
            raw=dict(self.m2['raw']); b=bytearray(raw[name]);b[index*width:(index+1)*width]=value.to_bytes(width,'little');raw[name]=bytes(b);return raw
        cases.extend((change('q',0,4,0x3f800001),change('kv',0,4,0x7f800000),change('probability',0,4,0xbf000000),change('probability',0,4,0x40000000),change('probability',0,4,0x3f000001),change('probability',1,4,0),change('presence',0,1,0),change('presence',1,1,1),change('frequency',0,2,7),change('frequency',1,2,8)))
        for raw in cases:
            with self.subTest(rawhash=hashlib.sha256(raw['probability']).hexdigest()):
                with self.assertRaises(ValueError):checker.ActualWords(2,**raw)
        for name in self.m2['raw']:
            raw=dict(self.m2['raw']);raw[name]=raw[name][:-1]
            with self.subTest(short=name),self.assertRaises(ValueError):checker.ActualWords(2,**raw)

    def test_frequency_little_endian(self):
        raw=dict(self.m2['raw']);raw['frequency']=b''.join(raw['frequency'][i:i+2][::-1] for i in range(0,len(raw['frequency']),2))
        with self.assertRaisesRegex(ValueError,'frequency'):checker.ActualWords(2,**raw)

    def test_frame_magic_length_canonical_json(self):
        cases=[]
        blob=frame(self.e1)
        cases.append(b'BADMAGIC'+blob[8:])
        cases.append(blob[:8]+(1025).to_bytes(4,'little')+blob[12:])
        cases.append(frame(self.e1,raw_override={0:json.dumps(self.e1[0]).encode()}))
        cases.append(frame(self.e1,raw_override={0:b'not-json'}))
        cases.append(frame(self.e1,raw_override={0:b'["acquire",true,["normal",29058]]'}))
        for blob in cases:
            with self.subTest(prefix=blob[:30]),self.assertRaises(ValueError):self.audit(self.e1,self.m1,blob)

    def test_footer_count_hash_trailing_truncated(self):
        cases=[frame(self.e1,count_delta=1),frame(self.e1,corrupt_footer=True),frame(self.e1,trailing=b'X'),frame(self.e1)[:-1],frame(self.e1)[:-44]]
        for blob in cases:
            with self.subTest(length=len(blob)),self.assertRaises(ValueError):self.audit(self.e1,self.m1,blob)

    def test_full_stream_hash_and_corrupt_payload(self):
        with self.assertRaisesRegex(ValueError,'same-FD stream hash'):
            self.audit(self.e1,self.m1,expected_sha256='0'*64)
        blob=bytearray(frame(self.e1));blob[20]^=1
        with self.assertRaises(ValueError):self.audit(self.e1,self.m1,bytes(blob))

    def test_m17_local_tail_and_head_boundary_only(self):
        data=synthetic(17)
        actual=checker.ActualWords(17,**data['raw'])
        # Local packet tests only: no full M17 event audit or cost extrapolation.
        for head in (5,6):
            q=data['q'][16][head]; kh=head//6
            for first,active in ((0,16),(16,1)):
                for depth in (0,112):
                    b=[w for row in data['kv'][0][first:first+active] for w in row[kh][depth:depth+16]]
                    b += [0]*(256-len(b))
                    expected=packet16(q[depth:depth+16],b)
                    self.assertEqual(actual.qk_packet(16,head,first,active,depth),expected)
            for column,key in ((0,0),(112,16)):
                expected=packet16([data['p'][head][16][key]]+[0]*15,data['kv'][1][key][kh][column:column+16]+[0]*240)
                self.assertEqual(actual.pv_packet(16,head,column,key),expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
