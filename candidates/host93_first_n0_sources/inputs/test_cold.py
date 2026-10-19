"""Tiny synthetic stdlib adapter tests; never reads real raw tensor files."""
import argparse
import ast
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--repo',required=True,type=Path)
args,remaining=parser.parse_known_args()
PINS=json.loads((HERE/'PROJECT_SOURCE_HASHES.json').read_text())['files']
raw=(HERE/'convert_providers.py').read_bytes()
if {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} != PINS['convert_providers.py']:
    raise ValueError('converter source changed before execution')
c=types.ModuleType('provider_converter_source')
c.__file__=str(HERE/'convert_providers.py');sys.modules[c.__name__]=c
exec(compile(raw,'convert_providers.py','exec',dont_inherit=True),c.__dict__)


def deadline():return time.monotonic()+30

def expected(data):return {'output_bytes':len(data),'expected_output_sha256':hashlib.sha256(data).hexdigest()}

def raw_expected(data):return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


class Cold(unittest.TestCase):
    def test_01_fixed_metadata_no_payload_read(self):
        spec=c.check_sources(args.repo)
        self.assertEqual(len(spec['providers']),14)
        self.assertEqual(spec['provider_payload_bytes'],94916608)
        self.assertEqual(spec['raw_receipt']['sha256'],
                         '0b319b9dc84a4c3942f3068b397e01f0e3493515b542ddf726d7d0677e01b6fa')

    def test_02_tiny_rectangular_transpose(self):
        raw=bytes.fromhex('010281820304838405068586')
        self.assertEqual(b''.join(c.transpose_bf16_rows(raw,[2,3],deadline())),
                         bytes.fromhex('010283848182050603048586'))
        self.assertEqual(b''.join(c.transpose_bf16_rows(raw,[3,2],deadline())),
                         bytes.fromhex('010203040506818283848586'))
        self.assertEqual(b''.join(c.transpose_bf16_rows(b'\x34\x12',[1,1],deadline())),b'\x34\x12')

    def test_03_transpose_size_failures(self):
        for data,shape in [(b'123',[1,2]),(b'12',[2,2]),(b'12',[0,1]),(b'12',[1]),(b'12',[True,1])]:
            with self.subTest(shape=shape),self.assertRaises(ValueError):
                list(c.transpose_bf16_rows(data,shape,deadline()))

    def test_04_fp32_exact_bit_patterns(self):
        words=[0,0x8000,1,0x807f,0x0080,0x3f80,0xbf80,0x7f7f]
        out=b''.join(c.fp32_from_bf16_chunks(struct.pack('<8H',*words),deadline()))
        self.assertEqual(struct.unpack('<8I',out),
                         (0,0x80000000,0x00010000,0x807f0000,0x00800000,0x3f800000,0xbf800000,0x7f7f0000))

    def test_05_nonfinite_rejected_even_outside_selection(self):
        for word in (0x7f80,0xff80,0x7f81,0xffff):
            with self.subTest(word=word),self.assertRaisesRegex(ValueError,'nonfinite'):
                list(c.fp32_from_bf16_chunks(struct.pack('<2H',0x3f80,word),deadline(),words=1))
        for data in (b'',b'\x00'):
            with self.assertRaises(ValueError):list(c.fp32_from_bf16_chunks(data,deadline()))

    def test_06_selection_and_chunk_limit(self):
        data=struct.pack('<3H',0x3f80,0x4000,0x4040)
        self.assertEqual(b''.join(c.fp32_from_bf16_chunks(data,deadline(),first_word=1,words=1)),
                         bytes.fromhex('00000040'))
        chunks=list(c.fp32_from_bf16_chunks(b'\x80\x3f'*16385,deadline()))
        self.assertEqual([len(x) for x in chunks],[65536,4])
        self.assertEqual(chunks[-1],bytes.fromhex('0000803f'))
        with self.assertRaises(ValueError):list(c.fp32_from_bf16_chunks(data,deadline(),words=4))

    def test_07_m16_rope_small_formula_and_padding(self):
        # M16 is a bounded synthetic check, not the fixed canonical M128 provider.
        data=b''.join(c.rope_chunks(16,deadline()))
        self.assertEqual(len(data),524288)
        self.assertEqual(data[:256],struct.pack('<I',0x3f800000)*64)
        self.assertEqual(data[262144:262400],bytes(256))
        self.assertEqual(struct.unpack_from('<I',data,256)[0],0x3f0a5140)
        self.assertEqual(struct.unpack_from('<I',data,262144+256)[0],0x3f576aa4)
        self.assertEqual(data[4096:262144],bytes(262144-4096))
        self.assertEqual(data[262144+4096:],bytes(262144-4096))
        with self.assertRaises(ValueError):list(c.rope_chunks(1,deadline()))

    def test_08_original_rope_rhs_ast_identical(self):
        spec=c.check_sources(args.repo)
        source='candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py'
        original=(args.repo/source).read_bytes()
        pin=next(p for p in spec['source_files'] if p['path']==source)
        self.assertEqual(c.digest(original),{k:pin[k] for k in ('bytes','sha256')})
        old=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='rope_bytes')
        new=next(n for n in ast.parse((HERE/'convert_providers.py').read_bytes()).body
                 if isinstance(n,ast.FunctionDef) and n.name=='rope_chunks')
        angle=lambda node:next(n.value for n in ast.walk(node) if isinstance(n,ast.Assign)
                               and any(isinstance(t,ast.Name) and t.id=='angle' for t in n.targets))
        self.assertEqual(ast.dump(angle(old)),ast.dump(angle(new)))
        calls=lambda node:{n.func.attr:ast.dump(n) for n in ast.walk(node) if isinstance(n,ast.Call)
                           and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
                           and n.func.value.id=='math'}
        self.assertEqual(calls(old),calls(new))

    def test_09_tiny_raw_owned_verified_buffer(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'raw';data=b'\x01\x02\x03\x04';p.write_bytes(data)
            actual=c.read_raw(p,raw_expected(data),deadline())
            self.assertIsInstance(actual,bytearray);self.assertEqual(actual,data)
            p.write_bytes(b'xxxx')
            self.assertEqual(actual,data)
            with self.assertRaisesRegex(ValueError,'SHA256'):c.read_raw(p,raw_expected(data),deadline())
            p.write_bytes(data+b'!')
            with self.assertRaisesRegex(ValueError,'size'):c.read_raw(p,raw_expected(data),deadline())
            p.write_bytes(data[:-1])
            with self.assertRaisesRegex(ValueError,'size'):c.read_raw(p,raw_expected(data),deadline())

    def test_10_raw_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);real=root/'raw';real.write_bytes(b'12');link=root/'link';link.symlink_to(real)
            with self.assertRaisesRegex(ValueError,'symlink'):c.read_raw(link,raw_expected(b'12'),deadline())

    def test_11_tiny_provider_success_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=b'abcdef'
            result=c.write_provider(root,'tiny',[b'abc',b'def'],expected(data),deadline())
            self.assertEqual((root/'tiny.bin').read_bytes(),data)
            self.assertFalse((root/'tiny.part').exists());self.assertEqual(result['sha256'],expected(data)['expected_output_sha256'])
            with self.assertRaisesRegex(ValueError,'exists'):
                c.write_provider(root,'tiny',[data],expected(data),deadline())
            self.assertEqual((root/'tiny.bin').read_bytes(),data)

    def test_12_failed_provider_stays_partial(self):
        for chunks,want in [([b'ab'],b'abc'),([b'abcd'],b'abc'),([b'abd'],b'abc'),([b''],b'abc')]:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                with self.assertRaises(ValueError):c.write_provider(root,'tiny',chunks,expected(want),deadline())
                self.assertFalse((root/'tiny.bin').exists());self.assertTrue((root/'tiny.part').exists())
                self.assertFalse((root/'PROVIDERS.json').exists())

    def test_13_readback_mismatch_stays_partial(self):
        with tempfile.TemporaryDirectory() as temp,mock.patch.object(c,'exact_hash',return_value='0'*64):
            root=Path(temp)
            with self.assertRaisesRegex(ValueError,'readback'):c.write_provider(root,'tiny',[b'ab'],expected(b'ab'),deadline())
            self.assertFalse((root/'tiny.bin').exists());self.assertTrue((root/'tiny.part').exists())

    def test_14_short_write_refused(self):
        class Short(io.BytesIO):
            def write(self,data):return super().write(data[:-1])
        with tempfile.TemporaryDirectory() as temp,mock.patch.object(Path,'open',return_value=Short()):
            with self.assertRaisesRegex(ValueError,'short provider write'):
                c.write_provider(Path(temp),'tiny',[b'ab'],expected(b'ab'),deadline())

    def test_15_deadline_and_commit_collision(self):
        with self.assertRaisesRegex(ValueError,'deadline'):list(c.transpose_bf16_rows(b'12',[1,1],0))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'a';b=root/'b';a.write_bytes(b'a');b.write_bytes(b'b')
            with self.assertRaises(FileExistsError):c.commit_new(a,b)
            self.assertEqual(a.read_bytes(),b'a');self.assertEqual(b.read_bytes(),b'b')

    def test_16_completion_not_written_after_late_failure(self):
        spec={'providers':[{'name':'wq','raw_relative_path':'dummy','raw_tensor':{'shape':[1,1]},
                            'output_bytes':2,'expected_output_sha256':hashlib.sha256(b'12').hexdigest()},
                           {'name':'wk','raw_relative_path':'missing','raw_tensor':{'shape':[1,1]}}]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with mock.patch.object(c,'read_raw',side_effect=[bytearray(b'12'),ValueError('bad next raw')]):
                with self.assertRaisesRegex(ValueError,'bad next'):c.collect(spec,root,root,deadline())
            self.assertEqual((root/'wq.bin').read_bytes(),b'12')
            self.assertFalse((root/'PROVIDERS.json').exists())

    def test_17_blocked_alarm_refused_before_limits(self):
        with mock.patch.object(c.signal,'pthread_sigmask',return_value={c.signal.SIGALRM}), \
             mock.patch.object(c.resource,'setrlimit') as limits:
            with self.assertRaisesRegex(ValueError,'blocked'):c.activate_limits({},deadline())
            limits.assert_not_called()

    def test_18_source_default_cannot_read_raw(self):
        with mock.patch.object(c,'read_raw',side_effect=RuntimeError('forbidden raw read')), \
             mock.patch.object(c,'check_receipt',side_effect=RuntimeError('forbidden receipt read')), \
             mock.patch.object(sys,'stdout',new_callable=io.StringIO):
            self.assertEqual(c.main(['--repo',str(args.repo)]),0)


if __name__=='__main__':unittest.main(argv=[sys.argv[0],*remaining],verbosity=2)
