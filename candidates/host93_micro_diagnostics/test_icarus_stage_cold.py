"""Cold synthetic-only checks; injected TARGET is the verified production buffer.

Only the synthetic_identity test helper temporarily overrides production package
length/digest. The production API has no pin override and no test mode.
No downloaded bytes or native/HDL programs are used or invoked by this suite.
"""
import contextlib
import email.message
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import types
import unittest
from unittest import mock

M = TARGET
REAL_ZSTD_LIBRARY = M._zstd_library
OFFICIAL_SELECTED_BASENAMES = '''blif-s.conf blif.conf blif.tgt cadpli.vpl
include/constants.vams include/disciplines.vams ivl ivlpp null-s.conf null.conf
null.tgt pcb-s.conf pcb.conf pcb.tgt sizer-s.conf sizer.conf sizer.tgt stub-s.conf
stub.conf stub.tgt system.vpi v2005_math.vpi v2009.vpi va_math.vpi vhdl-s.conf
vhdl.conf vhdl.tgt vhdl_sys.vpi vhdl_textio.vpi vhdlpp vlog95-s.conf vlog95.conf
vlog95.tgt vpi_debug.vpi vvp-s.conf vvp.conf vvp.tgt'''.split()


def tar_header(name, body=b'', kind=b'0', mode=0o644, link=b''):
    raw = bytearray(512)
    name = name.encode('ascii')
    if len(name) > 100:
        raise ValueError('test_name_bound')
    raw[:len(name)] = name
    for a, b, value in ((100,108,mode),(108,116,0),(116,124,0),
                        (124,136,len(body)),(136,148,0)):
        raw[a:b] = ('%0*o' % (b-a-1, value)).encode('ascii') + b'\0'
    raw[148:156] = b'        '
    raw[156:157] = kind
    raw[157:157+len(link)] = link
    raw[257:265] = b'ustar  \0'
    raw[148:156] = ('%06o' % sum(raw)).encode('ascii') + b'\0 '
    return bytes(raw)


def tar_entry(name, body=b'', kind=b'0', mode=0o644, link=b''):
    return tar_header(name, body, kind, mode, link) + body + b'\0' * (-len(body) % 512)


def tar_archive(entries):
    raw = b''.join(entries) + b'\0' * 1024
    return raw + b'\0' * (-len(raw) % 10240)


def ar_member(name, body):
    return (name.encode('ascii').ljust(16) + b'0'.ljust(12) + b'0'.ljust(6) +
            b'0'.ljust(6) + b'100644'.ljust(8) + str(len(body)).encode('ascii').ljust(10)
            + b'`\n' + body + (b'\n' if len(body) % 2 else b''))


def package(data=None, control=None, compression='zst'):
    if data is None:
        data = tar_archive([tar_entry('./', kind=b'5', mode=0o755)] + [
            tar_entry('./' + p, ('mock:' + p + '\n').encode('ascii'),
                      mode=0o755 if p in M.EXECUTABLE_PATHS else 0o644)
            for p in sorted(M.ALL_DATA_FILES)])
    if control is None:
        control = tar_archive([tar_entry('./control',
             b'Package: iverilog\nVersion: 12.0-2build2\nArchitecture: amd64\nDescription: mock only\n')])
    compress = lambda body: b'\x28\xb5\x2f\xfd' + body
    return (b'!<arch>\n' + ar_member('debian-binary', b'2.0\n') +
            ar_member('control.tar.' + compression, compress(control)) +
            ar_member('data.tar.' + compression, compress(data)))


class MockZstd:
    def ZSTD_findFrameCompressedSize(self, source, size):
        return size
    def ZSTD_decompress(self, destination, capacity, source, size):
        payload = source.raw[4:]
        if len(payload) > capacity:
            return 2**64 - 1
        ctypes.memmove(destination, payload, len(payload))
        return len(payload)
    def ZSTD_isError(self, value):
        return int(value == 2**64 - 1)


@contextlib.contextmanager
def mock_library():
    yield MockZstd(), {'kind': 'existing_host_libzstd_same_inode', 'basename': 'libzstd.so.1.0.0',
                       'bytes': 100, 'sha256': 'a'*64, 'device': 1, 'inode': 1}


