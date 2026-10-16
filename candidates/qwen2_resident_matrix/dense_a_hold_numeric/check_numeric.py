"""Opt-in bounded C++ host Matrix execution for the frozen A-hold candidate.

No compiler or arithmetic library is invoked on import. Run with a verified
existing compile receipt. Every output comes from accepted bank-fed td_step
packets; all 4096 cells execute. Saved output is comparison-only after both
owners have retired their actual DMA/result/seed/done obligations.
"""
from collections import deque
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

from ..dense_a_hold_candidate import model
from ..ffn_attention.matrix_service import configure_library

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASES = ((16,32,32,True),(16,32,96,False),(16,32,256,True),
         (128,32,160,True),(16,256,32,True))


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sources():
    pins = json.loads((HERE/'source_pins.json').read_text())
    for name,digest in pins['sources'].items():
        require(sha((ROOT/name).read_bytes()) == digest,'source drift: '+name)
    return pins


def snapshot():
    result = dict(sources()['sources'])
    for name in ('check_numeric.py','source_pins.json'):
        path = HERE/name
        result[str(path.relative_to(ROOT))] = sha(path.read_bytes())
    return result


def verify_library(receipt):
    pins = sources()
    raw = Path(receipt).read_bytes()
    require(sha(raw) == pins['compile_receipt_sha256'],'compile receipt drift')
    record = json.loads(raw)
    require(record['status'] == 'PASS' and record['returncode'] == 0,
            'successful existing compilation required')
    require(record['argv'][1:6] == ['-shared','-fPIC','-O2','-ffp-contract=off','-fno-fast-math'],
            'original strict FP32 compilation flags required')
    require(record['source_sha256'] == pins['compiled_sources'],'compiled closure mismatch')
    require(all(pins['sources'].get(name)==digest for name,digest in record['source_sha256'].items()),
            'compiled sources differ from the checked current closure')
    library = Path(record['library'])
    binary = library.read_bytes()
    require(binary[:4] == b'\x7fELF' and sha(binary) == record['library_sha256'] == pins['library_sha256'],
            'existing ELF identity mismatch')
    return record, library


def synthetic_bits(kind,index):
    # Finite BF16 input, both signs. FP32 ingress below additionally exercises
    # BF16 ties and just-below/above-tie RNE before the unchanged Matrix FMA.
    return ((index*13+(29 if kind == 'b' else 7)) & 0x807f) | 0x3f00


