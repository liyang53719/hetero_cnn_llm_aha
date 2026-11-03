#!/usr/bin/env python3
"""One bounded header-only request. Never persist response bodies or network text."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import urllib.error
import urllib.parse
import urllib.request

from acquire_weights import HEADER_BYTES, HEADER_SHA, HOSTS, SHARD_BYTES, URL, WEIGHT_BYTES

FROZEN_SHA = 'e93e1a8ff6e54f7f82ddd3d0134785350a09726e257c2cb73b6823625fa09c76'
HOST_LABELS = {
    'huggingface.co': 'HUGGINGFACE', 'us.aws.cdn.hf.co': 'HF_US_AWS_CDN',
    'cas-bridge.xethub.hf.co': 'HF_CAS_BRIDGE',
    'cdn-lfs.huggingface.co': 'HF_LFS', 'cdn-lfs-us-1.huggingface.co': 'HF_LFS_US1',
    'cdn-lfs.hf.co': 'HF_CDN_LFS', 'cdn-lfs-us-1.hf.co': 'HF_CDN_LFS_US1',
}


class ProbeFailure(Exception):
    def __init__(self, point, code):
        self.point, self.code = point, code
        super().__init__(code)


def check(ok, point, code):
    if not ok:
        raise ProbeFailure(point, code)


def url_ok(url, point='REQUEST'):
    try:
        p = urllib.parse.urlsplit(url)
        valid = (isinstance(url, str) and not any(ord(c) < 33 or ord(c) == 127 for c in url)
                 and p.scheme == 'https' and p.hostname in HOSTS
                 and p.username is None and p.password is None and p.port in (None, 443)
                 and not p.fragment)
    except (ValueError, TypeError):
        valid = False
    check(valid, point, 'URL_POLICY')
    return url


def unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('duplicate')
        out[k] = v
    return out


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('nonfinite')
    return number


def strict_json(raw):
    return json.loads(raw, object_pairs_hook=unique, parse_float=finite_float,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))


def diagnostic():
    return dict(schema='P0_HEADER_DIAGNOSTIC_V1', status='FAIL', failure_point='NOT_STARTED',
                failure_code='NONE', http_status=None, final_host=None, response_bytes=None,
                observed_header_sha256=None, header_sha_equal=None, geometry_checked=0,
                redirect_count=0)


class BoundedRedirect(urllib.request.HTTPRedirectHandler):
    """Override the whole handler: stdlib's redirect handler drains an unlimited body."""
    def __init__(self, report):
        super().__init__()
        self.report = report

    def http_error_302(self, req, fp, code, msg, headers):
        # Close even a rejected response, never read it, and never use stdlib redirect logic.
        fp.close()
        self.report['failure_point'] = 'REDIRECT'
        self.report['http_status'] = code if type(code) is int and 100 <= code <= 599 else None
        locations = headers.get_all('Location', [])
        check(len(locations) == 1 and isinstance(locations[0], str)
              and 0 < len(locations[0]) <= 8192
              and not any(ord(c) < 33 or ord(c) == 127 for c in locations[0]),
              'REDIRECT', 'URL_POLICY')
        target = urllib.parse.urljoin(req.full_url, locations[0])
        try:self.report['final_host'] = HOST_LABELS.get(urllib.parse.urlsplit(target).hostname, 'OTHER')
        except ValueError:self.report['final_host'] = 'OTHER'
        target = url_ok(target, 'REDIRECT')
        check(self.report['redirect_count'] < 4, 'REDIRECT', 'REDIRECT_LIMIT')
        self.report['redirect_count'] += 1
        next_req = urllib.request.Request(target, headers={
            'Range': f'bytes=0-{HEADER_BYTES - 1}', 'Accept-Encoding': 'identity'})
        return self.parent.open(next_req, timeout=60)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def load_weights(frozen):
    try:
        check(not frozen.is_symlink() and frozen.is_file()
              and frozen.stat().st_size <= 2 * 1024 * 1024, 'NOT_STARTED', 'INPUT_PIN')
        raw = frozen.read_bytes()
        check(hashlib.sha256(raw).hexdigest() == FROZEN_SHA, 'NOT_STARTED', 'INPUT_PIN')
        weights = strict_json(raw)['weights']
        check(len(weights) == 12 and len({w['name'] for w in weights}) == 12
              and sum(w['bytes'] for w in weights) == WEIGHT_BYTES, 'NOT_STARTED', 'INPUT_PIN')
        for w in weights:
            check(w['url'] == URL and w['shard_bytes'] == SHARD_BYTES
                  and w['dtype'] == 'BF16' and isinstance(w['shape'], list)
                  and all(type(d) is int and d > 0 for d in w['shape'])
                  and type(w['start']) is int and type(w['end']) is int
                  and HEADER_BYTES <= w['start'] <= w['end'] < SHARD_BYTES
                  and 2 * math.prod(w['shape']) == w['bytes'] == w['end'] - w['start'] + 1,
                  'NOT_STARTED', 'INPUT_PIN')
        return weights
    except ProbeFailure:
        raise
    except Exception:
        raise ProbeFailure('NOT_STARTED', 'INPUT_PIN') from None


