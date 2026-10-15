import struct
import unittest
from . import compare as C


def head_major(raw):
    return b''.join(raw[(t*C.HEADS+h)*C.DIM*4:(t*C.HEADS+h+1)*C.DIM*4]
                    for h in range(C.HEADS) for t in range(C.TOKENS))


def fixture():
    raw=b''.join(struct.pack('<f', float((t+h)%7)) * C.DIM
                 for t in range(C.TOKENS) for h in range(C.HEADS))
    p={'k':raw, 'v':raw, 'cache':raw+raw}
    hashes={k:C.sha(v) for k,v in p.items()}
    live='a'*64
    receipts={k:dict(role=k,run='synthetic01',live_identity=live,layout=C.LAYOUTS[k],
                    bytes=len(v),sha256=hashes[k],sealed=True,terminal=True,ack_bytes=len(v),
                    ack_64b_beats=len(v)//64, origin='SEALED_ACTUAL_KV_PHYSICAL_READBACK' if k=='cache' else 'SEALED_ACTUAL_PRODUCER')
              for k,v in p.items()}
    official={'k':head_major(raw), 'v':raw}
    return dict(payloads=p,receipts=receipts,expected_run='synthetic01',expected_live_identity=live,
                expected_artifacts=hashes,official=official,
                official_commitments={k:C.sha(v) for k,v in official.items()})


class Cold(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(C.compare(**fixture())['same_live_exact_copy'])

    def test_tolerated_official_difference(self):
        f=fixture(); f['official']['k']=struct.pack('<f',0.0078125)+f['official']['k'][4:]
        f['official_commitments']['k']=C.sha(f['official']['k'])
        r=C.compare(**f)
        self.assertTrue(r['same_live_exact_copy'])
        self.assertNotIn('passed',r);self.assertNotIn('comparisons',r)
        self.assertFalse(r['whole_block_acceptance_claimed'])
        self.assertFalse(r['official_kv_exact_copy'])

    def test_cache_corruption_even_with_matching_commitment(self):
        f=fixture(); f['payloads']['cache']=struct.pack('<f',1)+f['payloads']['cache'][4:]
        h=C.sha(f['payloads']['cache']); f['expected_artifacts']['cache']=h;f['receipts']['cache']['sha256']=h
        with self.assertRaises(ValueError):C.compare(**f)

    def test_single_bf16_bit_cache_corruption_within_tolerance(self):
        f=fixture()
        # +0 -> minimum BF16 subnormal: one bit, far below either numerical gate.
        f['payloads']['cache']=struct.pack('<I',0x00010000)+f['payloads']['cache'][4:]
        h=C.sha(f['payloads']['cache']);f['expected_artifacts']['cache']=h;f['receipts']['cache']['sha256']=h
        with self.assertRaises(ValueError):C.compare(**f)

    def test_truncated(self):
        f=fixture();f['payloads']['cache']=f['payloads']['cache'][:-4]
        with self.assertRaises(ValueError):C.compare(**f)

    def test_wrong_layout(self):
        f=fixture();f['receipts']['k']['layout']='HEAD_TOKEN_DIM_F32LE_BF16'
        with self.assertRaises(ValueError):C.compare(**f)
        f=fixture();f['official']['k']=f['payloads']['k'];f['official_commitments']['k']=C.sha(f['official']['k'])
        self.assertFalse(C.compare(**f)['official_kv_exact_copy'])

    def test_ack_seal_terminal_identity_and_digest(self):
        for key,value in [('ack_bytes',0),('ack_64b_beats',4095),('origin','RECONSTRUCTED_K_PLUS_V'),('sealed',False),('terminal',False),
                          ('run','other'),('live_identity','b'*64),('sha256','c'*64)]:
            f=fixture();f['receipts']['cache'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):C.compare(**f)

    def test_no_numeric_authority_even_for_large_official_error(self):
        for mean_only,raw in ((False,struct.pack('<f',0.0625)+fixture()['official']['k'][4:]),
                              (True,struct.pack('<f',0.015625)*C.WORDS)):
            f=fixture()
            if mean_only: # Isolate mean rejection below the max limit.
                for role in ('k','v'):f['payloads'][role]=b'\0'*C.SIZE
                f['payloads']['cache']=b'\0'*(2*C.SIZE)
                for role in f['payloads']:
                    h=C.sha(f['payloads'][role]);f['expected_artifacts'][role]=h;f['receipts'][role]['sha256']=h
                f['official']['v']=b'\0'*C.SIZE;f['official_commitments']['v']=C.sha(f['official']['v'])
            f['official']['k']=raw;f['official_commitments']['k']=C.sha(raw)
            self.assertFalse(C.compare(**f)['official_kv_exact_copy'])

    def test_nonfinite_or_non_bf16(self):
        for bits in (0x7f800000,0x7fc00000,0x3f800001):
            f=fixture();f['official']['k']=struct.pack('<I',bits)+f['official']['k'][4:]
            f['official_commitments']['k']=C.sha(f['official']['k'])
            with self.assertRaises(ValueError):C.compare(**f)

    def test_official_commitment_required(self):
        f=fixture();f['official_commitments']['k']='d'*64
        with self.assertRaises(ValueError):C.compare(**f)

class OriginalNumericalGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        from scripts import qwen2_layer0_model_gate as original
        from pathlib import Path
        cls.np=np;cls.original=original
        cls.policy=original.load_policy(Path(__file__).resolve().parents[2])
        assert cls.policy['operator']==C.LIMITS

    def test_original_mean_boundary_remains_failure(self):
        np=self.np
        small=[662700032,671088640,687865856,696254464,713031680,721420288,
               729808896,738197504,771751936,788529152,830472192,838860800,
               847249408,864026624,880803840,889192448,897581056,905969664,
               939524096,956301312,998244352,1006632960,1015021568]
        error=np.array([0]*27503+small+[1023410176]*5242,dtype='<u4').view('<f4')
        np.random.default_rng(3).shuffle(error)
        metric=self.original.compare(np.zeros(C.WORDS,dtype=np.float32),error)
        self.assertEqual(metric['max_abs'],0.03125)
        self.assertEqual(metric['mean_abs'],0.005000000000000001)
        self.assertFalse(self.original.stage_verdict('k',metric,'bf16',self.policy)['passed'])
        f=fixture()
        for role,size in (('k',C.SIZE),('v',C.SIZE),('cache',2*C.SIZE)):
            f['payloads'][role]=b'\0'*size
            h=C.sha(f['payloads'][role]);f['expected_artifacts'][role]=h;f['receipts'][role]['sha256']=h
        f['official']={'k':head_major(error.tobytes()),'v':b'\0'*C.SIZE}
        f['official_commitments']={k:C.sha(v) for k,v in f['official'].items()}
        result=C.compare(**f)
        self.assertTrue(result['same_live_exact_copy'])
        self.assertFalse(result['numerical_acceptance_claimed'])
        self.assertNotIn('passed',result)

    def test_original_signed_zero_bit_counter(self):
        np=self.np
        metric=self.original.compare(np.array([0.],dtype=np.float32),np.array([-0.],dtype=np.float32))
        self.assertEqual(metric['different_elements'],1)
        self.assertEqual(metric['max_abs'],0)

    def test_original_operator_max_mean_and_tolerated_difference(self):
        np=self.np
        for value,passed in ((0.00390625,True),(0.015625,False),(0.0625,False)):
            metric=self.original.compare(np.zeros(C.WORDS,dtype=np.float32),
                                         np.full(C.WORDS,value,dtype=np.float32))
            self.assertIs(self.original.stage_verdict('v',metric,'bf16',self.policy)['passed'],passed)


if __name__=='__main__':unittest.main()
