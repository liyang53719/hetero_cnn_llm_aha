"""Pure sanitizer tests: both retained byte buffers are pinned before either executes."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before source read')
import hashlib
from pathlib import Path
HERE=Path(__file__).absolute().parent
PINS={
 'safe_build_diagnostics.py':(6486,'7e73383cacf3d14992a6b9be083f7db4311ee5996a8b1cd54dbb11b2061176a1'),
 'test_safe_build_diagnostics.py':(9096,'a1a4255619fcccf142fa8956c02353979e818a0ab9b1bcc9776bf09da73deef7'),
}
buffers={name:(HERE/name).read_bytes() for name in PINS}
for name,(size,digest) in PINS.items():
    raw=buffers[name]
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError('fixed source identity before compile')
module={'__file__':str(HERE/'safe_build_diagnostics.py'),'__name__':'verified_sanitizer'}
fixture={'__file__':str(HERE/'test_safe_build_diagnostics.py'),'__name__':'verified_sanitizer_fixture'}
exec(compile(buffers['safe_build_diagnostics.py'],module['__file__'],'exec',dont_inherit=True),module)
exec(compile(buffers['test_safe_build_diagnostics.py'],fixture['__file__'],'exec',dont_inherit=True),fixture)
checks=fixture['run_tests'](module)
print('PURE_SANITIZER_TESTS_PASS checks='+str(checks)+' optimize='+str(sys.flags.optimize))
