import unittest,struct
from .pack import TypedABPackDriver,TypedMemory,WriteCommand,WriteAck

class PackTests(unittest.TestCase):
 def build(self,m=16):
  mem=TypedMemory();raws=[]
  for role,base in enumerate((0x1000,0x4000)):
   r=mem.allocate_output(base,m*64);raw=b''.join(struct.pack('<32H',*([role*1000+t]*32)) for t in range(m));raws.append(raw)
   for t in range(m):
    mem.begin_write(WriteCommand(base+t*64,1,10+role));mem.write_data(struct.unpack('<32H',raw[t*64:(t+1)*64]),True);mem.acknowledge(WriteAck(10+role,False,64))
   mem.publish(base,(10+role,None,m*64))
  mem.allocate_output(0x10000,m*128)
  return TypedABPackDriver(mem,0x1000,0x4000,0x10000,m),raws
 def run_driver(self,d,controls=lambda d:{}):
  for _ in range(5000):
   d.tick(**controls(d))
   if d.response is not None:return
  self.fail('no terminal')
 def test_real_reorder_m16_m128(self):
  for m in (16,128):
   d,raws=self.build(m);self.run_driver(d)
   self.assertIsNone(d.response.status);self.assertTrue(d.output.published)
   self.assertEqual(d.output.raw(),b''.join(raw[t*64:(t+1)*64] for t in range(m) for raw in raws))
   self.assertEqual(d.counts['ack_bytes'],m*128);self.assertEqual(d.counts['read_bytes'],m*128)
 def test_read_and_ack_errors(self):
  for state,index in [('read_wait',0),('read_wait',1),('ack_wait',0),('ack_wait',31)]:
   d,_=self.build();self.run_driver(d,lambda x:{'read_error':True} if x.state==state=='read_wait' and x.index==index else {'ack_error':True} if x.state==state=='ack_wait' and x.index==index else {})
   self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published);self.assertIsNone(d.memory.pending)
 def test_final_ack_stall_and_held_success_abort(self):
  d,_=self.build()
  while not(d.state=='ack_wait' and d.index==31):d.tick()
  for _ in range(4):d.tick(memory_response_ready=False)
  self.assertIsNotNone(d.memory.pending);self.assertFalse(d.output.published)
  d.tick();self.assertEqual(d.state,'terminal')
  for _ in range(3):d.tick(response_ready=False)
  d.tick(abort=True,response_ready=False);d.tick()
  self.assertEqual(d.response.status,'ABORTED');self.assertFalse(d.output.published)
 def test_abort_drains_real_accepted_write(self):
  d,_=self.build()
  while d.state!='ack_wait':d.tick()
  d.tick(abort=True,memory_response_ready=False)
  self.assertIsNotNone(d.memory.pending);self.assertIsNone(d.response)
  d.tick();d.tick();self.assertIsNone(d.memory.pending);self.assertFalse(d.output.published)
 def test_readonly_or_missing_ack_rejected(self):
  d,raws=self.build();d.sources[0].readonly=True
  with self.assertRaises(ValueError):TypedABPackDriver(d.memory,0x1000,0x4000,0x10000,16)
 def test_wrong_ack_identity_rejected(self):
  d,_=self.build()
  while d.state!='ack_wait':d.tick()
  with self.assertRaises(ValueError):d.memory.acknowledge(WriteAck(d.tag+1,False,64))
  with self.assertRaises(ValueError):d.memory.acknowledge(WriteAck(d.tag,False,128))
  self.assertIsNotNone(d.memory.pending);self.assertFalse(d.output.published)
if __name__=='__main__':unittest.main()
