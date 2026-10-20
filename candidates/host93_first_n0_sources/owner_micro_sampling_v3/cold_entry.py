#!/usr/bin/env python3
"""Fixed same-buffer cold loader. Pure mock/source checks, no native tools."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types
import unittest

MANIFEST_PIN = {'bytes': 1019, 'sha256': '67ae76c51aacbcabb47bdf10cc59a8d1cb7c506760907d506c7f09681279b6fc'}
TEST_PIN = {'bytes': 18076, 'sha256': 'b24ef0b0863c4db4441d8d873bf014d6c46fa093c7b462d868818de4edacb49e'}
FILES = ['owner_micro.cpp', 'owner_inputs.inc', 'owner_observations.inc', 'owner_readonly.vlt', 'sha256.hpp', 'PORTS.json', 'OBSERVATIONS.json']

def read_fixed(path, pin):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != pin['bytes']:
            raise ValueError('FIXED_SIZE_TYPE')
        raw = b''
        while len(raw) <= pin['bytes']:
            piece = os.read(fd, min(65536, pin['bytes'] + 1 - len(raw)))
            if not piece:
                break
            raw += piece
        after = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        stamp = lambda x: (x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if stamp(before) != stamp(after) or stamp(before) != stamp(named):
            raise ValueError('FIXED_STABLE')
        if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
            raise ValueError('FIXED_HASH')
        return raw
    finally:
        os.close(fd)

def load(root):
    m=json.loads(read_fixed(root/'PRODUCTION_MANIFEST.json', MANIFEST_PIN))
    if set(m) != {'schema','files'} or m['schema'] != 'OWNER_MICRO_PRODUCTION_V1' or set(m['files']) != set(FILES):
        raise ValueError('MANIFEST_SCHEMA')
    buffers={name:read_fixed(root/name, m['files'][name]) for name in FILES}
    test=read_fixed(root/'test_owner_cold.py', TEST_PIN)
    return buffers,test

def main():
    root=Path(__file__).resolve().parent
    buffers,test=load(root)
    module=types.ModuleType('owner_fixed_cold')
    module.__file__=str(root/'test_owner_cold.py')
    module.SOURCE_BUFFERS=buffers
    sys.modules[module.__name__]=module
    exec(compile(test,module.__file__,'exec'),module.__dict__)
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
