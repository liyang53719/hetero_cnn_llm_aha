"""Bounded, passive received-log markers and sampled-resource observation.

No subprocesses, target imports, acceptance checks, or writes. Marker timing is
parent receipt timing, not target execution timing. A label is never proof of
where all allocations/CPU occurred. Parent retains its original cleanup path.
"""
import hashlib
import json
import re

MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_LINES = 65536
MAX_EVENTS = 128
MAX_SAMPLES = 4000
MAX_SNAPSHOT_BYTES = 1024 * 1024
SAMPLE_SECONDS = 0.1
INITIAL = 'before_first_received_marker'

# Source line numbers are retained as evidence, not predicted from synthetic logs.
# The parent separately binds the exact official sources and release executable.
PREFIX = re.compile(rb'^- +(?P<file>V3[A-Za-z]+\.cpp):(?P<line>[0-9]{1,7}):[ \t]*(?P<body>[^\r\n]*)$')
FUNCTIONS = {
    (b'V3LinkCells.cpp', b'link:'): 'module_cell_link_entry',
    (b'V3LinkParse.cpp', b'linkParse:'): 'link_parse_entry',
    (b'V3LinkDot.cpp', b'linkDotPrimary:'): 'link_dot_primary_entry',
    (b'V3Param.cpp', b'param:'): 'parameterization_entry',
    (b'V3LinkDot.cpp', b'linkDotParamed:'): 'post_parameter_link_entry',
    (b'V3Dead.cpp', b'deadifyModules:'): 'dead_modules_entry',
    (b'V3Width.cpp', b'width:'): 'full_width_entry',
}
KNOWN_FILES = frozenset(k[0] for k in FUNCTIONS) | {b'V3HierBlock.cpp'}
# Only the selected official text families are observed. No opaque text is saved.
HIER_ADD = re.compile(rb"Add '[A-Za-z_][A-Za-z_0-9]{0,255}' with [0-9]{1,7} parameters and [0-9]{1,7} type parameters")
HIER_USE = re.compile(rb"Found usage relation '[A-Za-z_][A-Za-z_0-9]{0,255}' uses '[A-Za-z_][A-Za-z_0-9]{0,255}'")
PHASE_RANK = {INITIAL: 0, 'module_cell_link_entry': 1, 'link_parse_entry': 2,
              'link_dot_primary_entry': 3, 'parameterization_entry': 4,
              'post_parameter_link_entry': 5, 'dead_modules_entry': 6,
              'hierarchy_block_add': 7, 'hierarchy_usage_relation': 7,
              'full_width_entry': 8}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value, name):
    require(type(value) in (int, float), name + ' must be numeric, not bool')
    require(0 <= value <= 1.0e12 and value == value, name + ' must be finite nonnegative and at most 1e12')
    return float(value)


def count(value, name):
    require(type(value) is int and 0 <= value <= (1 << 63) - 1, name + ' must be nonnegative bounded integer')
    return value


