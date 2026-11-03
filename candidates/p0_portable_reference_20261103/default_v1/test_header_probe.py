"""Offline-only tests; any accidental socket creation fails the test."""
import copy
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.request

import acquire_weights
import header_probe as hp


def headers(**changes):
    values = {'Content-Range': f'bytes 0-{hp.HEADER_BYTES-1}/{hp.SHARD_BYTES}',
              'Content-Length': str(hp.HEADER_BYTES)}
    values.update(changes)
    h = Message()
    for k, v in values.items():
        if v is not None:
            h[k] = v
    return h


def synthetic(weights, mutate=None, raw=None, prefix=None):
    h = {w['name']: {'dtype': w['dtype'], 'shape': w['shape'],
                    'data_offsets': [w['start'] - hp.HEADER_BYTES, w['end'] + 1 - hp.HEADER_BYTES]}
         for w in weights}
    if mutate:
        mutate(h)
    encoded = json.dumps(h).encode() if raw is None else raw
    return struct.pack('<Q', hp.HEADER_BYTES - 8 if prefix is None else prefix) + encoded.ljust(hp.HEADER_BYTES - 8, b' ')


class Response(io.BytesIO):
    def __init__(self, body, status=206, hdr=None, url='https://us.aws.cdn.hf.co/file'):
        super().__init__(body)
        self.status, self.headers, self.url = status, hdr or headers(), url
        self.read_sizes = []

    def geturl(self):
        return self.url

    def read(self, size=-1):
        assert size == hp.HEADER_BYTES + 1, 'unbounded response read'
        self.read_sizes.append(size)
        return super().read(size)


