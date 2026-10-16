"""Cold source/contract checks. These do not compile, elaborate or simulate RTL."""
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_chisel import prepare as overlay
from candidates.qwen2_resident_matrix.raw_kv_parent import prepare_unit
from candidates.qwen2_resident_matrix.dense_a_hold_candidate import test_model as frozen


@pytest.fixture(scope='module')
def sources():
    with tempfile.TemporaryDirectory(prefix='a-hold-source-test-') as tmp:
        root = Path(tmp) / 'source'
        receipt = overlay.prepare(root)
        yield {p.name: p.read_text() for p in root.glob('*.scala')}, receipt


def owner_source(sources):
    return sources[0]['TransposedDenseOwner.scala'].split('class TransposedDenseDownOwner(', 1)[1]


def test_reproducible_real_parent_overlay_and_no_runtime_claim(sources):
    _, receipt = sources
    with tempfile.TemporaryDirectory(prefix='a-hold-second-') as tmp:
        second = overlay.prepare(Path(tmp) / 'source')
        assert second == receipt
    parent = json.loads((prepare_unit.HERE / 'unit_pins.json').read_text())
    assert receipt['parent_generated_sha256'] == parent['generated_sha256']
    assert len(receipt['generated_sha256']) == 13
    assert {p for p in receipt['generated_sha256'] if receipt['generated_sha256'][p] != receipt['parent_generated_sha256'][p]} == set(overlay.TARGETS)
    assert receipt['rtl_generated'] is False
    assert receipt['scala_compiled'] is False
    assert receipt['chisel_elaborated'] is False


def test_pins_fail_before_any_composition_or_output():
    with tempfile.TemporaryDirectory(prefix='a-hold-pin-drift-') as tmp:
        root = Path(tmp)
        with patch.object(overlay, 'ROOT', root), pytest.raises((ValueError, FileNotFoundError)):
            overlay.prepare(root / 'out')
        assert not (root / 'out').exists()


def test_fresh_output_required(sources):
    with tempfile.TemporaryDirectory(prefix='a-hold-not-fresh-') as tmp:
        with pytest.raises(ValueError, match='fresh A-hold'):
            overlay.prepare(Path(tmp))


def test_default_off_optional_internal_abi_and_payload_budget(sources):
    owner = owner_source(sources)
    bank = sources[0]['TransposedDenseBanks.scala']
    assert owner.startswith('burstWrites:Boolean=false,')
    assert 'enableRawKv:Boolean=false,enableAHold:Boolean=false) extends Module' in owner
    assert 'operandDepth=if(enableAHold)3 else 4' in owner
    assert 'new Queue(new MatrixStreamStep,operandDepth,pipe=true)' in owner
    assert 'heldA=if(enableAHold)Some(Reg(Vec(128,UInt(16.W))))else None' in owner
    assert 'readActivation=if(enableAHold)Some(Bool())else None' in bank
    assert 'activationValid=if(enableAHold)Some(Bool())else None' in bank
    # Whole declared packet and useful packet accounting must not be confused.
    packet_bits = 16*16 + 256*16 + 3 + 4
    hold_bits, control_bits = 128*16, 12+32+32+1+1
    assert packet_bits == 4359 and control_bits == 78
    assert 3*packet_bits + hold_bits + control_bits < 4*packet_bits
    assert 3*320 + 256 == 1216 < 4*320
    assert 'DenseOwnerIO.scala' not in overlay.TARGETS


def test_one_existing_a_port_and_unchanged_b_read_path(sources):
    bank = sources[0]['TransposedDenseBanks.scala'].split('class TransposedDownDenseBanks(', 1)[1]
    assert bank.count('SyncReadMem(1376,UInt(256.W))') == 1
    assert bank.count('SyncReadMem(160,UInt(256.W))') == 1
    assert bank.count('aBanks(bank).read(') == bank.count('aBanks(bank).write(') == 1
    assert bank.count('bBanks(bank).read(') == bank.count('bBanks(bank).write(') == 1
    assert 'val gatherActivation=readFire && io.read.bits.readActivation.getOrElse(true.B)' in bank
    assert 'loadFire || (gatherActivation && mt<8.U) || tileSignals.get.issueRead || tileSignals.get.issueWrite' in bank
    assert 'val readEnable=readFire && (first || rd1(3,0)===bank.U)' in bank
    assert 'io.read.ready:= !rmwPending && !io.zero.valid && !io.activation.valid && !tileSignals.get.busy' in bank
    assert 'when(kvBlock){io.activation.ready:=false.B;io.read.ready:=false.B}' in bank


