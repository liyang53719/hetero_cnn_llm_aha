# Native backend for original Chisel phase2

## Verified useful result

The existing official Debian Verilator5.032 package was recovered into a job-local runtime. Its package SHA256 and115 operational files matched the existing pinned manifest. Version and shared-library checks succeeded. Existing g++14.2, make4.4.1 and Perl were usable. The native ChiselTest6 JNA path works with the existing pinned JNA5.13.0 jar.

The byte-identical original HeteroFP32Alu passed4096 deterministic Add/Mul checks against exact binary32 outputs and zero exception flags. This probe used VerilatorBackendAnnotation and executed4096 cycles. Test-loop time was0.1194 seconds. Native elaboration/Verilog/C++ compilation plus simulation took8.957 wall/11.252 CPU seconds. Scala compilation separately took12.223 wall/28.621 CPU seconds. Both exited0 within60 CPU/90 wall-second stage limits. No passed phase1 test was replayed.

This establishes backend operability, not full phase2 numerical correctness,32-ALU compile cost or sustained phase2 throughput. The small test uses exact finite dyadic arithmetic, not comprehensive floating-point corner cases. No fullHost or32-ALU compilation was run here. Full-block acceptance remains0/5. Resource high-water RSS reported by the launch script is cumulative across child stages, not a separately isolated native-stage peak.

## Same-source phase2 route

1. Preserve original DerivedAndPairV2Owner, BlockScalarFloatPolicyV2, UnifiedVectorElement32BankV4, HardFloat and supporting source hashes. Keep the original32-lane bank source and receipt meanings unchanged; constant upper-lane optimization in a unit wrapper is not physical allocation evidence.
2. Change only the test's backend annotation to chiseltest.simulator.VerilatorBackendAnnotation.
3. Add the verified local JNA5.13 jar to the existing classpath. Set PATH to include the job-local Verilator wrapper directory. The wrapper sets its own VERILATOR_ROOT and VERILATOR_BIN.
4. Keep Java -XX:ActiveProcessorCount=1. ChiselTest uses this count for make -j, bounding native compilation parallelism. Set finite process/overall wall and CPU limits for the larger test independently.
5. Run one phase2 case, record original-source/fixture identity, numeric comparisons, request counts and elapsed compile versus simulation times. A successful small probe does not waive those checks.

ChiselTest emits Verilog using FIRRTL2, then invokes Verilator and make, and loads the generated native library through JNA. This tested route does not require firtool, javac or JNI headers. Verilator's native binary links only to the available libc/libm and loader. Tool identities are in TOOL_IDENTITY.json.

## Offline reproduction

Obtain exact official jars in DEPENDENCIES.json. Materialize the pinned official Debian package into a new job-local directory if no equivalent verified copy exists:

    python materialize_verilator.py --output runtime --execute-reviewed-acquisition
    python run_probe.py --jar-dir /path/to/verified/jars --runtime-dir runtime

The materializer downloads only its pinned official Debian URL, disallows redirects and checks size/hash before extraction. It does not globally install packages or run maintainer scripts. Existing recognized build-tool packages may also be used after identity verification.

run_probe.py is a portable wrapper of the executed local launch script. It passed Python syntax checking but was not used to repeat the completed numerical run. NativeAluProbe.scala and all original sources are unchanged from that run. Historical launch source and compact commands are retained for identity; generated circuit/build files and raw logs are excluded.

Thirty pinned Scala inputs consist of29 complete original files plus PreparedReceiptExactExcerpt.scala, the exact receipt-class excerpt adapter. The small probe elaborates only the original ALU. All binaries, packages, generated SV/C++, native libraries and classes stay local and are excluded from this source deliverable.