class NeverRead:
    closed = False
    def read(self, *args):
        raise AssertionError('redirect body must never be read')
    def close(self):
        self.closed = True


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weights = hp.load_weights(Path(__file__).with_name('FROZEN_P0.json'))

    def setUp(self):
        self.socket_guard = mock.patch.object(socket, 'socket', side_effect=AssertionError('network forbidden'))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)

    def result(self, body=None, **kwargs):
        if body is None:
            body = synthetic(self.weights)
        response = Response(body, **kwargs)
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(hp, 'HEADER_SHA', hashlib.sha256(body).hexdigest()):
            report = hp.probe(self.weights, hp.diagnostic(), opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Range'), 'bytes=0-38535')
        self.assertEqual(request.get_header('Accept-encoding'), 'identity')
        self.assertEqual(opener.open.call_count, 1)
        return report, response

    def test_exact_host_fix_and_policy(self):
        self.assertIn('us.aws.cdn.hf.co', acquire_weights.HOSTS)
        old = acquire_weights.HOSTS - {'us.aws.cdn.hf.co'}
        with self.assertRaises(ValueError):
            acquire_weights.allowed_url('https://us.aws.cdn.hf.co/x', old)
        hp.url_ok('https://us.aws.cdn.hf.co/x')
        for url in ['http://us.aws.cdn.hf.co/x', 'https://us.aws.cdn.hf.co.evil/x',
                    'https://evil.hf.co/x', 'https://a@us.aws.cdn.hf.co/x',
                    'https://us.aws.cdn.hf.co:444/x', 'https://us.aws.cdn.hf.co/x#fragment']:
            with self.assertRaises(hp.ProbeFailure):
                hp.url_ok(url)

    def test_pass_and_schema(self):
        report, response = self.result()
        self.assertEqual(report['status'], 'PASS_HEADER_ONLY')
        self.assertEqual(report['geometry_checked'], 12)
        self.assertEqual(report['final_host'], 'HF_US_AWS_CDN')
        self.assertEqual(response.read_sizes, [38537])
        self.assertEqual(set(report), {'schema', 'status', 'failure_point', 'failure_code',
            'http_status', 'final_host', 'response_bytes', 'observed_header_sha256',
            'header_sha_equal', 'geometry_checked', 'redirect_count'})

    def test_response_metadata_failures(self):
        cases = [({'status': 200}, 'HTTP_STATUS'),
                 ({'hdr': headers(**{'Content-Range': 'bytes 1-38536/3087467144'})}, 'CONTENT_RANGE'),
                 ({'hdr': headers(**{'Content-Length': '38537'})}, 'CONTENT_LENGTH'),
                 ({'hdr': headers(**{'Content-Encoding': 'gzip'})}, 'CONTENT_ENCODING')]
        for kwargs, code in cases:
            report, response = self.result(**kwargs)
            self.assertEqual(report['failure_code'], code)
            self.assertEqual(response.read_sizes, [])
        h = headers(); h['Content-Length'] = '38536'
        self.assertEqual(self.result(hdr=h)[0]['failure_code'], 'CONTENT_LENGTH')

    def test_body_sizes(self):
        for size in (0, 38535, 38537, 100000):
            report, response = self.result(body=b'x' * size)
            self.assertEqual(report['failure_code'], 'BODY_SIZE')
            self.assertEqual(report['response_bytes'], min(size, 38537))

    def test_hash_pin_not_weakened(self):
        response = Response(synthetic(self.weights))
        opener = mock.Mock(); opener.open.return_value = response
        report = hp.probe(self.weights, hp.diagnostic(), opener)
        self.assertEqual(report['failure_code'], 'HEADER_HASH')
        self.assertIs(report['header_sha_equal'], False)
        self.assertEqual(hp.HEADER_SHA, '124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987')

    def test_prefix_and_json(self):
        self.assertEqual(self.result(body=synthetic(self.weights, prefix=1))[0]['failure_code'], 'HEADER_PREFIX')
        for raw in (b'{', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'[]', b'\xff'):
            self.assertEqual(self.result(body=synthetic(self.weights, raw=raw))[0]['failure_code'], 'HEADER_JSON')

    def test_semantics(self):
        name = self.weights[0]['name']
        for key, value in [('dtype', 'F32'), ('shape', [1]), ('data_offsets', [0, 1])]:
            report, _ = self.result(body=synthetic(self.weights, lambda h: h[name].update({key: value})))
            self.assertEqual(report['failure_code'], 'SEMANTIC')
            self.assertEqual(report['geometry_checked'], 1)
        report, _ = self.result(body=synthetic(self.weights, lambda h: h.pop(name)))
        self.assertEqual(report['failure_code'], 'SEMANTIC')

    def redirect(self, target, count=0, code=302):
        report = hp.diagnostic(); report['redirect_count'] = count
        handler = hp.BoundedRedirect(report); handler.parent = mock.Mock()
        fp = NeverRead(); h = Message(); h['Location'] = target
        req = urllib.request.Request(hp.URL)
        try:
            getattr(handler, 'http_error_' + str(code))(req, fp, code, 'secret', h)
        finally:
            self.assertTrue(fp.closed)
        return report, handler.parent

    def test_redirect_without_read(self):
        for code in (301, 302, 303, 307, 308):
            report, parent = self.redirect('https://us.aws.cdn.hf.co/file?signature=SECRET', code=code)
            self.assertEqual(report['redirect_count'], 1)
            self.assertEqual(parent.open.call_count, 1)
            self.assertNotIn('SECRET', json.dumps(report))
            req = parent.open.call_args.args[0]
            self.assertEqual(req.get_header('Range'), 'bytes=0-38535')
            self.assertEqual(req.get_header('Accept-encoding'), 'identity')

    def test_redirect_guards(self):
        for target in ['http://us.aws.cdn.hf.co/file', 'https://us.aws.cdn.hf.co.evil/file', 'https://evil.test/x', ' https://us.aws.cdn.hf.co/x', '/' + 'x' * 8192]:
            with self.assertRaises(hp.ProbeFailure) as err:
                self.redirect(target)
            self.assertEqual(err.exception.code, 'URL_POLICY')
        with self.assertRaises(hp.ProbeFailure) as err:
            self.redirect('https://us.aws.cdn.hf.co/file', count=4)
        self.assertEqual(err.exception.code, 'REDIRECT_LIMIT')

    def test_http_and_transport_no_text(self):
        for exception, code in [(urllib.error.URLError('SECRET'), 'TRANSPORT'),
                                (TimeoutError('SECRET'), 'TRANSPORT'),
                                (urllib.error.HTTPError(hp.URL, 403, 'SECRET', headers(), NeverRead()), 'HTTP_ERROR')]:
            opener = mock.Mock(); opener.open.side_effect = exception
            report = hp.probe(self.weights, hp.diagnostic(), opener)
            self.assertEqual(report['failure_code'], code)
            self.assertNotIn('SECRET', json.dumps(report))
            if code == 'HTTP_ERROR':
                self.assertEqual(report['http_status'], 403)

    def test_input_failure_atomic_output_and_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); manifest = root / 'bad.json'; manifest.write_text('{"secret":"secret"}')
            output = root / 'out'
            report = hp.run(output, manifest)
            self.assertEqual(report['failure_code'], 'INPUT_PIN')
            self.assertEqual([x.name for x in output.iterdir()], ['HEADER_DIAGNOSTIC.json'])
            self.assertNotIn('secret', (output / 'HEADER_DIAGNOSTIC.json').read_text())
            with self.assertRaises(hp.ProbeFailure):
                hp.run(output, manifest)


if __name__ == '__main__':
    unittest.main()
