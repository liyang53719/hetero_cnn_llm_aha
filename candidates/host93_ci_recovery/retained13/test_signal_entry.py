#!/usr/bin/env python3
"""Pure tiny front-door fixtures. Never read or execute the production runner."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('python -I -S -B required')
import hashlib
import json
from pathlib import Path
import signal

root = Path(__file__).absolute().parent
launcher = root/'run_retained13.py'
raw = launcher.read_bytes()
if len(raw) != 1713 or hashlib.sha256(raw).hexdigest() != 'fc7129f0200148ead007dd9e5b3b6ecd77a378432084dea101e51f82b831c0a0':
    raise SystemExit('fixed launcher mismatch')
if len(sys.argv) != 2 or sys.argv[1] not in ('blocked', 'timer'):
    raise SystemExit('choose blocked or timer tiny fixture')
case = sys.argv[1]
if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, set()) or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
    raise SystemExit('test needs initially clear signal state')
if case == 'blocked':
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    expected = 'inherited SIGALRM blocked; refusing before project compile'
else:
    signal.setitimer(signal.ITIMER_REAL, 10.0)
    expected = 'inherited ITIMER_REAL occupied; refusing before project compile'
before_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
before_timer = signal.getitimer(signal.ITIMER_REAL)
events = []
runner = str(root/'assemble_retained13.py')


def audit(event, args):
    if ((event == 'open' and str(args[0]) == runner) or
            (event == 'compile' and len(args) > 1 and args[1] == runner) or
            (event == 'exec' and getattr(args[0], 'co_filename', None) == runner)):
        events.append(event)
        raise RuntimeError('production runner reached before rejection')


sys.addaudithook(audit)
try:
    exec(compile(raw, str(launcher), 'exec', dont_inherit=True),
         {'__name__': '__main__', '__file__': str(launcher)})
except SystemExit as error:
    if str(error) != expected:
        raise RuntimeError('unexpected rejection: ' + str(error))
else:
    raise RuntimeError('inherited signal fixture accepted')
after_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
after_timer = signal.getitimer(signal.ITIMER_REAL)
if events or after_mask != before_mask:
    raise RuntimeError('production touched or inherited mask changed')
if case == 'blocked' and (signal.SIGALRM not in after_mask or after_timer != before_timer):
    raise RuntimeError('blocked fixture changed')
if case == 'timer' and not (0 < after_timer[0] <= before_timer[0] and after_timer[1] == before_timer[1] == 0.0):
    raise RuntimeError('inherited timer cancelled or replaced')
print(json.dumps({'status': 'PASS_TINY_SIGNAL_REJECTION', 'case': case, 'optimize': sys.flags.optimize,
                  'production_events': events, 'mask_preserved': before_mask == after_mask,
                  'blocked_mask_still_blocked': signal.SIGALRM in after_mask,
                  'occupied_timer_still_running': after_timer[0] > 0,
                  'source_assembled': False}, sort_keys=True))
