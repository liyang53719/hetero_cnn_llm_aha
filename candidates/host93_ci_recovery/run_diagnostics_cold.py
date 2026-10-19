"""Pure sanitizer tests: both retained byte buffers are pinned before either executes."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before source read')
import hashlib
from pathlib import Path
HERE=Path(__file__).absolute().parent
PINS={
 'safe_build_diagnostics.py':(11942,'97ab72651c9acadf1e4d242225bdfc21dea3807aa911e448ce7330b762fa4a60'),
 'test_safe_build_diagnostics.py':(19000,'d01b997fded243138e48f5e06dd255a4750b037d6a64631e9104c972af58af66'),
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
context_checks=fixture['run_context_tests'](module)
print('PURE_SANITIZER_TESTS_PASS checks='+str(checks)+' context_checks='+str(context_checks)+' optimize='+str(sys.flags.optimize))
