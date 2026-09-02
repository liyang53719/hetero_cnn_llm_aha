from __future__ import annotations

import json

from heteronpu.command import Command128, Engine, NULL_INDEX, Opcode
from heteronpu.l9_transport_contract import EXPECTED_LAYER0, audit_layer_manifest, audit_manifest_file

_ENGINE = {"matrix": Engine.MATRIX, "sfu": Engine.SFU_CGRA, "kv": Engine.KV}
_OPCODE = {opcode.name.lower(): opcode for opcode in Opcode}


def make_layer_records(layer: int = 0):
    records = []
    for index, spec in enumerate(EXPECTED_LAYER0):
        opcode = _OPCODE[spec.opcode]
        src0 = 0x1000 + 3 * index
        src1 = NULL_INDEX if opcode is Opcode.SFU_SOFTMAX else src0 + 1
        dst = src0 + 2
        command = Command128(
            opcode=opcode,
            engine=_ENGINE[spec.engine],
            event_wait=index,
            event_signal=index + 1,
            src0=src0,
            src1=src1,
            dst=dst,
        )
        roots = {"src0": src0, "dst": dst}
        if src1 != NULL_INDEX:
            roots["src1"] = src1
        records.append(
            {
                "operation": spec.operation.replace("l0.", f"l{layer}.", 1),
                "engine": spec.engine,
                "opcode": spec.opcode,
                "word": f"0x{command.pack():032x}",
                "roots": roots,
                "root_bindings": {str(value): {"kind": "test"} for value in roots.values()},
            }
        )
    return records


def test_layer0_manifest_static_contract_passes():
    report = audit_layer_manifest(make_layer_records())
    assert report["status"] == "PASS_L9_4_LAYER_MANIFEST_STATIC_CONTRACT"
    assert report["engine_counts"] == {"sfu": 11, "matrix": 9, "kv": 1}
    assert report["checks"]["event_chain_0_to_21"]
    assert report["checks"]["contiguous_layer_records"]
    assert report["checks"]["six_phase_static_coverage"]
    assert report["evidence_scope"] == "static_manifest_and_Command128_encoding_only"


def test_layer_contract_detects_broken_event_chain():
    records = make_layer_records()
    command = Command128.unpack(int(records[7]["word"], 16))
    bad = Command128(
        opcode=command.opcode,
        engine=command.engine,
        event_wait=3,
        event_signal=command.event_signal,
        src0=command.src0,
        src1=command.src1,
        dst=command.dst,
    )
    records[7]["word"] = f"0x{bad.pack():032x}"
    report = audit_layer_manifest(records)
    assert report["status"].startswith("FAIL")
    assert not report["checks"]["event_chain_0_to_21"]
    assert any(error["kind"] == "event_wait_chain" for error in report["errors"])


def test_layer_contract_detects_missing_descriptor_binding():
    records = make_layer_records()
    records[10]["root_bindings"].pop(str(records[10]["roots"]["src1"]))
    report = audit_layer_manifest(records)
    assert report["status"].startswith("FAIL")
    assert any(error["kind"] == "missing_root_binding" for error in report["errors"])


def test_layer_contract_detects_reordered_operation():
    records = make_layer_records()
    records[1], records[2] = records[2], records[1]
    report = audit_layer_manifest(records)
    assert report["status"].startswith("FAIL")
    assert not report["checks"]["ordered_operations"]


def test_manifest_file_checks_total_record_count(tmp_path):
    path = tmp_path / "manifest.jsonl"
    records = make_layer_records()
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    passing = audit_manifest_file(path, expected_total_commands=21)
    failing = audit_manifest_file(path, expected_total_commands=588)
    assert passing["status"].startswith("PASS")
    assert len(passing["input"]["sha256"]) == 64
    assert failing["status"].startswith("FAIL")
    assert not failing["checks"]["manifest_total"]
