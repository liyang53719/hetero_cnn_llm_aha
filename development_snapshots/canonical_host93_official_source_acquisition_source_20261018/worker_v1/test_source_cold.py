"""Tiny synthetic tar/gzip and network mocks only. No real transport or child."""
import contextlib
import email.message
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE_BYTES = 24283
SOURCE_SHA = '1395add8592dbc8a7380cf826aea9369afedcc9b0527e43fdc1c3953dc59cfd4'
raw = (HERE / 'acquire_official_source.py').read_bytes()
if len(raw) != SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
    raise ValueError('fixed cold source identity')
worker = types.ModuleType('fixed_source_worker')
worker.__file__ = str(HERE / 'acquire_official_source.py')
exec(compile(raw, worker.__file__, 'exec', dont_inherit=True), worker.__dict__)
base, plan, fixed_selected = worker.load_inputs()
DATA = b'tiny source bytes; never executed\n'
NAME = 'src/tiny.cpp'
PREFIX = worker.PREFIX


def selected(data=DATA, mode='100644'):
    return {NAME: {'path': NAME, 'mode': mode, 'bytes': len(data),
                   'git_blob_sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}}


def entries():
    return [(PREFIX + '/', b'', tarfile.DIRTYPE, 0o755, ''),
            (PREFIX + '/' + NAME, DATA, tarfile.REGTYPE, 0o644, '')]


def tar_bytes(items=None, format=tarfile.USTAR_FORMAT, pax_headers=None):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w', format=format, pax_headers=pax_headers) as archive:
        for name, data, kind, mode, link in items if items is not None else entries():
            info = tarfile.TarInfo(name)
            info.type, info.mode, info.size, info.linkname = kind, mode, len(data), link
            archive.addfile(info, io.BytesIO(data))
    raw = result.getvalue()
    if pax_headers is not None:
        header = bytearray(raw[:512])
        header[:100] = b'pax_global_header'.ljust(100, b'\0')
        header[148:156] = b'        '
        header[148:156] = ('%06o\0 ' % sum(header)).encode()
        raw = bytes(header) + raw[512:]
    return raw


def observation():
    return {'received_bytes': 0, 'retained_archive_bytes': 0, 'archive_complete': False,
            'expanded_bytes': 0, 'tar_entries': 0, 'selected_bytes': 0,
            'verified_members': [], 'unselected_symlinks_skipped': 0}


def budget(clock=lambda: 1):
    return base.Budget({'total_transfer_bytes': worker.ARCHIVE_CAP, 'elapsed_check_seconds': 400}, clock=clock)


class Response(io.BytesIO):
    def __init__(self, data, url=worker.API_URL, status=200):
        super().__init__(data)
        self.status, self.url = status, url
        self.headers = email.message.Message()
        self.headers['Content-Length'] = str(len(data))
    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        return self.response


class Cold(unittest.TestCase):
    def setUp(self):
        self.deny = mock.patch.object(socket, 'socket', side_effect=AssertionError('network forbidden'))
        self.deny.start()
    def tearDown(self):
        self.deny.stop()
    def scan(self, raw, pins=None, obs=None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            worker.scan_tar(io.BytesIO(raw), pins or selected(), root, base, budget(), obs or observation())
            return (root / NAME).read_bytes(), stat.S_IMODE((root / NAME).stat().st_mode)
    def rejected(self, items, reason=None):
        with self.assertRaisesRegex((ValueError, base.AcquisitionError), reason or '.'):
            self.scan(tar_bytes(items))
    def run_mock(self, root, response, pins=None, b=None):
        return worker.execute(base, plan, pins or selected(), root, b or budget(), Opener(response))

    def test_01_fixed_inputs_no_old_group_mutation(self):
        self.assertEqual((len(fixed_selected), sum(x['bytes'] for x in fixed_selected.values())), (473,11747893))
        self.assertEqual(base.GROUP_HASHES['verilator'], 'dce545ae9c24a9c05d138edc113c9d72694d62152f8486c9dea6daab33958e6e')
        self.assertIsNone(plan['archive_sha256_before_fetch'])
        self.assertEqual(plan['prefix_status'], 'EXACT_UNTESTED_HYPOTHESIS')
    def test_02_tiny_regular_success_mode600(self):
        self.assertEqual(self.scan(tar_bytes()), (DATA, 0o600))
    def test_03_executable_git_mode_data_only(self):
        items=entries();items[1]=(items[1][0],DATA,tarfile.REGTYPE,0o775,'')
        self.assertEqual(self.scan(tar_bytes(items), selected(mode='100755')), (DATA,0o600))
        with self.assertRaisesRegex(ValueError,'mode mismatch'):
            self.scan(tar_bytes(items))
    def test_04_unsafe_paths(self):
        for name in ('../outside','/outside',PREFIX+'/../x',PREFIX+'//x',PREFIX+'/./x',PREFIX+'/x\\y',PREFIX+'/C:x',PREFIX+'/x\ny'):
            with self.subTest(name=name):self.rejected(entries()+[(name,b'x',tarfile.REGTYPE,0o644,'')])
    def test_05_unique_literal_root_not_inferred(self):
        self.rejected(entries()+[('other/x',b'x',tarfile.REGTYPE,0o644,'')],'fixed root')
    def test_06_duplicate(self):
        self.rejected(entries()+[entries()[1]],'duplicate')
    def test_07_collision_child_after_file(self):
        self.rejected(entries()+[(PREFIX+'/src/tiny.cpp/child',b'x',tarfile.REGTYPE,0o644,'')],'collision')
    def test_08_collision_file_after_implicit_directory(self):
        self.rejected(entries()+[(PREFIX+'/src',b'x',tarfile.REGTYPE,0o644,'')],'collision')
    def test_09_selected_links_and_devices(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.BLKTYPE,tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                self.rejected([entries()[0],(PREFIX+'/'+NAME,b'',kind,0o644,'target')])
    def test_10_unselected_safe_link_skipped_only(self):
        obs=observation()
        self.scan(tar_bytes(entries()+[(PREFIX+'/test/link',b'',tarfile.SYMTYPE,0o777,'target')]),obs=obs)
        self.assertEqual(obs['unselected_symlinks_skipped'],1)
    def test_11_unselected_escaping_link_rejected(self):
        self.rejected(entries()+[(PREFIX+'/test/link',b'',tarfile.SYMTYPE,0o777,'../../escape')])
    def test_12_missing_hash_size_and_mode(self):
        self.rejected([entries()[0]],'missing selected')
        self.rejected([entries()[0],(PREFIX+'/'+NAME,DATA+b'x',tarfile.REGTYPE,0o644,'')],'size mismatch')
        self.rejected([entries()[0],(PREFIX+'/'+NAME,b'x'*len(DATA),tarfile.REGTYPE,0o644,'')],'Git blob mismatch')
        self.rejected([entries()[0],(PREFIX+'/'+NAME,DATA,tarfile.REGTYPE,0o755,'')],'mode mismatch')
    def test_13_expanded_and_entry_and_single_caps(self):
        for name,value,pattern in (('EXPANDED_CAP',512,'expanded'),('ENTRY_CAP',1,'entry cap'),('MEMBER_CAP',1,'size mismatch')):
            with mock.patch.object(worker,name,value):
                with self.assertRaisesRegex(ValueError,pattern):self.scan(tar_bytes())
    def test_14_malformed_header_checksum_and_truncation(self):
        raw=bytearray(tar_bytes());raw[10]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):self.scan(bytes(raw))
        with self.assertRaisesRegex(ValueError,'truncated'):self.scan(tar_bytes()[:600])
    def test_15_nonzero_trailer_rejected(self):
        with self.assertRaisesRegex(ValueError,'after tar terminator'):
            self.scan(tar_bytes()+b'x')
    def test_16_global_pax_commit(self):
        data=tar_bytes(format=tarfile.PAX_FORMAT,pax_headers={'comment':worker.COMMIT})
        self.assertEqual(self.scan(data),(DATA,0o600))
        with self.assertRaisesRegex(ValueError,'commit mismatch'):
            self.scan(tar_bytes(format=tarfile.PAX_FORMAT,pax_headers={'comment':'0'*40}))
    def test_17_pax_bounds_and_bad_keys(self):
        for raw in (b'99 path=x\n',b'12 size=9999\n',b'11 path=x\n',b'0 x=1\n'):
            with self.assertRaises(ValueError):worker.parse_pax(raw)
    def test_18_redirect_exactly_once(self):
        first=Response(b'unread redirect body',worker.API_URL,302)
        first.headers['Location']=worker.REDIRECT_URL
        final=Response(b'x',worker.REDIRECT_URL)
        opener=mock.Mock();opener.open.side_effect=[first,final]
        self.assertEqual(worker.open_response(opener,budget(),[]),(final,worker.REDIRECT_URL))
        self.assertEqual(opener.open.call_count,2)
        self.assertTrue(first.closed)
        # A second 302 is returned, then final-response validation rejects it.
        again=Response(b'',worker.REDIRECT_URL,302)
        with self.assertRaises(ValueError):worker.check_response(again)
        for url in ('http://codeload.github.com/x',worker.REDIRECT_URL+'?x=1',worker.REDIRECT_URL+'/',worker.REDIRECT_URL.replace(worker.COMMIT,'0'*40)):
            first=Response(b'',worker.API_URL,302);first.headers['Location']=url
            opener=mock.Mock();opener.open.return_value=first
            with self.assertRaises(ValueError):worker.open_response(opener,budget(),[])
            self.assertEqual(opener.open.call_count,1)
        fp=mock.Mock()
        self.assertIs(worker.FixedRedirect().http_error_302(None,fp,302,'',None),fp)
        fp.read.assert_not_called()
    def test_19_response_headers_strict(self):
        response=Response(b'x');response.headers['Content-Length']='1'
        with self.assertRaisesRegex(ValueError,'ambiguous'):worker.check_response(response)
        for url,status in ((worker.REDIRECT_URL+'?secret=x',200),(worker.REDIRECT_URL,206)):
            with self.assertRaises(ValueError):worker.check_response(Response(b'x',url,status))
    def test_20_success_single_receipt_same_archive(self):
        archive=gzip.compress(tar_bytes(),mtime=0)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out';result=self.run_mock(root,Response(archive))
            self.assertEqual((root/'source.tar.gz').read_bytes(),archive)
            self.assertEqual(result['archive_sha256_observed'],hashlib.sha256(archive).hexdigest())
            self.assertEqual((root/'verilator'/NAME).read_bytes(),DATA)
            self.assertTrue((root/'SOURCE.json').exists());self.assertFalse((root/'FAILED.json').exists())
            self.assertFalse(result['terminal_success']);self.assertFalse(result['native_executed'])
            self.assertEqual(stat.S_IMODE((root/'source.tar.gz').stat().st_mode),0o600)
    def test_21_wrong_hash_preserves_archive_and_failure(self):
        archive=gzip.compress(tar_bytes(),mtime=0);pins=selected();pins[NAME]['git_blob_sha']='0'*40
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with self.assertRaisesRegex(ValueError,'Git blob'):self.run_mock(root,Response(archive),pins)
            self.assertEqual((root/'source.tar.gz').read_bytes(),archive)
            self.assertFalse((root/'SOURCE.json').exists())
            self.assertEqual(json.loads((root/'FAILED.json').read_bytes())['verified_members'],[])
    def test_22_failure_preserves_previously_verified_member(self):
        archive=gzip.compress(tar_bytes(entries()+[('other/x',b'x',tarfile.REGTYPE,0o644,'')]),mtime=0)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with self.assertRaisesRegex(ValueError,'fixed root'):self.run_mock(root,Response(archive))
            self.assertEqual((root/'verilator'/NAME).read_bytes(),DATA)
            self.assertEqual(len(json.loads((root/'FAILED.json').read_bytes())['verified_members']),1)
    def test_23_received_count_before_deadline(self):
        times=iter([0,0,401]);b=budget(clock=lambda:next(times));obs=observation();sink=io.BytesIO()
        with self.assertRaisesRegex(base.AcquisitionError,'elapsed'):
            worker.transfer(io.BytesIO(b'abc'),sink,b,obs)
        self.assertEqual((obs['received_bytes'],b.bytes,sink.getvalue()),(3,3,b''))
    def test_24_transfer_cap_and_oversized_read(self):
        with mock.patch.object(worker,'ARCHIVE_CAP',3):
            b=budget();obs=observation();sink=io.BytesIO()
            with self.assertRaisesRegex(base.AcquisitionError,'cap'):worker.transfer(io.BytesIO(b'abc'),sink,b,obs)
            self.assertEqual(sink.getvalue(),b'abc')
        class Bad:
            def read(self,n):return b'x'*(n+1)
        obs=observation();b=budget()
        with self.assertRaisesRegex(ValueError,'bounded'):worker.transfer(Bad(),io.BytesIO(),b,obs)
        self.assertEqual(obs['received_bytes'],worker.CHUNK+1)
    def test_25_transfer_failure_partial_preserved_no_retry(self):
        class Broken(Response):
            def read1(self,n):
                if self.tell():raise OSError('synthetic failure')
                return super().read1(min(10,n))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out';response=Broken(b'x'*30);opener=Opener(response)
            with self.assertRaises(OSError):worker.execute(base,plan,selected(),root,budget(),opener)
            self.assertEqual((root/'source.tar.gz.part').read_bytes(),b'x'*10)
            self.assertEqual(len(opener.calls),1)
            receipt=json.loads((root/'FAILED.json').read_bytes());self.assertEqual(receipt['received_bytes'],10)
            self.assertFalse(receipt['archive_complete'])
    def test_26_cleanup_cannot_mask_primary(self):
        class Broken(Response):
            def close(self):raise OSError('synthetic close')
        archive=b'notgzip'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out';response=Broken(archive)
            with self.assertRaisesRegex(ValueError,'pre-scan close'):
                self.run_mock(root,response)
            receipt=json.loads((root/'FAILED.json').read_bytes())
            self.assertEqual(receipt['cleanup_errors'][0]['resource'],'HTTP_response')
    def test_27_receipt_failure_keeps_primary(self):
        archive=gzip.compress(tar_bytes([entries()[0]]),mtime=0)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with mock.patch.object(base,'write_json',side_effect=OSError('receipt failure')):
                with self.assertRaisesRegex(ValueError,'missing selected') as raised:self.run_mock(root,Response(archive))
            self.assertIn('failure receipt publication error',raised.exception.__notes__[0])
            self.assertTrue((root/'source.tar.gz').exists())
    def test_28_absolute_shared_deadline(self):
        b=worker.shared_budget(base,100,510,clock=lambda:115)
        self.assertEqual(b.deadline,510)
        b=worker.shared_budget(base,100,510,clock=lambda:105)
        self.assertEqual(b.deadline,505)
        for start,end in ((100,511),(float('nan'),510),(200,510),(100,float('inf'))):
            with self.assertRaises(ValueError):worker.shared_budget(base,start,end,clock=lambda:115)
    def test_29_offline_main_no_open(self):
        with mock.patch.object(worker,'default_opener',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(worker.main([]),0)
        self.assertEqual(json.loads(out.getvalue())['status'],'SOURCE_PLAN_ONLY_NO_NETWORK_NO_BUILD')
    def test_30_symlink_output_reject(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'actual').mkdir();(root/'link').symlink_to(root/'actual',target_is_directory=True)
            with self.assertRaises(base.AcquisitionError):worker.write_member(root,'link/tiny.cpp',DATA,base)
            self.assertFalse((root/'actual'/'tiny.cpp').exists())
    def test_31_gzip_invalid_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with self.assertRaises(gzip.BadGzipFile):self.run_mock(root,Response(b'notgzip'))
            self.assertEqual((root/'source.tar.gz').read_bytes(),b'notgzip')
            self.assertTrue((root/'FAILED.json').exists())

    def test_32_primary_transfer_error_survives_close_error(self):
        class Broken(Response):
            def read1(self,n):raise OSError('primary transfer failure')
            def close(self):raise RuntimeError('secondary cleanup failure')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with self.assertRaisesRegex(OSError,'primary transfer failure'):self.run_mock(root,Broken(b'x'))
            receipt=json.loads((root/'FAILED.json').read_bytes())
            self.assertEqual(receipt['error_type'],'OSError')
            self.assertEqual(receipt['cleanup_errors'][0]['error_type'],'RuntimeError')
    def test_33_declared_length_mismatch_preserves(self):
        response=Response(b'abc');response.headers.replace_header('Content-Length','4')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with self.assertRaisesRegex(ValueError,'Content-Length'):self.run_mock(root,response)
            self.assertEqual((root/'source.tar.gz.part').read_bytes(),b'abc')
            self.assertFalse((root/'SOURCE.json').exists())
    def test_34_gzip_expansion_bound_preserves_archive(self):
        archive=gzip.compress(tar_bytes(),mtime=0)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(worker,'EXPANDED_CAP',1024):
            root=Path(d)/'out'
            with self.assertRaisesRegex(ValueError,'expanded'):self.run_mock(root,Response(archive))
            self.assertEqual((root/'source.tar.gz').read_bytes(),archive)
    def test_35_redirect_close_failure_no_second_open(self):
        class Broken(Response):
            def close(self):raise OSError('close failed')
        response=Broken(b'x',worker.API_URL,302);response.headers['Location']=worker.REDIRECT_URL
        opener=Opener(response);errors=[]
        with self.assertRaisesRegex(ValueError,'redirect close'):worker.open_response(opener,budget(),errors)
        self.assertEqual(len(opener.calls),1);self.assertEqual(errors[0]['resource'],'redirect_response')
    def test_36_opened_url_must_match_response(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out'
            with self.assertRaisesRegex(ValueError,'unexpected final'):self.run_mock(root,Response(b'x',worker.REDIRECT_URL))
            self.assertTrue((root/'FAILED.json').exists())
    def test_37_local_pax_path_and_raw_path(self):
        def pax_path(path,raw_name=PREFIX+'/short'):
            content=('path='+path+'\n').encode();n=len(content)+3
            while len(str(n).encode()+b' '+content)!=n:n=len(str(n).encode()+b' '+content)
            payload=str(n).encode()+b' '+content
            root=tarfile.TarInfo(PREFIX+'/');root.type=tarfile.DIRTYPE;root.mode=0o755
            extra=tarfile.TarInfo(PREFIX+'/PaxHeaders/tiny');extra.type=tarfile.XHDTYPE;extra.size=len(payload)
            actual=tarfile.TarInfo(raw_name);actual.size=len(DATA);actual.mode=0o644
            return root.tobuf(format=tarfile.USTAR_FORMAT)+extra.tobuf(format=tarfile.USTAR_FORMAT)+payload+b'\0'*((-len(payload))%512)+actual.tobuf(format=tarfile.USTAR_FORMAT)+DATA+b'\0'*((-len(DATA))%512)+b'\0'*1024
        self.assertEqual(self.scan(pax_path(PREFIX+'/'+NAME)),(DATA,0o600))
        with self.assertRaises(base.AcquisitionError):self.scan(pax_path(PREFIX+'/../escape'))
        with self.assertRaisesRegex(ValueError,'raw member'):self.scan(pax_path(PREFIX+'/'+NAME,'other/root'))
    def test_38_http_error_closes_without_body_read(self):
        fp=mock.Mock();error=worker.urllib.error.HTTPError(worker.API_URL,403,'denied',{},fp)
        opener=mock.Mock();opener.open.side_effect=error
        with self.assertRaises(worker.urllib.error.HTTPError):worker.open_response(opener,budget(),[])
        fp.close.assert_called_once();fp.read.assert_not_called();self.assertEqual(opener.open.call_count,1)
    def test_39_plan_not_reviewed_has_no_network_or_output(self):
        held=dict(plan,transport_reviewed=False)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'out';opener=mock.Mock()
            with self.assertRaisesRegex(ValueError,'HOLD'):worker.execute(base,held,selected(),root,budget(),opener)
            opener.open.assert_not_called();self.assertFalse(root.exists())
    def test_40_receipt_postcommit_cleanup_never_second_terminal(self):
        original=base.write_json
        def warning(path,value):
            original(path,value)
            return {'path':path.name+'.part','error_type':'SyntheticCleanup'}
        with tempfile.TemporaryDirectory() as d,mock.patch.object(base,'write_json',side_effect=warning):
            root=Path(d)/'out';result=self.run_mock(root,Response(gzip.compress(tar_bytes(),mtime=0)))
            self.assertTrue((root/'SOURCE.json').exists());self.assertFalse((root/'FAILED.json').exists())
            self.assertIn('receipt_postcommit_cleanup_warning',result)


if __name__=='__main__':
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise ValueError('Python -I -S -B required')
    unittest.main(verbosity=2)
