"""Source/mutation contracts only. Does not compile/elaborate/run the hardware."""
from pathlib import Path
from collections import Counter
import argparse
import difflib
import hashlib
import json
import re

R = Path(__file__).resolve().parent
checks = 0


def need(ok, why):
    global checks
    if not ok:
        raise ValueError(why)
    checks += 1


def without_comments(s):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', s, flags=re.S)


def deleted(a, b):
    return [line[1:] for line in difflib.ndiff(a.splitlines(), b.splitlines()) if line.startswith('- ')]


def contract(src, old):
    k = src['QwenOwnerProtocol.scala']; h = src['HostRuntimePrefixLeaseWiringV8.scala']
    c = src['GdnRuntimeChunkCoordinator.scala']; l = src['GdnRuntimeChunkLeafCollection.scala']
    p = src['GdnRuntimeRawPrepReceiptV8.scala']
    for name, text in src.items():
        stripped = without_comments(text)
        need('DontCare' not in stripped, 'no undefined proof '+name)
        need(not re.search(r'(?:SyncReadMem|Mem|Queue)\(', stripped), 'no new payload bank/queue '+name)
        if name in old:
            need(re.findall(r'Module\(new [^\n]+', text) == re.findall(r'Module\(new [^\n]+', old[name]),
                 'physical instances unchanged '+name)
    need(not deleted(old['QwenOwnerProtocol.scala'], k), 'Kernel old lines unchanged')
    need(not deleted(old['HostRuntimePrefixLeaseWiringV8.scala'], h), 'prefix old lines unchanged')
    need(l.replace('new GdnRuntimeRawPrepReceiptV8', 'new GdnRuntimeInputPrepResult') == old['GdnRuntimeChunkLeafCollection.scala'],
         'Collection only native receipt ABI replacement')
    for line in [
        'val runtimePrepDoneFire=if(enableRuntimeRawPrep)Some(Output(Valid(new GdnRuntimeRawPrepResultV7)))else None',
        'io.runtimePrepDoneFire.get.valid:=p.io.done.fire',
        'io.runtimePrepDoneFire.get.bits:=p.io.done.bits',
        'p.io.done.ready:=active && mode===4.U && ordinaryDone.ready',
        'require(!enableRuntimeRawPrep || enableRuntimeRmsNorm',
        'require(!enableRuntimeRmsNorm || (pipelined && enableUnifiedScalarService',
    ]:
        need(line in k, 'installed real Kernel path '+line)
    need(k.count('io.runtimePrepDoneFire.get.valid:=') == 1 and k.count('io.runtimePrepDoneFire.get.bits:=') == 1,
         'event has one real producer')
    # The Kernel's existing handshake assignments are literally unchanged.
    original_io = [s.strip() for s in old['QwenOwnerProtocol.scala'].splitlines() if re.search(r'\.(?:ready|valid)\s*:=', s)]
    changed_io = [s.strip() for s in k.splitlines() if re.search(r'\.(?:ready|valid)\s*:=', s) and 'runtimePrepDoneFire' not in s]
    need(changed_io == original_io, 'no Kernel ready/valid gating change')
    for line in [
        'val prepReceipt=Valid(new GdnRuntimeRawPrepReceiptV8)',
        'val prepReceiptValid=RegInit(false.B)',
        'val prepReceipt=Reg(new GdnRuntimeRawPrepReceiptV8)',
        'val prepReplacement=logicalStart && g.io.job.bits.kind===QwenOwnerKind.GdnInputPrep.U',
        'when(prepReplacement){prepReceiptValid:=false.B}',
        'val prepEvent=k.io.runtimePrepDoneFire.get',
        'val prepEventExact=owned && prepShape && !contextChanged &&',
        'g.io.physicalDone.fire && terminalExact &&',
        'prepEvent.bits.tag===physical && prepEvent.bits.accepted.asUInt===expectedPrep.asUInt &&',
        'g.io.physicalDone.bits.tag===prepEvent.bits.tag &&',
        'g.io.physicalDone.bits.status===prepEvent.bits.status &&',
        'g.io.physicalDone.bits.writeBytes===prepEvent.bits.writeBytes &&',
        'g.io.physicalDone.bits.cycles===prepEvent.bits.cycles',
        'val prepEventSuccess=prepEventExact && leaseEventSubmitted && !awaitPrepare &&',
        'prepEvent.bits.status===Status.Ok.U && prepEvent.bits.outputCommitted &&',
        'prepEvent.bits.writeBytes===logical.writeBytes &&',
        'prepEvent.bits.writeBytes===(expectedPrep.tokens.pad(64)*expectedPrep.layout.rowBytes.pad(64))(63,0)',
        'val receiptCurrent=authority.accepted && authority.transaction===prepReceipt.producer.transactionId &&',
        'authority.launch.epoch===prepReceipt.producer.hostEpoch && authority.launch.asUInt===host.asUInt',
        'val receiptFault=poison || currentIndependentFault || authority.currentFault || g.io.localFault || a.io.resetRequired',
        'when(prepEvent.valid){',
        'when(!prepEventExact || (prepEvent.bits.status===Status.Ok.U && !prepEventSuccess) || prepReceiptValid){',
        '}.elsewhen(prepEventSuccess && !receiptFault){',
        'prepReceipt.producer.transactionId:=transaction',
        'prepReceipt.producer.hostEpoch:=host.epoch',
        'prepReceipt.producer.ownerSequence:=physical',
        'prepReceipt.result:=prepEvent.bits',
        'when(receiptFault || (prepReceiptValid && !receiptCurrent)){prepReceiptValid:=false.B}',
        'out.prepReceipt.bits:=prepReceipt',
        'out.prepReceipt.valid:=prepReceiptValid && receiptCurrent && !receiptFault && !prepReplacement && !busy &&',
        'slots.map(i=>a.io.status(i).resourcesDrained).reduce(_&&_) && k.io.runtimeRms.get.resourcesDrained',
        'out.localFault:=poison || contextChanged || physicalOfferBad || prepareBad',
    ]:
        need(line in h, 'real retained prefix provenance '+line)
    need('prepReceipt.ready' not in h and 'consume' not in without_comments(h), 'no fabricated consumer/release input')
    need('prepEvent' not in re.search(r'out.localFault:=([^\n]+)', h).group(1), 'event does not combinationally drive localFault')
    need('prepEvent' not in re.search(r'val firstFault=([^\n]+)', h).group(1), 'event does not combinationally drive firstFault')
    original_io = [s.strip() for s in old['HostRuntimePrefixLeaseWiringV8.scala'].splitlines() if re.search(r'\.(?:ready|valid)\s*:=', s)]
    changed_io = [s.strip() for s in h.splitlines() if re.search(r'\.(?:ready|valid)\s*:=', s) and 'out.prepReceipt' not in s]
    need(changed_io == original_io, 'all existing prefix held/retire service handshakes unchanged')
    for line in [
        'val prepBinding=new GdnRuntimeChunkPrepBindingV8',
        'val prepDone=Flipped(Decoupled(new GdnRuntimeRawPrepReceiptV8))',
        'val prepConsumed=RegInit(false.B)',
        'when(io.prepDone.fire){',
        'val receipt=io.prepDone.bits;val r=receipt.result;val a=r.accepted',
        'val b=accepted.prepBinding;val producer=receipt.producer',
        'val fresh= !prepConsumed || (producer.transactionId>=lastPrepTransaction &&',
        'producer.ownerSequence>lastPrepOwner && producer.ownerSequence>lastChunkOwner && c.tag>lastChunkOwner)',
        'val good=r.status===Status.Ok.U && r.outputCommitted && fresh &&',
        'producer.transactionId===b.transactionId && producer.hostEpoch===b.hostEpoch &&',
        'producer.ownerSequence===b.producerOwner && producer.ownerSequence=/="hffffffff".U &&',
        'c.tag=/="hffffffff".U && c.tag>producer.ownerSequence &&',
        'r.tag===producer.ownerSequence && a.tag===producer.ownerSequence &&',
        'a.asUInt===b.source.asUInt && a.tokens===c.tokens &&',
        'a.layout.keyHeads===p.keyHeads && a.layout.valueHeads===p.valueHeads &&',
        'a.layout.layoutId===p.layoutId && a.layout.layoutVersion===p.layoutVersion &&',
        'a.layout.rowBytes===p.rowBytes && a.output===c.input &&',
        'a.reductionPolicy===accepted.prepReductionPolicy && a.gatePolicy===accepted.prepGatePolicy &&',
        'r.writeBytes===(c.tokens*p.rowBytes).pad(64)',
        'prepConsumed:=true.B;lastPrepTransaction:=producer.transactionId',
        'lastPrepOwner:=producer.ownerSequence;lastChunkOwner:=c.tag',
    ]:
        need(line in c, 'consumer producer identity '+line)
    # Only original prep acceptance changes; the entire issue/leaf fault/drain
    # suffix remains byte-for-byte equal, including held offers/terminal logic.
    marker='  for((fire,kind,next)<-Seq((io.stateJob.fire'
    need(c[c.index(marker):] == old['GdnRuntimeChunkCoordinator.scala'][old['GdnRuntimeChunkCoordinator.scala'].index(marker):],
         'all leaf issue/retire/fault/terminal semantics unchanged')
    for target in ('io.prepDone.ready:=', 'val faultNow=', 'val heldCommitment=', 'io.job.ready:='):
        need(next(s for s in c.splitlines() if target in s) == next(s for s in old['GdnRuntimeChunkCoordinator.scala'].splitlines() if target in s),
             'original fault-gated acceptance '+target)
    need(not re.search(r'(?:receipt|r|a|producer)\.(?:tag|ownerSequence|outputCommitted)\s*:=', without_comments(c)),
         'producer ACK never retagged or fabricated')
    need('r.tag===c.tag' not in c[c.index('  when(io.prepDone.fire)'):c.index(marker)], 'producer P not forced to consumer C')
    for line in ('val transactionId=UInt(64.W)', 'val hostEpoch=UInt(16.W)', 'val ownerSequence=UInt(32.W)',
                 'val result=new GdnRuntimeRawPrepResultV7', 'val source=new GdnRuntimeRawPrepJobV7'):
        need(line in p, 'explicit native V8 field '+line)
    need('GdnRuntimeInputPrepResult' not in p, 'historical receipt class not redefined')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-source-dir', type=Path, required=True, help='Ten exact original inputs, not bundled')
    args = parser.parse_args()
    pins = json.loads((R/'SOURCE_PINS.json').read_text())['source_check_originals']
    old = {}
    for row in pins:
        path = args.parent_source_dir / row['name']; data = path.read_bytes()
        need(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'frozen original unchanged '+str(path))
        old[row['name']] = data.decode()
    src = {p.name: p.read_text() for p in (R/'source').glob('*.scala')}
    need(len(src) == 5, 'single five-source candidate')
    # Optional Public21 wrapper does not buffer ordinary RawPrep completion:
    # the actual child event and outer Guard physicalDone fire coincide.
    router = old['Public21QkvReductionRouter.scala']
    for line in ('io.done.bits:=Mux(state===reducing,reduction.io.dense.result.bits,io.ordinaryDone.bits)',
                 'state===ordinary && io.ordinaryDone.valid)',
                 'io.ordinaryDone.ready:=state===ordinary && io.done.ready'):
        need(line in router, 'real ordinary completion pass-through '+line)
    guard = old['HostRuntimeOwnerGuardV5.scala']
    for line in ('val nextSequence=RegInit(0.U(32.W))',
                 'heldPhysicalSequence:=nextSequence;nextSequence:=nextSequence+1.U',
                 'val sequenceAvailable=nextSequence=/="hffffffff".U'):
        need(line in guard, 'real no-wrap owner allocator '+line)
    contract(src, old)
    mutations = [
        ('QwenOwnerProtocol.scala', 'valid:=p.io.done.fire', 'valid:=p.io.done.valid'),
        ('QwenOwnerProtocol.scala', 'bits:=p.io.done.bits', 'bits:=0.U.asTypeOf(p.io.done.bits)'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'g.io.physicalDone.fire && terminalExact', 'terminalExact'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'prepEvent.bits.accepted.asUInt===expectedPrep.asUInt', 'prepEvent.bits.accepted.tokens===expectedPrep.tokens'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'prepReceipt.producer.transactionId:=transaction', 'prepReceipt.producer.transactionId:=authority.transaction'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'prepReceipt.result:=prepEvent.bits', 'prepReceipt.result.outputCommitted:=true.B'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'prepEventSuccess && !receiptFault', 'prepEventSuccess'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'prepEvent.bits.writeBytes===logical.writeBytes', 'prepEvent.bits.writeBytes<=logical.writeBytes'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'authority.launch.epoch===prepReceipt.producer.hostEpoch', 'true.B'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'out.prepReceipt.valid:=prepReceiptValid && receiptCurrent && !receiptFault && !prepReplacement && !busy &&', 'out.prepReceipt.valid:=prepReceiptValid &&'),
        ('HostRuntimePrefixLeaseWiringV8.scala', '!receiptFault && !prepReplacement && !busy', '!receiptFault && !busy'),
        ('HostRuntimePrefixLeaseWiringV8.scala', 'out.localFault:=poison || contextChanged', 'out.localFault:=prepEvent.valid || poison || contextChanged'),
        ('GdnRuntimeChunkCoordinator.scala', 'producer.transactionId===b.transactionId', 'true.B'),
        ('GdnRuntimeChunkCoordinator.scala', 'producer.hostEpoch===b.hostEpoch', 'true.B'),
        ('GdnRuntimeChunkCoordinator.scala', 'producer.ownerSequence===b.producerOwner', 'true.B'),
        ('GdnRuntimeChunkCoordinator.scala', 'c.tag>producer.ownerSequence', 'c.tag===producer.ownerSequence'),
        ('GdnRuntimeChunkCoordinator.scala', 'a.asUInt===b.source.asUInt', 'a.tokens===b.source.tokens'),
        ('GdnRuntimeChunkCoordinator.scala', 'r.outputCommitted && fresh', 'r.outputCommitted'),
        ('GdnRuntimeChunkCoordinator.scala', 'r.writeBytes===(c.tokens*p.rowBytes).pad(64)', 'r.writeBytes<=(c.tokens*p.rowBytes).pad(64)'),
        ('GdnRuntimeChunkCoordinator.scala', 'when(io.prepDone.fire){', 'when(io.prepDone.valid){'),
        ('GdnRuntimeChunkLeafCollection.scala', 'coordinator.io.prepDone<>io.prepDone', 'coordinator.io.prepDone.bits.result.outputCommitted:=true.B'),
    ]
    for name, before, after in mutations:
        need(before in src[name], 'mutation anchor '+before)
        changed = dict(src); changed[name] = changed[name].replace(before, after, 1)
        try:
            contract(changed, old)
        except ValueError:
            pass
        else:
            raise ValueError('mutation escaped: '+before)
    print(json.dumps(dict(status='PASS_SOURCE_CONTRACT_ONLY', checks=checks,
        rejected_mutations=len(mutations), source_files=len(src), frozen_pins=len(pins),
        scala_compile=False, elaboration=False, rtl=False, dut=False), indent=2))


if __name__ == '__main__':
    main()
