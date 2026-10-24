"""Bounded main-thread SIGPROF sampling. Diagnostic, not per-domain CPU metering.

No tracing/profile API, model calls, I/O or names/locals inspection in handler.
Code objects, line numbers and counts are retained; frames never are. SIGALRM
and ITIMER_REAL are deliberately untouched. An active prior PROF timer is an
error, not something to overwrite or restart with an extended deadline.
"""
import signal
import threading
import time

HZ = 100
MAX_SAMPLES = 12000
MAX_STACKS = 4096
MAX_DEPTH = 48
MAX_CODES = 2048


class LoopSampler:
    def __init__(self):
        self.active = self.restored = False
        self.started = self.stopped = False
        self.samples = self.overflow_samples = self.overflow_stacks = 0
        self.truncated_stacks = self.reentrant_dropped = 0
        self.stacks = {}
        self.codes = set()
        self.overflow_codes = 0
        self.busy = False
        self.callback = self._sample
        self.first_cpu_ns = self.last_cpu_ns = None
        self.max_gap_ns = self.gaps_over_50ms = 0
        self.pending_drained = 0
        self.cleanup_error = None

    def _sample(self, signum, frame):
        # No catch: in particular never swallow a nested SIGALRM TimeoutError.
        if not self.active:
            return
        if self.busy:
            self.reentrant_dropped += 1
            return
        self.busy = True
        try:
            if self.samples >= MAX_SAMPLES:
                self.overflow_samples += 1
                return
            now = time.process_time_ns()
            if self.first_cpu_ns is None:
                self.first_cpu_ns = now
            if self.last_cpu_ns is not None:
                gap = now - self.last_cpu_ns
                if gap > self.max_gap_ns:
                    self.max_gap_ns = gap
                if gap > 50000000:
                    self.gaps_over_50ms += 1
            self.last_cpu_ns = now
            stack = []
            while frame is not None and len(stack) < MAX_DEPTH:
                stack.append((frame.f_code, frame.f_lineno))
                frame = frame.f_back
            if frame is not None:
                self.truncated_stacks += 1
            key = tuple(stack)
            self.samples += 1
            additions = {code for code, _ in stack} - self.codes
            if len(self.codes) + len(additions) > MAX_CODES:
                self.overflow_codes += 1
                return
            self.codes.update(additions)
            if key in self.stacks:
                self.stacks[key] += 1
            elif len(self.stacks) < MAX_STACKS:
                self.stacks[key] = 1
            else:
                self.overflow_stacks += 1
        finally:
            self.busy = False

    def start(self):
        if self.started or threading.current_thread() is not threading.main_thread():
            raise RuntimeError('one fresh sampler in main thread required')
        self.old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGPROF})
        installed = False
        restore_mask = True
        try:
            if signal.SIGPROF in self.old_mask:
                raise RuntimeError('SIGPROF already blocked')
            if signal.getitimer(signal.ITIMER_PROF) != (0.0, 0.0):
                raise RuntimeError('active ITIMER_PROF cannot be overwritten')
            if signal.SIGPROF in signal.sigpending():
                raise RuntimeError('pre-existing pending SIGPROF')
            self.old_handler = signal.getsignal(signal.SIGPROF)
            signal.signal(signal.SIGPROF, self.callback)
            installed = True
            self.started = self.active = True
            self.start_wall = time.monotonic()
            self.start_cpu = time.process_time()
            signal.setitimer(signal.ITIMER_PROF, 1.0 / HZ, 1.0 / HZ)
        except BaseException:
            if installed:
                signal.setitimer(signal.ITIMER_PROF, 0)
                self.active = False
                restore_mask = False
                for _ in range(8):
                    if signal.SIGPROF not in signal.sigpending():
                        break
                    if signal.sigtimedwait({signal.SIGPROF}, 0) is not None:
                        self.pending_drained += 1
                if signal.SIGPROF in signal.sigpending():
                    self.cleanup_error = 'SIGPROF pending during aborted sampler start'
                else:
                    signal.signal(signal.SIGPROF, self.old_handler)
                    restore_mask = True
            raise
        finally:
            if restore_mask:
                signal.pthread_sigmask(signal.SIG_SETMASK, self.old_mask)

    def stop(self):
        if not self.started or self.stopped:
            raise RuntimeError('stop requires one active sampling session')
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGPROF})
        try:
            signal.setitimer(signal.ITIMER_PROF, 0)
            self.active = False
            # Standard signals coalesce. The bounded loop also handles a stray
            # external PROF without handing our own pending tick to SIG_DFL.
            for _ in range(8):
                if signal.SIGPROF not in signal.sigpending():
                    break
                if signal.sigtimedwait({signal.SIGPROF}, 0) is not None:
                    self.pending_drained += 1
            if signal.SIGPROF in signal.sigpending():
                self.cleanup_error = 'SIGPROF remains pending after bounded drain'
                return  # Do not mask an original DUT/timeout exception in finally.
            signal.signal(signal.SIGPROF, self.old_handler)
            self.stop_wall = time.monotonic()
            self.stop_cpu = time.process_time()
            self.stopped = True
        finally:
            # A failed drain must not unblock a pending signal into the old
            # default handler. Keep the safe sampling handler and block PROF;
            # caller fails and process cleanup remains parent-owned.
            if self.stopped:
                signal.pthread_sigmask(signal.SIG_SETMASK, self.old_mask)
                self.restored = (signal.getsignal(signal.SIGPROF) is self.old_handler and
                    signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0) and
                    signal.pthread_sigmask(signal.SIG_BLOCK, set()) == self.old_mask)

    def report(self):
        if not self.stopped or self.active:
            raise RuntimeError('report only after stopped sampling')
        codes = {}
        rows = []
        leaf = {}
        inclusive = {}
        for stack, count in self.stacks.items():
            indices = []
            seen = set()
            for code, line in stack:
                if code not in codes:
                    codes[code] = len(codes)
                index = codes[code]
                indices.append([index, line])
                if index not in seen:
                    inclusive[index] = inclusive.get(index, 0) + count
                    seen.add(index)
            if indices:
                index = indices[0][0]
                leaf[index] = leaf.get(index, 0) + count
            rows.append(dict(stack=indices, count=count))
        ok = (self.restored and self.samples > 0 and self.overflow_samples == 0 and
              self.overflow_stacks == 0 and self.overflow_codes == 0 and self.reentrant_dropped == 0)
        return dict(schema='fixed93-main-loop-sigprof-report-v1',
            status='PASS_BOUNDED_MAIN_LOOP_SAMPLING' if ok else 'INCOMPLETE_SAMPLING',
            diagnostic_only=True, speed_measurement=False, active=self.active,
            restored=self.restored, hz=HZ, max_samples=MAX_SAMPLES,
            max_stacks=MAX_STACKS, max_depth=MAX_DEPTH, max_codes=MAX_CODES, samples=self.samples,
            unique_stacks=len(rows), overflow_samples=self.overflow_samples,
            overflow_stacks=self.overflow_stacks, overflow_codes=self.overflow_codes, truncated_stacks=self.truncated_stacks,
            reentrant_dropped=self.reentrant_dropped, pending_drained=self.pending_drained,
            max_observed_sample_cpu_gap_ns=self.max_gap_ns, gaps_over_50ms=self.gaps_over_50ms,
            sampled_region_cpu_seconds=self.stop_cpu-self.start_cpu,
            sampled_region_wall_seconds=self.stop_wall-self.start_wall,
            code_table=[dict(id=i, filename=c.co_filename, qualname=c.co_qualname,
                             firstlineno=c.co_firstlineno) for c,i in codes.items()],
            stacks=rows, leaf_counts=leaf, inclusive_counts=inclusive,
            limitations=['No C/native stack; delayed or coalesced signals can land at Python recovery.',
                         'Sample fractions are not exact subdomain CPU time.',
                         'Depth-truncated stacks retain the innermost 48 frames.',
                         'Sampling perturbs execution; this is not a speed acceptance run.'])
