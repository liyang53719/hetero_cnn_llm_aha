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
    def test_high_snapshot_commit_low_settle_gate_order(self):
        a=self.s.index('high.captured=true;high.edge=edge;high.resetRequired=d.io_resetRequired;high.rtl=last;')
        b=self.s.index('need(!context.gotError()&&!context.gotFinish(),"RUNTIME_STOP_HIGH")')
        c=self.s.index('auto next=p;next.retire(')
        d=self.s.index('ram->retire(fires,edge,next.draining);p=next;')
        e=self.s.index('d.clock=0;ram->drive(d,edge+1);d.eval();ram->priority(d);d.eval();')
        f=self.s.index('need(!d.io_resetRequired,"RESET_REQUIRED_SETTLED")')
        g=self.s.index('if(p.target_edge)')
        self.assertEqual([a,b,c,d,e,f,g],sorted([a,b,c,d,e,f,g]))
        self.assertNotIn('d.clock=1',self.s[e:g])
        self.assertNotIn('RESET_REQUIRED_HIGH',self.s)
    def test_low_gate_still_before_each_sampled_edge(self):
        self.assertLess(self.s.index('need(!d.io_resetRequired,"RESET_REQUIRED_LOW")'), self.s.index('const auto low=last;const auto fires=ram->low'))
    def test_raw_high_is_retained_in_same_record(self):
        self.assertIn('raw_high_before_settle',self.s)
        self.assertIn('high&&high->captured&&high->edge==edge',self.s)
        self.assertIn('<<high->rtl.N;',self.s)
        self.assertIn('HIGH_EVAL_POST_EXTERNAL_INPUTS_PRE_RETIREMENT',self.s)
    def test_settled_software_ledger_has_distinct_label(self):
        self.assertIn('LOW_POST_EDGE_SETTLED_SOFTWARE_RETIRED',self.s)
        self.assertIn('HIGH_EVAL_POST_SOFTWARE_PREVIOUS_EDGE',self.s)
    def test_no_reset_mask_or_internal_write_added(self):
        self.assertNotIn('d.io_resetRequired=',self.s)
        self.assertEqual(self.s.count('d.reset=1;'),1)
        self.assertEqual(self.s.count('d.reset=0;'),1)
        self.assertIn('need(!d.io_resetRequired,"RESET_REQUIRED_SETTLED")',self.s)
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


class Sampling(unittest.TestCase):
    """Finite expression/driver-order mock, never actual Verilated execution."""
    @staticmethod
    def unexpected(valid, state): return bool(valid and state not in (2,3))
    def turn(self, *, valid=True, ready=True, tag=True, error=False, sticky=False,
             retain_after_fire=False, runtime_error=False, contract_error=False):
        events=['low_gate','capture_fires','rise','raw_high_capture']
        if runtime_error: raise ValueError('RUNTIME_STOP_HIGH')
        fired=valid and ready
        state=3 if ready else 2
        status=0
        if fired:
            state=1 if tag and not error else 0
            status=0 if tag and not error else (8 if error else 7)
        raw=self.unexpected(valid,state) or sticky or bool(status)
        if contract_error:raise ValueError('ORIGINAL_TRANSACTION_GATE')
        events.extend(['ledger_retire','clock_low','drive','eval','priority','eval','settled_gate'])
        nextvalid=valid if not fired or retain_after_fire else False
        settled=self.unexpected(nextvalid,state) or sticky or bool(status)
        if settled:raise ValueError('RESET_REQUIRED_SETTLED')
        return dict(raw=raw,settled=settled,acks=int(fired),valid=nextvalid,events=events)
    def test_legal_ack_raw_alarm_settled_clear(self):
        x=self.turn();self.assertTrue(x['raw']);self.assertFalse(x['settled']);self.assertEqual(x['acks'],1)
    def test_stall_preserves_valid_without_false_retirement(self):
        x=self.turn(ready=False);self.assertTrue(x['valid']);self.assertEqual(x['acks'],0);self.assertFalse(x['raw'])
    def test_no_response_does_not_create_ack(self):
        x=self.turn(valid=False);self.assertEqual(x['acks'],0)
    def test_runtime_error_is_never_deferred(self):
        with self.assertRaisesRegex(ValueError,'RUNTIME_STOP_HIGH'):self.turn(runtime_error=True)
    def test_original_transaction_gate_is_not_bypassed(self):
        with self.assertRaisesRegex(ValueError,'ORIGINAL_TRANSACTION_GATE'):self.turn(contract_error=True)
    def test_bad_tag_survives_valid_withdrawal(self):
        with self.assertRaisesRegex(ValueError,'RESET_REQUIRED_SETTLED'):self.turn(tag=False)
    def test_error_response_survives_valid_withdrawal(self):
        with self.assertRaisesRegex(ValueError,'RESET_REQUIRED_SETTLED'):self.turn(error=True)
    def test_sticky_fault_survives_valid_withdrawal(self):
        with self.assertRaisesRegex(ValueError,'RESET_REQUIRED_SETTLED'):self.turn(sticky=True)
    def test_duplicate_response_rejected_before_next_rising(self):
        with self.assertRaisesRegex(ValueError,'RESET_REQUIRED_SETTLED'):self.turn(retain_after_fire=True)
    def test_settle_contains_no_second_rising_edge(self):
        x=self.turn();self.assertEqual(x['events'].count('rise'),1)
        self.assertLess(x['events'].index('clock_low'),x['events'].index('settled_gate'))
    def test_original_raw_gate_counterexample(self):
        self.assertFalse(self.unexpected(True,3));self.assertTrue(self.unexpected(True,1));self.assertFalse(self.unexpected(False,1))
    def test_sampled_response_retires_exactly_once(self):
        m=RamMock();m.descriptor()
        for i in range(10):m.data(i==9)
        m.response();self.assertEqual((m.acks,m.committed),(1,640))
        with self.assertRaises(ValueError):m.response()
        self.assertEqual(m.acks,1)
    def test_raw_alarm_does_not_miss_legal_response(self):
        x=self.turn();self.assertTrue(x['raw']);self.assertEqual(x['acks'],1)
        self.assertEqual(x['events'].count('ledger_retire'),1)
    def test_two_scalar_snapshots_still_bounded(self):
        names=[x['name'] for x in json.loads(source('OBSERVATIONS.json'))]
        worst_two_snapshots=2*sum(len(n)+24 for n in names)
        self.assertLess(worst_two_snapshots+8192,32768)
        self.assertLessEqual(17*32768,1024*1024)
    def test_top_clock_trigger_model(self):
        previous=0;bits=[]
        for clock in [0,1,1,0,0,1]:bits.append(bool(clock and not previous));previous=clock
        self.assertEqual(bits,[False,True,False,False,False,True])


