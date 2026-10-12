"""Small source-scope and isolated arithmetic tests; never a full-block run."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from . import builder as b

class SourceTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original,cls.header,cls.identity=b.regenerate_sources()
        cls.profile=(b.ROOT/b.PROFILE_REL).read_bytes()
        cls.changed,cls.audit=b.transform(cls.original,cls.profile)

    def test_regenerates_exact_frozen_numerical_source_and_header(self):
        self.assertEqual(b.sha(self.original),b.ORIGINAL_CPP_SHA)
        self.assertEqual(b.sha(self.header),b.HEADER_SHA)
        self.assertEqual(b.sha(self.changed),'e13bddc69714e6af6a774198d7382b4100f2f50cd843eea5d780bace14c6aacf')

    def test_preserved_executed_sources_and_receipts(self):
        from .completed import verify_source_provenance, EXECUTED_FROZEN_SHA
        frozen=b.frozen_json(b.HERE/'executed_m16_v1/FROZEN.json',EXECUTED_FROZEN_SHA)
        for relative,digest in frozen['source_sha256'].items():
            name=Path(relative).name+('.txt' if relative.endswith('.py') else '')
            self.assertEqual(b.file_sha(b.HERE/'executed_m16_v1'/name),digest)
        provenance=verify_source_provenance(frozen,EXECUTED_FROZEN_SHA)
        self.assertTrue(provenance['preserved_execution_source_used'])
        self.assertEqual(len(provenance['source_locations']),4)
        for name,digest in [('PREPARED.json','84a850e72e9d2c3c2226586aac4a39ca9541f4ba171d765768ead953384e2c1a'),
                            ('RESULT.json','5eeff614754ea28b6f690b5e0b4a54de03b79bb7fa6ceda104beff89d263d728')]:
            self.assertEqual(b.file_sha(b.HERE/'executed_m16_v1'/name),digest)
        prepared=json.loads((b.HERE/'executed_m16_v1/PREPARED.json').read_bytes())
        self.assertTrue(prepared['source_sha256'].items()<=frozen['source_sha256'].items())
        with self.assertRaisesRegex(ValueError,'frozen source drift'):
            verify_source_provenance(frozen,'0'*64)

    def test_runtime_archives_must_be_explicit(self):
        with self.assertRaisesRegex(ValueError,'explicit archive_directory'):b.archive_context(16)
        self.assertNotIn('work/',b.PROFILE_REL)
        self.assertEqual(b.sha(self.profile),b.PROFILE_SHA)

    def test_inverse_patch_proves_every_other_source_byte(self):
        result=b.verify_transform(self.original,self.changed,self.profile)
        self.assertTrue(result['all_other_source_byte_exact'])
        self.assertEqual(result['restored_original_sha256'],b.ORIGINAL_CPP_SHA)
        text=self.changed.decode()
        self.assertEqual(text.count('dense_qkv_block_pair('),4) # one declaration, three calls
        for call in b.CALLS:self.assertNotIn(call,text)
        for begin,end in [('  void norm(','  // BEGIN'),('  void dense(','  void rope('),
                          ('  void rope(','  void attention('),('  void attention(','  void computeReference(')]:
            if begin=='  void norm(':
                expected=self.original.decode().split(begin,1)[1].split('  void dense(',1)[0]
            else:expected=self.original.decode().split(begin,1)[1].split(end,1)[0]
            self.assertEqual(text.split(begin,1)[1].split(end,1)[0],expected)
        self.assertFalse(result['acceptance'].startswith('PASS'))

    def test_rejects_unrelated_norm_edit(self):
        bad=self.changed.replace(b'variance=mean+1e-6f',b'variance=mean+2e-6f')
        with self.assertRaisesRegex(ValueError,'non-QKV source'):b.verify_transform(self.original,bad,self.profile)

    def test_rejects_helper_or_call_changes(self):
        with self.assertRaisesRegex(ValueError,'explicit helper'):
            b.verify_transform(self.original,self.changed.replace(b'(issue^1)',b'(issue^0)'),self.profile)
        with self.assertRaisesRegex(ValueError,'replacement'):
            b.verify_transform(self.original,self.changed.replace(b'dense_qkv_block_pair(OFF_N0,OFF_WQ',b'dense(OFF_N0,OFF_WQ'),self.profile)

    def test_rejects_old_source_and_unreviewed_profile(self):
        with self.assertRaisesRegex(ValueError,'original numerical'):b.transform(self.original+b'\n',self.profile)
        profile=json.loads(self.profile);profile['parameters']['block_sizes']=[512,1024]
        with self.assertRaisesRegex(ValueError,'unreviewed backend'):b.transform(self.original,json.dumps(profile).encode())

    def test_generic_block_validation_does_not_assume_1024(self):
        self.assertEqual(b.validate_blocks([2,4],6),(2,4))
        self.assertEqual(b.validate_blocks([4,2],6),(4,2))
        for blocks,k in [([3,3],6),([True,5],6),([0,6],6),([2,2],6),([2,2,2],6)]:
            with self.assertRaises(ValueError):b.validate_blocks(blocks,k)

    def test_m1_and_carried_are_not_new_profile_claims(self):
        with self.assertRaisesRegex(ValueError,'M16/M128'):b.archive_context(1)
        self.assertIn(b'(tokens==16 || tokens==128) && past==0',self.changed)

    def test_complete_transformed_source_syntax_only(self):
        with tempfile.TemporaryDirectory(prefix='qkv_reference_syntax_') as name:
            d=Path(name);(d/'candidate.cpp').write_bytes(self.changed)
            (d/'block_layout.h').write_bytes(self.header)
            result=subprocess.run(['g++','-std=c++17','-ffp-contract=off','-fno-fast-math','-fsyntax-only',str(d/'candidate.cpp')],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((d/'candidate').exists())

    def test_only_isolated_dot_helper_numerics(self):
        # Hand-constructed normal cancellation cases distinguish pair order
        # and the explicit block boundary. No weight/model/owner is run here.
        prefix=r'''
#include <array>
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <xmmintrin.h>
static void need(bool x,const std::string& s){if(!x)throw std::runtime_error(s);}
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
static float fp(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static float bf(float x){uint32_t u=bits(x);return fp((u+0x7fff+((u>>16)&1))&0xffff0000u);}
static float add(float a,float b){return a+b;}
struct IndependentDot {
'''
        suffix=r'''
};
int main(){
 std::fesetround(FE_TONEAREST);_mm_setcsr(_mm_getcsr()&~(0x6000u|0x8040u));
 float x[6]={1,1,1,1,1,1},w[6*32]={},y[16]={};
 for(int j=0;j<16;j++){w[j]=1;w[2*32+j]=-1;w[3*32+j]=fp(0x33800000u);}
 int a[2]={4,2},b[2]={2,4};
 IndependentDot::reference_qkv_pair_dot16(x,w,6,32,0,a,2,y);
 for(float v:y)need(bits(v)==0,"pair-high-first cancellation");
 float sequential=0;for(int k=0;k<6;k++)sequential=std::fma(x[k],w[k*32],sequential);
 need(bits(sequential)==0x33800000u,"control must distinguish increasing K");
 IndependentDot::reference_qkv_pair_dot16(x,w,6,32,0,b,2,y);
 for(float v:y)need(bits(v)==0x33800000u,"independent block reset and add");
 int invalid[2]={3,3};bool failed=false;
 try{IndependentDot::reference_qkv_pair_dot16(x,w,6,32,0,invalid,2,y);}catch(const std::runtime_error&){failed=true;}
 need(failed,"odd block accepted");
 float sx[4]={fp(0x00010000u),0,0,0},sw[4*32]={};int two[2]={2,2};
 for(int j=0;j<16;j++)sw[j]=1;
 IndependentDot::reference_qkv_pair_dot16(sx,sw,4,32,0,two,2,y);
 for(float v:y)need(bits(v)==0x00010000u,"gradual underflow must remain enabled");
 float cx[4]={1,0,0,0},cw[4*32]={};for(int j=16;j<32;j++)cw[j]=float(j);
 IndependentDot::reference_qkv_pair_dot16(cx,cw,4,32,16,two,2,y);
 for(int j=0;j<16;j++)need(y[j]==float(16+j),"K,N stride or output lane alias");
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='qkv_reference_dot_') as name:
            d=Path(name);source=prefix+(b.HERE/'dot16.inc').read_text()+suffix;(d/'dot.cpp').write_text(source)
            compile_=subprocess.run(['g++','-O2','-std=c++17','-fno-fast-math','-ffp-contract=off','-fno-builtin-fmaf',str(d/'dot.cpp'),'-o',str(d/'dot')],capture_output=True,text=True,timeout=15)
            self.assertEqual(compile_.returncode,0,compile_.stderr)
            run=subprocess.run([str(d/'dot')],capture_output=True,text=True,timeout=5)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__':unittest.main()
