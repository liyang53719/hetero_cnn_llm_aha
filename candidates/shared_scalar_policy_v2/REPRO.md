# Shared Scalar runtime policy V2 — finite actual qualification

Three source files, one fixed hardware definition. This replaces the original `BlockScalarFloat(enableSoftplus=true)`, not its disabled default and not an extra Scalar/SFU. Policy0 retains that original ordering. Policy1 is valid only with opcode4 (finite nonpositive split-ln2 gradual P7 decay); policy2 only opcode7 (pinned Softplus with that internal decay); policy3 rejects. Ordinary operations remain policy0. No model-specific elaboration.

## Actual, not proposed

The exact r2 source compiled; its three original Treadle cases completed61 requests:41 fixed recipe requests on one DUT withoutreset,15 rejection requests,5 legacy primitive requests. Every successful `run` checks output, policy, error, flags and flag-valid on eachof4 held cycles. Eachcase uses a separate instance, but allthree lowFIR hashes match. No new Verilog/RTL replay or fullGDN/M128/full4096/fullblock run.

The first compiler attempt failed on the24-state list declaration and producedzero classes. `history/ENUM_ONLY.patch` preserves the exact declaration-only successor; names/order/statewidth and all arithmetic remained unchanged. Compiler rootcause is not claimed beyond the observed diagnostic. The older failure remains recorded separately in ACTUAL_SUMMARY.

## Source/rebuild roles

1. Resolve the exact public baseline28-source closure and106 ordered JARs via SOURCE_REFS, not floating main or arbitrary cachedclasses. Build those unchanged providers and these3Scala sources with Scala2.13.16/Chisel6.7.0 plugin. Reject duplicate classpaths. The original run reused168 qualified providerclasses and compiled8 newclasses; source/class identity is not a portable build-cache PASS.
2. Run only `heteronpu.continuous.BlockScalarFloatPolicyV2Spec` through `org.scalatest.tools.Runner -R ROLE_NEW_CLASSES -oD -s heteronpu.continuous.BlockScalarFloatPolicyV2Spec` with exact provider/newclasses and ordered JARs. No other suite, extra tests, emitter or retry is authorized by this packet.
3. Reconstruct a new local closed launcher with `env -i`, fixed Python `-I -S -B`, PATH/locale, explicit single CPU and fresh output. Qualify sources/classes/JARs/JDK before and after. Java flags are `-XX:-UsePerfData -Xmx512m -Xss4m -XX:ActiveProcessorCount=1`; home/tmp must be fresh localroles.
4. Resolve `__ROLE_STRICT_CLEANUP__` in the supervisor librarytemplate to its fixed sourcehash. The actual admitted wrapper imported `owned_run`, never the old standalonemain. Originalbudget: CPU240, work270, cleanup285, owned300, outer330 startingbeforepreflight; beforeJava remaining>=310; sampledRSS1GiB, output32MiB. Preserve leader until strictgroupabsencebarrier then reap. Standalone template is a nonexecuted reproduction aid, not byte-identical actual wrapper or a universal safety certification.
5. Require nativeexit0, cleanup, exact3/3 and threecase lines, unchanged inputs and generatedIR inventory; wrapperexit alone is insufficient. Do not silently increase budgets or rerun on failure.

The Spec is selfcontained. To regenerate the optional146481B rationalnodefixture, copy `reference/recipe_oracle.py` to a freshscratchdirectory and run it with ordinary isolatedstdlibPython. Expected41cases/1109nodes/hash is pinned. This helper is NOT a generalIEEE/exp oracle: double-negative-zero Add loses its sign, absent fromthisfixture. Preserve that limit; do not use it to redefine a reference.

## Precision and integration limits

The archived `c2a00001` decay gives candidate `05bfec5b`, versus Torch `05bfec5a` (1ULP). Actual success means the frozen node-recipe expectation matched, not universal Torch equality. Softplus `x<=-80` remains unsupported; x>20 passthrough remains strict. Compound flag-valid remains false; only selected primitive flag cases were tested.1109internal nodes were not individually traced in this DUT run.

GDN integration needs a distinct owner/source gate: biasedSoftplus policy2/op7; negativeabsALog policy1/op4; betaexp stayslegacy0/op4; ordinaryops0. Check every policy echo/ownership/domain and original whole-owner reference under unchanged tolerances. Existing frozen RawPrep gate2 is stillUnsupported. See GDN_POLICY_INTEGRATION_CONDITIONS; no automatic broad admission, clipping, discarded inputs or tolerance widening.

New6FSMstates and reduced32/policy2registers/roundmode+constantmux are realresourceincrements. Same oneFP32ALU, oneDivSqrt and2conversionmodules remain; this is not area/timing or completehardware-resource proof. No actualweights/privateinputs/runtime/classes/largeIR/logs are included.