RAM_PROGRESS_PIN='933b2bbefbc4b5bf1cc769d6acfc55e6f54410602e99b7ad5f33442780649d56'

# v4 tests are pure synthetic/source projections, never native/RTL execution.
def nf32(u): return (u>>23)&255 != 255

def nrne(u):
    if not nf32(u): return ((u>>16)&0x8000)|0x7f80|(64 if u&0x7fffff else 0)
    return ((u+0x7fff+((u>>16)&1))>>16)&65535

def scan_numeric(words, *, fire=True, rows=128, saving=False, bf16out=False, materialize=False, source=None):
    if not fire:return {'scanned':0,'bad':0,'first':None,'masked':0,'nonfinite':0,'range':0,'sha':None}
    bad=[];masked=nonfinite=range_bad=0;raw=[]
    for i,u in enumerate(words):
        is_masked=source is None and not saving and i%128>=rows
        width=16 if source=='bf16' else 32
        finite=(u>>7)&255!=255 if width==16 else nf32(u)
        good=finite
        if source is None:good=finite and (saving or not(bf16out or materialize) or u&0x7fffffff<0x7f7f8000)
        elif source=='fp32_convert':good=finite and ((nrne(u)>>7)&255)!=255
        if is_masked:masked+=1;good=True
        if not good:
            bad.append((i,u))
            if finite:range_bad+=1
            else:nonfinite+=1
        raw.append(u.to_bytes(width//8,'little'))
    return {'scanned':len(words),'bad':len(bad),'first':bad[0] if bad else None,'masked':masked,'nonfinite':nonfinite,'range':range_bad,'sha':hashlib.sha256(b''.join(raw)).hexdigest()}

def numeric_candidates(old=0, result_fire=False, result_bad=False, protocol_bad=False, burst_fire=False, source_bad=False, burst_error=False, drain_active=False, tile_fire=False, tile_error=False, pending=True):
    return (int(old==0 and result_fire and result_bad and not protocol_bad),int(old==0 and burst_fire and source_bad and not burst_error),int(old==0 and drain_active and tile_fire and pending and tile_error))

class NumericClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=source('owner_micro.cpp');cls.block=cls.s.split('// NUMERICAL_OBSERVER_V4_BEGIN:',1)[1].split('// NUMERICAL_OBSERVER_V4_END',1)[0]
    def test_exact_4096_consumption_aliases(self):
        pairs=re.findall(r'&r->QwenOwnerKernel__DOT__core__DOT__packedQk__DOT__io_port_result_bits_value_(\d+)_(\d+)_0,',self.block)
        self.assertEqual(pairs,[(str(n),str(c)) for n in range(16) for c in range(256)])
    def test_exact_16_tile_response_values(self):
        xs=re.findall(r'&r->QwenOwnerKernel__DOT__TransposedDenseDownOwner__DOT__banks__DOT__responseValue_(\d+),',self.block)
        self.assertEqual(xs,[str(i) for i in range(16)])
    def test_metadata_complete(self):
        meta=self.block.split('struct NumericMeta {',1)[1].split('};',1)[0]
        declared=re.findall(r'std::uint64_t (\w+)=0;',meta)
        assigns=re.findall(r'm\.(\w+)=r->\w+;',self.block)
        self.assertEqual(len(declared),69);self.assertEqual(declared,assigns);self.assertEqual(len(set(declared)),69)
    def test_uses_selected_response_key(self):
        self.assertIn('banks__DOT__selectedTile_index',self.block);self.assertNotIn('banks__DOT__key_index',self.block)
    def test_no_unnamed_scheduler_boolean(self):self.assertNotIn('unnamedblk',self.block)
    def test_observer_readonly(self):
        self.assertNotRegex(self.block,r'(r->\w+|d\.\w+)\s*=(?!=)')
        for x in ('eval(', 'timeInc(', 'clock=', 'reset=', 'need('):self.assertNotIn(x,self.block)
    def test_low_preedge_exact_once(self):
        self.assertEqual(self.s.count('numerical.before(d,edge);'),1)
        a=self.s.index('const auto fires=ram->low(');b=self.s.index('numerical.before(d,edge);');c=self.s.index('context.timeInc(1);d.clock=1;',a)
        self.assertLess(a,b);self.assertLess(b,c)
    def test_scan_only_real_fire(self):
        self.assertIn('if(s.result_fire){',self.block);self.assertIn('s.result=numeric_result(r,m);',self.block)
        self.assertIn('if(s.burst_fire){',self.block);self.assertIn('if(s.tile_fire){',self.block)
    def test_masks_and_bf16_output_gate_retained(self):
        for x in ('!m.savingPrefix&&(i%128)>=m.job_m','m.job_outputBf16||m.job_materializeDenseOutput','(u&0x7fffffffU)<0x7f7f8000U'):self.assertIn(x,self.block)
    def test_candidates_not_winner(self):
        self.assertIn('candidate_numerical_writes',self.block);self.assertIn('UNKNOWN_NOT_ALL_LATER_WRITES_SAMPLED',self.block)
    def test_auxiliary_error_preserves_original_path(self):
        self.assertIn('catch(...){observer_error=true;current.complete=false;}',self.block)
        self.assertIn('void before(const VQwenOwnerKernel& d,std::uint64_t edge) noexcept',self.block)
        self.assertNotIn('throw',self.block)
    def test_original_ram_progress_unchanged_hash(self):
        a=self.s.index('struct Ram {');b=self.s.index('// NUMERICAL_OBSERVER_V4_BEGIN:')
        self.assertEqual(hashlib.sha256(self.s[a:b].encode()).hexdigest(),RAM_PROGRESS_PIN)
    def test_no_payload_print(self):
        for line in self.block.splitlines():
            if 'std::cout' in line:self.assertNotIn('words[',line)
    def test_first_only_and_transition(self):
        for x in ('!first_result.complete','!first_burst.complete','!first_tile.complete','current.m.status==0&&status==8&&!first_transition.complete'):self.assertIn(x,self.block)
    def test_high_settled_correlation(self):
        self.assertIn('numerical.high(edge,last.dense_status);',self.s);self.assertIn('numerical.settled(edge,last.dense_status);',self.s)
    def test_finite_all(self):self.assertEqual(scan_numeric([0]*4096)['bad'],0)
    def test_first_element_inf(self):
        x=[0]*4096;x[0]=0x7f800000;self.assertEqual(scan_numeric(x)['first'],(0,0x7f800000))
    def test_middle_element_nan(self):
        x=[0]*4096;x[2048]=0x7fc00001;self.assertEqual(scan_numeric(x)['first'],(2048,0x7fc00001))
    def test_last_element_snan(self):
        x=[0]*4096;x[-1]=0x7f800001;self.assertEqual(scan_numeric(x)['first'],(4095,0x7f800001))
    def test_second_physical_half_valid(self):
        x=[0]*4096;x[128]=0x7f800000;self.assertEqual(scan_numeric(x)['bad'],1)
    def test_first_bad_stays_first(self):
        x=[0]*4096;x[5]=0xff800000;x[6]=0x7fc00000;r=scan_numeric(x);self.assertEqual((r['bad'],r['first']),(2,(5,0xff800000)))
    def test_no_fire_nan_not_consumed(self):self.assertEqual(scan_numeric([0x7fc00000]*4096,fire=False)['scanned'],0)
    def test_stalled_repeat_not_double_count(self):
        rs=[scan_numeric([0x7fc00000],fire=f) for f in [False,False,True]];self.assertEqual(sum(r['scanned'] for r in rs),1)
    def test_finite_subnormal_max_and_negative_zero(self):self.assertEqual(scan_numeric([1,0x7fffff,0x7f7fffff,0x80000000,0xff7fffff])['bad'],0)
    def test_mask_m16(self):
        x=[0]*4096;x[16]=0x7f800000;self.assertEqual(scan_numeric(x,rows=16)['bad'],0)
    def test_mask_repeated_upper_half(self):
        x=[0]*4096;x[144]=0x7f800000;self.assertEqual(scan_numeric(x,rows=16)['bad'],0)
    def test_saving_disables_mask(self):
        x=[0]*4096;x[16]=0x7f800000;self.assertEqual(scan_numeric(x,rows=16,saving=True)['bad'],1)
    def test_finite_bf16_range_failure(self):
        r=scan_numeric([0x7f7f8000],bf16out=True);self.assertEqual((r['nonfinite'],r['range']),(0,1))
    def test_negative_bf16_range_failure(self):self.assertEqual(scan_numeric([0xff7f8000],materialize=True)['range'],1)
    def test_bf16_range_boundary_below(self):self.assertEqual(scan_numeric([0x7f7f7fff],materialize=True)['bad'],0)
    def test_saving_disables_output_range(self):self.assertEqual(scan_numeric([0x7f7fffff],saving=True,bf16out=True)['bad'],0)
    def test_burst_native_bf16(self):self.assertEqual(scan_numeric([0x3f80,0x7f80],source='bf16')['first'],(1,0x7f80))
    def test_burst_fp32_conversion_tie_overflow(self):self.assertEqual(scan_numeric([0x7f7f8000],source='fp32_convert')['range'],1)
    def test_burst_prefix_does_not_convert(self):self.assertEqual(scan_numeric([0x7f7f8000],source='prefix')['bad'],0)
    def test_nan_rne_payload_finite_reject(self):self.assertEqual(nrne(0x7f800001),0x7fc0)
    def test_payload_hash_little_endian_complete(self):
        x=[0x12345678,0x80000000];self.assertEqual(scan_numeric(x)['sha'],hashlib.sha256(bytes.fromhex('7856341200000080')).hexdigest())
    def test_protocol_precedes_matrix8(self):self.assertEqual(numeric_candidates(result_fire=True,result_bad=True,protocol_bad=True),(0,0,0))
    def test_error_precedes_burst8(self):self.assertEqual(numeric_candidates(burst_fire=True,source_bad=True,burst_error=True),(0,0,0))
    def test_draining_error_regardless_matching(self):self.assertEqual(numeric_candidates(drain_active=True,tile_fire=True,tile_error=True),(0,0,1))
    def test_inactive_drain_excluded(self):self.assertEqual(numeric_candidates(tile_fire=True,tile_error=True),(0,0,0))
    def test_pending_false_excluded(self):self.assertEqual(numeric_candidates(drain_active=True,tile_fire=True,tile_error=True,pending=False),(0,0,0))
    def test_sticky_old_status(self):self.assertEqual(numeric_candidates(old=7,result_fire=True,result_bad=True,burst_fire=True,source_bad=True,drain_active=True,tile_fire=True,tile_error=True),(0,0,0))
    def test_multiple_candidates_kept(self):self.assertEqual(numeric_candidates(result_fire=True,result_bad=True,burst_fire=True,source_bad=True),(1,1,0))
    def test_coordinate_bijection(self):
        coords={(c%128,32*2+n+16*(c//128)) for n in range(16) for c in range(256)}
        self.assertEqual(coords,{(r,c) for r in range(128) for c in range(64,96)})
    def test_log_record_bounded_conservative(self):
        # 69 metadata fields, full-width decimal upper bound, five bounded snapshots.
        meta={x:(2**64-1) for x in re.findall(r'std::uint64_t (\w+)=0;',self.block.split('struct NumericMeta {',1)[1].split('};',1)[0])}
        scalar={str(i):2**64-1 for i in range(40)}
        snapshot={'metadata':meta,'scalar_padding':scalar,'three_hashes':['f'*64]*3}
        bound=len(json.dumps({'snapshots':[snapshot]*5},separators=(',',':')).encode())+12000
        self.assertLess(bound,32768)

if __name__=='__main__':unittest.main(verbosity=2)
