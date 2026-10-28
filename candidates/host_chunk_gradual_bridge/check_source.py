#!/usr/bin/env python3
"""TEMP source/contract guard. Does not compile Scala or execute the hardware."""
from pathlib import Path
import hashlib
import json
import re
import sys
import os

P = Path(__file__).resolve().parent
W = Path(os.environ["CHUNK_PARENT_INPUTS"]).resolve()
ADAPTER = "UnifiedMoeSharedArithmeticAdapterV5.scala"
PROTOCOL = "UnifiedMoeSharedArithmeticProtocolV5.scala"
EXECUTE = "GdnRuntimeChunkExecuteOwnerV8.scala"
DERIVED = "GdnRuntimeChunkDerivedAndPairV2Owner.scala"


def compact(text):
    return re.sub(r"\s+", "", text)


def block(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


def source_checks(sources):
    a, p, e, d = (sources[n] for n in (ADAPTER, PROTOCOL, EXECUTE, DERIVED))
    pins = json.loads((P / "BASE_PINS.json").read_text())
    originals = {Path(x["path"]).name: (W / x["path"]).read_text() for x in pins["sources"]}
    old = originals[ADAPTER]
    checks = {}
    def c(name, result):
        checks[name] = bool(result)
    def has(name, text, expected):
        c(name, compact(expected) in compact(text))

    c("private_mode_in_both_bundles", p.count("val gradual=Bool()") == 2 and p.count("val formatOnly=Bool()") == 2)
    c("unchanged_v2_payload_types", "val payload=new UnifiedVectorRequestV2" in p and "val payload=new UnifiedVectorResultV2" in p)
    c("unchanged_lease_and_client_contract", p.split("/** Private ordinary vector operation.")[0] == originals[PROTOCOL].split("/** Private ordinary vector operation.")[0])
    has("gradual_canonical_policy0", a, "val ordinaryGradualCanonical=ordinaryRaw.policy===UnifiedVectorPolicyV2.LegacyRaw.U")
    has("format_canonical_unchanged", a, "val ordinaryFormatCanonical=ordinaryRaw.policy===0.U && !ordinaryRaw.multiply && ordinaryRaw.b.map(x=>x===0.U).reduce(_&&_)")
    has("complete_mode_shape_guard", a, """val ordinaryShapeBad=io.ordinaryVectorRequest.valid &&
      ((ordinaryFormatRequested && ordinaryGradualRequested) ||
       (ordinaryFormatRequested && !ordinaryFormatCanonical) ||
       (ordinaryGradualRequested && !ordinaryGradualCanonical))""")
    has("gradual_request_bit_read", a, "val ordinaryGradualRequested=io.ordinaryVectorRequest.bits.gradual")
    has("format_request_bit_read", a, "val ordinaryFormatRequested=io.ordinaryVectorRequest.bits.formatOnly")
    has("shape_fault_current", a, "terminalError || ordinaryShapeBad || io.externalPoison")
    has("shape_fault_sticky", a, "when(currentFault){poison:=true.B}")
    has("shape_fault_no_accept", a, "io.ordinaryVectorRequest.ready:=varb.io.in(i).ready && clientMayAccept(client) && !ordinaryShapeBad")
    has("global_new_accept_gated", a, "varb.io.out.ready:=(!vOffer || bank.io.request.ready) && admit")
    has("admit_rejects_current_fault", a, "val admit= !poison && !currentFault && !scalarQuarantine && !vectorQuarantine")
    has("captured_offer_not_suppressed", a, "bank.io.request.valid:=vOffer;bank.io.request.bits:=vPacket")
    has("explicit_physical_mode_mapping", a, """varb.io.in(i).bits.payload.policy:=Mux(format,UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U,
      Mux(gradual,UnifiedVectorElement32PolicyV4.RawFp32FiniteGradual.U,
        Mux(raw.policy===3.U,UnifiedVectorElement32PolicyV4.Bf16AddRne.U,raw.policy.pad(3))))""")
    has("physical_gradual_bit", a, "val gradual=io.ordinaryVectorRequest.bits.gradual")
    has("high16_real_zero", a, "varb.io.in(i).bits:=0.U.asTypeOf(new UnifiedVectorElement32RequestV4)")
    has("low16_operands_exact", a, """for(j<-0 until 16){
      varb.io.in(i).bits.payload.a(j):=raw.a(j)
      varb.io.in(i).bits.payload.b(j):=Mux(format,0.U,raw.b(j))
    }""")
    has("gradual_multiply_preserved", a, "varb.io.in(i).bits.payload.multiply:=Mux(format,false.B,raw.multiply)")
    has("gradual_from_retained_vpolicy", a, "val ordinaryVectorGradual=ordinaryVectorClient && vPolicy===UnifiedVectorElement32PolicyV4.RawFp32FiniteGradual.U")
    has("format_from_retained_vpolicy", a, "val ordinaryVectorFormat=ordinaryVectorClient && vPolicy===UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U")
    has("gradual_echo", a, "io.ordinaryVectorResult.bits.gradual:=ordinaryVectorGradual")
    has("format_echo", a, "io.ordinaryVectorResult.bits.formatOnly:=ordinaryVectorFormat")
    has("raw_policy_echo", a, "io.ordinaryVectorResult.bits.payload.policy:=vRawPolicy")
    has("actual_full_fp32_low16", a, "io.ordinaryVectorResult.bits.payload.value(j):=bank.io.result.bits.payload.value(j)")
    has("actual_five_flags_low16", a, "io.ordinaryVectorResult.bits.payload.flags(j):=bank.io.result.bits.payload.arithFlags(j)")
    has("actual_flags_valid", a, "io.ordinaryVectorResult.bits.arithFlagsValid:=bank.io.result.bits.payload.arithFlagsValid")
    has("gradual_arithmetic_format_not", a, "val vectorClientIsRaw=vectorClients.map(i=>vClient===i.U).reduce(_||_) || (ordinaryVectorClient && !ordinaryVectorFormat)")
    has("physical_response_identity_and_flags", a, """val vectorIdentity=bank.io.result.bits.identity.asUInt===vTag.asUInt &&
      bank.io.result.bits.payload.policy===vPolicy &&
      bank.io.result.bits.payload.arithFlagsValid===vectorClientIsRaw &&
      !bank.io.result.bits.payload.formatFlagsValid""")
    has("actual_error_and_raw3_diagnostic", a, "io.ordinaryVectorResult.bits.payload.error:=bank.io.result.bits.payload.error || (!ordinaryVectorFormat && vRawPolicy===3.U)")
    has("unknown_result_quarantined", a, "when(unknownVector){vectorQuarantine:=true.B}")
    has("match_before_bank_return", a, "bank.io.result.ready:=vectorResponseOwned && vectorConsumerReady")
    c("response_not_live_request", "io.ordinaryVectorRequest" not in block(a, "  // Modes are retained", "  val vectorIssue="))
    c("scalar_datapath_unchanged", block(a, "  // The immutable packet", "  // Exactly one accepted") == block(old, "  // The immutable packet", "  // Exactly one accepted"))
    c("scalar_arbiter_unchanged", block(a, "  val sarb=", "  val varb=") == block(old, "  val sarb=", "  val varb="))
    c("legacy_vector_response_unchanged", block(a, "  for(i<-0 until 2){\n    io.vectorResult", "  io.ordinaryVectorResult.valid") == block(old, "  for(i<-0 until 2){\n    io.vectorResult", "  io.ordinaryVectorResult.valid"))
    c("legacy_vector_request_unchanged", block(a, "    }else if(i<6){", "    }else{") == block(old, "    }else if(i<6){", "    }else{"))
    c("lease_count_retire_drain_unchanged", a.split("  // Authoritative acquisition", 1)[1] == old.split("  // Authoritative acquisition", 1)[1])
    c("queue_capture_issue_return_unchanged", block(a, "  val vectorIssue=", "  val numericalFault=") == block(old, "  val vectorIssue=", "  val numericalFault="))
    c("raw_policy_retention_unchanged", block(a, "  val selectedRawPolicy=", "  // Authoritative acquisition") == block(old, "  val selectedRawPolicy=", "  // Authoritative acquisition"))
    for name, text in sources.items():
        original = originals[name]
        c("same_registers_" + name, re.findall(r"\b(?:Reg|RegInit)\([^;\n]*", text) == re.findall(r"\b(?:Reg|RegInit)\([^;\n]*", original))
        c("same_modules_" + name, re.findall(r"\bModule\(new [^\n]*", text) == re.findall(r"\bModule\(new [^\n]*", original))
        c("no_absent_v2_gradual_" + name, "UnifiedVectorPolicyV2.RawFp32FiniteGradual" not in text)
    c("one_existing_bank", a.count("Module(new UnifiedVectorElement32BankV4)") == 1)
    has("execute_canonical0", e, "val requestedPolicy=UnifiedVectorPolicyV2.LegacyRaw.U")
    has("execute_retained_job_gradual", e, "val requestedGradual=context.vectorPolicy===GdnChunkVectorPolicy.FiniteGradualUnderflow.U")
    has("execute_format_excludes_gradual", e, "io.vectorRequest.bits.gradual:= !formatOnly && requestedGradual")
    has("execute_response_mode_and_flags", e, """val identityMatches=io.vectorResult.bits.formatOnly===formatOnly &&
      io.vectorResult.bits.gradual===(!formatOnly && requestedGradual) &&
      r.policy===Mux(formatOnly,0.U,requestedPolicy) &&
      io.vectorResult.bits.arithFlagsValid=== !formatOnly""")
    has("derived_canonical0", d, "val vectorPolicy = UnifiedVectorPolicyV2.LegacyRaw.U")
    has("derived_retained_job_gradual", d, "val vectorGradual = context.vectorPolicy===GdnChunkVectorPolicy.FiniteGradualUnderflow.U")
    has("derived_not_format", d, "io.vectorRequest.bits.formatOnly := false.B")
    has("derived_explicit_gradual", d, "io.vectorRequest.bits.gradual := vectorGradual")
    has("derived_payload_policy", d, "io.vectorRequest.bits.payload.policy := vectorPolicy")
    has("derived_response_mode_and_flags", d, """val identityMatches = !io.vectorResult.bits.formatOnly &&
      io.vectorResult.bits.gradual===vectorGradual && r.policy===vectorPolicy &&
      io.vectorResult.bits.arithFlagsValid""")
    for name, text in ((EXECUTE, e), (DERIVED, d)):
        has("private_request_" + name, text, "val vectorRequest = Decoupled(new UnifiedOrdinaryVectorRequestV5)")
        has("private_result_" + name, text, "val vectorResult = Flipped(Decoupled(new UnifiedOrdinaryVectorResultV5))")
        has("response_payload_" + name, text, "val r = io.vectorResult.bits.payload")
        has("protocol_fault_" + name, text, "when(!identityMatches){fail(Status.Protocol.U)}")
        c("no_extra_rounding_" + name, "TensorMath.bf16Rne" not in text and "F32.bf(" not in text)
    for name, text in sources.items():
        clean = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', '', text, flags=re.S)
        stack = []
        balanced = True
        for ch in clean:
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}":
                if not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[ch]:
                    balanced = False
                    break
        c("lexical_balance_" + name, balanced and not stack)
    return checks


