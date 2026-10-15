"""Cold synthetic format fixtures; no numerical execution or log I/O."""
import json
import unittest
from . import parser as P

MEM='src:bf16::blocked:ab::f0 wei:bf16::blocked:ba::f0 dst:bf16::blocked:ab::f0'
LINE='onednn_verbose,v1,primitive,exec,cpu,matmul,brg_matmul:avx512_core_amx,undef,'+MEM+',attr-scratchpad:user attr-post-ops:sum,,128x1536:1536x1536,0.25'

class ParserTests(unittest.TestCase):
    def test_exact_cpu_bf16_biased_target_exec(self):
        result=P.parse(LINE)
        self.assertEqual(result,dict(schema=1,status='LINEAR_BACKEND_OBSERVATION',backend='ONEDNN',
            isa='AVX512_CORE_AMX',matched_primitive=True,matched_count=1,evidence='MATCHED'))
        for original,new in [('v1,primitive','v1,123456.25,primitive')]:
            self.assertEqual(P.parse(LINE.replace(original,new)),result)

    def test_create_dispatch_info_and_other_primitive_do_not_match(self):
        lines=[LINE.replace(',exec,',',create:cache_miss,'),LINE.replace(',exec,',',create:dispatch,'),
            LINE.replace(',matmul,',',reorder,'),LINE.replace(',cpu,',',gpu,'),
            'onednn_verbose,v1,info,cpu,isa:Intel AVX-512 with AMX']
        for line in lines:
            result=P.parse(line);self.assertFalse(result['matched_primitive'])
            self.assertEqual(result['isa'],'UNOBSERVED')

    def test_wrong_geometry_dtype_bias_or_postop_do_not_match(self):
        replacements=[('128x1536:1536x1536','1x128x1536:1x1536x1536'),
            ('128x1536:1536x1536','128x1536:1536x256'),('src:bf16','src:f32'),
            ('wei:bf16','wei:f32'),('dst:bf16','dst:f32'),
            ('dst:bf16','bia:bf16::blocked:ab::f0_mask2 dst:bf16'),
            ('attr-post-ops:sum','attr-post-ops:sum:1'),
            ('attr-post-ops:sum','attr-post-ops:eltwise_relu'),
            ('128x1536:1536x1536,','128x1536:1536x1536:128x1536,'),('undef','forward_training')]
        for old,new in replacements:
            with self.subTest(old=old,new=new):self.assertFalse(P.parse(LINE.replace(old,new))['matched_primitive'])

    def test_no_log_is_not_fallback(self):
        for text in ('','unrelated private application text'):
            result=P.parse(text)
            self.assertEqual((result['backend'],result['evidence']),('UNDETERMINED','NO_LOG'))
        self.assertEqual(P.parse('onednn_verbose,v1,info,cpu,runtime:OpenMP')['evidence'],'NO_MATCH')

    def test_unknown_version_and_malformed_are_unresolved(self):
        for line in (LINE.replace(',v1,',',v9,'),LINE+',extra',LINE.rsplit(',',1)[0]+',nan'):
            result=P.parse(line);self.assertEqual(result['evidence'],'UNSUPPORTED')
            self.assertEqual(result['backend'],'UNDETERMINED')

    def test_count_mixed_isa_and_unknown_implementation(self):
        self.assertEqual(P.parse(LINE+'\n'+LINE)['matched_count'],2)
        self.assertEqual(P.parse(LINE+'\n'+LINE.replace('avx512_core_amx','avx512_core_bf16'))['isa'],'MIXED')
        result=P.parse(LINE.replace('brg_matmul:avx512_core_amx','private_unknown_implementation'))
        self.assertEqual(result['isa'],'UNKNOWN');self.assertEqual(result['backend'],'ONEDNN')
        self.assertNotIn('private',json.dumps(result))

    def test_descriptor_duplicate_and_unknown_rejected(self):
        for replacement in (MEM+' unknown:bf16::blocked:ab::f0',MEM.replace('dst:bf16','src:bf16')):
            self.assertFalse(P.parse(LINE.replace(MEM,replacement))['matched_primitive'])

    def test_strict_schema_and_bounds(self):
        good=P.parse(LINE)
        for key,value in [('extra','private'),('schema',True),('matched_count',True),
                          ('matched_count',65),('matched_count',0),('matched_primitive',1),
                          ('isa','private'),('evidence','FALLBACK'),('backend','ATEN')]:
            with self.subTest(key=key),self.assertRaises(ValueError):P.checked({**good,key:value})
        for text in (b'bytes','x'*(P.MAX_BYTES+1),'\n'*(P.MAX_LINES+1),'x'*(P.MAX_LINE+1)):
            with self.assertRaises(ValueError):P.parse(text)
        with self.assertRaises(ValueError):P.parse('\n'.join([LINE]*65))

    def test_info_isa_never_overrides_matched_implementation(self):
        header='onednn_verbose,v1,info,cpu,isa:Intel AVX-512 with AMX'
        line=LINE.replace('brg_matmul:avx512_core_amx','brg_matmul:avx512_core_bf16')
        self.assertEqual(P.parse(header+'\n'+line)['isa'],'AVX512_CORE_BF16')
        self.assertEqual(P.parse(header)['isa'],'UNOBSERVED')

    def test_disabled_mode_or_no_sum_does_not_prove_aten_fallback(self):
        for line in (LINE.replace('attr-scratchpad:user attr-post-ops:sum','attr-scratchpad:user'),
                     LINE.replace('attr-scratchpad:user attr-post-ops:sum',''),
                     LINE.replace('onednn_verbose,v1','onednn_verbose,v0'),
                     LINE.replace(':bf16','_bf16')):
            result=P.parse(line)
            self.assertFalse(result['matched_primitive'])
            self.assertEqual(result['backend'],'UNDETERMINED')

    def test_no_raw_values_are_exported(self):
        text=json.dumps(P.parse(LINE))
        for secret in ('128x1536','0.25','brg_matmul','src:bf16','onednn_verbose'):
            self.assertNotIn(secret,text)

if __name__=='__main__':unittest.main()
