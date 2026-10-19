"""Fixed same-buffer pure/mock cold entry. Never invokes a native tool."""
import hashlib
from pathlib import Path
import sys

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('COLD_REQUIRE_PYTHON_ISOLATED_NO_SITE_NO_BYTECODE')

TEST_PIN = (47283, '28d99de70a2c892377b65b1492cd414c9e2b848507b2a7de9f2053437d6e5336')
path = Path(__file__).resolve().parent / 'test_relink_cold.py'
raw = path.read_bytes()
if TEST_PIN is None or (len(raw), hashlib.sha256(raw).hexdigest()) != TEST_PIN:
    raise SystemExit('COLD_TEST_SOURCE_IDENTITY')
namespace = {'__name__': '__main__', '__file__': str(path)}
exec(compile(raw, str(path), 'exec', dont_inherit=True), namespace)
