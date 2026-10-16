"""Streaming observation of the unchanged original owner AST/Fraction oracle."""
import hashlib
import struct
from ..attention_matrix_batch.test_model import OriginalSchedule


class Stream:
    def __init__(self, kind):
        if kind not in ('request','read','write'): raise ValueError('trace kind')
        self.kind,self.count,self.digest=kind,0,hashlib.sha256()
    def append(self, value):
        if self.kind=='request':
            if len(value.a)!=16 or len(value.b)!=256:raise ValueError('request shape')
            data=struct.pack('<III??',value.opcode,value.steps,len(value.a),value.clear,value.last)
            data+=struct.pack('<272H',*(value.a+value.b))
        elif self.kind=='read':data=struct.pack('<Q',value)
        else:
            address,words=value
            if len(words)!=16:raise ValueError('write shape')
            data=struct.pack('<Q16I',address,*words)
        self.digest.update(data);self.count+=1
    def __len__(self):return self.count
    def hexdigest(self):return self.digest.hexdigest()


class ScalarTrace:
    OPCODES={'add':1,'mul':2,'div':3,'bf':4}
    POLICIES={'legacy_scalar':1,'vector':2}
    def __init__(self, *, capture_scores=True):
        if type(capture_scores) is not bool:raise ValueError("score observer mode")
        self.capture_scores=capture_scores
        self.count=0;self.digest=hashlib.sha256();self.recent=[]
        self.dots=[];self.scores=[]
    def append(self, entry):
        op,a,b,result,policy=entry
        self.digest.update(struct.pack('<BBIII',self.OPCODES[op],self.POLICIES[policy],a,b,result))
        if self.capture_scores and self.recent and self.recent[-1][0]=='mul' and self.recent[-1][2]==0x3db504f3:
            if len(self.recent)!=2:raise ValueError('score boundary prefix')
            before,multiply=self.recent
            if before[0]!='bf' or before[3]!=multiply[1] or entry[:2]!=('bf',multiply[3]):raise ValueError('original QK boundary')
            self.dots.append(before[1]);self.scores.append(result)
        self.recent.append(entry)
        if len(self.recent)>2:del self.recent[0]
        self.count+=1
    def __len__(self):return self.count
    def hexdigest(self):return self.digest.hexdigest()


class Oracle(OriginalSchedule):
    """Only observation storage changes; original generators/services remain."""
    def __init__(self,*args):
        super().__init__(*args)
        self.scalar.trace=ScalarTrace()
        self.requests=Stream('request');self.reads=Stream('read');self.writes=Stream('write')
    def scores(self):return tuple(self.scalar.trace.dots),tuple(self.scalar.trace.scores)
