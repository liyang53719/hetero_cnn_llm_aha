"""Fixed same-buffer execution entry; run only after separate admission."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B')
import hashlib
from pathlib import Path
p = Path(__file__).resolve().parent / 'run_reference.py'
raw = p.read_bytes()
if (len(raw), hashlib.sha256(raw).hexdigest()) != (14870, 'a1eef5869774d6b66aa332966d1de7a3b0cbca5fad640e65d9ee666d609f9684'):
    raise SystemExit('execution source identity')
ns = {'__name__': 'pc1_reference_execution', '__file__': str(p)}
exec(compile(raw, str(p), 'exec', dont_inherit=True), ns)
ns['main']()
