# Source and actual-control reproduction

`python3 -I -S -B tests/make_profile_spec.py` checks all profile fields against the pinned official-config-derived reference and regenerates the exact Spec. It is only a source check.

For real compilation use the repository-pinned Scala2.13.16/Chisel6.7.0 plugin plus ChiselTest6.0.0/ScalaTest3.2.19 complete106-JAR lock. In an empty CLASSES directory:

```
java -Xmx1g -Xss4m -XX:ActiveProcessorCount=1 -cp "$PINNED_CP" scala.tools.nsc.Main -classpath "$PINNED_CP" -Xplugin:"$PINNED_PLUGIN" -language:reflectiveCalls -d "$CLASSES" source/*.scala
java -Xmx1g -Xss4m -XX:ActiveProcessorCount=1 -cp "$CLASSES:$PINNED_CP" org.scalatest.tools.Runner -R "$CLASSES" -oW -s heteronpu.continuous.UnifiedBlockAdmissionSpec
```

No original production/model classes are needed or allowed to shadow these new classes. Compilation and tests are separate bounded stages, not a shell chain. The observed run used one CPU, heap1GiB/AS4GiB/sampledRSS2GiB; compile120CPU/150wall and test60CPU/90wall. Actual typecheck produced15classes215756B. The single test elaborates one small admission DUT and switches runtime profiles without intervening reset. Treadle produces lowered FIRRTL; it does not instantiate/validate the full4096 arithmetic datapath.

Current completed scope:5 profiles,13 reject cases,74 independent boundary vectors,backpressure/latching and wrong-profile terminal poison. Wrong transactionId,undrained/backend-reset completion and counter saturation are source semantics but not tested by this Spec. No technology synthesis/PPA/numeric/MAC-useful claim.

Exact existing public dependency lock: `candidates/qwen2_core_client_chirrtl_evidence/pins/OFFICIAL_DEPENDENCY_PINS.json` at commit `7bf6fc287ba9e7b5f696c44a691f432a3e3958c4` (106 ordered entries; identities in `pins/SOURCE_AND_EVIDENCE_PINS.json`). Obtain each official Maven artifact by its lock URL and verify byte count and SHA256 before constructing PINNED_CP in index order. PINNED_PLUGIN is the separately pinned Chisel plugin from that same closure. These are external recoverable dependencies, not files included in this source package. The observed Java21 launcher/old runtime manifest hashes are identity metadata only, not a newly audited complete runtime. Compilation/test require independently approved bounded launchers; this document is not such a launcher or GO.
