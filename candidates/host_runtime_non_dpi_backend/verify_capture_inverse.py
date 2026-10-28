"""Verify the original compiled carrier from its one privately supplied path literal.
No compiler, execution, path output, source output or file writes. Not equivalence proof.
"""
from pathlib import Path
import argparse, hashlib, json

def verify(root, literal):
    if not literal or any(c in literal for c in ('"', '\n', '\r', '\x00', '\\')):
        raise ValueError('invalid original literal')
    rows=json.loads((root/'SOURCE_PINS.json').read_text())['files']
    row=next(r for r in rows if r['path']=='source/HostCompiledLatestCapture.scala')
    data=(root/row['path']).read_bytes()
    token=b'"REQUIRES_PARENT_ORIGINAL_HIGH"'
    if data.count(token)!=1:raise ValueError('one redaction required')
    data=data.replace(token,('"'+literal+'"').encode())
    if len(data)!=row['original']['bytes'] or hashlib.sha256(data).hexdigest()!=row['original']['sha256']:
        raise ValueError('original identity mismatch')
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_literal_file',type=Path)
    a=p.parse_args()
    verify(Path(__file__).resolve().parent,a.private_literal_file.read_text().rstrip('\n'))
    print('PASS_ORIGINAL_SOURCE_HASH_ONLY_NOT_RECOMPILED_OR_EQUIVALENCE')
