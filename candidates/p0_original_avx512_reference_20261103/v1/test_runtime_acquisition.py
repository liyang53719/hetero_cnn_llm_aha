#!/usr/bin/env python3
"""Pure offline/mock tests. Does not import Torch or download/install anything."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import prepare_runtime as runtime
import acquire_weights as weights

HERE = Path(__file__).resolve().parent


class Response:
    status = 206

    def __init__(self, body=b'abcd', length='4', span=None):
        self.body = body
        self.headers = {'Content-Length': length,
                        'Content-Range': span or f'bytes 0-3/{weights.SHARD_BYTES}'}

    def geturl(self):
        return weights.URL

    def read(self, n):
        return self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def open(self, *args, **kwargs):
        self.calls += 1
        return self.response


def budget():
    return {'requested': 0, 'received': 0, 'started': time.monotonic()}


class Tests(unittest.TestCase):
    def test_range(self):
        op = Opener(Response())
        b = budget()
        self.assertEqual(weights.fetch(op, 0, 3, b), b'abcd')
        self.assertEqual((op.calls, b['received']), (1, 4))
        for response in (Response(b'abc'), Response(length='5'), Response(span='bytes 1-4/5')):
            with self.assertRaises(ValueError):
                weights.fetch(Opener(response), 0, 3, budget())
        with self.assertRaises(ValueError):
            weights.fetch(op, 0, weights.MAX_BLOCK, budget())
        with self.assertRaises(ValueError):
            weights.fetch(op, 0, 3, dict(budget(), requested=weights.WEIGHT_BYTES + weights.HEADER_BYTES))

    def test_urls_json_names(self):
        for url in ('http://huggingface.co/file', 'https://example.org/file',
                    'https://x@huggingface.co/file', 'https://huggingface.co:444/file'):
            with self.assertRaises(ValueError):
                runtime.allowed_url(url, weights.HOSTS)
        with self.assertRaises(ValueError):
            runtime.safe_name('../bad')
        with self.assertRaises(ValueError):
            runtime.unique([('x', 1), ('x', 2)])

    def test_manifest_and_sidecar_serialization(self):
        f = runtime.read_json(HERE / 'FROZEN_P0.json')
        self.assertEqual((len(f['wheels']), sum(x['size_bytes'] for x in f['wheels'])), (26, 238463458))
        self.assertEqual((len(f['weights']), sum(x['bytes'] for x in f['weights'])), (12, 93595648))
        for item in f['wheels']:
            runtime.allowed_url(item['url'], runtime.WHEEL_HOSTS)
        e = f['runtime_sidecar']['content']
        order = ('transformers.models.qwen2.modeling_qwen2',
                 'transformers.models.qwen2.configuration_qwen2', 'transformers.activations',
                 'transformers.cache_utils', 'torch.nn.functional', 'torch._C')
        a = {'framework_revision': e['framework_revision'],
             'module_sha256': {k: e['module_sha256'][k] for k in order},
             'module_relative_paths': {k: e['module_relative_paths'][k] for k in order},
             'native_file_sha256': dict(sorted(e['native_file_sha256'].items())),
             'artifact_sha256': {k: e['artifact_sha256'][k] for k in ('framework', 'torch')},
             'identity': e['identity'], 'limits': e['limits']}
        serialized = (json.dumps(a, indent=2) + '\n').encode()
        self.assertEqual(hashlib.sha256(serialized).hexdigest(), f['runtime_sidecar']['sha256'])

    def test_safe_failure_and_progress(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            weights.progress(out, 0, 0)
            weights.progress(out, 4, 0)
            self.assertEqual(runtime.read_json(out / 'WEIGHT_CHECKS.json')['checked'], 4)
            exc = OSError('secret path and URL must not escape')
            runtime.failure_receipt(out, exc, 'PRECHECK_PIN')
            receipt = runtime.read_json(out / 'FAILURE.json')
            self.assertEqual(receipt, {'schema': 'P0_STAGE_FAILURE_V1', 'status': 'FAIL', 'reason': 'PRECHECK_PIN'})
            self.assertFalse(isinstance(exc, runtime.StageFailure))
            with self.assertRaises(runtime.StageFailure) as captured:
                weights.weight_check(False, 'WEIGHT_HASH', mismatch=True)
            self.assertTrue(captured.exception.mismatch)
            weights.progress(out, 4, 1)
            self.assertEqual(runtime.read_json(out / 'WEIGHT_CHECKS.json')['mismatch_count'], 1)
            # First comparison failure counts as checked=1, mismatch_count=1.
            weights.progress(out, 0, 0)
            with patch.object(weights, 'acquire', side_effect=runtime.StageFailure('WEIGHT_HASH', True)), \
                 patch.object(weights, 'CREATED_OUTPUT', out), \
                 patch('sys.argv', ['acquire_weights.py', '--output', str(out), '--frozen', 'unused']):
                with self.assertRaises(SystemExit):
                    weights.main()
            observed = runtime.read_json(out / 'WEIGHT_CHECKS.json')
            self.assertEqual((observed['checked'], observed['mismatch_count']), (1, 1))

    def test_clean_environment_and_ast(self):
        self.assertFalse({'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONUSERBASE', 'LD_PRELOAD', 'LD_LIBRARY_PATH'}
                         & runtime.clean_env().keys())
        for name in ('prepare_runtime.py', 'acquire_weights.py'):
            ast.parse((HERE / name).read_text())


if __name__ == '__main__':
    unittest.main()
