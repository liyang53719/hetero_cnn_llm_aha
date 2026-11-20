import unittest
from pc1_weight_feed_trace import audit

SPANS={"input_activation":(0x1000,0x1100),"weight":(0x2000,0x2200),"output":(0x3000,0x3100)}
P0="TRACE_COMPLETION_FIRE profile=0 tick=101 count=1"
def event(t,kind,data):
    return f"TRACE_CONSUMED profile=0 tick={t} {kind} {data}"

class TestAudit(unittest.TestCase):
    def test_duplicate_window_and_partial(self):
        rows=[P0,event(103,"AR","addr=0x2000 id=2 len=1"),event(105,"R","id=2 last=0"),
              event(107,"R","id=2 last=1"),event(109,"AR","addr=0x2040 id=2 len=1"),
              event(111,"R","id=2 last=0"),event(113,"R","id=2 last=1")]
        p=audit(rows,0,112,SPANS)
        self.assertEqual(p["open_AR_count"],1)
        self.assertEqual(p["outstanding_R_beats"],1)
        self.assertEqual(list(p["traffic"]["weight"].values()),[2,3,192,128,64])
        q=audit(rows,0,116,SPANS)
        self.assertEqual(q["open_AR_count"],0)
        self.assertEqual(list(q["traffic"]["weight"].values()),[2,4,256,192,64])

    def test_state_and_barrier(self):
        rows=[event(99,"R","id=0 last=1"),P0,
              event(103,"AR","addr=0x1000 id=0 len=0"),event(105,"R","id=0 last=1"),
              "TRACE_COMPLETION_FIRE profile=0 tick=107 count=2",
              event(109,"AR","addr=0x2000 id=0 len=0"),event(111,"R","id=0 last=1")]
        a=audit(rows,0,112,SPANS)
        self.assertEqual(a["traffic"]["weight"]["accepted_R"],0)
        self.assertEqual(a["traffic"]["input_activation"]["accepted_read_bytes"],64)
        self.assertEqual(a["typed_PC1_tick"],107)

    def test_wrong_last_or_sibling_or_unknown_scope(self):
        with self.assertRaisesRegex(ValueError,"orphan"):
            audit([P0,event(103,"R","id=0 last=1")],0,110,SPANS)
        with self.assertRaisesRegex(ValueError,"crosses"):
            audit([P0,event(103,"AR","addr=0x20c0 id=0 len=5")],0,110,SPANS)
        with self.assertRaisesRegex(ValueError,"last"):
            audit([P0,event(103,"AR","addr=0x2000 id=0 len=0"),event(105,"R","id=0 last=0")],0,110,SPANS)
        self.assertIsNone(audit([P0,event(103,"AR","addr=0x2000 id=0 len=0")],1,110,SPANS)["typed_PC0_tick"])
if __name__=="__main__":
    unittest.main()