class NativeDriver:
    def __init__(self,lib,job,enabled):
        self.lib,self.job = lib,job
        self.owner = model.DenseAHoldModel(model.PrefixWorkspace(0x10000000,8*16384,7,128),
                                           enable_a_hold=enabled)
        require(lib.td_reset() == 0,'FP32/RNE reset failed')
        require(lib.matrix_guard_enable() == 0,'guard enable failed')
        require(lib.matrix_acquire(1,job.tag) == 0,'Dense ownership failed')
        self.address = int(lib.matrix_accumulator_address())
        require(lib.matrix_accumulator_bytes() == 81920,'five-context physical allocation changed')
        self.cycle = 0
        self.rng = random.Random(19)
        self.read = self.write = self.ack = self.seed_ack = None
        self.results = deque()
        self.ticket = None
        self.memory = {}
        self.a,self.b,self.output = (C.c_uint16*16)(),(C.c_uint16*256)(),(C.c_uint32*4096)()
        self.packet_digest,self.result_digest,self.command_digest = hashlib.sha256(),hashlib.sha256(),hashlib.sha256()
        self.steps = self.groups = self.result_count = self.seed_count = self.a_gathers = 0
        self.max_results = self.max_reserved = 0
        self.terminal = None

    def read_beat(self,command):
        if command.kind == 'prefix':
            require(command.address in self.memory,'read of uncommitted prefix')
            words = self.memory[command.address]
        else:
            j = self.job
            native = j.activation_bf16 if command.kind == 'a' else j.weight_bf16
            base = j.a if command.kind == 'a' else j.b
            start = (command.address-base)//(2 if native else 4)
            require(command.address >= base and command.address % 64 == 0,'address decoder')
            words = tuple(synthetic_bits(command.kind,start+i) for i in range(32 if native else 16))
            if not native:
                tail = (0x7fff,0x8000,0x8001,0)
                words = tuple((x<<16)|tail[(start+i)%4] for i,x in enumerate(words))
        return model.ReadBeat(command.tag,words,True)

    def tick(self, *, offer=False):
        self.cycle += 1
        p = self.owner.ports()
        terminal = p['step'] is not None and p['step'].last
        opts = dict(job=self.job if offer else None,
                    read_command_ready=self.cycle%7 != 0,
                    step_ready=self.cycle%5 != 0 and (not terminal or len(self.results)<2),
                    write_command_ready=self.cycle%3 != 0,
                    write_data_ready=self.cycle%4 != 0)
        if self.read and self.read[1] <= self.cycle:
            opts['read_beat'] = self.read_beat(self.read[0])
        if self.results and self.results[0][1] <= self.cycle:
            opts['result'] = self.results[0][0]
        if self.ack and self.ack[1] <= self.cycle:
            opts['write_ack'] = self.ack[0]
        if self.seed_ack and self.seed_ack[1] <= self.cycle:
            opts['seed_ack'] = self.seed_ack[0]
        if self.lib.matrix_done_ready() and not self.results:
            opts['matrix_done'] = model.MatrixDone(self.job.tag)
        event = self.owner.tick(**opts)
        require(not self.owner.error,'owner failed: '+str(self.owner.error))
        require(self.address == self.lib.matrix_accumulator_address(),'accumulator allocation changed')
        self.max_reserved = max(self.max_reserved,event.get('reserved_after',0))
        if event.get('read_fire'):
            require(self.read is not None,'unsolicited DMA response')
            self.read = None
        if event.get('read_command_fire'):
            require(self.read is None,'more than one descriptor')
            command = event['read_command']
            self.read = (command,self.cycle+1+self.rng.randrange(3))
            self.command_digest.update(repr(command).encode())
        if event.get('group_fire'):
            require(not self.results,'group crossed unretired result payload')
            require(self.lib.td_group(self.owner.chunk_start,self.owner.chunk_end,self.owner.contexts)==0,
                    'native group rejected')
            self.ticket = int(self.lib.matrix_ticket())
            self.groups += 1
        if event.get('seed_begin_fire'):
            require(self.lib.td_seed_begin(event['seed_begin'].context)==0,'seed begin rejected')
        if event.get('seed_beat_fire'):
            beat = event['seed_beat']
            words = (C.c_uint32*16)(*beat.words)
            require(self.lib.td_seed_beat(beat.request.context,beat.index,words)==0,'seed beat rejected')
            if beat.last:
                require(self.lib.td_seed_commit(beat.request.context)==0,'seed commit rejected')
                self.seed_ack = (model.SeedAck(beat.request),self.cycle+2)
        if event.get('seed_ack_fire'):
            ack = opts['seed_ack']
            require(self.lib.matrix_seed_ack(self.ticket,ack.request.context,ack.error)==0,'seed ACK retirement')
            self.seed_ack = None
            self.seed_count += 1
        if event.get('step_fire'):
            step = event['step']
            self.packet_digest.update(repr((self.owner.n_base,self.owner.chunk_start,step)).encode())
            self.a[:],self.b[:] = step.a,step.b
            rc = self.lib.td_step(step.k,step.context,step.clear,step.last,step.finish,step.emit,
                                  self.a,self.b,self.output)
            require(rc == int(step.last),'native accepted step failed')
            self.steps += 1
            if rc:
                require(len(self.results)<2,'third joined result slot')
                raw = bytes(self.output)
                self.result_digest.update(raw)
                value = tuple(struct.unpack_from('<256I',raw,r*1024) for r in range(16))
                self.results.append((model.MatrixResult(step.context,value),self.cycle+2))
                self.max_results = max(self.max_results,len(self.results))
        if event.get('result_fire'):
            result,_ = self.results.popleft()
            require(result == opts['result'],'held result changed')
            require(self.lib.matrix_result_retire(self.ticket,result.context,result.last)==0,'result retirement')
            self.result_count += 1
        if opts.get('matrix_done') is not None and event['matrix_done_ready']:
            require(self.lib.matrix_done_retire(self.ticket,self.job.tag,0)==0,'done retirement')
        if event.get('write_command_fire'):
            require(self.write is None and self.ack is None,'overlapping write obligation')
            self.write = [event['write_command'],0]
        if event.get('write_data_fire'):
            command,index = self.write
            beat = event['write_data']
            address = command.address+64*index
            self.memory[address] = beat.words
            self.write[1] += 1
            if beat.last:
                self.ack = (model.WriteAck(command.tag,nbytes=command.beats*64),self.cycle+2)
                self.write = None
        if event.get('write_ack_fire'):
            self.ack = None
        if event.get('operand_read') and event['a_reads']:
            require(len(event['a_reads'])==8,'unexpected A gather width')
            self.a_gathers += 1
        if event.get('response_fire'):
            require(event['response']==(self.job.tag,None,self.job.m*self.job.n*4),'terminal mismatch')
            require(not (self.read or self.write or self.ack or self.seed_ack or self.results),'unretired external debt')
            require(self.lib.matrix_owner_reply_retire(1,self.job.tag)==0,'owner retirement')
            require(self.lib.matrix_release(1,self.job.tag)==0,'owner release')
            require(self.lib.matrix_state()==0,'native Matrix did not become quiescent')
            self.terminal = event['response']

    def run(self):
        self.tick(offer=True)
        for _ in range(80000):
            self.tick()
            if self.terminal is not None:
                break
        require(self.terminal is not None,'bounded native job did not finish')
        fmas = int(self.lib.matrix_dense_fmas())
        require(fmas==self.steps*4096,'native full-enabled-cell FMA count mismatch')
        raw = b''.join(struct.pack('<16I',*self.memory[self.job.dst+i])
                       for i in range(0,self.job.m*self.job.n*4,64))
        require(len(raw)==self.job.m*self.job.n*4,'missing logical outputs')
        return dict(shape=dict(m=self.job.m,k=self.job.k,n=self.job.n),
                    input_bf16=self.job.activation_bf16, a_hold=self.owner.enable_a_hold,
                    accepted_steps=self.steps,actual_fma_calls=fmas,groups=self.groups,
                    returned_full_4096_cell_payloads=self.result_count,
                    restored_seed_contexts=self.seed_count, max_joined_payload_slots=self.max_results,
                    max_reserved_operands=self.max_reserved,a_gathers=self.a_gathers,
                    output_words=len(raw)//4,output_sha256=sha(raw),
                    all_terminal_cells_sha256=self.result_digest.hexdigest(),
                    packets_sha256=self.packet_digest.hexdigest(),
                    dma_commands_sha256=self.command_digest.hexdigest(),
                    accumulator_bytes=int(self.lib.matrix_accumulator_bytes()),
                    accepted_debt_retired=True),raw


