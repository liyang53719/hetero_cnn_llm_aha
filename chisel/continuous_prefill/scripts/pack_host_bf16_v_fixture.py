#!/usr/bin/env python3
"""Source-authenticated layer3 V operands for the production Host path.

The standalone CLI reuses the code-pinned capture. The fresh top-level wrapper
calls rebuild_session(), retaining its frozen materializer digest in process.
Both paths preserve full-block failures and extract official bytes without
synthetic activations, native result injection or replacement weights.
"""
from pathlib import Path
from dataclasses import dataclass
import argparse, hashlib, json, sys
import numpy as np
from host_bf16_v_descriptor import HostVBinding, build_host_v_descriptor
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
from heteronpu import qk_norm256_materialization as capture
from heteronpu.pinned_block_payload import load_payload
# Host-local source admission, independent of the pending SharedL2 policy-1
# candidate. These bytes authenticate official prefix/layer3 execution only.
PINNED_CAPTURE = 'work/matrix_tile16_final/vectors/official'
PINNED_CAPTURE_SHA256 = '21eb0f6f3f59b3b1a33650a07692084eabe69a0d04cec60036a434357b2c1b02'

# The previous code-pinned manifest format remains admissible only with its
# exact known source map. No saved fresh receipt is accepted as a trust anchor.
LEGACY_PINNED_SOURCES = {
    'chisel/continuous_prefill/scripts/pack_host_bf16_v_fixture.py': '1d05d6a72dae9427efa86ede349f78babd99f9f036a05a26973b0389b8ca4695',
    'chisel/continuous_prefill/scripts/host_bf16_v_descriptor.py': '15e44d2644c3199d743ed8d08deeb72b27c726e1c5d9771a992deeb118c77a6c',
    'chisel/continuous_prefill/config/host_bf16_v_descriptor_contract.json': '78bf6bb4cba70ae9ffd97c5a0c479e2c914f5fde6bd47b5db0ea3de3260901f5',
}

@dataclass(frozen=True)
class CaptureSession:
    """In-process authority. The fresh digest comes directly from rebuild().

    There is deliberately no CLI, environment variable or saved-receipt loader
    for constructing fresh sessions from caller-supplied captures/digests.
    """
    directory: Path
    manifest_sha256: str
    payload_layer0: Path
    payload_layer3: Path
    payload_extra: Path
    fresh: bool

    def verify(self):
        capture.load_materialized(ROOT,self.directory,trusted_manifest_sha256=self.manifest_sha256)
        official=json.loads((self.directory/'provenance.json').read_text())
        payloads,_=capture._payload_inputs(ROOT,self.payload_layer0,self.payload_layer3,self.payload_extra)
        if official['payload_manifests']!=payloads:raise ValueError('official/current payload receipts differ')
        return official

    def evidence(self,official=None):
        official=self.verify() if official is None else official
        return dict(official_manifest_sha256=self.manifest_sha256,
            fresh_official_executions=2 if self.fresh else 0,reused_official_executions=0 if self.fresh else 2,
            cross_host_byte_equivalence_claimed=False,
            native_full_block_gate_pass={v:official['corpora'][v]['native_audit_gate_pass'] for v in capture.VARIANTS},
            native_full_block_status={v:official['corpora'][v]['native_audit_status'] for v in capture.VARIANTS},
            native_full_block_failed_comparisons={v:official['corpora'][v]['native_failed_comparisons'] for v in capture.VARIANTS},
            native_audit_report_sha256={v:official['corpora'][v]['fresh_audit_report']['sha256'] for v in capture.VARIANTS})

def pinned_session():
    return CaptureSession(ROOT/PINNED_CAPTURE,PINNED_CAPTURE_SHA256,
        ROOT/'work/qwen35_layer0_payload',ROOT/'work/qwen35_layer3_payload',ROOT/'work/qwen35_prefix_payload',False)

def rebuild_session(output:Path,payload_layer0:Path,payload_layer3:Path,payload_extra:Path):
    """Only fresh factory: retain the returned digest, never read trust from disk."""
    inputs=tuple(Path(p).resolve() for p in (payload_layer0,payload_layer3,payload_extra))
    _,digest=capture.rebuild(ROOT,*inputs,Path(output).resolve())
    session=CaptureSession(Path(output).resolve(),digest,*inputs,True)
    session.verify()
    return session