def verify_body(body, weights, report):
    report['response_bytes'] = len(body)
    observed = hashlib.sha256(body).hexdigest()
    report['observed_header_sha256'] = observed
    report['header_sha_equal'] = observed == HEADER_SHA
    check(len(body) == HEADER_BYTES, 'BODY_SIZE', 'BODY_SIZE')
    check(report['header_sha_equal'], 'HEADER_HASH', 'HEADER_HASH')
    check(struct.unpack('<Q', body[:8])[0] == HEADER_BYTES - 8, 'HEADER_PREFIX', 'HEADER_PREFIX')
    try:
        header = strict_json(body[8:].decode('utf-8'))
        check(isinstance(header, dict), 'HEADER_JSON', 'HEADER_JSON')
    except (ValueError, UnicodeError):
        raise ProbeFailure('HEADER_JSON', 'HEADER_JSON') from None
    for w in weights:
        report['geometry_checked'] += 1
        h = header.get(w['name'])
        check(isinstance(h, dict) and h.get('dtype') == w['dtype']
              and h.get('shape') == w['shape']
              and all(type(d) is int for d in h.get('shape', []))
              and h.get('data_offsets') == [w['start'] - HEADER_BYTES, w['end'] + 1 - HEADER_BYTES]
              and all(type(d) is int for d in h.get('data_offsets', [])), 'SEMANTIC', 'SEMANTIC')


def probe(weights, report, opener=None):
    try:
        report['failure_point'] = 'REQUEST'
        url_ok(URL)
        if opener is None:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), BoundedRedirect(report))
        req = urllib.request.Request(URL, headers={
            'Range': f'bytes=0-{HEADER_BYTES - 1}', 'Accept-Encoding': 'identity'})
        with opener.open(req, timeout=60) as response:
            report['http_status'] = response.status if type(response.status) is int and 100 <= response.status <= 599 else None
            final_url = response.geturl()
            report['final_host'] = HOST_LABELS.get(urllib.parse.urlsplit(final_url).hostname, 'OTHER')
            url_ok(final_url)
            check(response.status == 206, 'STATUS', 'HTTP_STATUS')
            expected = [('Content-Range', f'bytes 0-{HEADER_BYTES - 1}/{SHARD_BYTES}', 'RANGE', 'CONTENT_RANGE'),
                        ('Content-Length', str(HEADER_BYTES), 'LENGTH', 'CONTENT_LENGTH')]
            for key, val, point, code in expected:
                check(response.headers.get_all(key, []) == [val], point, code)
            check(response.headers.get_all('Content-Encoding', ['identity']) == ['identity'],
                  'ENCODING', 'CONTENT_ENCODING')
            report['failure_point'] = 'READ'
            # The single read is bounded, including the one-byte oversize sentinel.
            body = response.read(HEADER_BYTES + 1)
            verify_body(body, weights, report)
        report.update(status='PASS_HEADER_ONLY', failure_point='COMPLETE', failure_code='NONE')
    except ProbeFailure as exc:
        report.update(status='FAIL', failure_point=exc.point, failure_code=exc.code)
    except urllib.error.HTTPError as exc:
        report['http_status'] = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else None
        try:report['final_host'] = HOST_LABELS.get(urllib.parse.urlsplit(exc.url).hostname, 'OTHER')
        except (ValueError,TypeError):report['final_host'] = 'OTHER'
        exc.close()
        report.update(status='FAIL', failure_code='HTTP_ERROR')
    except Exception:
        report.update(status='FAIL', failure_code='TRANSPORT')
    return report


def run(output, frozen):
    report = diagnostic()
    # Never write into an existing or symlinked output tree.
    check(not output.exists() and not output.is_symlink(), 'NOT_STARTED', 'OUTPUT')
    try:
        output.mkdir()
    except Exception:
        raise ProbeFailure('NOT_STARTED', 'OUTPUT') from None
    try:
        weights = load_weights(frozen)
        probe(weights, report)
    except ProbeFailure as exc:
        report.update(failure_point=exc.point, failure_code=exc.code)
    temporary = output / 'HEADER_DIAGNOSTIC.json.next'
    try:
        with temporary.open('x', encoding='utf-8') as f:
            json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
            f.write('\n')
        temporary.replace(output / 'HEADER_DIAGNOSTIC.json')
    except Exception:
        raise ProbeFailure('NOT_STARTED', 'OUTPUT') from None
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output, args.frozen)
    except Exception:
        raise SystemExit(1) from None
    raise SystemExit(0 if result['status'] == 'PASS_HEADER_ONLY' else 1)


if __name__ == '__main__':
    main()
