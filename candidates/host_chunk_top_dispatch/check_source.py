"""Small source/ancestry checks only. No elaboration, simulation or numerical signoff."""
from pathlib import Path
import argparse,hashlib,json,re
C=Path(__file__).resolve().parent;W=C.parent
checks=0
def need(x,msg):
 global checks
 checks+=1
 if not x:raise ValueError(msg)
def pin(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-source-dir',type=Path,required=True,help='Eighteen exact original sources, not bundled')
args=parser.parse_args()
pins=json.loads((C/'SOURCE_PINS.json').read_text())
source_paths={r['name']:C/r['path'] for r in pins['compiler_sources'] if r['location']!='requires_parent'}
s={n:p.read_text() for n,p in source_paths.items()}
for row in pins['compiler_sources']:
 if row['location']=='requires_parent':continue
 q=pin(source_paths[row['name']]);need(q['bytes']==row['bytes'] and q['sha256']==row['sha256'],'public source drift '+row['name'])
base={'members':[dict(path=str(args.parent_source_dir/r['name']),bytes=r['bytes'],sha256=r['sha256']) for r in pins['source_check_originals']]}
for row in base['members']:
 q=pin(Path(row['path']));need(q==row,'original drift '+row['path'])
unchanged=['GdnRuntimeChunkCoordinator.scala','GdnRuntimeChunkLeafCollection.scala','GdnRuntimeRawPrepReceiptV8.scala',
 'UnifiedMoeSharedArithmeticAdapterV5.scala','UnifiedMoeSharedArithmeticProtocolV5.scala',
 'GdnRuntimeChunkDerivedAndPairV2Owner.scala','GdnRuntimeChunkExecuteOwnerV8.scala']
byname={Path(x['path']).name:x for x in base['members']}
for n in unchanged:need(pin(source_paths[n])['sha256']==byname[n]['sha256'],'unchanged numerical/receipt '+n)
required={
'HostBlockTopV4.scala':['new SharedMemoryArbiter(17)','enableRuntimeChunk=true','HostRuntimeChunkWiringV9.connect','normLease,prefixScalar,hub,ordinaryAdmissionFault','owner.io.runtimeChunk.get.committed:=cmd.io.runtimeChunkCommitted','!chunkEventsPending && chunkResourcesDrained'],
'HostRuntimeChunkProtocolV9.scala':['val prepBinding=Input(new GdnRuntimeChunkPrepBindingV8)','j.kind===QwenOwnerKind.GdnRecurrent.U && !j.gdnRecurrentMode &&','(j.m===16.U || j.m===128.U)','x.context.tag:=j.tag','x.context.scratch:=j.c','x.prepBinding:=b'],
'QwenOwnerProtocol.scala':['Some(Module(new GdnRuntimeChunkLeafCollection))','val ordinaryCanStart=canStartWithTiles || (enableRuntimeChunk.B && chunkJobHeld && choose===14.U)', '14.U->chunk.map(_.io.job.ready).getOrElse(false.B)','14.U->chunkValid','14.U->chunkDone','(enableRuntimeChunk.B && mode===14.U)','port.doneFire.valid:=c.io.done.fire','port.jobFire:=c.io.job.fire'],
'HostRuntimeChunkWiringV9.scala':['val logicalStart=g.io.job.fire && chunk(g.io.job.bits)','receipt:=saved','val start=g.io.physicalJob.fire && chunk(g.io.physicalJob.bits)','p.prepDone.valid:=receiptOffer;p.prepDone.bits:=receipt','when(p.prepDone.fire)','g.io.physicalJob.bits.tag>receipt.producer.ownerSequence','v.lease.identity.transactionId:=transaction','v.lease.identity.ownerSequence:=physical','v.lease.identity.stage:=72.U','v.authorityKind:=UnifiedArithmeticAuthorityKindV5.OrdinaryChunk.U',
'val currentFault=independentFault || g.io.localFault || poison || lifetimeChanged','a.io.acquire(8).valid:=prefix.scalarAcquire.valid || acquirePending','a.io.acquire(10).valid:=acquirePending','scalarOwner:=Mux(owned,scalarChoice+&1.U,0.U)','vectorPending:=true.B;vectorOwner:=vectorChoice','Mux(scalarChoiceHeld,scalarHeldChoice','Mux(vectorChoiceHeld,vectorHeldChoice','r.bits.tag===memoryTags(i)','request.bits.tag(63,32)===physical','hub.io.requests(i+12)','r.accepted.asUInt===expectedJob.asUInt','g.io.physicalDone.bits.status===r.status','g.io.physicalDone.bits.writeBytes===r.outputAckBytes+r.stateAckBytes','when(!exact || (r.status===Status.Ok.U && !successProof)){poison:=true.B}\n      .otherwise{','!p.scalar.map(x=>x.request.valid || x.result.valid).reduce(_||_)','!p.vector.map(x=>x.request.valid || x.result.valid).reduce(_||_)','p.fabricFault:=RegNext(', '663648.U+8.U*logical.m.pad(32)*logical.n.pad(32)'],
'HostBlockCommandsV4.scala':['sameAllocation(a,runtimePrepTensor)','runtimeChunk && !rcDistinct','runtimeChunk && !chunkLive','runtimeChunk && !chunkFresh','bound.c:=rhOut.address;bound.gdnStateOut:=rhIn.address','bound.gdnRecurrentMode:=true.B // explicit legacy mode','runtimeConv || runtimeChunk || coreRecurrent','shape2(rhOut,prepHeads,chunkStride>>2)','sourceAllowed(b,9.U)','Seq(d,rhIn,rhOut).map(t=>fresh(t) && readwrite(t))','io.runtimeChunkCommitted.valid:=stateValid'],
'SharedMemoryArbiter.scala':['require(clients >= 2 && clients <= 32)','val owner = Reg(UInt(log2Ceil(clients).W))','request.tag := sequence','originalTag := arb.io.out.bits.tag','reply.tag := originalTag','Seq.fill(clients)(0.U(64.W))']}
def contracts(src):
 for n,parts in required.items():
  for part in parts:
   if part not in src[n]:raise ValueError(n+' missing '+part)
for n,parts in required.items():
 for part in parts:need(part in s[n],n+' '+part)
contracts(s)
mutations=[('HostBlockTopV4.scala','new SharedMemoryArbiter(17)','new SharedMemoryArbiter(12)'),
 ('HostRuntimeChunkWiringV9.scala','g.io.physicalJob.bits.tag>receipt.producer.ownerSequence','g.io.physicalJob.bits.tag>=receipt.producer.ownerSequence'),
 ('HostRuntimeChunkWiringV9.scala','p.prepDone.valid:=receiptOffer','p.prepDone.valid:=prefix.prepReceipt.valid'),
 ('HostRuntimeChunkWiringV9.scala','val logicalStart=g.io.job.fire','val logicalStart=g.io.job.valid'),
 ('HostRuntimeChunkWiringV9.scala','val start=g.io.physicalJob.fire','val start=g.io.physicalJob.valid'),
 ('HostRuntimeChunkWiringV9.scala','when(p.prepDone.fire)','when(p.prepDone.valid)'),
 ('HostRuntimeChunkWiringV9.scala','g.io.physicalDone.bits.status===r.status','true.B'),
 ('HostRuntimeChunkWiringV9.scala','g.io.localFault || poison','poison'),
 ('HostRuntimeChunkWiringV9.scala','r.bits.tag===memoryTags(i)','true.B'),
 ('HostRuntimeChunkWiringV9.scala','!p.scalar.map(x=>x.request.valid || x.result.valid).reduce(_||_)','true.B'),
 ('HostRuntimeChunkProtocolV9.scala','(j.m===16.U || j.m===128.U)','true.B'),
 ('SharedMemoryArbiter.scala','clients <= 32','clients <= 16')]
for n,a,b in mutations:
 mutant=dict(s);mutant[n]=mutant[n].replace(a,b,1)
 try:contracts(mutant)
 except ValueError:pass
 else:raise ValueError('surviving mutation '+a)
 need(True,'rejected mutation')
need(s['QwenOwnerProtocol.scala'].count('Module(new GdnRuntimeChunkLeafCollection)')==1,'one actual collection')
need(s['UnifiedMoeSharedArithmeticAdapterV5.scala'].count('Module(new UnifiedVectorElement32BankV4)')==1,'one bank')
need(s['HostBlockTopV4.scala'].count('Module(new SharedMemoryArbiter(')==1,'one hub')
need('new Scalar' not in s['HostRuntimeChunkWiringV9.scala'] and 'new UnifiedVectorElement32Bank' not in s['HostRuntimeChunkWiringV9.scala'],'no physical arithmetic in helper')
# The runtime publication branch must not update committed roots or publish scratch.
publish=s['HostBlockCommandsV4.scala'].split('.elsewhen(bound.kind===QwenOwnerKind.GdnRecurrent.U){',1)[1].split('}.elsewhen(bound.kind===QwenOwnerKind.Dense.U)',1)[0]
for bad in ['stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:=','starts(stateIndex):=bound.c']:
 need(bad not in publish,'staging not root commit '+bad)
print(json.dumps(dict(status='PASS_SOURCE_ONLY_NOT_DUT',checks=checks,rejected_mutations=len(mutations),unchanged_numerical_receipt_sources=len(unchanged),source_files=len(s)),indent=2))
