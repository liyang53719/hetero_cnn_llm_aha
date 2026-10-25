"""Durable terminal-only small M2 raw evidence, not an arithmetic provider."""
import hashlib
import json
import os
from pathlib import Path
import struct


def persist_words(out, label, words):
    raw=struct.pack('<%dI'%len(words),*words)
    path=Path(out)/(label+'.u32le')
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return dict(file=path.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def persist_fields(out, prefix, fields):
    records={}
    for name,field in fields.items():
        row=persist_words(out,prefix+'_'+name,field['words'])
        presence=bytes(field['observed']);path=Path(out)/(prefix+'_PRESENCE_'+name+'.binmeta')
        with path.open('xb') as stream:
            stream.write(presence);stream.flush();os.fsync(stream.fileno())
        row.update(shape=field['shape'],presence_file=path.name,presence_sha256=hashlib.sha256(presence).hexdigest(),frequency=list(field['frequency']))
        records[name]=row
    with (Path(out)/(prefix+'_FIELDS.json')).open('x') as stream:
        json.dump(records,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return records