@contextlib.contextmanager
def synthetic_identity(raw):
    # The sole test-only override point. No production test mode or override API.
    ar = []
    tar = {}
    selected = {}
    pos = 8
    for i in range(3):
        if pos + 60 > len(raw):
            break
        h = raw[pos:pos+60]
        name = h[:16].rstrip(b' ').decode('ascii')
        size = int(h[48:58])
        body = raw[pos+60:pos+60+size]
        ar.append((name,size,hashlib.sha256(body).hexdigest()))
        if name.endswith('.zst'):
            expanded = body[4:]
            tar[name] = (len(expanded),hashlib.sha256(expanded).hexdigest())
            if name.startswith('data.'):
                try:
                    files,_ = M._parse_tar(expanded,M.ALL_DATA_FILES,complete=False)
                    selected = {p:(len(b),hashlib.sha256(b).hexdigest()) for p,b in files.items()
                                if p in M.SELECTED_PATHS}
                except M.AcquisitionError:
                    pass
        pos += 60 + size + (size % 2)
    while len(ar) < 3:
        ar.append(M.AR_PINS[len(ar)])
    with mock.patch.object(M,'PACKAGE_BYTES',len(raw)), \
         mock.patch.object(M,'PACKAGE_SHA256',hashlib.sha256(raw).hexdigest()), \
         mock.patch.object(M,'AR_PINS',tuple(ar)), \
         mock.patch.object(M,'TAR_PINS',tar), \
         mock.patch.object(M,'SELECTED_PINS',selected), \
         mock.patch.object(M,'_zstd_library',mock_library):
        yield


class FakeResponse:
    def __init__(self, raw, *, status=200, url=None, headers=()):
        self.body = io.BytesIO(raw)
        self.status = status
        self.url = M.PACKAGE_URL if url is None else url
        self.headers = email.message.Message()
        for key, value in headers:
            self.headers[key] = value
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url
    def read(self, n):
        return self.body.read(n)