def test_synchronous_credit_and_private_packet_capture(sources):
    owner = owner_source(sources)
    assert 'operands.io.count+&banks.io.response.valid.asUInt<operandDepth.U' in owner
    assert 'when(banks.io.read.fire){pendingAGeneration.get:=groupSequence}' in owner
    assert 'val fillingNow=banks.io.response.valid && pendingContext===0.U &&' in owner
    assert 'pendingK===readK && responseCurrent && responseHasA && !holdKill && !holdFault' in owner
    assert '(heldCurrent && heldAK.get===readK) || fillingNow' in owner
    assert 'responseA:=Mux(pendingContext===0.U,banks.io.response.bits.activation,heldA.get)' in owner
    assert 'step.b(m):=Mux(m.U<job.m,responseA(m),0.U)' in owner
    assert owner.index('when(pendingContext+1.U===contexts){heldAValid.get:=false.B}') > owner.index('heldAValid.get:=true.B')
    assert 'when(operands.io.enq.valid){assert(operands.io.enq.ready,' in owner


def test_fault_kill_has_no_response_ready_or_fire_feedback(sources):
    owner = owner_source(sources)
    start = owner.index('val badDmaOffer=')
    end = owner.index('val responseCurrent=', start)
    guard = owner[start:end]
    assert 'io.burstResponse.valid && burstOutstanding && responseBad' in guard
    assert 'burstResponse.fire' not in guard and 'burstResponse.ready' not in guard
    assert 'state=/=execute || !aCommitted || io.resetRequired || leaseInvalidate' in guard
    assert 'banks.io.zero.valid || banks.io.activation.valid || badDmaOffer' in guard
    assert 'holdAvailable && !holdKill && !holdFault' in owner
    assert 'operands.io.enq.valid:=banks.io.response.valid && status===0.U && !holdKill && !holdFault' in owner
    assert 'operands.io.deq.ready:=Mux(status=/=0.U,true.B,' in owner
    assert 'when(holdKill || holdFault){heldAValid.get:=false.B}' in owner
    # The patch never clears accepted DMA, seed, result or writeback debt.
    patch_text = (overlay.HERE / 'a_hold.patch').read_text()
    added = '\n'.join(x[1:] for x in patch_text.splitlines() if x.startswith('+') and not x.startswith('+++'))
    for name in ('burstOutstanding:=', 'seedOutstanding:=', 'writeState:=', 'groupDone:=', 'halfReady:='):
        assert name not in added


@pytest.mark.parametrize('begin,end', [(0,32), (16,128), (128,256), (240,256)])
def test_ordinal_identity_preserves_pair_address_and_order(sources, begin, end):
    owner = owner_source(sources)
    assert 'heldAK.get:=pendingK' in owner
    assert 'pendingK===readK' in owner
    assert 'executionBegin+((readK-executionBegin)^kPolicy.get.pairReverse.asUInt)' in owner
    for reverse in (0,1):
        addresses = [begin+((k-begin)^reverse) for k in range(begin,end)]
        assert sorted(addresses) == list(range(begin,end))
        # All contexts share the exact physical address for each ordinal;
        # per-output arithmetic continues to visit ordinals in original order.
        for contexts in (1,3,5):
            packets = [(k,c,addresses[k-begin]) for k in range(begin,end) for c in range(contexts)]
            for context in range(contexts):
                assert [k for k,c,_ in packets if c == context] == list(range(begin,end))
            assert len({(k,address) for k,_,address in packets}) == end-begin


def test_prepared_scala_scope_and_no_automatic_simulator(sources):
    scala = (overlay.HERE / 'AHoldUnit.scala').read_text()
    assert 'extends TransposedDenseDownOwner(' in scala
    emitter = (overlay.HERE / 'AHoldElaborate.scala').read_text()
    assert 'ChiselStage.emitCHIRRTL(owner())' in emitter
    assert 'emitSystemVerilog' not in scala and 'VerilatorBackendAnnotation' not in scala
    assert 'for(reuse<-Seq(false,true);full<-Seq(false,true))' in emitter
    assert 'exercise(d,reuse,32,false)' in scala and 'exercise(d,true,256,true)' in scala
    assert 'fault edge issued new bank work' in scala
    assert 'pending.isEmpty && accepted==returned' in scala
    assert 'subprocess.run' not in scala


def test_frozen_contract_packets_remain_equivalent():
    # Executes only the already-reviewed Python reference, not patched Chisel.
    job = frozen.Job(m=16,k=32,n=160)
    off = frozen.ColdDriver(frozen.make_owner(),job).run()
    on = frozen.ColdDriver(frozen.make_owner(True),job).run()
    assert off.packets == on.packets and off.writes == on.writes
    assert on.owner.hold_counts['a_gathers'] == 32
    assert on.owner.hold_counts['b_only_gathers'] == 128
    assert on.owner.max_reserved == 3


def test_frozen_contract_same_edge_fault_and_accepted_debt():
    frozen.test_same_edge_dma_fault_does_not_issue_new_bank_read_or_revive_hold()
    frozen.test_invalidation_drains_pending_debt_without_resurrection('invalidate_lease',2)


def test_frozen_reference_files_are_untouched():
    pins=json.loads((overlay.HERE / 'source_pins.json').read_text())
    for relative,digest in pins['frozen_reference_sha256'].items():
        assert hashlib.sha256((overlay.ROOT / relative).read_bytes()).hexdigest()==digest
