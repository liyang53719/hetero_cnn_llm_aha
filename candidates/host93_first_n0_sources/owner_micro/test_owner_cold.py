#!/usr/bin/env python3
"""Pure synthetic protocol-contract/source tests. Never RTL or C++ execution."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent

def source(name):
    if 'SOURCE_BUFFERS' in globals():
        return SOURCE_BUFFERS[name].decode('utf-8')
    return (ROOT / name).read_text()
A, B, D = 4483535872, 4295032896, 4484322368
TAG, IDENT = 458753, 458754

def need(ok, code):
    if not ok:
        raise ValueError(code)

def fixed(raw, size, digest):
    need(len(raw) == size, 'SIZE')
    need(hashlib.sha256(raw).hexdigest() == digest, 'HASH')
    return raw

class RamMock:
    """Tiny address-only contract mock; no arithmetic/model output synthesis."""
    def __init__(self):
        self.state = 'idle'
        self.tag = self.address = self.index = self.count = 0
        self.returned = self.committed = self.descriptors = self.acks = 0
        self.covered = set()
    def read_request(self, address, tag=TAG << 32):
        need(self.state == 'idle', 'DEBT')
        need(address % 64 == 0, 'ALIGN')
        need(A <= address <= A + 786432 - 64 or B <= address <= B + 4718592 - 64, 'RANGE')
        need(tag >> 32 == TAG, 'TAG')
        self.address, self.tag, self.state = address, tag, 'read'
    def read_response(self, tag=None, last=True, ready=True):
        need(self.state == 'read', 'DEBT')
        need(tag is None or tag == self.tag, 'TAG')
        need(last, 'LAST')
        if ready:
            self.returned += 64
            self.state = 'idle'
    def descriptor(self, address=None, beats=10, tag=TAG << 32, draining=True):
        if address is None:
            address = D + self.descriptors * 6144
        need(self.state == 'idle' and draining, 'PHASE')
        need(self.descriptors < 128, 'EXTRA')
        need(address == D + self.descriptors * 6144 and beats == 10, 'ROW')
        need(address % 64 == 0 and 1 <= beats <= 16 and address % 1024 + 64 * beats <= 1024, 'SPAN')
        need(tag >> 32 == TAG, 'TAG')
        self.address, self.tag, self.count, self.index = address, tag, beats, 0
        self.state = 'data'
        self.descriptors += 1
    def data(self, last, ready=True):
        need(self.state == 'data' and self.index < self.count, 'DEBT')
        need(last == (self.index + 1 == self.count), 'LAST')
        if not ready:
            return
        addresses = set(range(self.address + 64 * self.index, self.address + 64 * (self.index + 1)))
        need(not addresses & self.covered, 'DUPLICATE')
        self.covered |= addresses
        self.index += 1
        self.committed += 64
        if self.index == self.count:
            self.state = 'response'
    def response(self, tag=None, ready=True):
        need(self.state == 'response' and self.index == self.count, 'DEBT')
        need(tag is None or tag == self.tag, 'TAG')
        if ready:
            self.acks += 1
            self.state = 'idle'

def request(i, **changes):
    slot = i % 2
    x = dict(identity=IDENT, ng=(i // 2) * 160, cols=160, slot=slot,
             reuse=i != 0, enabled=1, begin=1024 if slot else 0,
             end=1536 if slot else 1024, block=slot + 1, reverse=1)
    x.update(changes)
    return x

def check_request(i, x):
    need(x == request(i), 'REQUEST_METADATA')

def terminal(i, **changes):
    x = request(i)
    x.pop('reuse')
    x.update(tag=TAG, rows=128, status=0, committed=1, produced=1280, ddr=0, lease=1)
    x.update(changes)
    return x

def check_terminal(i, x, issues, dones):
    need(x == terminal(i), 'TERMINAL_METADATA')
    need(issues == (2560 if i % 2 else 5120) and dones == i + 1, 'PHYSICAL')

class Source(unittest.TestCase):
    def setUp(self):
        self.s = source('owner_micro.cpp')
    def test_primary_exit_survives_report_failure(self):
        def model(verified, reporter):
            primary_exit = 1 if verified else 2
            try:
                reporter()
            except RuntimeError:
                pass
            return primary_exit
        def secondary_failure():
            raise RuntimeError('synthetic report failure')
        self.assertEqual(model(True, secondary_failure), 1)
        self.assertEqual(model(False, secondary_failure), 2)
    def test_primary_exit_source_order(self):
        clause = self.s.split('}catch(const Failure& f){', 1)[1].split('}catch(const std::bad_alloc&)', 1)[0]
        self.assertIn('const int primary_exit=verified?1:2;', clause)
        self.assertIn('catch(...){}', clause)
        self.assertIn('return primary_exit;', clause)
        self.assertNotIn('return 2;', clause)
    def test_exact_port_counts(self):
        p = json.loads(source('PORTS.json'))
        self.assertEqual((len(p), sum(x['direction']=='input' for x in p), sum(x['direction']=='output' for x in p)), (196,150,46))
        self.assertEqual(len({x['name'] for x in p}),196)
        self.assertEqual(sum(x['name'].startswith('io_job_bits_') for x in p),30)
    def test_all_inputs_initialized_only(self):
        p = json.loads(source('PORTS.json'))
        names = set(re.findall(r'd\.(\w+)', source('owner_inputs.inc')))
        self.assertEqual(names, {x['name'] for x in p if x['direction']=='input'})
    def test_exact_observation_triplet(self):
        o = json.loads(source('OBSERVATIONS.json'))
        v = source('owner_readonly.vlt')
        inc = source('owner_observations.inc')
        self.assertEqual(len(o),95)
        self.assertEqual(len({x['name'] for x in o}),95)
        for x in o:
            self.assertTrue(1<=x['width']<=64)
            self.assertIn('public_flat_rd -module "'+x['module']+'" -var "'+x['variable']+'"',v)
            self.assertIn('OBS('+x['name']+', '+x['member']+')',inc)
        self.assertNotIn('public_flat_rw',v)
    def test_only_read_root(self):
        self.assertIn('t.N=r->M;',self.s)
        self.assertNotRegex(self.s,r'r->\w+\s*=(?!=)')
        self.assertNotIn('rootp->',self.s)
    def test_no_internal_force(self):
        for word in ('force(', 'system(', 'popen(', 'execl(', 'dlopen(', 'fork(', 'rand(', 'numpy', 'torch'):
            self.assertNotIn(word,self.s)
    def test_fixed_job_and_workspace(self):
        for value in ('A=4483535872ULL','B=4295032896ULL','D=4484322368ULL','WORKSPACE=4507654464ULL','EXTENT=786432ULL','TAG=458753U','d.io_prefixWorkspace_generation=8','d.io_job_bits_m=128','d.io_job_bits_n=1536','d.io_job_bits_k=1536'):
            self.assertIn(value,self.s)
        self.assertNotIn('io_prefixWorkspace_splitK',self.s)
    def test_fixed_full_inputs(self):
        self.assertIn('load(argv[1],786432,N0_SHA)',self.s)
        self.assertIn('load(argv[2],4718592,WQ_SHA)',self.s)
        self.assertIn('3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f',self.s)
        self.assertIn('ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72',self.s)
    def test_same_buffer_file_guards(self):
        for value in ('O_NOFOLLOW','O_NONBLOCK','S_ISREG','fstatat','stamp(before,after)','stamp(before,named)','hash.update(data.data(),data.size())','return data;'):
            self.assertIn(value,self.s)
    def test_failure_before_software_commit(self):
        a=self.s.index('need(!d.io_resetRequired,"RESET_REQUIRED_HIGH")')
        b=self.s.index('auto next=p;next.retire(')
        c=self.s.index('ram->retire(fires,edge,next.draining);p=next;')
        self.assertLess(a,b);self.assertLess(b,c)
    def test_full_word_coverage_before_mutation(self):
        self.assertLess(self.s.index('for(unsigned j=0;j<64;++j)need(!covered[off+j]'), self.s.index('output[n]=std::uint8_t'))
    def test_global_single_transaction(self):
        self.assertIn('State {Idle,Read,WriteData,WriteResponse}',self.s)
        self.assertIn('!d.io_memory_valid&&!d.io_burst_valid',self.s)
        self.assertIn('MULTIPLE_RAM_RETIREMENTS',self.s)
        self.assertIn('UNEXPECTED_MEMORY_CHANNEL',self.s)
    def test_boundary_not_counter_only(self):
        self.assertIn('requests==4&&terminals==3&&drain_terminals==1&&issues==12801&&groups==4&&dones==3',self.s)
        self.assertIn('WINDOW_PHYSICAL_RETIREMENT',self.s)
        self.assertIn('DRAIN_EXTERNAL_RETIREMENT',self.s)
    def test_budget_and_bounded_json(self):
        self.assertIn('LIMIT=500000, PERIOD=32768',self.s)
        self.assertIn('edge%PERIOD==0',self.s)
        self.assertIn('job_completed\\\":false',self.s)
        self.assertIn('idma_axi_executed\\\":false',self.s)
        self.assertNotIn('std::cout<<argv',self.s)
    def test_no_array_output(self):
        for value in ('write(output', 'fwrite(', 'ofstream', '.f32le', 'words[i]<<', 'output[i]<<'):
            self.assertNotIn(value,self.s)

class Protocol(unittest.TestCase):
    def test_all_three_partial_terminals(self):
        for i in range(3): check_terminal(i,terminal(i),2560 if i%2 else 5120,i+1)
    def test_four_window_requests(self):
        for i in range(4): check_request(i,request(i))
    def test_single_read_with_backpressure(self):
        m=RamMock();m.read_request(A);m.read_response(ready=False);self.assertEqual(m.returned,0);m.read_response();self.assertEqual(m.returned,64)
    def test_weight_last_full_beat(self):
        m=RamMock();m.read_request(B+4718592-64);m.read_response()
    def test_independent_read_write_sequence(self):
        m=RamMock();tag=TAG<<32;m.read_request(A,tag);m.read_response(tag);m.descriptor(tag=tag)
    def test_full_first_window_retirement(self):
        m=RamMock()
        for row in range(128):
            m.descriptor()
            for j in range(10):m.data(j==9)
            m.response()
        self.assertEqual((m.descriptors,m.acks,m.committed,len(m.covered)),(128,128,81920,81920))
    def test_response_hold(self):
        m=RamMock();m.descriptor()
        for i in range(10):m.data(i==9)
        m.response(ready=False);self.assertEqual(m.acks,0);m.response();self.assertEqual(m.acks,1)
    def test_data_hold(self):
        m=RamMock();m.descriptor();m.data(False,ready=False);self.assertEqual(m.committed,0)
    def test_full_hash_same_object(self):
        raw=bytes(range(64));self.assertIs(fixed(raw,64,hashlib.sha256(raw).hexdigest()),raw)

# Every mutation is a separate ordinary/-O test; no language assert guards.
for field in terminal(0):
    def make(field):
        def test(self):
            x=terminal(0);x[field]+=1
            with self.assertRaises(ValueError):check_terminal(0,x,5120,1)
        return test
    setattr(Protocol,'test_bad_terminal_'+field,make(field))
for field in request(3):
    def make(field):
        def test(self):
            x=request(3);x[field]=int(x[field])+1
            with self.assertRaises(ValueError):check_request(3,x)
        return test
    setattr(Protocol,'test_bad_request_'+field,make(field))

BAD_CASES={
 'read_unaligned':lambda m:m.read_request(A+1),
 'read_weight_reservation_tail':lambda m:m.read_request(B+4718592),
 'read_qraw':lambda m:m.read_request(D),
 'read_workspace':lambda m:m.read_request(4507654464),
 'read_wrong_tag':lambda m:m.read_request(A,1),
 'read_duplicate_descriptor':lambda m:(m.read_request(A),m.read_request(A)),
 'unsolicited_read_response':lambda m:m.read_response(),
 'read_wrong_response_tag':lambda m:(m.read_request(A),m.read_response(0)),
 'read_missing_last':lambda m:(m.read_request(A),m.read_response(last=False)),
 'write_wrong_row':lambda m:m.descriptor(D+64),
 'write_wrong_beats':lambda m:m.descriptor(beats=11),
 'write_wrong_tag':lambda m:m.descriptor(tag=1),
 'write_outside_drain':lambda m:m.descriptor(draining=False),
 'write_during_read':lambda m:(m.read_request(A),m.descriptor()),
 'read_during_write':lambda m:(m.descriptor(),m.read_request(A)),
 'unsolicited_write_data':lambda m:m.data(False),
 'early_last':lambda m:(m.descriptor(),m.data(True)),
 'unsolicited_write_response':lambda m:m.response(),
 'early_write_response':lambda m:(m.descriptor(),m.response()),
 'short_partial_issues':lambda m:check_terminal(0,terminal(0),5119,1),
 'missing_matrix_done':lambda m:check_terminal(0,terminal(0),5120,0),
 'wrong_input_size':lambda m:fixed(b'ab',3,hashlib.sha256(b'ab').hexdigest()),
 'wrong_input_hash':lambda m:fixed(b'ab',2,hashlib.sha256(b'ac').hexdigest()),
}
for name,call in BAD_CASES.items():
    def make(call):
        def test(self):
            with self.assertRaises(ValueError):call(RamMock())
        return test
    setattr(Protocol,'test_'+name,make(call))

if __name__=='__main__':unittest.main(verbosity=2)
