#!/usr/bin/env python3
"""Bounded HOST-model M128/K1536/N160 split at K768 using sealed real inputs.

Accepted bank-model payloads drive two groups in the same five host banks.
First-group physical values traverse real modeled DDR writes/ACKs. Those saved
bytes are reread and streamed as raw seed writes after the host banks are erased.
Final values traverse the same output gather/write/ACK path before comparison.
No golden tensor supplies the owner or seed port. This is not retained RTL.
"""
import argparse
from array import array
from collections import deque
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
TASK=Path(__file__).resolve().parent
INPUTS={
    "a":("work/qwen2_rectangular_numeric_20261011/m128/phase_0_n0_recipe.f32le","ccf1e6c065c6bc4e90458194aeda7475149451ac73479a6781d2fd638bf631df"),
    "qr_after_bias":("work/qwen2_rectangular_numeric_20261011/m128/phase_1_qr_recipe.f32le","bd97c7b89801abddbbd88370c5d19c1cf912d572bf42121946168537c58f595b"),
    "weight_output_major":("work/qwen2_layer0_payload_20261011/self_attn.q_proj.weight.bin","142ece1271ee9eb6b1e91055e2a6293a5572bf9b5395c56c77f9584728ee89d4"),
    "bias":("work/qwen2_layer0_payload_20261011/self_attn.q_proj.bias.bin","c68e4379e1c3701dabe73e98cda2fc87c85cce47adb6e4dc7f871fba9f497d9d"),
}


def sha(data):return hashlib.sha256(data).hexdigest()


