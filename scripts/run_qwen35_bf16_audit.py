#!/usr/bin/env python3
"""Collect full producer-rounded BF16 audit; --require-pass rejects any failure.

A successful collection is NOT BF16 numerical acceptance. Inspect gate_pass and
failed_producers. Complete native/oracle arrays are retained even on rejection.
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import inspect
import io
import json
from pathlib import Path
import platform
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.model_geometry import require, load_json
from heteronpu.pinned_block_payload import load_payload
from heteronpu.qwen35_numpy_reference import decode_bf16
from heteronpu.qwen35_bf16_reference import forward, require_bf16, producer_compare, local_gemm_bound, softmax_invariants, diagnose_trace
from heteronpu.weight_header_contract import sha256

CONTRACT_SHA256 = "13b52da81746346f62c6a2f28cc1d6fa565989bd71d834dd4951ee2056355d97"
SELECTED = {"aten.linear.default", "aten.pow.Tensor_Scalar", "aten.mean.dim", "aten.add.Tensor", "aten.rsqrt.default",
            "aten.mul.Tensor", "aten.matmul.default", "aten.softmax.int", "aten.sigmoid.default", "aten.silu.default"}
STRUCTURAL = {"aten.cat.default", "aten.chunk.default", "aten.contiguous.default", "aten.detach_.default",
              "aten.dropout.default", "aten.expand.default", "aten.lift_fresh.default", "aten.neg.default",
              "aten.reshape.default", "aten.slice.Tensor", "aten.to.dtype", "aten.transpose.int",
              "aten.type_as.default", "aten.unsqueeze.default", "aten.view.default"}


def load_contract(root):
    path = root / "config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json"
    require(sha256(path.read_bytes()) == CONTRACT_SHA256, "BF16 contract drift")
    return load_json(path)


def verify_sequence(trace, contract):
    expected = contract["producer_sequence"]
    require(len(trace) == len(expected), "missing/extra numerical producer")
    for item, pin in zip(trace, expected, strict=True):
        require(item["key"] == pin["key"] and item["dtype"] == pin["storage_dtype"], "producer order/dtype drift")
        a = item["value"]
        require(a.dtype == np.float32, "decoded producer dtype drift")
        require(np.isfinite(a).all(), "nonfinite producer")
        require(np.all((a == 0) | (np.abs(a) >= np.finfo(np.float32).tiny)), "subnormal/flush boundary unsupported")
        if item["dtype"] == "bfloat16": require_bf16(a, item["key"])


def bits_equal(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a.view(np.uint32), b.view(np.uint32))


def load_upstream(root, directory, contract, *, trusted_fresh_digest=None):
    # Saved fixture is admitted only by a separately frozen original report hash.
    # The fresh digest is supplied internally after running the pinned producer,
    # never accepted as a CLI override or copied out of untrusted input JSON.
    trusted_digest = trusted_fresh_digest or contract["saved_upstream_report_sha256"]
    require(sha256((directory / "result.json").read_bytes()) == trusted_digest,
            "untrusted upstream report: use the frozen fixture or rebuild the pinned prefix")
    report = load_json(directory / "result.json")
    require(report["model_id"] == contract["model_id"], "upstream model identity drift")
    require(report["revision"] == contract["revision"] and report["framework_revision"] == contract["framework_revision"], "upstream model/framework drift")
    require(report["status"] == "PASS_REAL_EMBEDDING_OFFICIAL_PREFIX_CHAIN_U00_2_OPEN" and report["official_TextModel_prefix_executed"] is True,
            "requires verified official prefix producer report")
    require(report["upstream_activation_provenance_verified_for_layers_0_to_3"] is True, "unverified upstream provenance")
    expected_sources = {"scripts/run_qwen35_prefix_chain.py", "src/heteronpu/pinned_prefix_payload.py", "src/heteronpu/qwen35_prefix_reference.py", "src/heteronpu/qwen35_gdn_numpy_reference.py", "src/heteronpu/qwen35_numpy_reference.py", "src/heteronpu/pinned_gdn_payload.py", "src/heteronpu/pinned_block_payload.py"}
    require(set(report["runner_source_sha256"]) == expected_sources, "missing/extra upstream source binding")
    require(len(report["comparisons"]) == 32 and all(c["mismatches"] == 0 for c in report["comparisons"]), "upstream mathematical audit not passed")
    for name, digest in report["runner_source_sha256"].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root.resolve()) and sha256(path.read_bytes()) == digest, "upstream runner source drift")
    require(report["query_tokens"] == 128 and report["batch"] == 1, "upstream shape drift")
    path = directory / "prefix_activations_and_states.npz"
    require(report["arrays"]["file"] == path.name and path.stat().st_size == report["arrays"]["bytes"] and sha256(path.read_bytes()) == report["arrays"]["sha256"], "upstream NPZ digest/size drift")
    arrays = np.load(path, allow_pickle=False)
    for case in ("cold_m128", "carried_m128"):
        name = f"source_mixed_bf16_{case}_layer3_input"
        require(bits_equal(arrays[name], arrays[f"source_mixed_bf16_{case}_layer2_output"]), "upstream layer2 link drift")
        for producer in ("input", "output", "key", "value"):
            a = arrays[f"source_mixed_bf16_{case}_layer3_{producer}"]
            require_bf16(a, producer)
            rows = [r for r in report["array_reports"] if (r["mode"],r["case"],r["layer"],r["producer"]) == ("source_mixed_bf16",case,3,producer)]
            require(len(rows) == 1 and rows[0]["storage_dtype"] == "bfloat16" and sha256(a.tobytes()) == rows[0]["array_sha256"], "upstream producer digest/dtype drift")
    return report, arrays


def run(root, payload, upstream, output, *, rebuild_layer0=None, rebuild_extra=None):
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be fresh or empty")
    require(root.resolve() == Path(__file__).resolve().parents[1], "runner root/import identity drift")
    contract = load_contract(root)
    for name, digest in contract["fresh_prefix_source_sha256"].items():
        require(sha256((root / name).read_bytes()) == digest, "pinned prefix source drift")
        if name.startswith("src/heteronpu/"):
            module = importlib.import_module("heteronpu." + Path(name).stem)
            require(Path(module.__file__).resolve() == (root/name).resolve(), "prefix module import identity drift")
    source_hashes = {name: sha256((root/name).read_bytes()) for name in
        ("scripts/run_qwen35_bf16_audit.py", "src/heteronpu/qwen35_bf16_reference.py", *contract["fresh_prefix_source_sha256"])}
    manifest, raw = load_payload(root, payload)
    w = {r["local_name"]: decode_bf16(raw[r["local_name"]], r["shape"]).copy() for r in manifest["tensors"]}
    require((rebuild_layer0 is None) == (rebuild_extra is None), "both prefix rebuild payloads required")
    fresh_digest = None
    if rebuild_layer0 is not None:
        spec = importlib.util.spec_from_file_location("pinned_prefix_producer", root / "scripts/run_qwen35_prefix_chain.py")
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        fresh_report = producer.run(root, rebuild_layer0, payload, rebuild_extra, upstream)
        require(load_json(upstream / "result.json") == fresh_report, "fresh prefix report/return mismatch")
        fresh_digest = sha256((upstream / "result.json").read_bytes())
    source_report, source = load_upstream(root, upstream, contract, trusted_fresh_digest=fresh_digest)
    import torch
    import transformers.activations as activation_source
    import transformers.cache_utils as cache_source
    from torch.utils._python_dispatch import TorchDispatchMode
    from transformers.cache_utils import DynamicCache
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig
    config_path = root / "config/upstream/qwen3_5_0p8b/config.json"
    require(sha256(config_path.read_bytes()) == contract["config_sha256"], "official config drift")
    installed = {"modeling": (Path(inspect.getfile(official)), contract["official_modeling_sha256"]),
        "cache": (Path(inspect.getfile(cache_source)), "abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b"),
        "activations": (Path(inspect.getfile(activation_source)), "5b20c0a3625edc0001a98f09ce3c6b5baa1100e1d7ad8dee649e4d45c8468665"),
        "configuration": (Path(inspect.getfile(Qwen3_5TextConfig)), sha256((root / "config/upstream/qwen3_5_0p8b/configuration_qwen3_5.py").read_bytes()))}
    require(all(sha256(path.read_bytes()) == digest for path,digest in installed.values()), "installed official source drift")
    direct_url = json.loads(importlib.metadata.distribution("transformers").read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == "https://github.com/huggingface/transformers/archive/" + contract["framework_revision"] + ".zip" and direct_url.get("archive_info",{}).get("hashes",{}).get("sha256") == "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d", "framework archive drift")
    require(torch.__version__.split("+")[0] == contract["torch_version"] and np.__version__ == contract["numpy_version"], "unsupported runtime version")
    require(torch.version.cuda is None and not torch.is_autocast_enabled("cpu"), "only non-autocast CPU runtime supported")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    torch.set_flush_denormal(False)
    config = Qwen3_5TextConfig.from_dict(load_json(config_path)["text_config"])
    config._attn_implementation = "eager"
    layer = official.Qwen3_5DecoderLayer(config, layer_idx=3).to(dtype=torch.bfloat16).eval()
    loaded = layer.load_state_dict({k:torch.from_numpy(v).to(torch.bfloat16) for k,v in w.items()}, strict=True)
    require(not loaded.missing_keys and not loaded.unexpected_keys, "incomplete real layer")
    require(all(p.dtype == torch.bfloat16 and p.device.type == "cpu" for p in layer.parameters()), "parameter dtype/device drift")
    rotary = official.Qwen3_5TextRotaryEmbedding(config)
    require(rotary.inv_freq.dtype == torch.float32, "RoPE inverse-frequency must stay FP32")
    stack, handles = [], []
    for name,module in layer.named_modules():
        def before(mod,args,n=name): stack.append(n)
        def after(mod,args,result): stack.pop()  # Must return None; returning popped name changes forward output.
        handles.extend((module.register_forward_pre_hook(before), module.register_forward_hook(after)))
    trace, counters, operation_counts, local_gemm = [], {}, {}, []
    class Trace(TorchDispatchMode):
        def __torch_dispatch__(self,func,types,args=(),kwargs=None):
            op = str(func)
            require(op in SELECTED | STRUCTURAL, "unsupported dispatched boundary " + op)
            if op == "aten.dropout.default":
                require(args[1] == 0 and args[2] is False, "dropout enabled")
            out = func(*args,**(kwargs or {}))
            operation_counts[op] = operation_counts.get(op,0)+1
            if op in ("aten.to.dtype","aten.type_as.default") and out.dtype == torch.bfloat16 and args[0].dtype == torch.float32:
                op = "cast_bf16"
            if op in SELECTED or op == "cast_bf16":
                require(stack, "producer outside layer module stack")
                path = stack[-1]; key = (path,op); i = counters.get(key,0); counters[key] = i+1
                if op in ("aten.linear.default", "aten.matmul.default"):
                    left = args[0].detach().float().cpu().numpy().copy()
                    right = args[1].detach().float().cpu().numpy().copy()
                    if op == "aten.linear.default": right = right.T
                    local_gemm.append({"case":case,"producer":f"{path}|{op}|{i}",**local_gemm_bound(out.detach().float().cpu().numpy().copy(),left,right)})
                trace.append({"key": f"{path}|{op}|{i}", "dtype": str(out.dtype).removeprefix("torch."), "value": out.detach().float().cpu().numpy().copy()})
            return out
    artifacts, comparisons, replay, continuity, invariants, diagnoses = {}, [], [], [], [], []
    cache, independent_past = DynamicCache(config=config), None
    prior_native = prior_reference = None
    try:
        for case,offset in (("cold_m128",0),("carried_m128",128)):
            xnp = source[f"source_mixed_bf16_{case}_layer3_input"].copy()
            x = torch.from_numpy(xnp).to(torch.bfloat16)
            positions = torch.arange(offset,offset+128).reshape(1,128).expand(3,1,128)
            position_embeddings = rotary(x,positions)
            mask = torch.from_numpy(source[f"source_mixed_bf16_{case}_attention_mask"].copy()).to(torch.bfloat16)
            trace.clear(); counters.clear()
            with torch.inference_mode(),Trace():
                result = layer(x,position_embeddings=position_embeddings,attention_mask=mask,past_key_values=cache)
            require(not stack, "unbalanced trace hooks")
            expected,independent_past,reference_trace,reference_position = forward(xnp,w,independent_past,position_start=offset)
            verify_sequence(trace,contract); verify_sequence(reference_trace,contract)
            diagnoses.append({"case": case, **diagnose_trace(trace, reference_trace, w)})
            for mode, rows in (("native", trace), ("numpy", reference_trace)):
                probability = next(r["value"] for r in rows if r["key"] == "self_attn|aten.softmax.int|0")
                invariants.append({"case": case, "mode": mode, **softmax_invariants(probability, reference_position["mask"])})
            native = {"output":result.float().detach().numpy().copy(),"key":cache.layers[3].keys.float().numpy().copy(),"value":cache.layers[3].values.float().numpy().copy()}
            oracle = {"output":expected,"key":independent_past[0],"value":independent_past[1]}
            artifacts[case+"_input"] = xnp
            for i,(actual,ref) in enumerate(zip(trace,reference_trace,strict=True)):
                comparisons.append({"case":case,"producer":actual["key"],"storage_dtype":actual["dtype"],**producer_compare(actual["value"],ref["value"])})
                for mode,row in (("native",actual),("numpy",ref)):
                    artifacts[f"{case}_{mode}_producer_{i:02d}"] = row["value"]
            for name in ("output","key","value"):
                same = bits_equal(native[name],source[f"source_mixed_bf16_{case}_layer3_{name}"])
                require(same,"traced native result differs from original official prefix " + name)
                replay.append({"case":case,"producer":name,"bit_identical_to_original_prefix":same})
                comparisons.append({"case":case,"producer":name,"storage_dtype":"bfloat16",**producer_compare(native[name],oracle[name],block=name=="output")})
                artifacts[f"{case}_native_{name}"],artifacts[f"{case}_numpy_{name}"] = native[name],oracle[name]
            for name,value in (("cos",position_embeddings[0]),("sin",position_embeddings[1]),("mask",mask)):
                a = value.float().detach().numpy().copy(); b = reference_position[name]
                comparisons.append({"case":case,"producer":"rope_"+name if name != "mask" else name,"storage_dtype":"bfloat16",**producer_compare(a,b)})
                artifacts[f"{case}_native_{name}"],artifacts[f"{case}_numpy_{name}"] = a,b
                if name == "mask": require(bits_equal(a,b),"mask semantics drift")
            if offset:
                for mode,current,previous in (("native",native,prior_native),("numpy",oracle,prior_reference)):
                    require(all(bits_equal(current[n][:,:,:128],previous[n]) for n in ("key","value")),"carried KV prefix drift")
                    require(not bits_equal(current["value"][:,:,128:],previous["value"]),"stale carried V")
                    continuity.append({"mode":mode,"cold_prefix_bit_exact":True,"new_values_differ":True})
            prior_native = {n:native[n].copy() for n in ("key","value")}
            prior_reference = {n:oracle[n].copy() for n in ("key","value")}
    finally:
        for handle in handles: handle.remove()
    output.mkdir(parents=True,exist_ok=True)
    path = output / "all_bf16_producers.npz"
    np.savez_compressed(path,**artifacts)
    failed = [r for r in comparisons if not r["pass"]]
    gate_pass = not failed and all(row["pass"] for row in invariants)
    numpy_config = io.StringIO()
    with redirect_stdout(numpy_config): np.show_config()
    require(all(sha256((root/name).read_bytes()) == digest for name,digest in source_hashes.items()), "source changed during audit")
    report = {"schema_version":1,"status":"PASS_SOURCE_NATIVE_BF16_DIAGNOSTIC_ONLY" if gate_pass else "BLOCKED_BF16_PRODUCER_GATE",
        "audit_collection_complete":True,"gate_pass":gate_pass,"created_at":datetime.now(timezone.utc).isoformat(),
        "model_id":contract["model_id"],"revision":contract["revision"],"framework_revision":contract["framework_revision"],
        "layer_id":3,"batch":1,"query_tokens":128,"cases":["cold_m128","carried_m128"],
        "contract_sha256":CONTRACT_SHA256,"threshold_source":contract["threshold_source"],"thresholds":contract["thresholds"],
        "input_origin":"verified saved real official mixed-BF16 embedding/GDN0..2 prefix outputs; fixed artificial token IDs",
        "upstream_report_sha256":sha256((upstream/"result.json").read_bytes()),"upstream_arrays":source_report["arrays"],
        "payload_manifest_sha256":sha256((payload/"manifest.json").read_bytes()),"producer_sequence":contract["producer_sequence"],
        "comparisons":comparisons,"failed_producers":failed,"softmax_invariants":invariants,"divergence_diagnoses":diagnoses,
        "scope":contract["scope"],"hardware_v0_semantics_accepted":False,"hardware_v0_rope_gap":contract["hardware_v0_rope_gap"],
        "upstream_admission":"fresh_pinned_prefix_executed_in_process" if fresh_digest else "immutable_saved_prefix_report_digest","native_replay":replay,"kv_continuity":continuity,
        "dispatch_operations":operation_counts,"local_gemm_conditional_audits":local_gemm,"oracle_reuses_native_intermediates":False,"oracle_reuses_native_cold_cache":False,
        "accumulation":"independent NumPy FP32 BLAS/mean/sum vs native Torch CPU FP32 backend; order and transcendental implementations can differ",
        "formal_backend_error_bound_proved":False,"backend_bit_identity_claimed":False,"GDN_bf16_dual_reference_accepted":False,
        "producer_dtype_boundary_contract_frozen_for_layer3":True,"producer_accumulation_tree_frozen":False,
        "U00_2_complete":False,"U01_complete":False,"rtl_executed":False,"mac_utilization_measured":False,
        "arrays":{"file":path.name,"bytes":path.stat().st_size,"sha256":sha256(path.read_bytes())},
        "environment":{"python":platform.python_version(),"torch":torch.__version__,"torch_git_version":torch.version.git_version,
            "numpy":np.__version__,"torch_threads":torch.get_num_threads(),"torch_cpu_capability":torch.backends.cpu.get_cpu_capability(),
            "torch_config":torch.__config__.show(),"numpy_config":numpy_config.getvalue(),"transformers_direct_url":direct_url,
            "official_source_sha256":{k:sha256(p.read_bytes()) for k,(p,digest) in installed.items()}},
        "runner_source_sha256":source_hashes}
    (output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument("--payload",type=Path,required=True)
    p.add_argument("--upstream",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--require-pass",action="store_true")
    p.add_argument("--rebuild-layer0",type=Path,help="Rebuild upstream in a fresh directory using this verified layer0 payload")
    p.add_argument("--rebuild-extra",type=Path,help="Verified embedding/layer1/layer2 payload for prefix rebuild")
    a = p.parse_args()
    try: report = run(a.root,a.payload,a.upstream,a.output,rebuild_layer0=a.rebuild_layer0,rebuild_extra=a.rebuild_extra)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print("BF16_AUDIT_UNSUPPORTED: "+str(exc),file=sys.stderr);raise SystemExit(3)
    print(json.dumps({k:report[k] for k in ("status","audit_collection_complete","gate_pass","failed_producers","arrays")},indent=2))
    if a.require_pass and not report["gate_pass"]: raise SystemExit(2)
