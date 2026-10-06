"""Independent goldens, cross-language checks and negative C03.3 admission tests."""
from copy import deepcopy
import importlib.util
import itertools
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

import pytest

from heteronpu.shape_layout_contract import (
    ContractError, evaluate, legacy_layout, shape_contract, tensor_v2, wide_address,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/block_contracts/shape_layout_vectors.json"
RAW = json.loads(FIXTURE.read_text())


def integers(value):
    if type(value) is str and re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
        return int(value)
    if isinstance(value, dict):
        return {k: integers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [integers(v) for v in value]
    return value


CASES = integers(RAW["vectors"])
BY_ID = {case["id"]: case for case in CASES}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_portable_vectors(case):
    assert evaluate(case["operation"], case["inputs"]) == case["expected"]


def test_metadata_and_exact_decimal_serialization():
    assert RAW["schema"] == "heteronpu.shape-layout-vectors.v1"
    assert RAW["evidence_class"] == "synthetic_E0"
    assert not any(RAW[k] for k in ("chisel_consumer_executed", "rtl_executed", "official_checkpoint_verified"))
    assert len(BY_ID) == len(CASES) == 62

    def no_numeric_json(value):
        assert type(value) not in (int, float)
        if isinstance(value, dict):
            for v in value.values():
                no_numeric_json(v)
        if isinstance(value, list):
            for v in value:
                no_numeric_json(v)
    no_numeric_json(RAW["vectors"])
    high = next(c for c in RAW["vectors"] if c["id"] == "wide_high_base_above_exact_double")
    assert high["inputs"]["base"] == "36028797018964032"


def test_generator_deterministic_and_detects_stale_vector(tmp_path):
    result = subprocess.run([sys.executable, "scripts/generate_shape_layout_vectors.py", "--check"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    spec = importlib.util.spec_from_file_location("vectors", ROOT / "scripts/generate_shape_layout_vectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.artifacts() == module.artifacts()
    for source in module.SOURCES:
        target = tmp_path/source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/source, target)
    subprocess.run([sys.executable, str(ROOT/"scripts/generate_shape_layout_vectors.py"), "--root", str(tmp_path)], check=True)
    target = tmp_path/module.FIXTURE
    changed = json.loads(target.read_text())
    changed["vectors"][0]["expected"]["result"]["max_row"] = "80"
    target.write_text(json.dumps(changed))
    result = subprocess.run([sys.executable, str(ROOT/"scripts/generate_shape_layout_vectors.py"), "--root", str(tmp_path), "--check"],
                            capture_output=True, text=True)
    assert result.returncode != 0 and "STALE_VECTOR" in result.stderr


def test_shape_literal_goldens_no_square_attention_or_hidden_alias():
    result = shape_contract(**BY_ID["decoupled_query_kv"]["inputs"])
    assert result["widths"] == dict(hidden=64, ffn=80, q=128, k=32, v=32, context=128)
    assert result["max_row"] == 128
    assert result["tensors"] == {"q": [3, 128], "k_new": [3, 32], "v_new": [3, 32],
        "k_cache": [1025, 32], "v_cache": [1025, 32], "score": [4, 3, 1025],
        "probability": [4, 3, 1025], "context": [3, 128], "output": [3, 64]}
    assert result["virtual_tensors"] == ["score", "probability"]
    assert result["dense_mnk"] == {"q_proj": [3, 128, 64], "o_proj": [3, 64, 128]}
    assert result["qk_mnk"] == [3, 1025, 32] and result["pv_mnk"] == [3, 32, 1025]
    value = shape_contract(**BY_ID["distinct_value_width"]["inputs"])
    assert value["widths"]["context"] == 256 and value["max_row"] == 256
    assert value["tensors"]["v_cache"] == [1025, 64]
    extra = shape_contract(**BY_ID["explicit_extra_max_row"]["inputs"])
    assert extra["max_row"] == 12288


def test_legacy_tail_literal_offsets_and_all_regions():
    result = legacy_layout(**BY_ID["legacy_tail"]["inputs"])
    assert result["writable_start"] == 124288 and result["total"] == 244672
    assert [r["offset"] for r in result["regions"]] == [
        0, 16384, 24576, 32768, 49152, 69632, 90112, 110592, 110848, 111104,
        111360, 111488, 111616, 113728, 115840, 124288, 132736, 141184, 145408,
        149632, 158080, 162304, 170752, 179200, 187648, 196096, 206656, 217216, 227776, 236224]
    assert len(result["regions"]) == 30
    assert sum(not r["external"] for r in result["regions"]) == 15
    assert not {r["name"] for r in result["regions"]} & {"score", "probability"}
    for a, b in zip(result["regions"], result["regions"][1:]):
        assert a["offset"] + 4*a["words"] <= b["offset"]
    wide = legacy_layout(**BY_ID["legacy_wide_product"]["inputs"])
    assert wide["regions"][0]["words"] == 4290774016  # signed Int product would be negative
    assert wide["regions"][4]["words"] == 4291822080
    assert wide["total"] == 85849019328
    q2 = legacy_layout(**BY_ID["legacy_qwen2"]["inputs"])
    assert (q2["writable_start"], q2["total"]) == (194007040, 363876352)


def test_wide_literal_goldens_and_exclusive_end():
    wide = wide_address(**BY_ID["wide_multiply_above_u32"]["inputs"])
    assert wide == {"elements": 4294836225, "payload_bytes": 17179344900,
        "span_bytes": 17179344900, "offset": 17179344896, "address": 17179344896,
        "end": 17179344900, "padded_end": 17179344960}
    edge = wide_address(**BY_ID["wide_end_u64_exact"]["inputs"])
    assert edge["end"] == 18446744073709551616
    assert edge["address"] == 18446744073709551612
    assert edge["padded_end"] == edge["end"]
    for name, error in (("wide_end_u64_overflow", "address_overflow"),
                        ("wide_span_sum_overflow", "span_overflow"),
                        ("wide_payload_u64_overflow", "span_overflow")):
        assert evaluate("wide_address", BY_ID[name]["inputs"]) == {"accepted": False, "error": error}


def test_reader_encoding_boundary_is_not_owner_admission():
    inputs = BY_ID["v2_u32_elements_max"]["inputs"]
    result = tensor_v2(**inputs)
    assert result == {"elements": 4294967295, "payload_bytes": 17179869180,
                      "padded_end": 17179885568, "owner_dimensions_fit_u16": False}
    assert BY_ID["v2_u32_elements_overflow"]["expected"] == {"accepted": False, "error": "bounds"}
    assert BY_ID["row_u16_max"]["expected"]["accepted"]
    assert not BY_ID["row_u16_overflow"]["expected"]["accepted"]
    assert BY_ID["v2_u18_dimension_max"]["expected"]["accepted"]
    assert not BY_ID["v2_s24_stride_overflow"]["expected"]["accepted"]


@pytest.mark.parametrize("bad", [True, False, 1.0, 1.5, "1", None, float("nan"), float("inf"), -1, 0, 65536])
@pytest.mark.parametrize("field", ["hidden", "ffn", "q_heads", "kv_heads", "head_dim", "value_dim", "query_tokens", "kv_tokens", "max_query_tokens", "max_kv_tokens"])
def test_no_integer_coercion_or_owner_truncation(field, bad):
    inputs = deepcopy(BY_ID["decoupled_query_kv"]["inputs"])
    inputs[field] = bad
    with pytest.raises(ContractError):
        shape_contract(**inputs)


@pytest.mark.parametrize("extra", [[], {"q": 32}, {"": 32}, {"gate": True}, {"gate": 0}])
def test_extra_rows_explicit_valid_non_aliasing(extra):
    inputs = dict(BY_ID["decoupled_query_kv"]["inputs"], extra_rows=extra)
    with pytest.raises(ContractError):
        shape_contract(**inputs)


def test_enumerated_small_strided_addresses_independent_oracle():
    rng = random.Random(303)
    for _ in range(80):
        dims = [rng.randrange(1, 5) for _ in range(rng.randrange(1, 5))]
        element_bytes = rng.choice((1, 2, 4, 8))
        strides = [element_bytes]
        for d in reversed(dims[1:]):
            strides.insert(0, strides[0]*d + rng.randrange(4)*element_bytes)
        indices = [d-1 for d in dims]
        points = [sum(i*s for i, s in zip(ix, strides))
                  for ix in itertools.product(*(range(d) for d in dims))]
        result = wide_address(base=4096, dims=dims, byte_strides=strides,
                              element_bytes=element_bytes, indices=indices)
        assert result["elements"] == len(points)
        assert result["span_bytes"] == max(points) + element_bytes
        assert result["offset"] == max(points)
        assert result["payload_bytes"] == len(points)*element_bytes
        assert result["padded_end"] == ((4096 + max(points) + element_bytes + 63)//64)*64
        assert result["padded_end"] % 64 == 0


def tsv(case):
    i = case["inputs"]
    comma = lambda values: ",".join(str(v) for v in values)
    if case["operation"] == "wide_address":
        fields = ["wide_address", i["base"], len(i["dims"]), comma(i["dims"]), comma(i["byte_strides"]),
                  i["element_bytes"], comma(i["indices"]), i.get("address_bits", 56), i.get("stride_bits", 64), i.get("span_bits", 64)]
    else:
        fields = ["tensor_v2", i["base"], i["rank"], comma(i["dims"]), comma(i["strides"]),
                  i["dtype"], i["region_base"], i["region_limit"], 0, 0]
    return "\t".join(str(v) for v in fields)


@pytest.fixture(scope="session")
def cpp_oracle(tmp_path_factory):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ unavailable; C++ consumer NOT executed")
    out = tmp_path_factory.mktemp("c03_cpp") / "oracle"
    subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    str(ROOT/"cpp/shape_layout_oracle.cpp"), "-o", str(out)], check=True)
    return out


def test_independent_cpp_cross_language_wide_vectors(cpp_oracle):
    cases = [c for c in CASES if c["operation"] in ("wide_address", "tensor_v2")]
    result = subprocess.run([str(cpp_oracle)], input="\n".join(map(tsv, cases))+"\n", text=True, capture_output=True, check=True)
    outputs = result.stdout.splitlines()
    assert len(outputs) == len(cases)
    for case, output in zip(cases, outputs):
        expected = case["expected"]
        if not expected["accepted"]:
            assert output == "REJECT\t" + expected["error"], case["id"]
        else:
            keys = (["elements", "payload_bytes", "span_bytes", "offset", "address", "end", "padded_end"]
                    if case["operation"] == "wide_address" else
                    ["elements", "payload_bytes", "padded_end", "owner_dimensions_fit_u16"])
            assert output == "OK\t" + "\t".join(str(int(expected["result"][k])) for k in keys), case["id"]


@pytest.mark.parametrize("optimized", [False, True])
def test_interpreter_checks_survive_optimization(optimized):
    code = '''from heteronpu.shape_layout_contract import *
for name, args in [('wide_address', dict(base=2**64-64,dims=[17],byte_strides=[4],element_bytes=4,indices=[16],address_bits=64)),
                   ('shape', dict(hidden=64,ffn=65536,q_heads=2,kv_heads=1,head_dim=32,value_dim=32,query_tokens=1,kv_tokens=1))]:
    if evaluate(name,args)['accepted']: raise SystemExit(9)
print('REJECTED_NO_WRAP')
'''
    result = subprocess.run([sys.executable] + (["-O"] if optimized else []) + ["-c", code],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REJECTED_NO_WRAP"


def test_cpp_seeded_differential_and_malformed_stream(cpp_oracle):
    rng = random.Random(30303)
    cases = []
    for _ in range(1200):
        rank = rng.randrange(1, 5)
        dims = [rng.choice((1, 2, 17, 255, 65535)) for _ in range(rank)]
        e = rng.choice((1, 2, 4, 8))
        strides = [e]
        for d in reversed(dims[1:]):
            strides.insert(0, strides[0]*d + rng.choice((0, 64, 1 << 32)))
        inputs = dict(base=rng.choice((0, 64, (1 << 55)+64, (1 << 56)-64)),
                      dims=dims, byte_strides=strides, element_bytes=e,
                      indices=[d-1 for d in dims], address_bits=rng.choice((32, 56, 64)),
                      stride_bits=rng.choice((24, 32, 64)), span_bits=rng.choice((32, 64)))
        if rng.randrange(5) == 0:
            inputs["indices"][0] += 1
        cases.append({"operation": "wide_address", "inputs": inputs})
    malformed = ["", "wide_address\t0", "wide_address\t1e6\t1\t1\t4\t4\t0\t56\t64\t64",
                 "wide_address\t0.0\t1\t1\t4\t4\t0\t56\t64\t64",
                 "wide_address\tTrue\t1\t1\t4\t4\t0\t56\t64\t64"]
    lines = list(map(tsv, cases)) + malformed + [tsv(BY_ID["wide_end_u64_exact"])]
    result = subprocess.run([str(cpp_oracle)], input="\n".join(lines)+"\n", text=True, capture_output=True, check=True)
    outputs = result.stdout.splitlines()
    assert len(outputs) == len(lines)
    for case, output in zip(cases, outputs):
        expected = evaluate(case["operation"], case["inputs"])
        if expected["accepted"]:
            assert output == "OK\t" + "\t".join(str(v) for v in expected["result"].values())
        else:
            assert output == "REJECT\t" + expected["error"]
    assert outputs[len(cases):-1] == ["REJECT\tinput"]*len(malformed)
    assert outputs[-1].endswith("\t18446744073709551616\t18446744073709551616")


def test_unknown_operation_is_a_normalized_rejection():
    assert evaluate("future_v2", {}) == {"accepted": False, "error": "unknown_operation"}


def test_candidate_capacity_override_and_hidden_max_row():
    inputs = dict(BY_ID["decoupled_query_kv"]["inputs"], query_tokens=1025, max_query_tokens=1025)
    assert shape_contract(**inputs)["query_tokens"] == 1025
    inputs.update(hidden=256)
    assert shape_contract(**inputs)["max_row"] == 256


@pytest.mark.parametrize("operation,case,changes,error", [
    ("wide_address", "wide_multiply_above_u32", {"dims": []}, "rank"),
    ("wide_address", "wide_multiply_above_u32", {"byte_strides": [4]}, "strides_rank"),
    ("wide_address", "wide_multiply_above_u32", {"indices": []}, "indices_rank"),
    ("tensor_v2", "v2_fp32", {"dtype": True}, "dtype"),
    ("tensor_v2", "v2_fp32", {"dtype": 6}, "dtype"),
    ("tensor_v2", "v2_fp32", {"rank": 4, "dims": [262143]*4}, "bounds"),
    ("tensor_v2", "v2_fp32", {"region_limit": (1 << 56)+64}, "region_range"),
])
def test_additional_admission_edges(operation, case, changes, error):
    assert evaluate(operation, dict(BY_ID[case]["inputs"], **changes)) == {"accepted": False, "error": error}


def test_profile_sized_synthetic_mnk_not_official_validation():
    for case, q_width, hidden, max_row in (("synthetic_2048_4096_2048",4096,2048,8192),
                                          ("synthetic_2560_6144_2560",6144,2560,10240)):
        result = shape_contract(**BY_ID[case]["inputs"])
        assert result["dense_mnk"]["q_proj"] == [3, q_width, hidden]
        assert result["dense_mnk"]["o_proj"] == [3, hidden, q_width]
        assert result["max_row"] == max_row