def run(out):
    if out.exists():raise ValueError("use a new evidence directory")
    out.mkdir(parents=True)
    report={"status":"STARTED","scope":"ONE_ACTUAL_INPUT_N160_SPLIT_K768_PREFIX_HOST_MODEL_ONLY",
            "rtl_generated":False,"hardware_arithmetic_executed":False,"matrix_latency_modeled":False,
            "full_projection_or_block_executed":False,"native_m128_and_fp32_final_acceptance":"UNCHANGED_FAIL_POLICY_PENDING"}
    def save():(out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    start=time.monotonic()
    try:
        if sys.byteorder!="little":raise ValueError("explicit little-endian host required")
        data={};report["input_pins"]={}
        for key,(path,digest) in INPUTS.items():
            raw=(ROOT/path).read_bytes()
            if sha(raw)!=digest:raise ValueError("frozen input identity drift: "+path)
            data[key]=raw;report["input_pins"][key]={"path":path,"sha256":digest,"bytes":len(raw)}
        for name in ("manifest.json",):
            path=ROOT/"work/qwen2_layer0_payload_20261011"/name
            report["payload_manifest"]={"path":str(path.relative_to(ROOT)),"sha256":sha(path.read_bytes())}
        pins={"source_commit":"825caff3a6c618419c49c7da452e009ce86ae8b5"}
        recipe=subprocess.check_output(["git","show",pins["source_commit"]+":chisel/continuous_prefill/tests/qwen2_block.cpp"],cwd=ROOT).decode()
        cpp=(TASK/"numeric_smoke.cpp").read_text()
        for name in ("bits","fp","bf","add"):
            line=next(line for line in recipe.splitlines() if line.startswith("static ") and " "+name+"(" in line)
            if line not in cpp:raise ValueError("original recipe helper changed: "+name)
        report["recipe_source"]={"commit":pins["source_commit"],"sha256":sha(recipe.encode()),
                                 "reduction":"increasing K, std::fma(float,float,float), initial +0; separate FP32 add bias"}
        report["source_sha256"]={name:sha((TASK/name).read_bytes()) for name in
                                  ("numeric_smoke.cpp","check_numeric_smoke.py","model.py")}
        source_snapshot=out/"source";source_snapshot.mkdir()
        for name,digest in report["source_sha256"].items():
            raw=(TASK/name).read_bytes()
            if sha(raw)!=digest:raise ValueError("source changed before capture")
            (source_snapshot/name).write_bytes(raw)
        # Save pins BEFORE compiling or computing. No dependency download.
        report["budget"]={"total_wall_seconds":60,"host_fma_updates":2*128*160*1536,
                          "retained_host_accumulator_bytes":5*16*256*4,"estimated_memory_mib":64}
        save()
        library=out/"numeric_smoke.so"
        argv=["g++","-std=c++17","-O2","-fno-fast-math","-ffp-contract=off","-fPIC","-shared",str(TASK/"numeric_smoke.cpp"),"-o",str(library)]
        with (out/"compile.log").open("w") as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
        report["compile"]={"argv":argv,"binary_sha256":sha(library.read_bytes()),"compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0]}
        spec=importlib.util.spec_from_file_location("numeric_owner_model",TASK/"model.py")
        model=importlib.util.module_from_spec(spec);sys.modules[spec.name]=model;spec.loader.exec_module(model)
        lib=C.CDLL(str(library));u16=C.POINTER(C.c_uint16);u32=C.POINTER(C.c_uint32)
        lib.td_group.argtypes=[C.c_uint,C.c_uint];lib.td_group.restype=C.c_int
        lib.td_seed_begin.argtypes=[C.c_uint];lib.td_seed_begin.restype=C.c_int
        lib.td_seed_beat.argtypes=[C.c_uint,C.c_uint,u32];lib.td_seed_beat.restype=C.c_int
        lib.td_seed_commit.argtypes=[C.c_uint];lib.td_seed_commit.restype=C.c_int
        lib.td_step.argtypes=[C.c_uint]*6+[u16,u16,u32];lib.td_step.restype=C.c_int
        lib.td_reference.argtypes=[u32,u16,u32];lib.td_reference.restype=C.c_int
        lib.td_add_bias.argtypes=[u32,u16,u32];lib.td_add_bias.restype=C.c_int
        if lib.td_reset()!=0:raise ValueError("cannot establish FE_TONEAREST")
        raw_a=array("I");raw_a.frombytes(data["a"])
        raw_w=array("H");raw_w.frombytes(data["weight_output_major"])
        raw_bias=array("H");raw_bias.frombytes(data["bias"])
        raw_qr=array("I");raw_qr.frombytes(data["qr_after_bias"])
        if (len(raw_a),len(raw_w),len(raw_bias),len(raw_qr))!=(128*1536,1536*1536,1536,128*1536):
            raise ValueError("frozen source shapes changed")
        # Derived unit shape, not a claim to execute the complete Q projection.
        weight=array("H",(raw_w[n*1536+k] for k in range(1536) for n in range(160)))
        report["derived_weight"]={"shape":[1536,160],"layout":"K-major N160","sha256":sha(weight.tobytes())}
        job=model.Job(m=128,k=1536,n=160,activation_bf16=False,weight_bf16=True,output_bf16=False,
                      tag=0x514b0010,write_bytes=128*160*4)
        workspace=model.PrefixWorkspace(0x10000000,5*16384,1,768)
        owner=model.DenseOwnerModel(workspace);owner.tick(job=job)
        operand_a=(C.c_uint16*16)();operand_b=(C.c_uint16*256)();physical=(C.c_uint32*4096)()
        seed_words=(C.c_uint32*16)();seed_ack=None;prefix={};seed_trace=hashlib.sha256();seed_capture=bytearray();prefix_beats=prefix_reads=seed_beats=seed_acks=0
        pending_read=None;pending_write=None;pending_ack=None;results=deque();finished=None
        destination=array("I",[0x7fc00001]*(128*160));written=set();staged=[]
        trace=hashlib.sha256();step_count=read_count=write_beats=acks=0;result_peak=0
        while finished is None:
            if time.monotonic()-start>60:raise TimeoutError("bounded numeric smoke exceeded60s")
            p=owner.ports();kwargs={"step_ready":not (p["step"] is not None and p["step"].last and len(results)>=2)}
            if pending_read is not None:
                if pending_read.kind=="prefix":
                    if not owner.prefix_valid or len(prefix)!=5*256 or owner.prefix_bytes!=5*16384:
                        raise ValueError("prefix read before complete writes ACK+Matrixdone")
                    if pending_read.address not in prefix:raise ValueError("prefix was never ACK-written")
                    kwargs["read_beat"]=model.ReadBeat(pending_read.tag,prefix[pending_read.address],True)
                else:
                    source=raw_a if pending_read.kind=="a" else weight
                    base=job.a if pending_read.kind=="a" else job.b
                    size=4 if pending_read.kind=="a" else 2
                    offset=(pending_read.address-base)//size
                    kwargs["read_beat"]=model.ReadBeat(pending_read.tag,tuple(source[offset:offset+64//size]),True)
            if results:kwargs["result"]=results[0]
            if owner.group_started and not owner.group_done and owner.group_accepted_steps==(owner.chunk_end-owner.chunk_start)*5 and owner.results_received==5 and not results:
                kwargs["matrix_done"]=model.MatrixDone(job.tag)
            if pending_ack is not None:kwargs["write_ack"]=pending_ack
            if seed_ack is not None:kwargs["seed_ack"]=seed_ack
            group_start=owner.chunk_start;group_end=owner.chunk_end
            edge=owner.tick(**kwargs)
            if edge["group_fire"]:
                if group_start==768:
                    if len(prefix)!=1280 or owner.prefix_bytes!=81920 or seed_beats:
                        raise ValueError("prefix snapshot boundary is not complete/pre-seed")
                    before_seed=b"".join(struct.pack("<16I",*prefix[a]) for a in sorted(prefix))
                    (out/"acknowledged_prefix_physical.f32le").write_bytes(before_seed)
                    report["prefix_captured_before_seed_begin"]=True
                if lib.td_group(group_start,group_end):raise ValueError("host group setup")
            if edge["seed_begin_fire"]:
                if lib.td_seed_begin(edge["seed_begin"].context):raise ValueError("host seed reserve")
            if edge["seed_beat_fire"]:
                b=edge["seed_beat"];seed_words[:]=b.words;seed_beats+=1
                seed_trace.update(struct.pack("<IB",b.request.context,b.index));seed_trace.update(bytes(seed_words))
                # Records are <tag:u32, sequence:u32, generation:u32,
                # context:u8, index:u8, last:u8, reserved:u8, words:16*u32>.
                seed_capture.extend(struct.pack("<IIIBBBB16I",b.request.tag,b.request.sequence,b.request.generation,
                    b.request.context,b.index,b.last,0,*b.words))
                if lib.td_seed_beat(b.request.context,b.index,seed_words):raise ValueError("host seed write")
                if b.last:
                    if lib.td_seed_commit(b.request.context):raise ValueError("host seed commit")
                    seed_ack=model.SeedAck(b.request)
            if edge["seed_ack_fire"]:seed_ack=None;seed_acks+=1
            if edge["read_fire"]:pending_read=None
            if edge["read_command_fire"]:
                if pending_read is not None:raise ValueError("read descriptors overlap")
                pending_read=edge["read_command"];read_count+=1;prefix_reads+=int(pending_read.kind=="prefix")
            if edge["step_fire"]:
                s=edge["step"];step_count+=1
                operand_a[:]=s.a;operand_b[:]=s.b
                trace.update(struct.pack("<HBBBBBB",s.k,s.context,s.clear,s.last,s.finish,s.emit,0))
                trace.update(bytes(operand_a));trace.update(bytes(operand_b))
                returned=lib.td_step(s.k,s.context,s.clear,s.last,s.finish,s.emit,operand_a,operand_b,physical)
                if returned<0 or bool(returned)!=s.last:raise ValueError("accepted-step FMA protocol/finite error")
                if returned:
                    tile=tuple(tuple(physical[r*256+c] for c in range(256)) for r in range(16))
                    results.append(model.MatrixResult(s.context,tile));result_peak=max(result_peak,len(results))
            if edge["result_fire"]:results.popleft()
            if edge["write_command_fire"]:
                if pending_write is not None:raise ValueError("write descriptors overlap")
                pending_write=(edge["write_command"],0);staged=[]
            if edge["write_data_fire"]:
                command,index=pending_write;packet=edge["write_data"]
                staged.append((command.address+64*index,packet.words));write_beats+=1
                pending_write=(command,index+1)
                if packet.last:pending_ack=model.WriteAck(command.tag,nbytes=64*command.beats)
            if edge["write_ack_fire"]:
                for address,words in staged:
                    if workspace.base<=address<workspace.base+workspace.extent:
                        if address in prefix:raise ValueError("duplicate prefix ACK store")
                        prefix[address]=tuple(words);prefix_beats+=1
                        continue
                    first=(address-job.dst)//4
                    for i,value in enumerate(words):
                        if not 0<=first+i<len(destination) or first+i in written:raise ValueError("duplicate/out-of-bounds store")
                        destination[first+i]=value;written.add(first+i)
                staged=[];pending_ack=None;pending_write=None;acks+=1
            if edge["response_fire"]:finished=edge["response"]
            if owner.error:raise ValueError("clocked owner failed: "+owner.error)
        if finished!=(job.tag,None,128*160*4) or step_count!=7680 or len(written)!=128*160:
            raise ValueError("terminal/count/output completeness mismatch")
        if pending_read or pending_write or pending_ack or results or staged or seed_ack:
            raise ValueError("completion with outstanding external obligation")
        # Only after the SAME owner has finished its actual ACK path, compute
        # the independent raw-input reference. It never serves Matrix results.
        reference=(C.c_uint32*(128*160))();biased=(C.c_uint32*(128*160))()
        ca=(C.c_uint32*len(raw_a)).from_buffer(raw_a);cw=(C.c_uint16*len(raw_w)).from_buffer(raw_w)
        cd=(C.c_uint32*len(destination)).from_buffer(destination);cb=(C.c_uint16*len(raw_bias)).from_buffer(raw_bias)
        if lib.td_reference(ca,cw,reference) or lib.td_add_bias(cd,cb,biased):raise ValueError("nonfinite independent comparison")
        mismatch=sum(x!=reference[i] for i,x in enumerate(destination))
        if (prefix_beats,prefix_reads,seed_beats,seed_acks,owner.prefix_bytes)!=(1280,1280,1280,5,81920):
            raise ValueError("prefix physical transaction count mismatch")
        bias_mismatch=sum(biased[m*160+n]!=raw_qr[m*1536+n] for m in range(128) for n in range(160))
        prefix_raw=b"".join(struct.pack("<16I",*prefix[a]) for a in sorted(prefix))
        if (out/"acknowledged_prefix_physical.f32le").read_bytes()!=prefix_raw:raise ValueError("prefix changed after pre-seed capture")
        (out/"accepted_seed_records.bin").write_bytes(seed_capture)
        old_output=ROOT/"work/qwen2_transposed_owner_20261011/numeric_01/acknowledged_dense.f32le"
        old_digest="0243fc968ac2bf2532e1145ccc418c03f26c42677fc8dc3e4e1233bed8b674d8"
        if sha(old_output.read_bytes())!=old_digest:raise ValueError("frozen old single-chunk artifact drift")
        if destination.tobytes()!=old_output.read_bytes():raise ValueError("split output differs from frozen actual old owner artifact")
        report["old_single_chunk_output"]={"path":str(old_output.relative_to(ROOT)),"sha256":old_digest,"bit_mismatches":0}
        report["retained_prefix_artifacts"]={
            "acknowledged_prefix_physical.f32le":{"sha256":sha(prefix_raw),"bytes":len(prefix_raw),"layout":"context then physical16x256 row-major FP32 bits"},
            "accepted_seed_records.bin":{"sha256":sha(seed_capture),"bytes":len(seed_capture),"record_bytes":80,"format":"<IIIBBBB16I"}}
        (out/"acknowledged_dense.f32le").write_bytes(destination.tobytes())
        (out/"independent_prebias.f32le").write_bytes(bytes(reference))
        (out/"acknowledged_then_bias.f32le").write_bytes(bytes(biased))
        report.update(accepted_steps=step_count,host_fma_per_path=128*160*1536,
            prefix_ack_beats=prefix_beats,prefix_read_descriptors=prefix_reads,seed_beats=seed_beats,seed_acks=seed_acks,
            prefix_ack_bytes=owner.prefix_bytes,prefix_payload_sha256=sha(b"".join(struct.pack("<16I",*prefix[a]) for a in sorted(prefix))),
            seed_trace_sha256=seed_trace.hexdigest(),same_existing_host_banks_erased_at_rollover=True,
            accepted_step_trace_sha256=trace.hexdigest(),read_descriptors=read_count,write_data_beats=write_beats,
            write_acks=acks,acknowledged_bytes=finished[2],logical_output_cells=len(written),
            independent_prebias_bit_mismatches=mismatch,saved_recipe_after_bias_bit_mismatches=bias_mismatch,
            protocol_model_ticks=owner.clock,protocol_model_ticks_are_hardware_cycles=False,
            operand_reservation_peak=owner.max_reserved,physical_result_fifo_peak=result_peak,
            output_sha256={p.name:sha(p.read_bytes()) for p in out.glob("*.f32le")},wall_seconds=time.monotonic()-start)
        if mismatch or bias_mismatch:raise ValueError("numeric comparison failed")
        for name,digest in report["source_sha256"].items():
            if sha((TASK/name).read_bytes())!=digest:raise ValueError("source changed during numeric run")
        report["status"]="PASS_ACTUAL_INPUT_PREFIX_SAVE_RESTORE_HOST_MODEL_ONLY";save();return report
    except Exception as error:
        report["status"]="FAILED";report["error"]=str(error);report["wall_seconds"]=time.monotonic()-start;save();raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,required=True)
    result=run(parser.parse_args().out.resolve());print(json.dumps({"status":result["status"],"wall_seconds":result["wall_seconds"]}))
