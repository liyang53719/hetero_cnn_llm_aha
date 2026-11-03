"""Independent historical all-visible-byte pins. No framework imports."""
import hashlib
import json
from pathlib import Path

FROZEN_SHA256 = 'e93e1a8ff6e54f7f82ddd3d0134785350a09726e257c2cb73b6823625fa09c76'
HERE = Path(__file__).resolve().parent

class FixtureMismatch(ValueError):
    def __init__(self, reason, name=None):
        super().__init__(reason)
        self.reason = reason
        self.name = name

def need(ok, reason, name=None):
    if not ok:
        raise FixtureMismatch(reason, name)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def strict_json(path):
    p = Path(path)
    need(p.is_file() and not p.is_symlink() and p.stat().st_size <= 1 << 20, 'PRECHECK_PIN')
    def pairs(rows):
        value = {}
        for key, item in rows:
            need(key not in value, 'PRECHECK_PIN')
            value[key] = item
        return value
    def invalid(_):
        raise FixtureMismatch('PRECHECK_PIN')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid)

def frozen():
    p = HERE / 'FROZEN_P0.json'
    need(sha(p) == FROZEN_SHA256, 'PRECHECK_PIN')
    return strict_json(p)

def check_weight(record, path):
    pins = {r['name']: r for r in frozen()['weights']}
    need(record['name'] in pins, 'WEIGHT_HASH')
    expected = pins[record['name']]
    need(all(record[k] == expected[k] for k in ('name', 'shape', 'dtype', 'bytes', 'start', 'end', 'url', 'shard_bytes')), 'WEIGHT_HASH')
    need(Path(path).stat().st_size == expected['bytes'] and sha(path) == expected['sha256'], 'WEIGHT_HASH')
    need(record['actual_sha256'] == expected['sha256'], 'WEIGHT_HASH')

class Gate:
    def __init__(self, output, names=None):
        self.fixture = frozen()['frozen_fixture']
        self.expected = dict(self.fixture['tensor_records'])
        self.expected['rope1024'] = self.fixture['rope1024']
        self.names = set(self.expected) if names is None else set(names)
        need(self.names <= self.expected.keys(), 'REFERENCE_INVENTORY')
        self.output = Path(output)
        self.checks = {}

    def write(self):
        # Private local receipt only, rebuilt into explicit safe schema by controller.
        p = self.output / 'CHECKS_INTERNAL.json'
        temp = self.output / 'CHECKS_INTERNAL.pending'
        temp.write_text(json.dumps(self.checks, sort_keys=True, allow_nan=False) + '\n')
        temp.replace(p)

    def check(self, name, shape, dtype, data):
        need(name in self.names and name not in self.checks, 'REFERENCE_INVENTORY')
        expected = self.expected[name]
        digest = hashlib.sha256(data).hexdigest()
        row = dict(status='MISMATCH', expected_bytes=expected['bytes'], observed_bytes=len(data), expected_sha256=expected['sha256'], observed_sha256=digest, shape_equal=type(shape) is list and shape == expected['shape'], dtype_equal=dtype == expected['dtype'])
        geometry = row['shape_equal'] and row['dtype_equal'] and len(data) == expected['bytes']
        exact = geometry and digest == expected['sha256']
        if exact:
            row['status'] = 'PASS'
        self.checks[name] = row
        self.write()  # Record actual digest before the first mismatch raises.
        reason = ('ROPE_HASH' if name == 'rope1024' else 'REFERENCE_HASH') if geometry else 'REFERENCE_GEOMETRY'
        need(exact, reason, name)
        return digest

    def finish(self):
        need(set(self.checks) == self.names, 'REFERENCE_INVENTORY')
        need(all(r['status'] == 'PASS' for r in self.checks.values()), 'REFERENCE_HASH')
        if self.names == set(self.fixture['tensor_records']):
            need(len(self.checks) == 24 and sum(r['observed_bytes'] for r in self.checks.values()) == 10650624, 'REFERENCE_INVENTORY')


def write_failure(output, exc):
    p = Path(output)
    if p.is_dir():
        # Exception messages, paths and tensors never enter this receipt.
        reason = exc.reason if isinstance(exc, FixtureMismatch) else 'REFERENCE_HASH'
        name = exc.name if isinstance(exc, FixtureMismatch) else None
        (p / 'FAILURE.json').write_text(json.dumps(dict(reason=reason, name=name), allow_nan=False) + '\n')
