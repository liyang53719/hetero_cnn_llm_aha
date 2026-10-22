"""LEC1: bounded lossless opaque-byte evidence; no numerical interpretation."""
import hashlib
import json
import struct
from dataclasses import dataclass

MAGIC = b"LEC1\r\n\x1a\n"
HEADER = struct.Struct("<8sBBBBIIIIQQQ")
FRAME = struct.Struct("<QBBBBQQQQIII")
TERMINAL = struct.Struct("<QQQ32s")
OPEN, RESET, CLOSE, BANK, VALUE_BEGIN, VALUE_CHUNK, VALUE_END, EVENT, FINISH = (1,2,3,4,5,6,7,8,255)
RAW, SAME, XOR_ZLIB = (0,1,2)
NONE = (1 << 64) - 1
NO_CONTEXT = 255
DIGEST_SIZE = 32
TRAILER_SIZE = FRAME.size + 2 + TERMINAL.size + DIGEST_SIZE

class CodecError(ValueError):
    pass


def uint(value, label):
    if type(value) is not int or not 0 <= value < NONE:
        raise CodecError("invalid unsigned integer: " + label)
    return value


@dataclass(frozen=True)
class Limits:
    contexts: int = 5
    bank_bytes: int = 16384
    max_chunk: int = 65536
    max_metadata: int = 4096
    max_record: int = 69720
    max_records: int = 1000000
    max_output: int = 1073741824
    max_raw: int = 1073741824

    def validate(self):
        for key, value in vars(self).items():
            if type(value) is not int or not 1 <= value <= (1 << 63)-1:
                raise CodecError("invalid limit: " + key)
        if self.contexts > 5 or self.bank_bytes > 16384 or self.max_chunk > 65536 or self.max_metadata > 4096:
            raise CodecError("hard state/chunk/metadata bound")
        needed = FRAME.size + DIGEST_SIZE + self.max_metadata + max(self.bank_bytes, self.max_chunk, TERMINAL.size)
        if self.max_metadata < 2 or self.max_record < needed or self.max_record > 69720:
            raise CodecError("record bound cannot contain raw fallback")
        if self.max_output < HEADER.size + TRAILER_SIZE:
            raise CodecError("output bound cannot contain terminal")
        return self

    def header(self):
        self.validate()
        return HEADER.pack(MAGIC,1,1,self.contexts,0,self.bank_bytes,self.max_chunk,
                           self.max_metadata,self.max_record,self.max_records,self.max_output,self.max_raw)


def parse_header(data, policy):
    policy.validate()
    magic, version, endian, contexts, reserved, bank, chunk, meta, record, count, output, raw = HEADER.unpack(data)
    if (magic,version,endian,reserved) != (MAGIC,1,1,0):
        raise CodecError("invalid header/version/little-endian claim")
    limits = Limits(contexts,bank,chunk,meta,record,count,output,raw).validate()
    if any(v > getattr(policy,k) for k,v in vars(limits).items()):
        raise CodecError("header exceeds decoder policy")
    return limits


def metadata_bytes(metadata, cap):
    if type(metadata) is not dict or len(metadata) > 32:
        raise CodecError("metadata must be a flat bounded dictionary")
    def scalar(value):
        if value is None or type(value) is bool:
            return
        if type(value) is int and -(1 << 63) <= value < (1 << 64):
            return
        if type(value) is str and len(value) <= 512:
            return
        raise CodecError("unsupported metadata value")
    parts = []
    used = 2
    for key in metadata:
        if type(key) is not str or not 1 <= len(key) <= 64 or not all(33 <= ord(c) <= 126 for c in key):
            raise CodecError("invalid metadata key")
    for key in sorted(metadata):
        value = metadata[key]
        if type(value) is list:
            if len(value) > 16:
                raise CodecError("metadata list bound")
            for item in value:
                scalar(item)
        else:
            scalar(value)
        part = json.dumps(key,ensure_ascii=True) + ":" + json.dumps(value,ensure_ascii=True,separators=(",",":"),allow_nan=False)
        used += len(part) + bool(parts)
        if used > cap:
            raise CodecError("metadata byte bound")
        parts.append(part)
    return ("{" + ",".join(parts) + "}").encode("ascii")


def decode_metadata(raw, cap):
    try:
        value = json.loads(raw)
        if metadata_bytes(value,cap) != raw:
            raise CodecError("noncanonical or duplicate metadata")
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise CodecError("invalid metadata") from exc


def chain_hash(previous, frame, metadata, payload):
    h = hashlib.sha256()
    for part in (previous,frame,metadata,payload):
        h.update(part)
    return h.digest()


@dataclass(frozen=True)
class Record:
    ordinal: int
    kind: int
    context: int
    epoch: int
    ticket: int
    base: int
    auxiliary: int
    encoding: int
    metadata: dict
    data: bytes


@dataclass(frozen=True)
class Seal:
    records: int
    raw_bytes: int
    encoded_bytes: int
    final_hash: str