class ColdTests(unittest.TestCase):
    def setUp(self):
        self.no_network = mock.patch.object(M.urllib.request, 'build_opener',
                                            side_effect=RuntimeError('NETWORK_FORBIDDEN_SENTINEL'))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)
        self.no_native = mock.patch.object(M, '_zstd_library', mock_library)
        self.no_native.start()
        self.addCleanup(self.no_native.stop)

    def rejected(self, fn, label):
        with self.assertRaises(M.AcquisitionError) as caught:
            fn()
        self.assertEqual(str(caught.exception), label)

    def test_fixed_official_inventory(self):
        expected = {'usr/bin/iverilog', 'usr/bin/vvp'} | {
            'usr/lib/x86_64-linux-gnu/ivl/' + p for p in OFFICIAL_SELECTED_BASENAMES}
        self.assertEqual(set(M.SELECTED_PATHS), expected)
        self.assertEqual(len(M.SELECTED_PATHS), 39)
        self.assertEqual(len(M.ALL_DATA_FILES), 83)
        self.assertEqual(len(M.EXECUTABLE_PATHS), 5)
        self.assertEqual(M.PACKAGE_BYTES, 2125764)
        self.assertEqual(M.PACKAGE_SHA256,
            'f19394cee05ad526e0eb3873bc6c17a5828f56df17fbe2db40cb66513a2d4667')

    def test_identity_precedes_parser(self):
        with mock.patch.object(M, '_ar_entries', side_effect=RuntimeError('PARSER_MUST_NOT_RUN')) as parser:
            self.rejected(lambda: M.validate_package(b'bad'), 'package_identity')
            parser.assert_not_called()

    def test_zstd_mock_synthetic_success(self):
        raw = package()
        with synthetic_identity(raw):
            selected, receipt = M.validate_package(raw)
        self.assertEqual(set(selected), set(M.SELECTED_PATHS))
        self.assertEqual(len(receipt['selected']), 39)
        self.assertFalse(receipt['runtime_qualified'])
        self.assertFalse(receipt['executables_invoked'])
        self.assertNotIn('mock:', json.dumps(receipt))

    def test_other_compression_refused(self):
        self.rejected(lambda: M._expand(b'x','data.tar.xz',20000), 'compression_refused')

    def test_ar_magic(self):
        raw = b'badmagic' + package()[8:]
        with synthetic_identity(raw):
            self.rejected(lambda: M.validate_package(raw), 'ar_magic')

    def test_ar_extra_entry(self):
        raw = package() + ar_member('extra', b'abc')
        with synthetic_identity(raw):
            self.rejected(lambda: M.validate_package(raw), 'ar_trailing_or_extra_member')

    def test_ar_unrecognized_name(self):
        raw = b'!<arch>\n' + ar_member('debian-binary', b'2.0\n') + ar_member('unrecognized', b'fake')
        with mock.patch.object(M,'PACKAGE_BYTES',len(raw)), mock.patch.object(M,'PACKAGE_SHA256',hashlib.sha256(raw).hexdigest()):
            self.rejected(lambda: M.validate_package(raw), 'ar_name_or_order')

    def test_ar_odd_padding(self):
        raw = b'!<arch>\n' + ar_member('debian-binary', b'2.0\n') + ar_member('control.tar.zst', b'x')[:-1] + b'X'
        with synthetic_identity(raw):
            self.rejected(lambda: M.validate_package(raw), 'ar_padding')

    def test_ar_truncated(self):
        raw = package()[:-100]
        with synthetic_identity(raw):
            self.rejected(lambda: M.validate_package(raw), 'ar_member_truncated')

    def test_tar_symlink(self):
        raw = tar_archive([tar_entry('./usr/bin/iverilog', kind=b'2', mode=0o755, link=b'/tmp/escape')])
        self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_type_refused')

    def test_tar_hardlink_and_extensions(self):
        for kind in (b'1', b'x', b'g', b'L', b'K', b'3', b'4', b'6', b'7', b'\0'):
            raw = tar_archive([tar_entry('./usr/bin/iverilog', kind=kind)])
            with self.subTest(kind=kind):
                self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_type_refused')

    def test_tar_traversal(self):
        for path in ('./../escape', './usr//bin/iverilog', './usr/./bin/iverilog'):
            raw = tar_archive([tar_entry(path)])
            self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_path_components')

    def test_tar_absolute_and_backslash(self):
        raw = tar_archive([tar_entry('/usr/bin/iverilog')])
        self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_relative_prefix')
        raw = tar_archive([tar_entry('./usr\\bin\\iverilog')])
        self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_path_syntax')

    def test_tar_duplicate(self):
        e = tar_entry('./usr/bin/iverilog')
        raw = tar_archive([e, e])
        self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_duplicate_path')

    def test_tar_unlisted_file(self):
        raw = tar_archive([tar_entry('./usr/lib/x86_64-linux-gnu/ivl/evil')])
        self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_inventory_refused')

    def test_tar_missing_file(self):
        raw = package(data=tar_archive([]))
        with synthetic_identity(raw):
            self.rejected(lambda: M.validate_package(raw), 'tar_file_inventory')

    def test_tar_checksum(self):
        raw = bytearray(tar_archive([tar_entry('./usr/bin/iverilog')]))
        raw[0] = ord('X')
        self.rejected(lambda: M._parse_tar(bytes(raw), M.ALL_DATA_FILES, complete=False), 'tar_checksum')

    def test_tar_padding_and_terminator(self):
        raw = bytearray(tar_archive([tar_entry('./usr/bin/iverilog', b'x')]))
        raw[513] = 1
        self.rejected(lambda: M._parse_tar(bytes(raw), M.ALL_DATA_FILES, complete=False), 'tar_member_padding')
        self.rejected(lambda: M._parse_tar(b'\0' * 512, M.ALL_DATA_FILES, complete=False), 'tar_terminator')
        self.rejected(lambda: M._parse_tar(b'\0' * 11264, M.ALL_DATA_FILES, complete=False), 'tar_terminator')

    def test_tar_mode_and_executable_mode(self):
        raw = tar_archive([tar_entry('./usr/bin/iverilog', mode=0o4755)])
        self.rejected(lambda: M._parse_tar(raw, M.ALL_DATA_FILES, complete=False), 'tar_mode_refused')
        data = tar_archive([tar_entry('./' + p, mode=0o644) for p in sorted(M.ALL_DATA_FILES)])
        raw = package(data=data)
        with synthetic_identity(raw):
            self.rejected(lambda: M.validate_package(raw), 'executable_archive_mode')

    def test_control_identity_and_duplicate(self):
        self.rejected(lambda: M._control_identity(b'Package: other\nVersion: 12.0-2build2\nArchitecture: amd64\n'), 'control_identity')
        self.rejected(lambda: M._control_identity(b'Package: iverilog\nPackage: iverilog\n'), 'control_fields_refused')
        self.rejected(lambda: M._control_identity(b'\xff'), 'control_parse_failed')

    def test_zstd_frame_and_decoded_identity(self):
        raw = b'\x28\xb5\x2f\xfd' + b'\0' * 10240
        with mock.patch.object(M,'TAR_PINS',{'data.tar.zst':(10240,hashlib.sha256(raw[4:]).hexdigest())}), \
             mock.patch.object(M,'_zstd_library',mock_library):
            self.assertEqual(M._expand(raw,'data.tar.zst',20000)[0],raw[4:])
            with mock.patch.object(MockZstd,'ZSTD_findFrameCompressedSize',return_value=len(raw)-1):
                self.rejected(lambda: M._expand(raw,'data.tar.zst',20000),'compressed_stream_framing')
            self.rejected(lambda: M._expand(raw[:-1],'data.tar.zst',20000),'decompression_bound')
            self.rejected(lambda: M._expand(raw[:-1]+b'x','data.tar.zst',20000),'expanded_tar_identity')
            self.rejected(lambda: M._expand(raw,'data.tar.zst',2048),'decompression_bound')

    def test_zstd_bad_magic(self):
        self.rejected(lambda: M._expand(b'bad','data.tar.zst',M.MAX_DATA_TAR_BYTES),'zstd_input_refused')

    def test_deadline(self):
        self.rejected(lambda: M._remaining(time.monotonic() - 1), 'acquisition_deadline')

    def download(self, response, raw):
        opener = mock.Mock()
        opener.open.return_value = response
        with synthetic_identity(raw), mock.patch.object(M.urllib.request, 'build_opener', return_value=opener):
            result = M._download(time.monotonic() + 5)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, M.PACKAGE_URL)
        self.assertEqual(request.method, 'GET')
        self.assertEqual(request.get_header('Accept-encoding'), 'identity')
        return result

    def test_mock_transport_success(self):
        raw = b'fixed synthetic bytes'
        self.assertEqual(self.download(FakeResponse(raw, headers=(('Content-Length', str(len(raw))),)), raw), raw)
        self.assertEqual(self.download(FakeResponse(raw), raw), raw)

    def test_mock_transport_status_url_and_headers(self):
        raw = b'fixed synthetic bytes'
        cases = [({'status': 302}, 'http_status_refused'),
                 ({'url': 'https://other.invalid/package'}, 'response_url_refused'),
                 ({'headers': [('Content-Length', '1')]}, 'content_length_refused'),
                 ({'headers': [('Content-Length', str(len(raw)))] * 2}, 'content_length_refused'),
                 ({'headers': [('Content-Encoding', 'gzip')]}, 'content_encoding_refused')]
        for kwargs, label in cases:
            self.rejected(lambda: self.download(FakeResponse(raw, **kwargs), raw), label)

    def test_mock_transport_short_oversize_and_digest(self):
        raw = b'fixed synthetic bytes'
        for body, label in ((raw[:-1], 'package_identity'), (raw+b'x', 'package_size_exceeded'),
                            (b'x'*len(raw), 'package_identity')):
            self.rejected(lambda: self.download(FakeResponse(body), raw), label)

    def test_redirect_refused_before_target(self):
        handler = M._NoRedirect()
        for method in ('http_error_301','http_error_302','http_error_303','http_error_307','http_error_308'):
            self.rejected(lambda: getattr(handler, method)(None,None,302,'SECRET',None), 'redirect_refused')
        self.rejected(lambda: handler.redirect_request(None,None,302,'SECRET',None,'SECRET_URL'), 'redirect_refused')

    def test_transport_error_redaction(self):
        self.rejected(lambda: M._download(time.monotonic()+5), 'transport_failed')

    def test_stage_synthetic_modes_inventory_receipt(self):
        raw = package()
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            parent = Path(temp)
            os.chmod(parent, 0o700)
            destination = parent / 'stage'
            with synthetic_identity(raw), mock.patch.object(M, '_download', return_value=raw):
                receipt = M.stage(destination)
                self.assertEqual(M.verify_stage(destination, receipt), receipt)
            actual = {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
            self.assertEqual(actual, set(M.SELECTED_PATHS) | {'RECEIPT.json'})
            self.assertEqual(json.loads((destination/'RECEIPT.json').read_bytes()), receipt)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
            for path in M.SELECTED_PATHS:
                st = (destination/path).stat()
                self.assertEqual(stat.S_IMODE(st.st_mode), 0o700 if path in M.EXECUTABLE_PATHS else 0o600)
                self.assertEqual(st.st_nlink, 1)
                self.assertEqual((destination/path).read_bytes(), ('mock:' + path + '\n').encode('ascii'))

    def test_stage_existing_and_symlink_destination(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            root = Path(temp)
            (root/'existing').mkdir()
            (root/'link').symlink_to(root/'existing', target_is_directory=True)
            for leaf in ('existing','link'):
                with mock.patch.object(M, '_download') as download:
                    self.rejected(lambda: M.stage(root/leaf), 'destination_exists')
                    download.assert_not_called()

    def test_stage_parent_privacy_and_symlink(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            root = Path(temp)
            (root/'public').mkdir(mode=0o755)
            self.rejected(lambda: M.stage(root/'public'/'stage'), 'destination_parent_not_private')
            (root/'link').symlink_to(root/'public', target_is_directory=True)
            self.rejected(lambda: M.stage(root/'link'/'stage'), 'acquisition_failed')

    def test_stage_invalid_buffer_creates_nothing(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            destination = Path(temp)/'stage'
            with mock.patch.object(M, '_download', return_value=b'bad'):
                self.rejected(lambda: M.stage(destination), 'package_identity')
            self.assertFalse(destination.exists())

    def test_stage_errors_do_not_leak(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            with mock.patch.object(M, '_download', side_effect=RuntimeError('SECRET_URL_TOKEN_PATH')):
                self.rejected(lambda: M.stage(Path(temp)/'stage'), 'acquisition_failed')

    def test_writer_rejects_existing_symlink(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            path = Path(temp)
            (path/'target').write_bytes(b'unchanged')
            (path/'file').symlink_to(path/'target')
            fd = os.open(path, M.DIRECTORY_FLAGS)
            try:
                with self.assertRaises(FileExistsError):
                    M._write_at(fd, 'file', b'evil', 0o600)
            finally:
                os.close(fd)
            self.assertEqual((path/'target').read_bytes(), b'unchanged')


    def test_verify_stage_detects_body_and_receipt_replacement(self):
        raw = package()
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            destination = Path(temp)/'stage'
            with synthetic_identity(raw), mock.patch.object(M, '_download', return_value=raw):
                receipt = M.stage(destination)
                victim = destination/M.SELECTED_PATHS[0]
                original = victim.read_bytes()
                victim.write_bytes(b'x' * len(original))
                self.rejected(lambda: M.verify_stage(destination, receipt), 'verified_file_identity')
                victim.write_bytes(original)
                (destination/'RECEIPT.json').write_bytes(b'{}')
                self.rejected(lambda: M.verify_stage(destination, receipt), 'verified_file_inode')

    def test_verify_stage_rejects_extra_files_and_symlinks(self):
        raw = package()
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            destination = Path(temp)/'stage'
            with synthetic_identity(raw), mock.patch.object(M, '_download', return_value=raw):
                receipt = M.stage(destination)
                (destination/'extra').write_bytes(b'x')
                self.rejected(lambda: M.verify_stage(destination, receipt), 'verified_inventory')
                (destination/'extra').unlink()
                victim = destination/M.SELECTED_PATHS[0]
                victim.unlink()
                victim.symlink_to(destination/M.SELECTED_PATHS[1])
                self.rejected(lambda: M.verify_stage(destination, receipt), 'stage_verification_failed')


    def test_exact_official_package_with_mock_decoder(self):
        identity = {'kind': 'existing_host_libzstd_same_inode', 'basename': 'libzstd.so.1.0.0',
                    'bytes': 100, 'sha256': 'a'*64, 'device': 1, 'inode': 1}
        class FixedMockDecoder(MockZstd):
            def ZSTD_decompress(self, destination, capacity, source, size):
                digest = hashlib.sha256(source.raw).hexdigest()
                bodies = {
                    '8a41e241b984bd48d81c7de952a932ea037e7df1877ea367d99278330e632917': FIXED_CONTROL_TAR,
                    '60583389fb0eba7a4b9407c850624648e22ea80f3e85d50e1e4f25deaaa57f45': FIXED_DATA_TAR}
                body = bodies[digest]
                if len(body) != capacity:
                    raise RuntimeError('fixed_mock_capacity')
                ctypes.memmove(destination, body, len(body))
                return len(body)
        @contextlib.contextmanager
        def fixed_decoder():
            yield FixedMockDecoder(), identity
        with mock.patch.object(M, '_zstd_library', fixed_decoder):
            selected, receipt = M.validate_package(FIXED_PACKAGE)
        self.assertEqual(len(selected), 39)
        self.assertEqual(sum(len(x) for x in selected.values()), 6379063)
        self.assertEqual(receipt['control_tar_sha256'],
                         'aeac2541904d12b884d3b263948dc6b5e05593d712fbb9705b56403810fd631e')
        self.assertEqual(receipt['data_tar_sha256'],
                         'd520b7e4086b27bc55b984dd3ca73f7a58bbe2f310c877ad67c3e11eadf0fe01')
        self.assertEqual({p:(len(b),hashlib.sha256(b).hexdigest()) for p,b in selected.items()}, M.SELECTED_PINS)
        self.assertLess(len(M._checked_receipt(receipt)), M.MAX_RECEIPT_BYTES)

    def test_zstd_preflight_precedes_network(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            with mock.patch.object(M, '_zstd_library', side_effect=M.AcquisitionError('zstd_decoder_unavailable')), \
                 mock.patch.object(M, '_download') as download:
                self.rejected(lambda: M.stage(Path(temp)/'stage'), 'zstd_decoder_unavailable')
                download.assert_not_called()


    def test_zstd_host_adapter_mock_same_inode(self):
        def st(mode, inode, size):
            return types.SimpleNamespace(st_dev=1, st_ino=inode, st_uid=0, st_mode=mode,
                st_nlink=1, st_size=size, st_mtime_ns=1, st_ctime_ns=1)
        directory = st(stat.S_IFDIR|0o755, 1, 0)
        link = st(stat.S_IFLNK|0o777, 2, 16)
        library = st(stat.S_IFREG|0o644, 3, 7)
        fake = mock.Mock()
        def named(name, **kwargs):
            return link if name == 'libzstd.so.1' else library
        with mock.patch.object(M.os,'open',side_effect=[3,4,5,6,7]) as opened, \
             mock.patch.object(M.os,'close') as closed, \
             mock.patch.object(M.os,'fstat',side_effect=lambda fd: library if fd == 7 else directory), \
             mock.patch.object(M.os,'stat',side_effect=named), \
             mock.patch.object(M.os,'readlink',return_value='libzstd.so.1.5.7'), \
             mock.patch.object(M.os,'read',side_effect=[b'library',b'',b'library',b'']), \
             mock.patch.object(M.os,'lseek'), \
             mock.patch.object(M.ctypes,'CDLL',return_value=fake) as cdll:
            with REAL_ZSTD_LIBRARY() as (decoder, identity):
                self.assertIs(decoder, fake)
                self.assertEqual(identity['sha256'],hashlib.sha256(b'library').hexdigest())
            cdll.assert_called_once_with('/proc/self/fd/7',mode=M.ctypes.RTLD_LOCAL)
            self.assertEqual(opened.call_args_list[-1].args[1],M.READ_FLAGS)
            self.assertEqual(fake.ZSTD_decompress.argtypes,
                             [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t])
            self.assertEqual(fake.ZSTD_decompress.restype,ctypes.c_size_t)
            self.assertEqual(fake.ZSTD_findFrameCompressedSize.restype,ctypes.c_size_t)
            self.assertEqual(fake.ZSTD_isError.restype,ctypes.c_uint)
            fake.ZSTD_decompress.assert_not_called()
            self.assertIn(mock.call(7),closed.call_args_list)
            self.assertIn(mock.call(6),closed.call_args_list)

    def test_zstd_host_adapter_missing_is_redacted(self):
        with mock.patch.object(M.os,'open',side_effect=FileNotFoundError('SECRET_HOST_PATH')):
            def attempt():
                with REAL_ZSTD_LIBRARY():
                    pass
            self.rejected(attempt,'zstd_decoder_unavailable')


def run():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ColdTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    return result.testsRun