def main():
    pins = json.loads((P / "BASE_PINS.json").read_text())
    sources = {f.name: f.read_text() for f in (P / "source").glob("*.scala")}
    checks = source_checks(sources)
    for group in ("sources", "frozen_original", "dependencies"):
        for item in pins[group]:
            path = W / item["path"]
            checks["pin_" + group + "_" + item["path"]] = path.stat().st_size == item["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    v2 = (W / pins["dependencies"][0]["path"]).read_text()
    v4 = (W / pins["dependencies"][1]["path"]).read_text()
    bank = (W / pins["dependencies"][2]["path"]).read_text()
    checks["v2_namespace_remains_012"] = "object UnifiedVectorPolicyV2 { val LegacyRaw=0;val Bf16MulRne=1;val Bf16AddRne=2 }" in v2
    checks["v2_flags_five_bits"] = "flags=Vec(16,UInt(5.W))" in v2
    checks["v4_gradual3_format4"] = "val RawFp32FiniteGradual = 3" in v4 and "val RawFp32ToBf16Rne = 4" in v4
    checks["pinned_bank_raw_result_for_gradual"] = "Mux(legacy || gradual, raw, bf16Expanded)" in bank
    checks["pinned_bank_actual_five_flags"] = "flags(i) := Mux(arithmetic, arithmeticFlags, 0.U)" in bank and "out.payload.arithFlags := flags" in bank
    checks["pinned_bank_format_flags_invalid"] = "out.payload.formatFlagsValid := false.B" in bank
    # Negative source mutations prove these guards fail on the target regressions.
    mutants = [
        (ADAPTER, "ordinaryFormatRequested && ordinaryGradualRequested", "false.B", "both_modes_allowed"),
        (ADAPTER, "Mux(gradual,UnifiedVectorElement32PolicyV4.RawFp32FiniteGradual.U,", "Mux(gradual,UnifiedVectorElement32PolicyV4.Bf16AddRne.U,", "gradual_wrong_physical_policy"),
        (ADAPTER, "io.ordinaryVectorResult.bits.gradual:=ordinaryVectorGradual", "io.ordinaryVectorResult.bits.gradual:=io.ordinaryVectorRequest.bits.gradual", "live_request_echo"),
        (ADAPTER, "!bank.io.result.bits.payload.formatFlagsValid", "true.B", "format_flags_unchecked"),
        (ADAPTER, "io.ordinaryVectorResult.bits.payload.flags(j):=bank.io.result.bits.payload.arithFlags(j)", "io.ordinaryVectorResult.bits.payload.flags(j):=0.U", "flags_lost"),
        (ADAPTER, "(!ordinaryVectorFormat && vRawPolicy===3.U)", "false.B", "raw3_silently_accepted"),
        (EXECUTE, "io.vectorResult.bits.gradual===(!formatOnly && requestedGradual)", "true.B", "execute_missing_mode_check"),
        (DERIVED, "io.vectorResult.bits.gradual===vectorGradual", "true.B", "derived_missing_mode_check"),
        (ADAPTER, "val bank=Module(new UnifiedVectorElement32BankV4)", "val extraBank=Module(new UnifiedVectorElement32BankV4);val bank=Module(new UnifiedVectorElement32BankV4)", "second_bank"),
    ]
    for filename, old, new, name in mutants:
        changed = dict(sources)
        changed[filename] = changed[filename].replace(old, new)
        checks["mutation_rejected_" + name] = old in sources[filename] and not all(source_checks(changed).values())
    result = {
        "status": "TEMP_SOURCE_CONTRACT_ONLY",
        "scope": "Source/pin/structural checks and negative source mutations only; NOT Scala typecheck, elaboration, RTL, native or floating-point numeric execution.",
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
        "all_pass": all(checks.values()),
        "full_m128_passes": 0,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
