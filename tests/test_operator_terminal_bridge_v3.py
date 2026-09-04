import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/operator_terminal_bridge_v3.json").read_text())
SOURCE_PROTOCOL = (ROOT / "chisel/three_model_operator_primitives/src/main/scala/heteronpu/operator/Protocol.scala").read_text()
TERMINAL_PROTOCOL = (ROOT / "integration/gemmini/operator_primitives/src/main/scala/gemmini/HeteroOperatorPrimitiveProtocol.scala").read_text()
BRIDGE = (ROOT / "integration/gemmini/operator_primitives/src/main/scala/gemmini/HeteroV3TerminalBridge.scala").read_text()


def names_in_object(text: str, object_name: str) -> set[str]:
    body = text.split(f"object {object_name}", 1)[1].split("\n}", 1)[0]
    return set(re.findall(r"\bval\s+(\w+)\s*=", body))


def test_every_source_kind_has_exactly_one_translation():
    source = names_in_object(SOURCE_PROTOCOL, "PrimitiveKind") - {"Width"}
    configured = set(CONFIG["simple"]) | set(CONFIG["composite"])
    assert len(source) == CONFIG["source_kind_count"] == 53
    assert configured == source
    for name in source:
        assert f"PrimitiveKind.{name}.U" in BRIDGE


def test_every_simple_target_exists_in_terminal_protocol():
    owners = names_in_object(TERMINAL_PROTOCOL, "HeteroPrimitiveOwner") - {"width"}
    opcodes = names_in_object(TERMINAL_PROTOCOL, "HeteroPrimitiveOpcode") - {"width"}
    for owner, opcode in CONFIG["simple"].values():
        assert owner in owners
        assert opcode in opcodes


def test_bridge_waits_for_checked_terminal_completion():
    assert "state === sWaitCompletion" in BRIDGE
    assert "io.terminalCompletion.fire" in BRIDGE
    assert "tagMismatch" in BRIDGE and "phaseMismatch" in BRIDGE
    assert "io.terminal.fire" in BRIDGE
    assert "HeteroPrimitiveCapability.terminal" in BRIDGE
    assert CONFIG["public_command_or_descriptor_change"] is False
    assert CONFIG["terminal_binding_count"] == 58