def run(receipt):
    pins = sources()
    before = snapshot()
    record,library = verify_library(receipt)
    lib = configure_library(C.CDLL(str(library.resolve())))
    lib.sf_reset.argtypes,lib.sf_reset.restype = [],C.c_int
    require(lib.sf_reset()==0,'existing IEEE FP32/RNE/gradual-subnormal environment gate')
    cases = []
    for m,k,n,native in CASES:
        job = model.Job(m=m,k=k,n=n,activation_bf16=native,weight_bf16=native)
        baseline,base_raw = NativeDriver(lib,job,False).run()
        reused,reused_raw = NativeDriver(lib,job,True).run()
        require(base_raw==reused_raw,'all-output bitwise mismatch')
        for name in ('actual_fma_calls','groups','restored_seed_contexts','returned_full_4096_cell_payloads',
                     'all_terminal_cells_sha256','packets_sha256','dma_commands_sha256'):
            require(baseline[name]==reused[name],'on/off mismatch: '+name)
        require(reused['a_gathers']==k*((n//32+4)//5),'A reuse count')
        cases.append(dict(baseline=baseline,candidate=reused,all_output_bits_equal=True,
                          all_terminal_cells_equal=True))
    require(pins==sources() and before==snapshot(),'source changed during numerical run')
    verify_library(receipt)
    result = dict(status='PASS_BOUNDED_NATIVE_HOST_A_HOLD_EQUIVALENCE',cases=cases,
                library_sha256=record['library_sha256'],compile_receipt_sha256=pins['compile_receipt_sha256'],
                source_sha256=before,recompiled=False,existing_library_reused=True,
                arithmetic='unchanged C++ std::fma; all4096 cells per accepted Dense step',
                numerical_endpoints_executed=True,synthetic_inputs=True,real_checkpoint_weights=False,
                independent_framework_reference=False,complete_business_block_acceptance=False,
                rtl_execution=False,timing_or_utilization_claim=False)
    validate_report(result)
    return result


def validate_report(result):
    require(result['status']=='PASS_BOUNDED_NATIVE_HOST_A_HOLD_EQUIVALENCE','report status')
    for name in ('real_checkpoint_weights','independent_framework_reference',
                 'complete_business_block_acceptance','rtl_execution','timing_or_utilization_claim','recompiled'):
        require(result[name] is False,'unsupported acceptance claim: '+name)
    require(result['numerical_endpoints_executed'] is True and result['existing_library_reused'] is True
            and result['synthetic_inputs'] is True,'execution provenance')
    pins = sources()
    require(result['source_sha256']==snapshot(),'report source closure')
    require(result['library_sha256']==pins['library_sha256'] and
            result['compile_receipt_sha256']==pins['compile_receipt_sha256'],'report ELF provenance')
    require(len(result['cases'])==len(CASES),'exact bounded case list')
    for case,(m,k,n,native) in zip(result['cases'],CASES):
        require(case['all_output_bits_equal'] is True and case['all_terminal_cells_equal'] is True,
                'all-output comparison')
        for label,enabled in (('baseline',False),('candidate',True)):
            run = case[label]
            require(run['shape']==dict(m=m,k=k,n=n) and run['input_bf16'] is native
                    and run['a_hold'] is enabled,'case geometry/configuration')
            require(run['accepted_steps']==k*(n//32) and run['actual_fma_calls']==k*(n//32)*4096,
                    'every enabled cell must execute the actual FMA')
            require(run['output_words']==m*n and run['accepted_debt_retired'] is True,'output/debt coverage')
            require(0<run['max_joined_payload_slots']<=2 and
                    0<run['max_reserved_operands']<=(3 if enabled else 4),'physical queue capacity')
            require(run['accumulator_bytes']==81920,'five existing accumulator contexts')
            require(run['a_gathers']==k*((n//32+4)//5 if enabled else n//32),'real A gather count')
            expected_groups=((k+127)//128)*((n//32+4)//5)
            require(run['groups']==expected_groups and
                    run['returned_full_4096_cell_payloads']==((k+127)//128)*(n//32) and
                    run['restored_seed_contexts']==((k-1)//128)*(n//32),'complete group/seed results')
        for name in ('output_sha256','all_terminal_cells_sha256','packets_sha256','dma_commands_sha256'):
            value = case['baseline'][name]
            require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
                    'canonical complete-output digest')
            require(value==case['candidate'][name],'default-on/off divergence: '+name)
    return result


if __name__ == '__main__':
    require(len(sys.argv)==3,'usage: python -m ...check_numeric compile_receipt.json result.json')
    output = Path(sys.argv[2])
    require(not output.exists(),'result already exists; choose a fresh output')
    result = run(sys.argv[1])
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(status=result['status'],cases=len(result['cases']))))