class PhaseObserver:
    """feed() and sample() must use one nondecreasing parent elapsed clock."""
    def __init__(self):
        self._failure_reason = None
        self._elapsed = 0.0
        self._hash = hashlib.sha256()
        self._bytes = 0
        self._lines = 0
        self._pending = b''
        self._line_start = 0
        self._events = []
        self._phase = INITIAL
        self._unknown_known_file_lines = 0
        self._ordinary_lines = 0
        self._order_regressions = 0
        self._samples = []
        self._sample_calls = 0
        self._last_saved_elapsed = None
        self._last_saved_event = None
        self._latest = None
        self._phase_peaks = {}
        self._peak_rss = 0
        self._peak_cpu = 0.0
        self._peak_tree = 0

    def _clock(self, elapsed):
        elapsed = number(elapsed, 'elapsed')
        require(elapsed >= self._elapsed, 'observation elapsed time decreased')
        self._elapsed = elapsed
        return elapsed

    def _line(self, raw, start, end, elapsed):
        self._lines += 1
        require(self._lines <= MAX_LINES, 'observation log line cap')
        body = raw[:-1]  # feed calls only on a newline-terminated raw line.
        if body.endswith(b'\r'):
            # CRLF is not emitted by the selected Linux source; do not invent a marker.
            self._ordinary_lines += 1
            return
        m = PREFIX.fullmatch(body)
        if m is None:
            # Unknown/binary lines remain in the separately retained raw log.
            self._ordinary_lines += 1
            return
        filename, text = m['file'], m['body'].rstrip(b' \t')
        if not 1 <= int(m['line']) <= 1000000:
            if filename in KNOWN_FILES:
                self._unknown_known_file_lines += 1
            else:
                self._ordinary_lines += 1
            return
        phase = FUNCTIONS.get((filename, text))
        if filename == b'V3HierBlock.cpp':
            if HIER_ADD.fullmatch(text):
                phase = 'hierarchy_block_add'
            elif HIER_USE.fullmatch(text):
                phase = 'hierarchy_usage_relation'
        if phase is None:
            if filename in KNOWN_FILES:
                self._unknown_known_file_lines += 1
            else:
                self._ordinary_lines += 1
            return
        require(len(self._events) < MAX_EVENTS, 'observation recognized event cap')
        if PHASE_RANK[phase] < PHASE_RANK[self._phase]:
            self._order_regressions += 1
        self._phase = phase
        self._events.append({'event_index': len(self._events), 'phase': phase,
                             'observed_elapsed': elapsed, 'log_line': self._lines,
                             'byte_start': start, 'byte_end_exclusive': end,
                             'source_file': filename.decode('ascii'),
                             'source_line': int(m['line'])})

    def feed(self, blob, observed_elapsed):
        require(self._failure_reason is None, 'observation already failed')
        try:
            return self._feed(blob, observed_elapsed)
        except ValueError as exc:
            self._failure_reason = str(exc)
            raise

    def _feed(self, blob, observed_elapsed):
        require(type(blob) is bytes, 'log feed must be bytes')
        require(self._bytes + len(blob) <= MAX_LOG_BYTES, 'observation raw log byte cap')
        elapsed = self._clock(observed_elapsed)
        self._hash.update(blob)
        self._bytes += len(blob)
        data = self._pending + blob
        at = 0
        while True:
            end = data.find(b'\n', at)
            if end < 0:
                pending = data[at:]
                require(len(pending) <= MAX_LINE_BYTES, 'observation pending line cap')
                self._pending = pending
                break
            end += 1
            require(end - at <= MAX_LINE_BYTES, 'observation complete line cap')
            self._line(data[at:end], self._line_start, self._line_start + end - at, elapsed)
            self._line_start += end - at
            at = end
        return len(self._events)

    def sample(self, elapsed, rss, cpu, treebytes):
        require(self._failure_reason is None, 'observation already failed')
        try:
            return self._sample(elapsed, rss, cpu, treebytes)
        except ValueError as exc:
            self._failure_reason = str(exc)
            raise

    def _sample(self, elapsed, rss, cpu, treebytes):
        # This method must be called only after the parent's existing resource
        # sample validation. It does not replace any CPU/RSS/wall/output gate.
        rss = count(rss, 'rss')
        treebytes = count(treebytes, 'treebytes')
        cpu = number(cpu, 'cpu')
        elapsed = self._clock(elapsed)
        event_index = len(self._events) - 1
        row = [elapsed, rss, cpu, treebytes, event_index]
        self._sample_calls += 1
        self._latest = row
        self._peak_rss = max(self._peak_rss, rss)
        self._peak_cpu = max(self._peak_cpu, cpu)
        self._peak_tree = max(self._peak_tree, treebytes)
        p = self._phase_peaks.setdefault(self._phase, {'sample_calls': 0, 'first_observed_elapsed': elapsed,
                                                    'last_observed_elapsed': elapsed, 'rss_peak_bytes': 0,
                                                    'cpu_peak_seconds': 0.0, 'tree_peak_bytes': 0})
        p['sample_calls'] += 1
        p['last_observed_elapsed'] = elapsed
        p['rss_peak_bytes'] = max(p['rss_peak_bytes'], rss)
        p['cpu_peak_seconds'] = max(p['cpu_peak_seconds'], cpu)
        p['tree_peak_bytes'] = max(p['tree_peak_bytes'], treebytes)
        save = (self._last_saved_elapsed is None or event_index != self._last_saved_event
                or elapsed - self._last_saved_elapsed >= SAMPLE_SECONDS)
        if save:
            require(len(self._samples) < MAX_SAMPLES, 'observation stored sample cap')
            self._samples.append(row)
            self._last_saved_elapsed = elapsed
            self._last_saved_event = event_index
        return save

    def snapshot(self):
        result = {'schema': 'received-frontend-phase-observations-v1',
                  'scope': 'DIAGNOSTIC_RECEIVED_MARKERS_AND_SAMPLED_RESOURCES_ONLY',
                  'phase_semantics': 'last received recognized marker; not a current-stack or allocation-location claim',
                  'cpu_semantics': 'sampled group plus parent counter; peaks are not a complete process-tree CPU integral',
                  'times_semantics': 'parent receipt/sample elapsed times; multiple markers in one chunk share receipt time',
                  'log_bytes': self._bytes, 'log_sha256': self._hash.hexdigest(),
                  'complete_log_lines': self._lines, 'trailing_unterminated_line_bytes': len(self._pending),
                  'last_received_phase': self._phase, 'event_count': len(self._events), 'events': self._events,
                  'known_source_unrecognized_lines': self._unknown_known_file_lines,
                  'ordinary_lines': self._ordinary_lines, 'marker_order_regressions': self._order_regressions,
                  'sample_calls': self._sample_calls, 'stored_sample_count': len(self._samples),
                  'samples': {'columns': ['observed_elapsed', 'rss_bytes', 'cpu_seconds', 'tree_bytes', 'last_event_index'],
                              'rows': self._samples},
                  'latest_sample': self._latest, 'phase_labeled_peaks': self._phase_peaks,
                  'all_sample_peaks': {'rss_bytes': self._peak_rss, 'cpu_seconds': self._peak_cpu, 'tree_bytes': self._peak_tree},
                  'limits': {'raw_log_bytes': MAX_LOG_BYTES, 'line_bytes': MAX_LINE_BYTES, 'log_lines': MAX_LINES,
                             'recognized_events': MAX_EVENTS, 'stored_samples': MAX_SAMPLES,
                             'snapshot_encoded_bytes': MAX_SNAPSHOT_BYTES, 'periodic_sample_seconds': SAMPLE_SECONDS},
                  'observation_failed': self._failure_reason is not None,
                  'observation_failure_reason': self._failure_reason,
                  'terminated_lines_fully_examined': self._failure_reason is None,
                  'truncated': False, 'hardware_or_plan_acceptance': False}
        encoded = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
        require(len(encoded) <= MAX_SNAPSHOT_BYTES, 'observation snapshot byte cap')
        # Return an independent value: callers cannot alter observer history.
        return json.loads(encoded)
