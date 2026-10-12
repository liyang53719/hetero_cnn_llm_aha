"""Asymmetric shapes catch token/head confusion without checkpoint payloads."""
import unittest
from unittest.mock import patch
import numpy as np
from . import reference_layout as r


class ReferenceLayoutTests(unittest.TestCase):
    def test_asymmetric_token_major_export_and_logical_cache_match(self):
        logical=np.arange(2*3*5*7,dtype='<u4').reshape(2,3,5,7)
        exported=logical.transpose(0,2,1,3).copy().tobytes()
        actual=r.decode_qk(exported,logical.shape,'token_major')
        self.assertEqual(actual.tobytes(),logical.tobytes())
        self.assertNotEqual(r.decode_qk(exported,logical.shape,'head_major').tobytes(),logical.tobytes())

    def test_head_major_is_not_transposed_even_when_dimensions_equal(self):
        logical=np.arange(1*3*3*7,dtype='<u4').reshape(1,3,3,7)
        self.assertEqual(r.decode_qk(logical.tobytes(),logical.shape,'head_major').tobytes(),logical.tobytes())
        self.assertNotEqual(r.decode_qk(logical.tobytes(),logical.shape,'token_major').tobytes(),logical.tobytes())

    def test_identity_rejects_unpinned_payload_and_unknown_case(self):
        for rows,method,name in ((16,'official_self_cache','q'),(128,'independent_self_cache','k'),(32,'official_self_cache','q')):
            with self.assertRaises(ValueError):r.read_native_reference(b'\0'*4,rows=rows,method=method,name=name,shape=(1,12 if name=='q' else 2,rows,128))

    def test_size_shape_and_unknown_layout_reject(self):
        for shape,layout in (((1,2,3),'head_major'),((1,2,0,4),'head_major'),((1,2,3,4),'auto')):
            with self.assertRaises(ValueError):r.decode_qk(b'\0'*4,shape,layout)

    def test_pinned_decoder_checks_both_raw_and_logical_hash(self):
        x=np.arange(1*2*16*128,dtype='<u4').reshape(1,2,16,128)
        raw=x.transpose(0,2,1,3).copy().tobytes()
        key=(16,'official_self_cache','k')
        with patch.dict(r.QK_PINS,{key:(r.sha(raw),r.sha(x.tobytes()))}):
            self.assertEqual(r.read_native_reference(raw,rows=16,method=key[1],name='k',shape=x.shape).tobytes(),x.tobytes())
            with self.assertRaises(ValueError):r.read_native_reference(raw,rows=16,method=key[1],name='k',shape=(1,16,2,128))
        with patch.dict(r.QK_PINS,{key:(r.sha(raw),'0'*64)}):
            with self.assertRaises(ValueError):r.read_native_reference(raw,rows=16,method=key[1],name='k',shape=x.shape)


if __name__=='__main__':unittest.main()
