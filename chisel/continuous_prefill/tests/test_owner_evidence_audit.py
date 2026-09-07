#!/usr/bin/env python3
"""Read-only mutations against an actual completed DUT artifact.

All mutations exist only behind mocked file reads; no original log, tensor or
source file is changed or deleted. This tests the verifier, not hardware.
"""
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'))
from audit_owner_block_abi import audit
ROOT=Path(os.environ['OWNER_EVIDENCE']).resolve()
RB=Path.read_bytes; RT=Path.read_text

class EvidenceAudit(unittest.TestCase):
    def reject(self,changes):
        def binary(p,*a,**kw):return changes.get(str(p),RB(p,*a,**kw))
        def text(p,*a,**kw):return changes[str(p)].decode() if str(p) in changes else RT(p,*a,**kw)
        with patch.object(Path,'read_bytes',binary),patch.object(Path,'read_text',text):
            with self.assertRaises((ValueError,OSError,KeyError)):audit(ROOT)
    def table(self,name,offset,mask):
        p=ROOT/'tensors'/name;raw=bytearray(p.read_bytes());raw[offset]^=mask
        return {str(p):bytes(raw),str(ROOT/'fixture'/name):bytes(raw)}
    def test_actual_complete_artifact(self):self.assertEqual(audit(ROOT)['status'],'PASS_OWNER_PUBLIC_ABI_AND_NUMERICAL_RECHECK')
    def test_bad_command_engine(self):self.reject(self.table('host_commands.bin',1,1))
    def test_reserved_command_flags(self):self.reject(self.table('host_commands.bin',2,1))
    def test_policy_program_id(self):self.reject(self.table('host_descriptors.bin',3*16+7,1))
    def test_source_element_stride(self):self.reject(self.table('host_descriptors.bin',2*16+7,1))
    def test_matrix_dimension(self):
        f=json.loads((ROOT/'fixture/manifest.json').read_text());ix=f['schedule'][1]['roots'][0]+3
        self.reject(self.table('host_descriptors.bin',ix*16+7,1))
    def test_nonzero_command_padding(self):self.reject(self.table('host_commands.bin',21*16,1))
    def test_single_output_bit(self):
        p=ROOT/'tensors/y_actual.f32le';r=bytearray(p.read_bytes());r[0]^=1;self.reject({str(p):bytes(r)})
    def test_equal_nan_actual_reference(self):
        p=ROOT/'tensors/down_actual.f32le';r=bytearray(p.read_bytes());r[:4]=b'\x01\x00\xc0\x7f'
        self.reject({str(p):bytes(r),str(p.with_name('down_reference.f32le')):bytes(r)})
    def test_short_down(self):
        p=ROOT/'tensors/down_actual.f32le';self.reject({str(p):p.read_bytes()[:-4]})
    def test_nonzero_simulator_exit(self):self.reject({str(ROOT/'simulation.exit'):b'2\n'})
    def test_missing_completion(self):
        p=ROOT/'run.log';r='\n'.join(x for x in p.read_text().splitlines() if not x.startswith('OWNER_COMPLETION pc=20 '));self.reject({str(p):r.encode()})
    def test_early_completion_time(self):
        p=ROOT/'run.log';lines=p.read_text().splitlines()
        import re
        lines=[re.sub(r'cycle=\d+','cycle=1',x) if x.startswith('OWNER_COMPLETION pc=20 ') else x for x in lines]
        self.reject({str(p):('\n'.join(lines)+'\n').encode()})
    def test_wrong_completion_write_bytes(self):
        p=ROOT/'run.log';lines=p.read_text().splitlines()
        import re
        lines=[re.sub(r'write_ack_bytes=\d+','write_ack_bytes=0',x) if x.startswith('OWNER_COMPLETION pc=20 ') else x for x in lines]
        self.reject({str(p):('\n'.join(lines)+'\n').encode()})
    def test_stale_source_hash(self):
        p=ROOT/'sources.sha256.json';j=json.loads(p.read_text());j[next(iter(j))]='x';self.reject({str(p):json.dumps(j).encode()})

if __name__=='__main__':unittest.main()
