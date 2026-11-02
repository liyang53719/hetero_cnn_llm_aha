import hashlib,unittest
from pathlib import Path
D=Path(__file__).resolve().parent
def reverse(text):
    new='      if(vectorFire){if(vectors==0)println(s"B_FIRST_VECTOR_REQUEST tick=$ticks protocol_only=true");p.vector.request.bits.binaryAdd.get.expect(true.B);vectors+=1}\n      if(vectorReturn && vectors==1)println(s"B_FIRST_VECTOR_RETURN tick=$ticks protocol_only=true")'
    old='      if(vectorFire){p.vector.request.bits.binaryAdd.get.expect(true.B);vectors+=1}'
    if text.count(new)!=1:raise ValueError('single finite event insertion')
    text=text.replace(new,old)
    a=text.index('      // Current fields matter:');b=text.index('      def fire(',a);block=text[a:b]
    if text.count(block)!=1 or text.count('      p.burst.ready.poke(')!=1:raise ValueError('single unchanged check block')
    text=text[:a]+text[b:];text=text.replace('      p.burst.ready.poke(',block+'      p.burst.ready.poke(')
    return text
class Mechanical(unittest.TestCase):
    def test_spec_whole_byte_inverse(self):
        s=(D/'Public21DownOwnerCrossWindowProtocolOnlySpec.scala').read_text();self.assertEqual(hashlib.sha256(reverse(s).encode()).hexdigest(),'d48f2a40f4953deeb3dc449afc94131a487a428f9ae459ed94d42e11e17ea97d')
    def test_direct_driver_whole_byte_inverse(self):
        s=(D/'Public21DownOwnerDirectDriver.scala').read_text();self.assertEqual(hashlib.sha256(reverse(s).encode()).hexdigest(),'c53d12a233da2e1da51e926fb04e2f141270601abc076c2f46896467d038617b')
    def test_drive_then_check_then_snapshot_then_edge(self):
        s=(D/'Public21DownOwnerCrossWindowProtocolOnlySpec.scala').read_text();loop=s[s.index('    while(returnedWindows'):]
        drive=loop.index('      p.vector.busy.poke');checks=loop.index('      // Current fields matter:');snapshot=loop.index('      def fire(');edge=loop.index('      d.clock.step();ticks+=1')
        self.assertLess(drive,checks);self.assertLess(checks,snapshot);self.assertLess(snapshot,edge)
        self.assertNotIn('.poke(',loop[checks:snapshot]);self.assertIn('p.resetRequired.expect(false.B)',loop[checks:snapshot])
if __name__=='__main__':unittest.main()
