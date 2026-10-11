#!/usr/bin/env python3
"""Bounded, cache-only actual-owner/service Chisel frontend gate. Never RTL.

The full QwenOwnerKernel is NOT compiled by this gate. Its exact selection
patch is applied and validated; its actual canStart expression is extracted
into a frontend probe. Dense owners, SRAMs and Matrix service are real sources.
Only the pre-existing retained endpoint/clockgate arithmetic is a BlackBox,
using declarations extracted byte-for-byte from the pinned production source.
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
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
PREFIX = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, expected, name):
    if sha(data) != expected:
        raise ValueError("source identity changed: " + str(name))
    return data


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resource_audit(fir, enabled, abi):
    memories = re.findall(r"^[ \t]*smem (\w+) : UInt<256>[ \t]*\[(\d+)\]", fir, re.M)
    if len(memories) != 32 or sorted(int(n) for _, n in memories) != [160]*16+[1376]*16:
        raise ValueError("expected exactly sixteen A1376 and sixteen B160 memories")
    physical_ports=Counter(re.findall(r"^[ \t]*(read|write) mport \w+ = (\w+)\[",fir,re.M))
    ports = {}
    for name, depth in memories:
        reads,writes=physical_ports["read",name],physical_ports["write",name]
        if reads != 1 or writes != 1:
            raise ValueError(f"memory port drift {name}: {reads}R/{writes}W")
        ports[name] = {"words": int(depth), "word_bits": 256, "reads": reads, "writes": writes}
    # Derive the COMPLETE expected ABI from the already SHA-validated original
    # BlackBox declarations, including directions/types/order and defname.
    extmodules={name:[line.strip() for line in body.splitlines() if line.strip()]
                for name,body in re.findall(r"^  extmodule (\w+) :[^\n]*\n((?:    [^\n]*\n|\n)*)",fir,re.M)}
    instances=re.findall(r"^[ \t]*inst (\w+) of (\w+)",fir,re.M)
    all_expected=set();abi_checks={}
    for cls,defname,prefix in (("RetainedMatrixEndpoint","qwen2_matrix_command_endpoint","leaves_"),
                               ("RetainedMatrixClockGate","tc_clk_gating","gate")):
        block=abi[abi.index("class "+cls):]
        block=block.split("\nclass ",1)[0]
        declarations=re.findall(r"val (\w+)=(Input|Output)\((Clock\(\)|Bool\(\)|UInt\((\d+)\.W\))\)",block)
        expected=[]
        for name,direction,typ,bits in declarations:
            wire="Clock" if typ=="Clock()" else "UInt<"+(bits or "1")+">"
            expected.append(direction.lower()+" "+name+" : "+wire)
        if len(expected)!=(22 if cls=="RetainedMatrixEndpoint" else 4):
            raise ValueError("cannot derive every original ABI port")
        expected.append("defname = "+defname)
        names=[defname]+[defname+"_"+str(i) for i in range(1,8)]
        all_expected.update(names)
        expected_instances=[(prefix+str(i) if prefix=="leaves_" else ("gate" if i==0 else "gate_"+str(i)),names[i]) for i in range(8)]
        actual=[pair for pair in instances if pair[1].startswith(defname)]
        if actual!=expected_instances:
            raise ValueError("missing/extra/wrong retained instance reference: "+defname)
        for name in names:
            if extmodules.get(name)!=expected:
                raise ValueError("retained ABI/defname/parameter drift: "+name)
        abi_checks[defname]={"instances":actual,"complete_declaration":expected}
    if set(extmodules)!=all_expected:
        raise ValueError("unexpected/missing arithmetic or clockgate external module")
    if len(re.findall(r"^[ \t]*reg finalValue : UInt<32>\[256\]\[16\]", fir, re.M)) != 1:
        raise ValueError("not exactly one existing 16-KiB final-value buffer")
    for depth in (4, 8):
        if not re.search(r"^[ \t]*cmem ram : .*\}[ \t]*\["+str(depth)+r"\]", fir, re.M):
            raise ValueError("missing fixed queue depth "+str(depth))
    if not re.search(r"^[ \t]*reg storage : .*\}[ \t]*\[2\]", fir, re.M):
        raise ValueError("missing two-entry existing Matrix result FIFO")
    owners=[pair[1] for pair in instances if pair[1] in ("StreamingDenseOwner","TransposedDenseOwner")]
    if owners != ["TransposedDenseOwner" if enabled else "StreamingDenseOwner"]:
        raise ValueError("both owners were instantiated, or the wrong owner was selected")
    if enabled:
        if not re.search(r"reg aHigh : UInt<256>", fir) or not re.search(r"reg rmw : .*value : UInt<256>", fir):
            raise ValueError("declared native-BF16 staging is not two 256-bit pieces")
        if re.search(r"reg \w+ : UInt<4096>", fir):
            raise ValueError("unaccounted 4096-bit SRAM response hold")
        if not re.search(r"zero : \{.*bits : UInt<11>", fir):
            raise ValueError("A physical write/clear port cannot address word1375")
    return {"bank_ports": ports, "sram_bytes": 768*1024, "endpoints": 8,
            "retained_abi_checks":abi_checks,
            "physical_fmas": 4096, "retained_contexts": 5, "operand_fifo": 4,
            "metadata_fifo": 8, "result_fifo": 2, "final_value_bytes": 16384,
            "native_a_staging_bits": 512 if enabled else 256,
            "physical_area_timing_or_arithmetic_measured": False}


def run(out, cache, validate_only, hardfloat=None):
    if out.exists():
        raise ValueError("use a new evidence directory")
    out.mkdir(parents=True)
    pins = json.loads((TASK/"source_pins.json").read_text())
    report = {"status": "STARTED", "source_commit": pins["source_commit"],
              "rtl_generated": False, "arithmetic_executed": False,
              "full_qwen_owner_kernel_compiled": False,
              "hardware_protocol_executed": False, "commands": [],
              "native_m128_and_fp32_final_acceptance": "UNCHANGED_FAIL_POLICY_PENDING"}

    def save():
        (out/"summary.json").write_text(json.dumps(report, indent=2)+"\n")

    def command(argv, log):
        start = time.monotonic()
        with (out/log).open("w") as stream:
            p = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report["commands"].append({"argv": argv, "log": log, "exit_code": p.returncode,
                                   "wall_seconds": time.monotonic()-start})
        save()
        if p.returncode:
            raise RuntimeError("frontend command failed: "+log)

    try:
        frozen = {}
        for path, digest in pins["frozen_sources"].items():
            data = subprocess.check_output(["git", "show", pins["source_commit"]+":"+path], cwd=ROOT)
            frozen[path] = checked(data, digest, path)
        route = ROOT/"candidates/qwen2_resident_matrix/transposed_route"
        route_manifest = json.loads(frozen[str((route/"manifest.json").relative_to(ROOT))])
        helper_path = ROOT/"scripts/check_matrix_interface_candidate.py"
        checked(helper_path.read_bytes(), route_manifest["dependencies"][str(helper_path.relative_to(ROOT))], helper_path)
        helper = load_module("owner_frontend_helpers", helper_path)
        lock = checked((ROOT/"chisel/rope_hardware_oracle/maven-lock.json").read_bytes(),
                       route_manifest["maven_lock_sha256"], "Maven lock")
        jars = helper.dependency_paths(json.loads(lock)["artifacts"])
        if len(jars) != 87:
            raise ValueError("dependency set changed")
        for path, digest in jars.items():
            checked((cache/path).read_bytes(), digest, path)
        cp, plugin, receipt = helper.prepare_dependencies(ROOT, cache, route_manifest)
        (out/"dependency_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
        report["dependency_receipt_sha256"] = sha((out/"dependency_receipt.json").read_bytes())
        source = out/"source"; source.mkdir()
        def write(name, data):
            path=source/PREFIX/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data if isinstance(data,bytes) else data.encode());return path
        for name in ("BurstProtocol.scala","MatrixPipeline.scala","RetainedMatrix.scala","WideMatrix.scala"):
            path=PREFIX+name
            data=subprocess.check_output(["git","show",pins["source_commit"]+":"+path],cwd=ROOT)
            frozen[path]=checked(data,route_manifest["original_sources"][name],name)
        for name in ("BurstProtocol.scala","MatrixPipeline.scala","QwenOwnerProtocol.scala","StreamingDense.scala"):
            write(name,frozen[PREFIX+name])
        combined=frozen[str((route/"combined_service.patch").relative_to(ROOT))]
        (out/"combined_service.patch").write_bytes(combined)
        for patch in (out/"combined_service.patch",TASK/"owner_selection.patch"):
            subprocess.run(["git","apply","--check",str(patch)],cwd=source,check=True)
            subprocess.run(["git","apply",str(patch)],cwd=source,check=True)
        for name,digest in {**route_manifest["patched_sources"],**pins["patched_sources"]}.items():
            checked((source/PREFIX/name).read_bytes(),digest,name)
        header="package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n"
        abi=header
        for filename,names in (("RetainedMatrix.scala",("RetainedMatrixEndpoint","RetainedMatrixClockGate")),
                               ("WideMatrix.scala",("WideMatrixStep","WideMatrixResult"))):
            for name in names:
                abi+=helper.declaration(frozen[PREFIX+filename].decode(),name)+"\n"
        checked(abi.encode(),route_manifest["abi_declarations_sha256"],"exact retained ABI")
        abi_file=write("RetainedAbi.scala",abi)
        qwen=frozen[PREFIX+"QwenOwnerProtocol.scala"].decode()
        qwen_types=header+re.search(r"^object QwenOwnerKind .*",qwen,re.M).group()+"\n"
        qwen_types+="\n".join(helper.declaration(qwen,n) for n in ("QwenOwnerJob","QwenOwnerResult"))
        qwen_file=write("QwenOwnerTypes.scala",qwen_types)
        original=frozen[PREFIX+"StreamingDense.scala"].decode()
        start=original.index("  val io=IO(new Bundle {",original.index("class StreamingDenseOwner"))
        end=original.index("\n  })",start)
        old_io=header+"class OriginalDenseIO(burstWrites:Boolean) extends Bundle {"+original[start+len("  val io=IO(new Bundle {"):end]+"\n}\n"
        original_io_file=write("OriginalDenseIO.scala",old_io)
        # Preserve original source basename AND line numbers in assertion
        # strings. Do not strip or normalize these strings to pass equivalence.
        profile=helper.declaration(original,"DenseCycleProfile")
        old_owner=original.replace(profile,"\n"*profile.count("\n"),1)
        old_owner=old_owner.replace("class StreamingDenseOwner(","class OriginalStreamingDenseOwner(",1)
        pos=old_owner.index("{",old_owner.index("class OriginalStreamingDenseOwner"))+1
        old_owner=old_owner[:pos]+' override def desiredName: String = "StreamingDenseOwner";'+old_owner[pos:]
        originals_file=source/"original_dense"/"StreamingDense.scala"
        originals_file.parent.mkdir(parents=True);originals_file.write_text(old_owner)
        # Except for the exact IO declaration, the disabled legacy owner body
        # is required to be byte-identical before compiling or reusing evidence.
        old_end=end+len("\n  })")
        expected=original[:start]+"  val io=IO(new DenseOwnerIO(burstWrites))"+"\n"*original[start:old_end].count("\n")+original[old_end:]
        if expected!=(source/PREFIX/"StreamingDense.scala").read_text():
            raise ValueError("legacy owner body changed beyond shared IO declaration")
        kernel=(source/PREFIX/"QwenOwnerProtocol.scala").read_text()
        guard=re.search(r"^    val canStart=.*",kernel,re.M).group().strip()
        if "bf16Gdn||bf16QkNormRope||enableTransposedDense" not in guard:
            raise ValueError("candidate does not block all owners after shared poison")
        probe=header+"""class ActualKernelCanStartProbe(enableTransposedDense:Boolean) extends Module {
  val io=IO(new Bundle {
    val active=Input(Bool());val rejected=Input(Bool());val gdnPoison=Input(Bool());val sharedPoison=Input(Bool());val ready=Output(Bool())
  })
  val active=io.active;val rejected=io.rejected;val gdnPoison=io.gdnPoison;val sharedPoison=io.sharedPoison
  val bf16Gdn=false;val bf16QkNormRope=false
  """+guard+"\n  io.ready:=canStart\n}\n"
        probe_file=write("ActualKernelCanStartProbe.scala",probe)
        sources=[abi_file,qwen_file,original_io_file,originals_file,probe_file]
        for name in ("Protocol.scala","DenseReadPlanner.scala"):
            sources.append(write(name,frozen[PREFIX+name]))
        sources += [source/PREFIX/n for n in ("BurstProtocol.scala","MatrixPipeline.scala","StreamingDense.scala")]
        sources += [TASK/n for n in ("DenseOwnerIO.scala","TransposedDenseBanks.scala","TransposedDenseOwner.scala","TransposedOwnerElaboration.scala")]
        report["source_pins"]=pins
        report["compiled_source_sha256"]={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sources}
        report["task_source_sha256"]={p.name:sha(p.read_bytes()) for p in TASK.iterdir() if p.is_file()}
        report["actual_kernel_guard_expression"]=guard
        report["java_budget"]={"max_heap_mib":1024,"active_processors":1,"timeout_seconds_per_command":180}
        if validate_only:
            report["status"]="PASS_SOURCE_AND_CACHE_VALIDATION_ONLY";save();return report
        classes=out/"classes";classes.mkdir()
        java=["java","-Xmx1024m","-XX:ActiveProcessorCount=1"]
        command(java+["-cp",cp,"scala.tools.nsc.Main","-classpath",cp,"-Xplugin:"+str(plugin),"-d",str(classes)]+list(map(str,sources)),"compile.log")
        command(java+["-cp",str(classes)+":"+cp,"heteronpu.continuous.TransposedOwnerElaboration",str(out/"chirrtl")],"elaboration.log")
        report["default_off_ir"]={}
        for mode in ("single","burst"):
            old=helper.normalized_chirrtl((out/"chirrtl"/f"original_dense_{mode}.fir").read_text())
            new=helper.normalized_chirrtl((out/"chirrtl"/f"shared_io_dense_{mode}.fir").read_text())
            report["default_off_ir"][mode]={"equal":old==new,"before_sha256":sha(old.encode()),"after_sha256":sha(new.encode())}
            if old!=new:
                raise ValueError("default-off legacy Dense CHIRRTL changed: "+mode)
        report["resource_audit"]={}
        for enabled in (False,True):
            for mode in ("single","burst"):
                name=f"owner_{'transposed' if enabled else 'normal'}_{mode}.fir"
                report["resource_audit"][name]=resource_audit(helper.normalized_chirrtl((out/"chirrtl"/name).read_text()),enabled,abi)
        report["generated_chirrtl"]={p.name:{"sha256":sha(p.read_bytes()),"bytes":p.stat().st_size} for p in (out/"chirrtl").glob("*.fir")}
        for p in sources:
            checked(p.read_bytes(),report["compiled_source_sha256"][str(p.relative_to(ROOT))],p)
        if hardfloat is not None:
            # Compile the complete actual production source graph as a TYPE
            # CHECK only. Never invoke any production Emit* entry point.
            hf_commit="c1105e6ac6a0dd90fc80893efc4830ab609005d3"
            head=subprocess.check_output(["git","-C",str(hardfloat),"rev-parse","HEAD"],text=True).strip()
            if head!=hf_commit:
                raise ValueError("HardFloat commit identity changed")
            full=out/"kernel_source";full.mkdir()
            paths=subprocess.check_output(["git","ls-tree","-r","--name-only",pins["source_commit"],"--",
                "chisel/continuous_prefill/src/main/scala","chisel/p0_safety/src/main/scala",
                "integration/gemmini/EmitHeteroFP32Alu.scala","integration/gemmini/EmitHeteroBF16Fma.scala"],cwd=ROOT,text=True).splitlines()
            paths=[p for p in paths if p.endswith(".scala")]
            if sum(p.startswith("chisel/continuous_prefill/") for p in paths)!=47:
                raise ValueError("actual continuous main source set changed")
            full_sources=[]
            for path in paths:
                data=subprocess.check_output(["git","show",pins["source_commit"]+":"+path],cwd=ROOT)
                dest=full/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);full_sources.append(dest)
            for patch in (out/"combined_service.patch",TASK/"owner_selection.patch"):
                subprocess.run(["git","apply","--check",str(patch)],cwd=full,check=True)
                subprocess.run(["git","apply",str(patch)],cwd=full,check=True)
            hf_paths=subprocess.check_output(["git","-C",str(hardfloat),"ls-tree","-r","--name-only",hf_commit,
                "--","hardfloat/src/main/scala"],text=True).splitlines()
            hf_paths=[p for p in hf_paths if p.endswith(".scala")]
            if len(hf_paths)!=20:
                raise ValueError("HardFloat source set changed")
            for path in hf_paths:
                data=subprocess.check_output(["git","-C",str(hardfloat),"show",hf_commit+":"+path])
                dest=full/"pinned_hardfloat"/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);full_sources.append(dest)
            full_sources += [TASK/n for n in ("DenseOwnerIO.scala","TransposedDenseBanks.scala","TransposedDenseOwner.scala")]
            full_classes=out/"kernel_classes";full_classes.mkdir()
            report["kernel_typecheck_sources"]={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in full_sources}
            report["hardfloat_commit"]=hf_commit
            command(java+["-cp",cp,"scala.tools.nsc.Main","-classpath",cp,"-Xplugin:"+str(plugin),"-d",str(full_classes)]+
                    list(map(str,full_sources)),"kernel_typecheck.log")
            report["full_qwen_owner_kernel_compiled"]=True
            report["full_qwen_owner_kernel_elaborated"]=False
        report["status"]="PASS_OWNER_SERVICE_FRONTEND_ONLY";save();return report
    except Exception as error:
        report["status"]="FAILED";report["error"]=str(error);save();raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--cache",type=Path,required=True)
    parser.add_argument("--validate-only",action="store_true")
    parser.add_argument("--hardfloat",type=Path,help="optional pinned HardFloat checkout for complete main-source Scala typecheck only")
    args=parser.parse_args()
    result=run(args.out.resolve(),args.cache.resolve(),args.validate_only,args.hardfloat.resolve() if args.hardfloat else None)
    print(json.dumps({"status":result["status"],"rtl_generated":False,"arithmetic_executed":False}))