def pack_fixture(output:Path,*,variant='baseline',phase='cold',token_base=0,token_count=1,session=None):
    if variant not in capture.VARIANTS or phase not in ('cold','carried'):raise ValueError('invalid source selection')
    if type(token_base) is not int or type(token_count) is not int:raise ValueError('integer token window required')
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT/'work') or out.exists():raise ValueError('fresh output under ignored work required')
    session=pinned_session() if session is None else session
    official=session.verify();source=session.directory
    native=source/variant/'native/all_bf16_producers.npz'
    capture._verify_file(native,official['corpora'][variant]['fresh_audit_arrays'])
    prefix=phase+'_m128_native_producer_'
    with np.load(native,allow_pickle=False) as producers:
        if len(producers.files)!=len(set(producers.files)):raise ValueError('duplicate source arrays')
        activation=(capture._bf16_words(producers[prefix+'07'],(1,128,1024),prefix+'07')[0]>>16).astype('<u2')
        native_v=(capture._bf16_words(producers[prefix+'26'],(1,128,512),prefix+'26')[0]>>16).astype('<u2')
    manifest,raw=load_payload(ROOT,session.payload_layer3)
    weight=np.ascontiguousarray(np.frombuffer(raw['self_attn.v_proj.weight'],dtype='<u2').reshape(512,1024).T)
    base=0x120000000;cb=base;db=base+0x1000;aa=base+0x10000;bb=base+0x60000;scratch=base+0x200000;dd=scratch+0x1000;limit=dd+128*1024+64
    binding=HostVBinding(128,token_base,token_count,aa,bb,dd)
    command,records=build_host_v_descriptor(binding)
    out.mkdir(parents=True)
    def write(name,data):
        (out/name).write_bytes(data)
        return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    files={}
    files['activation.bf16le']=write('activation.bf16le',activation.tobytes())
    files['weight.bf16le']=write('weight.bf16le',weight.tobytes())
    files['native_v.bf16le']=write('native_v.bf16le',native_v.tobytes())
    files['host_commands.bin']=write('host_commands.bin',command.pack().to_bytes(16,'little')+bytes(48))
    ds=b''.join(records[i].pack().to_bytes(16,'little') for i in range(21));ds+=bytes((-len(ds))%64)
    files['host_descriptors.bin']=write('host_descriptors.bin',ds)
    values=[base,limit,cb,cb+64,1,db,db+len(ds),21,base+0x2000,scratch,aa,bb,dd,128,token_base,token_count]
    files['launch.txt']=write('launch.txt',(' '.join(map(str,values))+'\n').encode())
    report=dict(status='SOURCE_AUTHENTICATED_HOST_V_INPUTS_ONLY',variant=variant,phase=phase,
        token_base=token_base,token_count=token_count,rows=128,
        official_capture=str(source.relative_to(ROOT)),official_manifest_sha256=session.manifest_sha256,
        fresh_official_executions=2 if session.fresh else 0,reused_official_executions=0 if session.fresh else 2,
        native_full_block_gate_pass={v:official['corpora'][v]['native_audit_gate_pass'] for v in capture.VARIANTS},
        producer_activation=prefix+'07',producer_native_v=prefix+'26',
        source_weight_sha256=hashlib.sha256(raw['self_attn.v_proj.weight']).hexdigest(),
        model_revision=manifest['revision'],files=files,
        sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
          (Path(__file__).resolve(),Path(__file__).with_name('host_bf16_v_descriptor.py'),ROOT/'chisel/continuous_prefill/config/host_bf16_v_descriptor_contract.json')},
        scope='V projection only; all rows retained for window bounds/guards; numerical DUT has not run')
    if session.fresh:
        report.update(session.evidence(official))
        report['input_sha256']=fixture_input_hashes(out,report)
        report['capture_mode']='fresh_same_invocation'
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def fixture_input_hashes(directory,manifest):
    """Hashes of the actual addressed input window, full backing inputs and ABI."""
    base,count=manifest['token_base'],manifest['token_count'];directory=Path(directory)
    data=(directory/'activation.bf16le').read_bytes()
    return dict(activation_tensor=hashlib.sha256(data).hexdigest(),
        activation_window=hashlib.sha256(data[base*2048:(base+count)*2048]).hexdigest(),
        weight_tensor=hashlib.sha256((directory/'weight.bf16le').read_bytes()).hexdigest(),
        command=hashlib.sha256((directory/'host_commands.bin').read_bytes()).hexdigest(),
        descriptors=hashlib.sha256((directory/'host_descriptors.bin').read_bytes()).hexdigest(),
        launch=hashlib.sha256((directory/'launch.txt').read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path);p.add_argument('--variant',choices=('baseline','avx2'),default='baseline')
    p.add_argument('--phase',choices=('cold','carried'),default='cold')
    p.add_argument('--token-base',type=int,default=0);p.add_argument('--token-count',type=int,default=1)
    args=p.parse_args()
    report=pack_fixture(args.output,variant=args.variant,phase=args.phase,token_base=args.token_base,token_count=args.token_count)
    print(json.dumps({k:report[k] for k in ('status','variant','phase','token_count','native_full_block_gate_pass')},indent=2))

if __name__=='__main__':main()
