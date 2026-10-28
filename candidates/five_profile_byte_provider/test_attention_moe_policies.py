"""Independent whole-record field checks against Scala bit slices; no DUT."""
import unittest
import attention_moe_policies as p

def field(record, hi, lo):
    return (record >> lo) & ((1 << (hi-lo+1))-1)

def whole(pair, nxt=p.NULL):
    kind, payload = pair
    return kind | (nxt << 32) | (payload << 56)

class PolicyTest(unittest.TestCase):
    def test_qk(self):
        for role in (0,1):
            for recipe in (0xC1,0xC2):
                records=p.qknorm(role, 12 if role==0 else None, recipe)
                program, policy, extra=map(whole,records)
                self.assertEqual(field(program,71,56),0x32)
                self.assertEqual(field(program,79,72),2)
                self.assertEqual(field(program,103,96),16)
                self.assertEqual(field(program,127,104),0)
                self.assertEqual(field(policy,65,64),role)
                self.assertEqual(field(policy,67,66),0)
                self.assertEqual(field(policy,99,68),0)
                self.assertEqual(field(policy,107,100),128)
                self.assertEqual(field(policy,115,108),recipe)
                self.assertEqual(field(extra,79,56),12 if role==0 else p.NULL)
                self.assertEqual(field(extra,127,80),0)
            program,policy,extra=map(whole,p.rope(role))
            self.assertEqual(field(program,71,56),0x34)
            self.assertEqual(field(policy,67,66),1)
            self.assertEqual(field(policy,115,108),0xB1)
            self.assertEqual(field(extra,111,80),0)
    def test_core_context_and_matrix(self):
        for op in range(4):
            records=p.attention_core(op)
            policy,context=map(whole,records[-2:])
            self.assertEqual(field(policy,63,56),2)
            self.assertEqual(field(policy,67,64),op)
            self.assertEqual(field(policy,107,100),128)
            self.assertEqual(field(policy,115,108),0xA1 if op else 0)
            self.assertEqual(field(context,63,56),2)
            self.assertEqual(field(context,72,64),128)
            self.assertEqual(field(context,122,73),0)
            self.assertEqual(field(context,124,123),3)
            self.assertEqual(field(context,127,125),0)
            if op in (1,3):
                mat,aux=map(whole,records[:2])
                self.assertEqual(field(mat,71,56),128)
                self.assertEqual(field(mat,87,72),128 if op==1 else 256)
                self.assertEqual(field(mat,111,88),256 if op==1 else 128)
                self.assertEqual(field(mat,115,115),int(op==1))
                self.assertEqual(field(mat,127,116),0)
                self.assertEqual(field(aux,127,56),0x004000040020ffffff)
            elif op==2:
                self.assertEqual(field(whole(records[0]),79,72),1)
            else:self.assertEqual(len(records),2)
    def test_output_fence(self):
        for role in (0,1):
            w=whole(p.attention_output(role)[1])
            self.assertEqual(field(w,63,56),3)
            self.assertEqual(field(w,67,64),7)
            self.assertEqual(field(w,118,116),role)
            self.assertEqual(field(w,127,119),0)
        w=whole(p.attention_fence()[1])
        self.assertEqual(field(w,67,64),4)
        self.assertEqual(field(w,127,108),0)
    def test_manifest(self):
        for role in range(8):
            w=whole(p.moe_manifest_payload(role,100+role,200 if role==7 else None))
            self.assertEqual(field(w,7,0),0x60)
            self.assertEqual(field(w,66,64),role)
            self.assertEqual(field(w,90,67),100+role)
            if role==7:
                self.assertEqual(field(w,63,56),2)
                self.assertEqual(field(w,114,91),200)
                self.assertEqual(field(w,122,115),1)
                self.assertEqual(field(w,127,123),0)
            else:
                self.assertEqual(field(w,63,56),1)
                self.assertEqual(field(w,127,91),0)
    def test_invalid(self):
        calls=[lambda:p.qknorm(0), lambda:p.qknorm(1,42),lambda:p.qknorm(0,42,0xA1),
               lambda:p.rope(0,1),lambda:p.attention_core(4),lambda:p.attention_output(2),
               lambda:p.moe_manifest_payload(7,10),lambda:p.moe_manifest_payload(7,10,10),
               lambda:p.moe_manifest_payload(0,p.NULL),lambda:p.moe_manifest_payload(True,10)]
        for call in calls:
            with self.assertRaises(ValueError):call()

if __name__=='__main__': unittest.main()
