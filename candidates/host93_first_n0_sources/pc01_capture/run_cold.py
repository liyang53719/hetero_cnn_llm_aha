"""Fixed same-buffer pure/mock capture entry. Never invokes a native tool."""
import hashlib
from pathlib import Path
import sys

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('COLD_REQUIRE_PYTHON_ISOLATED_NO_SITE_NO_BYTECODE')

TEST_PIN = (62433, '938a0a5009a9357b58223841d845db995b98078a0b937a5fc4357747bd188dd6')
path = Path(__file__).resolve().parent / 'test_capture_cold.py'
raw = path.read_bytes()
if TEST_PIN is None or (len(raw), hashlib.sha256(raw).hexdigest()) != TEST_PIN:
    raise SystemExit('COLD_TEST_SOURCE_IDENTITY')
namespace = {'__name__': '__main__', '__file__': str(path)}
exec(compile(raw, str(path), 'exec', dont_inherit=True), namespace)
