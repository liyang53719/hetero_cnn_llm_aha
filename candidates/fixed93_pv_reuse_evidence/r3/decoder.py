"""Separate streaming decoder; successful seal exists only after real EOF."""
import hashlib
import zlib
from format import (BANK,CLOSE,EVENT,FINISH,FRAME,HEADER,NONE,NO_CONTEXT,OPEN,RAW,RESET,SAME,
                    TERMINAL,VALUE_BEGIN,VALUE_CHUNK,VALUE_END,XOR_ZLIB,
                    CodecError,Record,Seal,chain_hash,decode_metadata,parse_header)


class Decoder:
    def __init__(self,source,policy):
        self.source = source
        self.policy = policy.validate()
        self._read_bytes = self._ordinal = self._raw = 0
        self._failed = self._started = False
        self.seal = None
        try:
            header = self._take(HEADER.size,self.policy.max_output)
            self.limits = parse_header(header,policy)
        except BaseException:
            self._failed = True
            raise
        self._chain = hashlib.sha256(header).digest()
        self._contexts = [None] * self.limits.contexts
        self._epochs = [(-1,-1)] * self.limits.contexts
        self._values = None
        self._last_stream = -1

    def _take(self,size,cap):
        if self._read_bytes + size > cap:
            raise CodecError("decoder input cap before read")
        data = self.source.read(size)
        if type(data) is not bytes or len(data) != size:
            raise CodecError("truncated/invalid read")
        self._read_bytes += size
        return data

    def records(self):
        if self._started or self._failed:
            raise CodecError("decoder already consumed or failed")
        self._started = True
        try:
            while True:
                before = self._read_bytes
                frame = self._take(FRAME.size,self.limits.max_output)
                ordinal,kind,encoding,context,flags,epoch,ticket,base,aux,rawlen,mlen,plen = FRAME.unpack(frame)
                if ordinal != self._ordinal or flags or mlen < 2 or mlen > self.limits.max_metadata:
                    raise CodecError("ordinal/flags/metadata bound")
                if rawlen > max(self.limits.max_chunk,self.limits.bank_bytes):
                    raise CodecError("raw record bound")
                if FRAME.size + mlen + plen + 32 > self.limits.max_record:
                    raise CodecError("encoded record bound")
                if self._raw + rawlen > self.limits.max_raw:
                    raise CodecError("raw stream bound")
                if kind != FINISH and ordinal >= self.limits.max_records:
                    raise CodecError("record count bound")
                # Payload allocation is capped before reading, even for unknown kinds.
                if plen > max(self.limits.max_chunk,self.limits.bank_bytes,TERMINAL.size):
                    raise CodecError("payload bound")
                meta_raw = self._take(mlen,self.limits.max_output)
                payload = self._take(plen,self.limits.max_output)
                digest = self._take(32,self.limits.max_output)
                if digest != chain_hash(self._chain,frame,meta_raw,payload):
                    raise CodecError("record hash chain mismatch")
                metadata = decode_metadata(meta_raw,self.limits.max_metadata)
                if kind == FINISH:
                    if (encoding,context,epoch,ticket,base,aux,rawlen,mlen,plen) != (RAW,NO_CONTEXT,0,0,0,0,0,2,TERMINAL.size):
                        raise CodecError("malformed terminal")
                    count,raw,encoded,prior_hash = TERMINAL.unpack(payload)
                    if (count,raw,encoded,prior_hash) != (ordinal,self._raw,before,self._chain):
                        raise CodecError("terminal totals/hash mismatch")
                    if any(c is not None for c in self._contexts) or self._values is not None:
                        raise CodecError("terminal with unclosed state")
                    eof = self.source.read(1)
                    if type(eof) is not bytes or eof != b"":
                        raise CodecError("extra data or invalid nonbytes EOF after terminal")
                    self.seal = Seal(ordinal,raw,self._read_bytes,digest.hex())
                    return
                if kind in (OPEN,RESET,CLOSE,BANK):
                    if context >= self.limits.contexts or epoch == NONE or ticket == NONE:
                        raise CodecError("invalid context/epoch/ticket")
                    state = self._contexts[context]
                    if kind in (OPEN,RESET,CLOSE):
                        if (encoding,base,aux,rawlen,plen) != (RAW,0,0,0,0):
                            raise CodecError("invalid context boundary")
                        if kind in (OPEN,RESET):
                            if (kind == OPEN and (state is not None or (epoch,ticket) <= self._epochs[context])) or (kind == RESET and (state is None or epoch <= self._epochs[context][0])):
                                raise CodecError("invalid open/reset epoch/state")
                            self._contexts[context] = (epoch,ticket,None,None)
                            self._epochs[context] = (epoch,ticket)
                        else:
                            if state is None or state[:2] != (epoch,ticket):
                                raise CodecError("wrong close context")
                            self._contexts[context] = None
                        actual = b""
                    else:
                        if state is None or state[:2] != (epoch,ticket) or aux or rawlen != self.limits.bank_bytes:
                            raise CodecError("wrong bank context/boundary/size")
                        if encoding == RAW:
                            if base != NONE or plen != rawlen:
                                raise CodecError("invalid checkpoint")
                            actual = payload
                        elif encoding in (SAME,XOR_ZLIB):
                            if state[2] is None or base != state[3]:
                                raise CodecError("missing/stale/wrong-context bank base")
                            if encoding == SAME:
                                if plen:
                                    raise CodecError("same bank carries unexpected payload")
                                actual = state[2]
                            else:
                                if not 0 < plen < rawlen:
                                    raise CodecError("invalid delta payload size")
                                inflater = zlib.decompressobj()
                                try:
                                    delta = inflater.decompress(payload,rawlen+1)
                                except zlib.error as exc:
                                    raise CodecError("invalid compressed delta") from exc
                                if len(delta) != rawlen or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
                                    raise CodecError("oversized/truncated/concatenated delta")
                                actual = bytes(a ^ b for a,b in zip(state[2],delta))
                        else:
                            raise CodecError("unknown bank encoding")
                        self._contexts[context] = (epoch,ticket,actual,ordinal)
                else:
                    if context != NO_CONTEXT or encoding != RAW:
                        raise CodecError("unexpected context/encoding")
                    if kind == EVENT:
                        if (epoch,ticket,base,aux) != (0,0,0,0) or plen != rawlen or rawlen > self.limits.max_chunk:
                            raise CodecError("invalid event")
                        actual = payload
                    elif kind == VALUE_BEGIN:
                        if rawlen or plen or ticket or aux or self._values is not None or epoch == NONE or epoch <= self._last_stream or base > self.limits.max_raw:
                            raise CodecError("invalid value begin")
                        self._values = (epoch,base,0,0)
                        self._last_stream = epoch
                        actual = b""
                    elif kind in (VALUE_CHUNK,VALUE_END):
                        if self._values is None or (epoch,base,ticket,aux) != self._values:
                            raise CodecError("value stream identity/offset/index mismatch")
                        sid,total,position,index = self._values
                        if kind == VALUE_CHUNK:
                            if plen != rawlen or not 1 <= rawlen <= self.limits.max_chunk or position + rawlen > total:
                                raise CodecError("invalid value chunk length")
                            self._values = (sid,total,position+rawlen,index+1)
                            actual = payload
                        else:
                            if rawlen or plen or position != total:
                                raise CodecError("incomplete value stream")
                            self._values = None
                            actual = b""
                    else:
                        raise CodecError("unknown record kind")
                self._chain = digest
                self._ordinal += 1
                self._raw += rawlen
                yield Record(ordinal,kind,context,epoch,ticket,base,aux,encoding,metadata,actual)
        except BaseException:
            self._failed = True
            self.seal = None
            raise
