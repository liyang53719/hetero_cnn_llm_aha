#!/usr/bin/env python3
"""Assemble the actual resident Host chain and check the official BF16 source patch.

Only copies frozen sources and applies candidate patches in a NEW scratch tree.
Does not compile Scala, elaborate Chisel, generate RTL, execute hardware arithmetic,
measure resources, or establish numerical/physical acceptance. Source checks are
necessary wiring/structure evidence, not a substitute for those later gates.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GROUP = HERE.parent / 'ffn_group'
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER = 'candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala'
TOUCHED = tuple(PREFIX + name for name in (
    'QwenOwnerProtocol.scala', 'HostBlockTop.scala', 'HostBlockCommands.scala',
    'VectorSilu.scala', 'OverlappedSilu.scala', 'ElementwiseMemoryEngine.scala',
    'Qwen2Block.scala')) + (OWNER,)
PARENT_SHA256 = {
    'check_frontend.py': '16aa6c7f9d4b609275d5e1d946b78897bcc5d5de32508c4677e57d0cfe3db361',
    'source_pins.json': 'bf8b3f7619abc3513edc12cd465fd54ee760860760975502a6e9dfc0c56b6f67',
}
PUBLIC21_OPCODES = (0x32, 0x20, 0x30, 0x34, 0x20, 0x30, 0x34, 0x20, 0x30,
                    0x41, 0x23, 0x33, 0x24, 0x20, 0x30, 0x32, 0x20, 0x20,
                    0x35, 0x20, 0x30)
MATERIALIZED_DENSE_PCS = (13, 16, 17, 19)
RAW_QKV_PCS = (1, 4, 7)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def source_inventory(text):
    """Lexical instantiated-module and SRAM declarations, not elaborated QoR."""
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return {
        'module_constructors': dict(sorted(Counter(re.findall(r'Module\(new\s+(\w+)', clean)).items())),
        'memory_declarations': re.findall(r'\b(?:SyncReadMem|Mem)\([^\n]*', clean),
    }


def audit_sources(before, after):
    """Fail closed on missing boundaries, detached policy propagation, or storage drift."""
    require(before.keys() == after.keys(), 'assembled production source set changed')
    actual = {p for p in before if before[p] != after[p]}
    require(actual == set(TOUCHED), 'unexpected/missing production patch targets')
    inventory = {}
    for path in before:
        old, new = source_inventory(before[path]), source_inventory(after[path])
        require(old == new, 'source arithmetic/SRAM constructors changed: ' + path)
        if path in actual:
            inventory[path] = new
    def body(name):
        return after[PREFIX + name]
    def contains(text, fragments, label):
        for fragment in fragments:
            require(fragment in text, label + ': missing ' + fragment)
    proto = body('QwenOwnerProtocol.scala')
    contains(proto, ('sealed trait Qwen2NumericPolicy', 'case object LegacyV0',
        'case object Qwen2OfficialBf16V2', '!s.nativeProfile', 's.hidden==1536',
        's.ffn==8960', 's.headDim==128', 's.maxTokens==1024',
        'val materializeDenseOutput=Bool()',
        'enableGdnSoftplus=bf16GdnCore,numericPolicy=numericPolicy',
        'enableFfnDrain=enableFfnDrain,numericPolicy=numericPolicy',
        'enableTileLoan=enableFfnTiles,numericPolicy=numericPolicy'), 'policy/kernel wiring')
    top = body('HostBlockTop.scala')
    require(top.count('numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0') == 2,
            'Host root/collection must preserve explicit LegacyV0 defaults')
    require(top.count('numericPolicy=numericPolicy') == 3,
            'Host collection/parser/kernel policy propagation missing')
    host = body('HostBlockCommands.scala')
    contains(host, ('!officialBf16.B || l.commands===21.U',
        'pc===13.U || pc===16.U || pc===17.U || pc===19.U',
        'bound.materializeDenseOutput:=officialMaterializeDense && dense',
        'j.materializeDenseOutput:=officialMaterializeDense',
        '.elsewhen(!officialRoleOK){fail(Status.Unsupported.U)}',
        'waitEvent===pc && signalEvent===pc+1.U',
        'nativeWeight && a.dims(1)===Mux(pc===19.U,s.ffn.U,s.hidden.U)',
        '13.U->(dense && inputA(12) && readonly(b))',
        '16.U->(dense && inputA(15) && readonly(b))',
        '17.U->(dense && inputA(15) && readonly(b))',
        '19.U->(dense && inputA(18) && readonly(b))',
        '14.U->(vector && a.address===officialHidden.get && inputB(13)',
        '20.U->(vector && inputA(14) && inputB(19)',
        '9.U->(append && inputA(6) && inputB(8))',
        '10.U->(qk && inputA(3) && inputB(9))',
        'b.address===o(9)+officialRows.get.pad(64)*s.kv.U*4.U'), 'public role binding')
    dense_roles = re.search(r'val officialMaterializeDense=officialBf16.B && \(([^\n]+)\)', host)
    require(dense_roles is not None and tuple(int(x) for x in re.findall(r'pc===(\d+).U', dense_roles[1])) == MATERIALIZED_DENSE_PCS,
            'Dense materialization role set drift')
    opcodes = re.search(r'val expectedOpcode=VecInit\(Seq\((.*?)\)\.map', host, re.S)
    require(opcodes is not None and tuple(int(x.strip(), 0) for x in opcodes[1].split(',')) == PUBLIC21_OPCODES,
            'public21 opcode contract drift')
    require(host.count('rememberOfficial()') == 5, 'producer snapshots not captured at all validated branches')
    # No on-DDR flags, byte formulas, or storage assignment may be repurposed.
    for name in ('HostBlockCommands.scala', 'QwenOwnerProtocol.scala'):
        old = before[PREFIX + name]
        new = body(name)
        flags = lambda s: re.findall(r'(?:\w+\.)*(?:outputBf16|activationBf16|weightBf16):=[^;\n}]*', s)
        require(flags(old) == flags(new), 'storage flag assignment drift: ' + name)
    core = body('Qwen2Block.scala')
    contains(core, ('def materialize(x:UInt):UInt=if(officialBf16)F32.bf(x)else x',
        'new ElementwiseMemoryEngine(elemCfg,LocalSramConfig(rowsPerBank=elemCfg.localBytes/256),numericPolicy=numericPolicy)',
        '(rmsBlock.pad(11)<<9)+(rmsTerm.pad(11)<<5)+(rmsResidue.pad(11)<<3)+lane',
        'localRead(rmsIndex>>4,"normOfficialSquare")',
        'calc(ScalarOp.MulIeeeRne,av(rmsIndex(3,0)),av(rmsIndex(3,0)),"normOfficialAdd")',
        'calc(ScalarOp.Add,rmsPartial,scalarValue,"normOfficialTerm")',
        'when(rmsTerm===15.U){calc(ScalarOp.Add,rmsResidueSum,scalarValue,"normOfficialBlock")}',
        'when(rmsBlock===2.U){calc(ScalarOp.Add,rmsLaneSum,scalarValue,"normOfficialResidue")}',
        'when(rmsResidue===3.U){calc(ScalarOp.Add,sum,scalarValue,"normOfficialLane")}',
        'when(lane===7.U){state:=st("normMean")}',
        'calc(ScalarOp.Div,sum,F32.lit(1536.0),"normEps")',
        'calc(ScalarOp.Add,scalarValue,F32.lit(1e-6),"normSqrt")',
        'calc(ScalarOp.Sqrt,scalarValue,0.U,"normInv")',
        'calc(ScalarOp.Div,F32.lit(1),scalarValue,"normEmit")',
        'val normalized=VecInit(vout.map(materialize))',
        'when(officialBf16.B && normalized.map(x=> !TensorMath.finite(x)).reduce(_||_)){fail(Status.Numerical.U)}',
        '.otherwise{tmp:=normalized;state:=st("normProduct")}',
        'vectorA:=tmp;write(base+nOut',
        'calc(ScalarOp.Mul,materialize(scalarValue),F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")',
        'val score=materialize(scalarValue);scores.write(key,score)',
        'when(state===st("attPVWrite")){write(ptr("att",rowOffset(s.hidden.U)+head*s.headDim.U+col),VecInit(acc.map(materialize)).asUInt',
        'TensorMath.bf16Rne(Mux(isDense'), 'core arithmetic boundary graph')
    scalar = body('BlockFloat.scala')
    contains(scalar, ('val MulIeeeRne=6',
        'alu.io.op:=op===ScalarOp.Mul.U || op===ScalarOp.MulIeeeRne.U',
        'err:=alu.io.exceptionFlags(4,2).orR ||',
        '(alu.io.exceptionFlags(1) && op=/=ScalarOp.MulIeeeRne.U) || !TensorMath.finite(alu.io.out)'),
        'existing IEEE multiply exception policy')
    require(before[PREFIX + 'BlockFloat.scala'] == scalar, 'legacy scalar policy modified')
    contains(core, ('val bad=(0 until 16).map(i=> !TensorMath.finite(data(32*i+31,32*i))).reduce(_||_)',
        'when(bad){fail(Status.Numerical.U)}.otherwise{',
        'vectorA:=tmp;write(base+nOut+((rowOffset(s.hidden.U)+col).pad(64)<<2),VecInit(vout.map(F32.bf)).asUInt'),
        'final RMS BF16 overflow checked before store')
    added32 = re.findall(r'val (rms\w+)=RegInit\(0.U\(32.W\)\)', core)
    require(added32 == ['rmsPartial', 'rmsResidueSum', 'rmsLaneSum'], 'RMS partial register bound/order changed')
    for state, expected in {
        'ropeCos': 'cv:=VecInit(packet.asTypeOf(cv).map(materialize))',
        'ropeSin': 'dv:=VecInit(packet.asTypeOf(dv).map(materialize))',
        'ropeMul0': 'tmp:=VecInit(vout.map(materialize))',
        'ropeMul1': 'tmp2:=VecInit(vout.map(materialize))',
        'ropeAdd0': 'acc:=VecInit(vout.map(materialize))',
        'ropeAdd1': 'tmp:=VecInit(vout.map(materialize))',
        'ropeWrite0': 'tmp2:=VecInit(vout.map(materialize))',
        'ropeWrite1': 'VecInit(vout.map(materialize)).asUInt',
        'biasSum': 'VecInit(vout.map(materialize)).asUInt',
    }.items():
        line = next((x for x in core.splitlines() if 'when(state===st("' + state + '"))' in x), '')
        require(expected in line, 'missing materialization at ' + state)
    down = after[OWNER].split('class TransposedDenseDownOwner', 1)[1]
    contains(down, ('val raw=finalValue(n)(Cat(beat(0),writeRow))',
        'if(officialBf16)Mux(job.materializeDenseOutput,F32.bf(raw),raw)else raw',
        'p.write.bits.value(l):=(if(officialBf16)Mux(job.materializeDenseOutput,F32.bf(raw),raw)else raw)',
        'val shape=(!officialBf16.B || j.materializeDenseOutput)',
        'savingPrefix || !(job.outputBf16 || (officialBf16.B && job.materializeDenseOutput))'), 'Dense final/window boundary')
    for fragment in (
        'val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))',
        'val prefix=VecInit((0 until 16).map(i=>finalValue(prefixWriteIndex(7,4))(Cat(prefixWriteIndex(3,0),i.U(4.W))))).asUInt',
        'Mux(savingPrefix,prefix,Mux(job.outputBf16,bf16,fp32))',
        'val outputBytes=Mux(job.outputBf16,2.U(3.W),4.U(3.W))',
        'val outputBeats=Mux(job.outputBf16,1.U(2.W),2.U(2.W))',
        'val savingPrefix=chunkEnd<job.k',
        'finalValue:=r.value',
    ):
        require(fragment in down and fragment in before[OWNER], 'FP32 partial/store packing invariant drift: ' + fragment)
    silu = body('VectorSilu.scala')
    contains(silu, ('Mux(phase===4.U || phase===5.U,F32.bf(cores(i).io.result.bits),cores(i).io.result.bits)',
        'val cores = Seq.fill(lanes)(Module(new BlockScalarFloat))',
        'new SiluVectorUnit(16,numericPolicy=numericPolicy)'), 'shared SiLU phase boundaries')
    contains(body('OverlappedSilu.scala'), ('new VectorSiluOwner(enableTileLoan,numericPolicy=numericPolicy)',
        'new OverlappedSiluOwner(numericPolicy=numericPolicy)',
        'new SiluVectorUnit(16,numericPolicy=numericPolicy)'), 'SiLU wrapper propagation')
    elem = body('ElementwiseMemoryEngine.scala')
    contains(elem, ('Mux(job.op===ElemOp.Add.U,F32.bf(alu.io.out),alu.io.out)',
        'Mux(binary,arithmeticValue,a(32*i+31,32*i))',
        'val outputStride=Mux(job.dstBf16,32.U,16.U)'), 'residual Add/Copy/storage separation')
    return {'changed_production_sources': sorted(actual),
            'source_constructor_inventory_unchanged': inventory,
            'rms_added_fp32_partial_registers': added32,
            'dense_materialization_pcs': list(MATERIALIZED_DENSE_PCS),
            'raw_fp32_qkv_pcs': list(RAW_QKV_PCS),
            'public_command_and_descriptor_sources_unchanged': True,
            'source_structure_only': True, 'scala_compiled': False,
            'chisel_elaborated': False, 'rtl_generated': False,
            'hardware_arithmetic_executed': False, 'qor_measured': False,
            'numerical_acceptance': False}


def compose(out):
    out = Path(out).resolve()
    require(not out.exists(), 'use a new source assembly directory')
    require(not out.is_relative_to(ROOT / 'chisel') and not out.is_relative_to(ROOT / 'candidates'),
            'assembly destination must not overwrite production/candidate files')
    for name, digest in PARENT_SHA256.items():
        require(sha((GROUP / name).read_bytes()) == digest, 'resident group helper/pins drift: ' + name)
    spec = importlib.util.spec_from_file_location('official_bf16_parent_group', GROUP / 'check_frontend.py')
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    out.mkdir(parents=True)
    paths, pins = parent.compose(out)
    require(pins == json.loads((GROUP / 'source_pins.json').read_text()), 'resident source composition identity drift')
    before = {p: (out / p).read_text() for p in paths}
    patch = HERE / 'chisel_policy.patch'
    patch_targets = re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.M)
    require(set(patch_targets) == set(TOUCHED) and len(patch_targets) == len(TOUCHED), 'patch target scope drift')
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=out, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=out, check=True)
    after = {p: (out / p).read_text() for p in paths}
    report = audit_sources(before, after)
    report.update(status='PASS_SOURCE_STRUCTURE_ONLY',
        source_assembly=str(out), parent_composition='ffn_group exact source_pins.json',
        patch_sha256=sha(patch.read_bytes()),
        parent_source_pins_sha256=PARENT_SHA256['source_pins.json'],
        assembled_source_sha256={p: sha((out / p).read_bytes()) for p in paths},
        helper_sha256=sha(Path(__file__).read_bytes()))
    return paths, report, before, after


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    _, report, _, _ = compose(args.out)
    (args.out / 'official_bf16_source_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'patch_sha256',
        'scala_compiled', 'chisel_elaborated', 'rtl_generated', 'numerical_acceptance')}))
