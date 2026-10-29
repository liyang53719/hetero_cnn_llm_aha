# NEW portable test only; original executed test/results preserved separately.
from pathlib import Path
import tempfile, sys, os, json, hashlib, gzip, importlib.util, time, argparse
HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--baseline-supervisor', type=Path, required=True)
ap.add_argument('--supervisor', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
args = ap.parse_args()
if args.output.exists():
    raise ValueError('fresh synthetic evidence output required')
sys.path.insert(0, str(args.supervisor.resolve().parent))

def load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
new = load(args.supervisor.resolve(), 'new_watchdog')
old = load(args.baseline_supervisor.resolve(), 'old_watchdog')
results = []
with tempfile.TemporaryDirectory(prefix='bounded_watchdog_fixture_') as t:
    root = Path(t)
    tree = root / 'synthetic_tree'
    tree.mkdir()
    for i in range(64):
        d = tree / str(i)
        d.mkdir()
        for j in range(64):
            (d / str(j)).write_bytes(b'x' * 64)
    base = dict(wall_seconds=15, cleanup_seconds=5, file_bytes=32 * 1024 ** 2, tree_bytes=48 * 1024 ** 2, log_bytes=24 * 1024 ** 2, raw_log_bytes=24 * 1024 ** 2, max_entries=10000, per_process_as_bytes=192 * 1024 ** 2, per_process_cpu_seconds=15, rss_bytes=96 * 1024 ** 2, cpu_seconds=15, extra_watch_roots=[str(tree)], watch_tree_bytes=64 * 1024 ** 2, min_free_disk_bytes=1024 ** 2)

    def run(name, module, code, changes=None, expect_pass=False, expected=None):
        p = root / (name + '.py')
        p.write_text(code)
        caps = {**base, **(changes or {})}
        before = time.monotonic()
        r = module.execute([sys.executable, str(p)], root / name, root / 'exclusive.lock', caps, {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, {str(p): hashlib.sha256(p.read_bytes()).hexdigest()})
        elapsed = time.monotonic() - before
        if not elapsed < 60:
            raise AssertionError((name, elapsed))
        if not r['observed_peak_rss'] < 256 * 1024 ** 2:
            raise AssertionError('controlled fixture expectation')
        if not (r['status'] == 'PASS_PROCESS_ONLY') == expect_pass:
            raise AssertionError((name, r['errors']))
        if not r['cleanup_proof']['status'] == 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP':
            raise AssertionError('controlled fixture expectation')
        if not not r.get('observed_remaining'):
            raise AssertionError('controlled fixture expectation')
        if module is new:
            if not r['reader_join_barrier']['complete']:
                raise AssertionError('controlled fixture expectation')
            if not r['reader_started_after_popen']:
                raise AssertionError('controlled fixture expectation')
        raw = gzip.decompress((root / name / 'frontend.log.gz').read_bytes())
        rec = r['log_capture']
        if not (len(raw) == rec['raw_bytes'] and hashlib.sha256(raw).hexdigest() == rec['raw_sha256']):
            raise AssertionError('controlled fixture expectation')
        if not rec['gzip_finalized']:
            raise AssertionError('controlled fixture expectation')
        if expected is not None:
            if not (raw == expected and rec['pipe_eof_observed']):
                raise AssertionError('controlled fixture expectation')
        sample_times = [json.loads(z)['elapsed'] for z in (root / name / 'rss_samples.jsonl').read_text().splitlines()]
        maxgap = max([b - a for a, b in zip(sample_times, sample_times[1:])], default=0)
        row = {'name': name, 'status': r['status'], 'elapsed_seconds': elapsed, 'observed_rss': r['observed_peak_rss'], 'supervisor_cpu_seconds': r.get('supervisor_cpu_seconds'), 'observed_child_cpu_seconds': r['observed_cpu_seconds'], 'disk_census_total_seconds': r.get('disk_census_total_seconds'), 'native_exit': r['native_exit'], 'errors': r['errors'], 'capture': rec, 'actual_sample_max_gap_seconds': maxgap, 'disk_census_max_seconds': r.get('disk_census_max_seconds'), 'reader_barrier': r.get('reader_join_barrier')}
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'capture'}), flush=True)
    line = b'%Warning-FIXTURE: synthetic bounded line 0123456789abcdef\n'
    payload = line * 262144
    code = 'import sys\nb=' + repr(line) + '*4096\nfor i in range(64):sys.stdout.buffer.write(b)\nsys.stdout.buffer.flush()\n'
    run('old_noisy', old, code, expect_pass=True, expected=payload)
    run('new_noisy', new, code, expect_pass=True, expected=payload)
    run('new_disk_cap', new, "from pathlib import Path\nimport time\nPath('large').write_bytes(b'x'*1048576)\ntime.sleep(2)\n", {'tree_bytes': 32768})
    run('new_rss_cap', new, 'import time\nx=bytearray(48*1024*1024)\ntime.sleep(2)\n', {'rss_bytes': 24 * 1024 ** 2})
    run('new_raw_log_cap', new, code, {'raw_log_bytes': 32768})
    run('new_compressed_log_cap', new, 'import os,sys\nsys.stdout.buffer.write(os.urandom(32768))\nsys.stdout.buffer.flush()\n', {'log_bytes': 4096})
    run('new_timeout', new, 'import time\ntime.sleep(2)\n', {'wall_seconds': 0.3})
    run('new_disk_reserve', new, 'import time\ntime.sleep(2)\n', {'min_free_disk_bytes': 10 ** 18})
report = {'scope': 'Controlled synthetic only; no EDA/real repository scans. 4096 files x64 bytes +64 dirs; noisy expected ' + str(len(payload)) + ' bytes. No artificial census sleep. Each case <60sec/<256MiB childRSS. RSS/proc/disk remain synchronous sampled, not fast RSS guarantee.', 'results': results, 'all_pass': True}
args.output.write_text(json.dumps(report, indent=2) + '\n')
