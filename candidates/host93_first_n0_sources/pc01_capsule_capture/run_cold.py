"""Fixed same-buffer pure/mock capture entry. Never invokes a native tool."""
import hashlib
from pathlib import Path
import sys

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('COLD_REQUIRE_PYTHON_ISOLATED_NO_SITE_NO_BYTECODE')

TEST_PIN = (82987, '816466556843770ae54348575e5369dcb3084b9884a83816327bdc5de6d3b03e')
path = Path(__file__).resolve().parent / 'test_capture_cold.py'
raw = path.read_bytes()
if TEST_PIN is None or (len(raw), hashlib.sha256(raw).hexdigest()) != TEST_PIN:
    raise SystemExit('COLD_TEST_SOURCE_IDENTITY')
namespace = {'__name__': '__main__', '__file__': str(path)}
exec(compile(raw, str(path), 'exec', dont_inherit=True), namespace)
