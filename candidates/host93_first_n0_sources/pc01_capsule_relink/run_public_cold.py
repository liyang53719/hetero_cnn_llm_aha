"""Rebuild the fixed public cold fixture only; never runs compiler or model."""
import hashlib
from pathlib import Path
import sys

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('PUBLIC_COLD_REQUIRE_ISOLATED_NO_SITE_NO_BYTECODE')

def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in (
        'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen'
    ):
        raise RuntimeError('PUBLIC_COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'torch', 'ctypes'):
        raise RuntimeError('PUBLIC_COLD_NUMERICAL_IMPORT_FORBIDDEN')
sys.addaudithook(audit)

import argparse
import json
import tempfile

PREFIX = 'candidates/host93_first_n0_sources/pc01_capsule_relink'
ENTRY_PIN = (2045, 'b6cc7020d4691305d6aebf33f8fab7c3a13b7b7bf3bd9b5c68ab13222858bd74')
INPUTS_PIN = (12127, '53cd03fa0107b0723725194ace4c6ec15d6f91fbf94799a211a611f006028ddc')
p = argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[3])
args = p.parse_args()
repo = args.repo_root.resolve(strict=True)
entry_path = repo / PREFIX / 'launch.py'
entry_raw = entry_path.read_bytes()
if (len(entry_raw), hashlib.sha256(entry_raw).hexdigest()) != ENTRY_PIN:
    raise SystemExit('PUBLIC_COLD_ENTRY_IDENTITY')
# Reuse the accepted canonical, nofollow, descriptor-stable checked reader.
entry = {'__name__': 'public_cold_checked_reader', '__file__': str(entry_path)}
exec(compile(entry_raw, str(entry_path), 'exec', dont_inherit=True), entry)
manifest = json.loads(entry['checked'](repo / PREFIX / 'PUBLIC_COLD_INPUTS.json', INPUTS_PIN))
if manifest['schema'] != 'PC01_CAPSULE_RELINK_PUBLIC_COLD_INPUTS_V1' or len(manifest['files']) != 39:
    raise SystemExit('PUBLIC_COLD_FIXED_INPUT_SET')
buffers = {}
for rel, row in manifest['files'].items():
    origin = Path(row['repository_path'])
    target = Path(rel)
    if origin.is_absolute() or target.is_absolute() or '..' in origin.parts or '..' in target.parts:
        raise SystemExit('PUBLIC_COLD_RELATIVE_SOURCE')
    expected = row['identity']
    buffers[rel] = entry['checked'](repo / origin, (expected['bytes'], expected['sha256']))
# Import does no native work. Use only the original exclusive checked-buffer writer.
runner_path = repo / PREFIX / 'run_relink.py'
runner = {'__name__': 'public_cold_stage_only', '__file__': str(runner_path)}
exec(compile(buffers['run_relink.py'], str(runner_path), 'exec', dont_inherit=True), runner)
with tempfile.TemporaryDirectory(prefix='pc01_capsule_relink_cold_') as folder:
    stage = Path(folder).resolve()
    for rel, raw in buffers.items():
        runner['write_exact'](stage / rel, raw)
    cold_path = stage / 'run_cold.py'
    # Consume the already verified buffer; the unchanged cold entry pins its test.
    exec(compile(buffers['run_cold.py'], str(cold_path), 'exec', dont_inherit=True),
         {'__name__': '__main__', '__file__': str(cold_path)})
