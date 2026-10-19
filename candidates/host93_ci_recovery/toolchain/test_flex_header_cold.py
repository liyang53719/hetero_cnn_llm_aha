"""Isolated SOURCE/mocked tests only. No download, build, or native execution."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import argparse
import ast
import builtins
from contextlib import contextmanager
import copy
from email.message import Message
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
from unittest import mock

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True, type=Path)
args = parser.parse_args()
HERE = Path(__file__).absolute().parent
RAW = (HERE / 'flex_header.py').read_bytes()
MODULE_BYTES = 13781
MODULE_SHA256 = '66bad0a2aa866d8df0d6380d15620e095afcc2819d014e01c202e18f017dfce6'
if len(RAW) != MODULE_BYTES or hashlib.sha256(RAW).hexdigest() != MODULE_SHA256:
    raise ValueError('cold component pin mismatch')
g = types.ModuleType('_cold_flex_header')
g.__file__ = str(HERE / 'flex_header.py')
exec(compile(RAW, g.__file__, 'exec', dont_inherit=True), g.__dict__)
BASE = args.repo / 'development_snapshots'
PLAN = json.loads((BASE / 'canonical_verilator_dependencies_source_20261018/worker/DEPENDENCY_PLAN.json').read_bytes())
PINS = json.loads((BASE / 'canonical_host93_dependency_source_20261018/worker/PINS.json').read_bytes())
PIN = next(p for p in PINS['packages'] if p['package'] == 'libfl-dev')
PARSER_PATH = BASE / 'canonical_host93_dependency_source_20261018/worker/stage_dependencies.py'
PARSER_RAW = PARSER_PATH.read_bytes()
TESTS = []


def test(name, fn):
    fn()
    TESTS.append(name)


def rejects(fn, message):
    try:
        fn()
    except g.AcquisitionError as error:
        g.require(str(error) == message, 'unexpected rejection class/message')
        return error
    raise ValueError('missing rejection: ' + message)


@contextmanager
def patch_values(**values):
    old = {k: getattr(g, k) for k in values}
    for k, v in values.items():
        setattr(g, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(g, k, v)


PACKAGE = b'fixture-deb\n'
HEADER = b'fixture-header\n'
PARSER = ("def validate_package(raw, pin):\n"
          "    if raw != " + repr(PACKAGE) + ":\n"
          "        raise ValueError('wrong synthetic bytes')\n"
          "    return {'usr/include/FlexLexer.h': " + repr(HEADER) + "}, {}\n").encode('ascii')


@contextmanager
def fixture(parser_raw=PARSER):
    plan, pin = copy.deepcopy(PLAN), copy.deepcopy(PIN)
    p = next(p for p in plan['artifacts'] if p['package'] == 'libfl-dev')
    p.update(known_size_bytes=len(PACKAGE), max_transfer_bytes=len(PACKAGE) + 1, sha256=g.sha(PACKAGE))
    pin.update(deb_bytes=len(PACKAGE), deb_sha256=g.sha(PACKAGE))
    pin['selected'][0].update(bytes=len(HEADER), sha256=g.sha(HEADER))
    row = next(r for r in pin['members'] if r['name'] == './usr/include/FlexLexer.h')
    row.update(bytes=len(HEADER), sha256=g.sha(HEADER))
    with patch_values(PACKAGE_BYTES=len(PACKAGE), PACKAGE_SHA256=g.sha(PACKAGE),
                      HEADER_BYTES=len(HEADER), HEADER_SHA256=g.sha(HEADER),
                      PARSER_BYTES=len(parser_raw), PARSER_SHA256=g.sha(parser_raw),
                      PLAN_SHA256=g.canonical_sha(plan), PACKAGE_PIN_SHA256=g.canonical_sha(pin)):
        yield plan, pin, parser_raw


class Response:
    def __init__(self, body=PACKAGE, status=200, url=None, headers=None, chunk_size=None):
        self.body, self.status, self.pos = body, status, 0
        self.url = g.PACKAGE_URL if url is None else url
        self.headers = Message()
        for key, value in ([] if headers is None else headers):
            self.headers[key] = value
        self.requests, self.closed = [], False
        self.chunk_size = chunk_size

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, count):
        self.requests.append(count)
        if self.chunk_size is not None:
            count = min(count, self.chunk_size)
        result = self.body[self.pos:self.pos + count]
        self.pos += len(result)
        return result


class Opener:
    def __init__(self, response):
        self.response, self.calls = response, []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        return self.response


@contextmanager
def transport(response=None):
    response = Response() if response is None else response
    opener = Opener(response)
    handlers = []
    def build(*args):
        handlers.extend(args)
        return opener
    with mock.patch.object(g.urllib.request, 'build_opener', side_effect=build):
        yield opener, response, handlers


def stage_fixture(output, values):
    return g.stage(output, *values, '/diagnostic/only/parser.py')


def production_contract():
    g._checked_config(PLAN, PIN)
    g.require(g.PACKAGE_BYTES == 85600 and g.HEADER_BYTES == 6893 and g.PARSER_BYTES == 20634,
              'fixed byte contract')
    g.require(g.PACKAGE_URL == 'https://deb.debian.org/debian/pool/main/f/flex/libfl-dev_2.6.4-8.2+b4_amd64.deb',
              'fixed HTTPS source')
    g.require((g.DEADLINE_SECONDS, g.SOCKET_TIMEOUT_SECONDS, g.MAX_RECEIPT_BYTES) == (90, 30, 4096),
              'finite internal limits')
    expected = {'schema', 'purpose', 'package', 'header', 'parser', 'plan_sha256', 'package_pin_sha256'}
    g.require(set(g._receipt()) == expected, 'minimal receipt keys')

test('production_fixed_plan_pin_header_and_receipt', production_contract)


def import_no_application_io():
    ns = {'__name__': '_cold_import_guard', '__file__': '/unread/module.py'}
    def forbidden(*args, **kwargs):
        raise ValueError('unexpected import I/O')
    with mock.patch('builtins.open', side_effect=forbidden), \
            mock.patch.object(os, 'open', side_effect=forbidden), \
            mock.patch.object(Path, 'read_bytes', side_effect=forbidden), \
            mock.patch.object(g.urllib.request, 'build_opener', side_effect=forbidden):
        exec(compile(RAW, ns['__file__'], 'exec', dont_inherit=True), ns)
    g.require(callable(ns['stage']), 'import defines stage')
    g.require(not any(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(RAW))),
              'checks survive optimized mode')

test('import_has_no_application_io_or_assert_checks', import_no_application_io)


def real_parser_exact_buffer():
    with mock.patch.object(Path, 'read_bytes', side_effect=ValueError('path reopen')), \
            mock.patch('builtins.open', side_effect=ValueError('path reopen')):
        fn = g._load_parser(PARSER_RAW, '/nonexistent/label/stage_dependencies.py')
    g.require(callable(fn), 'verified parser loaded from supplied exact buffer')
    with mock.patch.object(g, 'compile', create=True, side_effect=ValueError('compile reached')):
        rejects(lambda: g._load_parser(PARSER_RAW + b'\n', str(PARSER_PATH)), 'parser buffer identity')

test('real_parser_hash_before_exact_buffer_compile_no_reopen', real_parser_exact_buffer)


def config_rejections():
    with mock.patch.object(g.urllib.request, 'build_opener', side_effect=ValueError('network reached')):
        bad = copy.deepcopy(PLAN)
        bad['transport'] = 'redirect'
        rejects(lambda: g.stage(Path('/not/used'), bad, PIN, PARSER_RAW, str(PARSER_PATH)), 'plan identity')
        bad = copy.deepcopy(PIN)
        bad['members'][0]['mode'] = '0o777'
        rejects(lambda: g.stage(Path('/not/used'), PLAN, bad, PARSER_RAW, str(PARSER_PATH)), 'package pin identity')
        rejects(lambda: g._checked_config([], PIN), 'configuration type')
        bad = copy.deepcopy(PLAN)
        bad['artifacts'][3]['url'] = 'https://elsewhere.invalid/secret'
        with patch_values(PLAN_SHA256=g.canonical_sha(bad)):
            rejects(lambda: g._checked_config(bad, PIN), 'package plan contract')
        bad = copy.deepcopy(PIN)
        bad['selected'][0]['kind'] = 'symlink'
        with patch_values(PACKAGE_PIN_SHA256=g.canonical_sha(bad)):
            rejects(lambda: g._checked_config(PLAN, bad), 'single selected header contract')
        bad = copy.deepcopy(PIN)
        bad['members'][3]['linkname'] = 'foreign'
        with patch_values(PACKAGE_PIN_SHA256=g.canonical_sha(bad)):
            rejects(lambda: g._checked_config(PLAN, bad), 'header member contract')
        bad = copy.deepcopy(PIN)
        bad['control_fields']['Architecture'] = 'arm64'
        with patch_values(PACKAGE_PIN_SHA256=g.canonical_sha(bad)):
            rejects(lambda: g._checked_config(PLAN, bad), 'package pin contract')

test('wrong_plan_pin_url_selection_member_and_architecture_refused', config_rejections)


def success():
    with tempfile.TemporaryDirectory() as tmp, fixture() as values:
        out = Path(tmp) / 'output'
        response = Response(headers=[('Content-Length', str(len(PACKAGE))), ('Content-Encoding', 'identity')], chunk_size=3)
        with transport(response) as (opener, response, handlers):
            receipt = stage_fixture(out, values)
        g.require(len(opener.calls) == 1 and len(handlers) == 1
                  and isinstance(handlers[0], g._NoRedirect), 'default opener with one no-redirect handler')
        request, timeout = opener.calls[0]
        g.require(request.full_url == g.PACKAGE_URL and request.get_method() == 'GET'
                  and request.get_header('Accept-encoding') == 'identity' and 0 < timeout <= 30,
                  'fixed request and finite socket timeout')
        g.require(response.closed and sum(response.requests) >= len(PACKAGE)
                  and response.pos == len(PACKAGE), 'bounded response consumed and closed')
        actual = sorted(p.relative_to(out).as_posix() for p in out.rglob('*'))
        g.require(actual == ['RECEIPT.json', 'include', 'include/FlexLexer.h'], 'only two regular outputs')
        g.require((out / 'include/FlexLexer.h').read_bytes() == HEADER, 'header exact bytes')
        expected_raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode('ascii')
        g.require((out / 'RECEIPT.json').read_bytes() == expected_raw and receipt == g._receipt(), 'receipt exact serialization')
        for path in (out / 'RECEIPT.json', out / 'include/FlexLexer.h'):
            st = path.stat()
            g.require(st.st_mode & 0o777 == 0o600 and st.st_nlink == 1, 'regular private single-link output')

test('synthetic_end_to_end_two_file_success', success)


def bad_transport(response, message):
    with tempfile.TemporaryDirectory() as tmp, fixture() as values, transport(response) as (opener, resp, _):
        out = Path(tmp) / 'output'
        rejects(lambda: stage_fixture(out, values), message)
        g.require(not out.exists() and len(opener.calls) == 1 and resp.closed, 'reject before output and close response')
        g.require(resp.pos <= len(PACKAGE) + 1, 'at most size plus one consumed')


for name, response, message in (
    ('wrong_package', Response(body=b'x' * len(PACKAGE)), 'package identity'),
    ('oversize', Response(body=PACKAGE + b'!'), 'package size exceeded'),
    ('short', Response(body=PACKAGE[:-1]), 'package identity'),
    ('status', Response(status=206), 'HTTP status refused'),
    ('redirect_status', Response(status=302), 'HTTP status refused'),
    ('changed_response_url', Response(url='https://other.invalid/secret'), 'response URL refused'),
    ('content_length_short', Response(headers=[('Content-Length', '1')]), 'content length refused'),
    ('content_length_oversize', Response(headers=[('Content-Length', '99999')]), 'content length refused'),
    ('content_length_duplicate', Response(headers=[('Content-Length', '12'), ('Content-Length', '12')]), 'content length refused'),
    ('content_length_signed', Response(headers=[('Content-Length', '+12')]), 'content length refused'),
    ('content_length_unicode', Response(headers=[('Content-Length', '\u0661\u0662')]), 'content length refused'),
    ('compressed_body', Response(headers=[('Content-Encoding', 'gzip')]), 'content encoding refused'),
    ('encoding_duplicate', Response(headers=[('Content-Encoding', 'identity'), ('Content-Encoding', 'identity')]), 'content encoding refused'),
):
    test(name + '_refused', lambda response=response, message=message: bad_transport(response, message))


def redirects():
    handler = g._NoRedirect()
    for code in (301, 302, 303, 307, 308):
        fn = getattr(handler, 'http_error_' + str(code))
        rejects(lambda fn=fn, code=code: fn(None, None, code, 'secret', {'Location': 'https://other.invalid/secret'}),
                'redirect refused')
    rejects(lambda: handler.redirect_request(None, None, 302, 'secret', {}, 'https://other.invalid/secret'), 'redirect refused')

test('all_redirect_handlers_refuse_before_location_use', redirects)


def safe_transport_error():
    with fixture(), mock.patch.object(g.urllib.request, 'build_opener',
                                      side_effect=RuntimeError('proxy password secret')):
        err = rejects(lambda: g._download(g.time.monotonic() + 90), 'transport failed')
        g.require(err.__suppress_context__, 'transport error context suppressed')

test('transport_errors_do_not_expose_remote_or_proxy_text', safe_transport_error)


def deadline():
    with fixture(), transport() as (opener, response, _), mock.patch.object(g.time, 'monotonic', return_value=100):
        rejects(lambda: g._download(99), 'acquisition deadline')
        g.require(not opener.calls, 'expired deadline makes no network request')
    with fixture(), transport() as (_, response, _), mock.patch.object(g.time, 'monotonic', side_effect=[0, 0, 0, 91]):
        rejects(lambda: g._download(90), 'acquisition deadline')
        g.require(response.closed, 'body deadline closes response')

test('monotonic_deadline_before_open_and_after_read', deadline)


def selected_rejection(parser_raw, message):
    with tempfile.TemporaryDirectory() as tmp, fixture(parser_raw) as values, transport():
        out = Path(tmp) / 'out'
        rejects(lambda: stage_fixture(out, values), message)
        g.require(not out.exists(), 'invalid parser selection produces no output')


test('selected_header_mismatch_refused', lambda: selected_rejection(
    b"def validate_package(raw, pin):\n    return {'usr/include/FlexLexer.h': b'wrong'}, {}\n", 'selected header identity'))
test('extra_selected_member_refused', lambda: selected_rejection(
    b"def validate_package(raw, pin):\n    return {'unexpected': b'x'}, {}\n", 'selected header set'))
test('parser_rejection_redacted', lambda: selected_rejection(
    b"def validate_package(raw, pin):\n    raise ValueError('untrusted package secret')\n", 'package parser rejected'))


def destination_refusals():
    with tempfile.TemporaryDirectory() as tmp, fixture() as values, \
            mock.patch.object(g.urllib.request, 'build_opener', side_effect=ValueError('network reached')):
        base = Path(tmp)
        existing = base / 'existing'
        existing.mkdir(mode=0o700)
        rejects(lambda: stage_fixture(existing, values), 'output destination exists')
        link = base / 'link'
        link.symlink_to(existing, target_is_directory=True)
        rejects(lambda: stage_fixture(link, values), 'output destination exists')
        rejects(lambda: stage_fixture(link / 'out', values), 'acquisition failed')
        (base / 'regular').write_bytes(b'unmodified')
        rejects(lambda: stage_fixture(base / 'regular', values), 'output destination exists')
        os.chmod(existing, 0o755)
        rejects(lambda: stage_fixture(existing / 'out', values), 'output parent must be private')
        rejects(lambda: stage_fixture(base / 'missing' / 'out', values), 'acquisition failed')
        rejects(lambda: stage_fixture(Path('relative/out'), values), 'absolute output directory required')
        g.require((base / 'regular').read_bytes() == b'unmodified' and not (existing / 'out').exists(),
                  'existing destinations unmodified')

test('existing_file_dir_symlink_ancestor_nonprivate_and_missing_parent_refused', destination_refusals)


def exclusive_write_refusals():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / 'target'
        target.write_bytes(b'untouched')
        (root / 'FlexLexer.h').symlink_to(target)
        fd = os.open(root, g.DIRECTORY_FLAGS)
        try:
            try:
                g._write_at(fd, 'FlexLexer.h', b'bad')
            except FileExistsError:
                pass
            else:
                raise ValueError('exclusive writer followed symlink')
        finally:
            os.close(fd)
        g.require(target.read_bytes() == b'untouched', 'nofollow exclusive write preserved target')

test('exclusive_writer_refuses_symlink_and_preserves_target', exclusive_write_refusals)

print(json.dumps({'status': 'PASS_SOURCE_AND_SYNTHETIC_ONLY', 'test_count': len(TESTS),
                  'tests': TESTS, 'network_or_native_execution': False}, sort_keys=True))
