"""One-beat typed DMA transpose of real A/B producers into [A32,B32] rows.

Software protocol model only. No arithmetic, oracle imports or block commit.
"""
from collections import Counter
from dataclasses import dataclass
import struct
from ..qwen35_gdn_prefill.typed_dense import TypedMemory,FULL_MASK
from ..qwen35_gdn_prefill.rms_owner import WriteCommand,WriteAck,sha,require

@dataclass(frozen=True)
class PackResponse:
    tag:int
    status:object
    write_bytes:int

class TypedABPackDriver:
    def __init__(self,memory,a,b,output,tokens,tag=35200):
        require(type(memory) is TypedMemory and memory.pending is None,'drained pack memory')
        require(type(tokens) is int and tokens in (16,128),'pack M16/M128')
        self.memory,self.tokens,self.tag=memory,tokens,tag
        self.sources=(memory.exact(a,tokens*64,readable=True),memory.exact(b,tokens*64,readable=True))
        require(all(not r.readonly and r.written==r.acknowledged==set(range(0,r.extent,64)) for r in self.sources),'actual complete A/B producers')
        self.output=memory.exact(output,tokens*128,readable=False)
        self.source_hashes=tuple(sha(r.raw()) for r in self.sources)
        self.index=0;self.state='read';self.buffer=None;self.pending=None;self.error=None
        self.response=None;self.counts=Counter();self.aborted=False
    def tick(self,*,memory_ready=True,memory_response_ready=True,response_ready=True,read_error=False,ack_error=False,abort=False,reset=False):
        require(self.response is None,'pack already retired')
        self.counts['ticks']+=1
        if abort or reset:
            self.aborted=True;self.error=self.error or 'ABORTED'
        if self.state=='terminal':
            if response_ready:
                require(self.pending is None and self.memory.pending is None,'pack terminal before drain')
                require(self.source_hashes==tuple(sha(r.raw()) for r in self.sources),'pack producer changed')
                self.response=PackResponse(self.tag,self.error,self.output.extent)
                if self.error is None:self.memory.publish(self.output.base,(self.tag,None,self.output.extent))
            return
        if self.state=='read_wait':
            if memory_response_ready:
                self.counts['read_response_fire']+=1
                if read_error:self.error=self.error or 'READ_ERROR'
                self.buffer=self.pending if self.error is None else None;self.pending=None
                self.state='write' if self.error is None else 'terminal'
            return
        if self.state=='ack_wait':
            if memory_response_ready:
                self.memory.acknowledge(WriteAck(self.tag,bool(ack_error),64));self.pending=None
                self.counts['ack_fire']+=1
                if not ack_error:self.counts['ack_bytes']+=64
                else:self.error=self.error or 'WRITE_ERROR'
                self.buffer=None;self.index+=1
                self.state='terminal' if self.error is not None or self.index==2*self.tokens else 'read'
            return
        if self.error is not None:self.buffer=None;self.state='terminal';return
        if not memory_ready:return
        if self.state=='read':
            row,role=divmod(self.index,2)
            self.pending=self.memory.read64(self.sources[role].base+row*64)
            self.counts['read_bytes']+=64;self.counts['read_command_fire']+=1;self.state='read_wait'
        elif self.state=='write':
            require(type(self.buffer) is bytes and len(self.buffer)==64,'single retained beat')
            self.memory.begin_write(WriteCommand(self.output.base+self.index*64,1,self.tag))
            self.memory.write_data(struct.unpack('<32H',self.buffer),True,mask=FULL_MASK)
            self.pending=True;self.counts['write_bytes']+=64;self.counts['write_command_fire']+=1;self.state='ack_wait'
        else:raise ValueError('pack state')
    def report(self):
        return dict(complete=self.response is not None,status=None if self.response is None else self.response.status,
            state=self.state,counts=dict(self.counts),output_published=self.output.published,
            input_sha256=list(self.source_hashes),output_sha256=sha(self.output.raw()),local_buffer_bytes=64,
            hardware_cycles=None,full_block=False,history_committed=False,rtl_executed=False)
