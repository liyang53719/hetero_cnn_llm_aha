"""Portable bounded tests. Explicit source roots; SHA pins; no hidden fallback.

Example:
 python -I -S -B tests/run_tests.py --source-root SOURCE \
   --scala-baseline SELECTED_QWEN2BLOCK --work-dir NEW_EMPTY_DIRECTORY
Only two small verified source files are materialized in the requested work dir.
No weights, CDLL, native build, downloads, fullblock or RTL are used.
"""
import argparse
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import re
import runpy
import sys
import types

if sys.flags.optimize:
    raise SystemExit('Optimized Python (-O/-OO) is forbidden: assertions are test gates')

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True,
                    help='Read-only predecessor Python source root, containing candidates/')
parser.add_argument('--scala-baseline', type=Path, required=True,
                    help='Read-only selected predecessor Qwen2Block.scala file')
parser.add_argument('--work-dir', type=Path, required=True,
                    help='New/empty writable directory for patched tiny sources and results')
args = parser.parse_args()
source, scala, work = (p.resolve() for p in (args.source_root, args.scala_baseline, args.work_dir))
pins = json.loads((PACKAGE/'CORE_PINS.json').read_text())
def verify(path, sha):
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != sha:
        raise SystemExit('Pinned source mismatch: '+str(path))
    return blob.decode()
old_scala = verify(scala, pins['baseline_scala_sha256'])
old_python = verify(source/'candidates/qwen2_fixed93_attention/owner.py', pins['baseline_python_sha256'])
verified = {rel: verify(source/rel, sha) for rel, sha in pins['source_dependencies'].items()}
namespaces = set()
for rel in (*verified, 'candidates/qwen2_fixed93_attention/owner.py'):
    for parent in Path(rel).parents:
        if parent == Path('.'): continue
        namespaces.add(parent)
for relative in namespaces:
    directory = source/relative
    unexpected = list(directory.glob('__init__.*')) + list((directory/'__pycache__').glob('__init__.*.pyc'))
    if unexpected:
        raise SystemExit('Unpinned namespace initializer forbidden: '+str(unexpected[0]))
if work.exists() and any(work.iterdir()): raise SystemExit('Work directory must be new or empty; no evidence overwritten')
work.mkdir(parents=True, exist_ok=True)
for sub in ('baseline','delta','reports'): (work/sub).mkdir()
(work/'baseline/Qwen2Block.scala').write_text(old_scala)
(work/'baseline/owner.py').write_text(old_python)
originals = {'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala': old_scala,
             'candidates/qwen2_fixed93_attention/owner.py': old_python}
patch = (PACKAGE/'CORE_DELTA.patch').read_text().splitlines(True)
i = 0; seen = set()
while i < len(patch):
    assert patch[i].startswith('--- a/'), 'unexpected patch header'
    rel = patch[i][6:].strip(); assert rel in originals and rel not in seen
    seen.add(rel); assert patch[i+1] == '+++ b/'+rel+'\n'; i += 2
    old = originals[rel].splitlines(True); output = []; cursor = 0
    while i < len(patch) and patch[i].startswith('@@'):
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n', patch[i]); assert match
        start = int(match[1])-1; assert cursor <= start
        output.extend(old[cursor:start]); cursor = start; i += 1
        removed = added = 0
        while i < len(patch) and not patch[i].startswith(('@@','--- a/')):
            line = patch[i]; marker, content = line[0], line[1:]
            if marker in ' -':
                assert old[cursor] == content, 'patch context does not match pinned input'
                cursor += 1; removed += 1
            if marker in ' +': output.append(content); added += 1
            assert marker in ' +-'; i += 1
        assert removed == int(match[2] or 1) and added == int(match[4] or 1)
    output.extend(old[cursor:]); text = ''.join(output)
    assert hashlib.sha256(text.encode()).hexdigest() == pins['outputs'][rel], 'candidate output pin mismatch'
    path = work/'delta'/rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
assert seen == set(originals)
# Explicit namespace modules avoid importing unpinned initializers or adding
# the source root to sys.path. Load each dependency from its verified bytes,
# never a timestamp-valid but unpinned bytecode cache.
for relative in sorted(namespaces, key=lambda p: len(p.parts)):
    name = '.'.join(relative.parts)
    module = types.ModuleType(name); module.__path__ = [str(source/relative)]; module.__package__ = name
    sys.modules[name] = module
    if '.' in name:
        parent, child = name.rsplit('.', 1); setattr(sys.modules[parent], child, module)
class PinnedLoader(importlib.abc.Loader):
    def __init__(self, rel): self.rel = rel
    def create_module(self, spec): return None
    def exec_module(self, module):
        module.__file__ = str(source/self.rel)
        exec(compile(verified[self.rel], module.__file__, 'exec'), module.__dict__)
class PinnedFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        rel = fullname.replace('.', '/')+'.py'
        if rel in verified: return importlib.util.spec_from_loader(fullname, PinnedLoader(rel))
sys.meta_path.insert(0, PinnedFinder())
config = types.ModuleType('pv_reuse_test_config')
config.WORK_ROOT, config.SOURCE_ROOT, config.SCALA_BASELINE = work, source, scala
sys.modules[config.__name__] = config
sys.path.insert(0, str(HERE))
# unittest does not parse the runner's command line; test_reuse builds its suite.
runpy.run_path(str(HERE/'test_reuse.py'), run_name='__main__')
