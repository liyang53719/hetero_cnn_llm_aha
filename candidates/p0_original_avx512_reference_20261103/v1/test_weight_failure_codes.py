#!/usr/bin/env python3
"""Pure offline classification and bounded redirect regression tests."""
import hashlib
import io
import json
from email.message import Message
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

import acquire_weights as aw
from prepare_runtime import StageFailure, failure_receipt
from weight_errors import WEIGHT_FAILURE_REASONS


class NoRead(io.BytesIO):
    def read(self, *args):
        raise AssertionError('error/redirect body must never be read')


class Response(io.BytesIO):
    status = 206

    def __init__(self, body=b'abcd', **headers):
        super().__init__(body)
        self.headers = {'Content-Range': f'bytes 0-3/{aw.SHARD_BYTES}',
                        'Content-Length': '4', **headers}
        self.read_sizes = []

    def geturl(self):
        return 'https://us.aws.cdn.hf.co/opaque'

    def read(self, n=-1):
        self.read_sizes.append(n)
        return super().read(n)


class WeightFailureTests(unittest.TestCase):
    def reason(self, expected, function, *args):
        with self.assertRaises(StageFailure) as cm:
            function(*args)
        self.assertEqual(cm.exception.reason, expected)
        self.assertIn(expected, WEIGHT_FAILURE_REASONS)

    def fetch(self, response=None, error=None):
        opener = Mock()
        if error is not None:
            opener.open.side_effect = error
        else:
            opener.open.return_value = response
        return aw.fetch(opener, 0, 3,
                        {'started': time.monotonic(), 'received': 0, 'requested': 0})

    def test_http_enums_and_no_body_read(self):
        for code in (401, 403, 404, 408, 429, 500, 502, 503, 504, 418):
            with self.subTest(code=code):
                body = NoRead(b'private error body')
                error = urllib.error.HTTPError(aw.URL, code, 'private text', {}, body)
                expected = f'WEIGHT_HTTP{code}' if code != 418 else 'WEIGHT_HTTP_OTHER'
                self.reason(expected, self.fetch, None, error)
                self.assertTrue(body.closed)

    def test_transport(self):
        for error in (urllib.error.URLError('secret'), TimeoutError('secret')):
            self.reason('WEIGHT_TRANSPORT', self.fetch, None, error)

    def test_response_guards_and_bounded_read(self):
        for headers, body, expected in (
            ({'Content-Range': 'bytes 1-4/99'}, b'abcd', 'WEIGHT_RANGE_HEADER'),
            ({'Content-Length': '5'}, b'abcd', 'WEIGHT_RANGE_LENGTH'),
            ({'Content-Encoding': 'gzip'}, b'abcd', 'WEIGHT_ENCODING'),
            ({}, b'abc', 'WEIGHT_BODY_SIZE'),
            ({}, b'abcdef', 'WEIGHT_BODY_SIZE')):
            self.reason(expected, self.fetch, Response(body, **headers))
        response = Response()
        response.status = 200
        self.reason('WEIGHT_RANGE_STATUS', self.fetch, response)
        response = Response()
        self.assertEqual(self.fetch(response), b'abcd')
        self.assertEqual(response.read_sizes, [5])

    def redirect(self, location, hops=0, extra=None):
        handler = aw.BoundedWeightRedirect()
        handler.parent = Mock()
        req = urllib.request.Request(aw.URL, headers={'Range': 'bytes=0-3',
                                                     'Accept-Encoding': 'identity'})
        req.timeout = 60
        req._weight_redirect_hops = hops
        headers = Message()
        if location is not None:
            headers.add_header('Location', location)
        if extra is not None:
            headers.add_header('Location', extra)
        body = NoRead(b'private redirect body')
        try:
            handler.http_error_302(req, body, 302, 'private', headers)
        finally:
            self.assertTrue(body.closed)
        return handler.parent.open.call_args

    def test_exact_host_and_redirect_policy(self):
        self.assertEqual(aw.weight_url('https://us.aws.cdn.hf.co/x'),
                         'https://us.aws.cdn.hf.co/x')
        for location in ('https://us.aws.cdn.hf.co.evil.test/x',
                         'http://us.aws.cdn.hf.co/x', 'https://evil.test/x',
                         'https://user@us.aws.cdn.hf.co/x', 'https://us.aws.cdn.hf.co:80/x',
                         'x' * 8193, None, 'https://us.aws.cdn.hf.co/\nx'):
            self.reason('WEIGHT_REDIRECT_POLICY', self.redirect, location)
        self.reason('WEIGHT_REDIRECT_POLICY', self.redirect, aw.URL, 0, aw.URL)

    def test_redirect_limit_per_request_and_headers(self):
        for hops in range(4):
            call = self.redirect('https://us.aws.cdn.hf.co/x', hops)
            req = call.args[0]
            self.assertEqual(req._weight_redirect_hops, hops + 1)
            self.assertEqual(req.get_header('Range'), 'bytes=0-3')
            self.assertEqual(req.get_header('Accept-encoding'), 'identity')
            self.assertEqual(call.kwargs, {'timeout': 60})
        self.reason('WEIGHT_REDIRECT_LIMIT', self.redirect, aw.URL, 4)
        self.assertEqual(self.redirect(aw.URL, 0).args[0]._weight_redirect_hops, 1)

    def header_reason(self, expected, header, weights):
        # Synthetic metadata is pinned locally only, never changes production pins.
        with patch.object(aw, 'HEADER_SHA', hashlib.sha256(header).hexdigest()), \
                patch.object(aw, 'HEADER_BYTES', len(header)):
            self.reason(expected, aw.validate_header, header, weights)

    def test_header_failures(self):
        self.reason('WEIGHT_HEADER_HASH', aw.validate_header, b'bad pin', [])
        self.header_reason('WEIGHT_HEADER_PREFIX', struct.pack('<Q', 100) + b'{}', [])
        self.header_reason('WEIGHT_HEADER_JSON', struct.pack('<Q', 1) + b'{', [])
        data = json.dumps({'w': {'dtype': 'BF16', 'shape': [1], 'data_offsets': [0, 2]}}).encode()
        header = struct.pack('<Q', len(data)) + data
        w = {'name': 'w', 'dtype': 'BF16', 'shape': [1],
             'start': len(header), 'end': len(header) + 1}
        with patch.object(aw, 'HEADER_SHA', hashlib.sha256(header).hexdigest()), \
                patch.object(aw, 'HEADER_BYTES', len(header)):
            aw.validate_header(header, [w])
        self.header_reason('WEIGHT_HEADER_GEOMETRY', header, [{**w, 'shape': [2]}])
        self.header_reason('WEIGHT_HEADER_GEOMETRY', header, [{**w, 'name': 'missing'}])

    def test_receipt_only_fixed_reason(self):
        for reason in WEIGHT_FAILURE_REASONS | {'PRECHECK_PIN', 'INSTALL', 'WEIGHT_HASH'}:
            with tempfile.TemporaryDirectory() as folder:
                failure_receipt(Path(folder), StageFailure(reason), 'INSTALL')
                receipt = json.loads((Path(folder) / 'FAILURE.json').read_text())
                self.assertEqual(receipt, {'schema': 'P0_STAGE_FAILURE_V1',
                                          'status': 'FAIL', 'reason': reason})


if __name__ == '__main__':
    unittest.main()
