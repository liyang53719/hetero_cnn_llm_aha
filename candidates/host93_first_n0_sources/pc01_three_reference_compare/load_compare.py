"""Same-buffer loader for one frozen read-only consumer. No native or file writes."""
import hashlib
from pathlib import Path
import stat
import types

SOURCE_PIN = (15167, 'c8e8026838bc955364ae1c171e9775d7138acff20074fb168dfe3000b2fc4820')

def load_compare(source_root):
    root = Path(source_root)
    if not (root.is_absolute() and '..' not in root.parts and root.resolve(strict=True) == root and
            not any(p.is_symlink() for p in (root, *root.parents))):
        raise ValueError('COMPARE_SOURCE_ROOT')
    path = root / 'compare.py'
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != SOURCE_PIN[0]:
        raise ValueError('COMPARE_SOURCE_SIZE')
    raw = path.read_bytes()
    after = path.lstat()
    stamp = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if stamp(before) != stamp(after) or (len(raw),hashlib.sha256(raw).hexdigest()) != SOURCE_PIN:
        raise ValueError('COMPARE_SOURCE_IDENTITY')
    module = types.ModuleType('fixed_pc01_comparison')
    module.__file__ = str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module.compare
