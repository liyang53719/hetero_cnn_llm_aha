"""Frozen Host lease integration and default-off isolation contracts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("host_frontend_check", HERE / "check_frontend.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class HostSourceCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work = check.ROOT / "work/qwen2_transposed_host_20261011"
        work.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="source_test_", dir=work)
        cls.out = Path(cls.temp.name)
        cls.paths, cls.pins = check.compose(cls.out)
        cls.commands = (cls.out / check.PREFIX / "HostBlockCommands.scala").read_text()
        cls.top = (cls.out / check.PREFIX / "HostBlockTop.scala").read_text()
        cls.kernel = (cls.out / check.PREFIX / "QwenOwnerProtocol.scala").read_text()
        cls.patch = (HERE / "host_workspace.patch").read_text()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_frozen_composition_and_postimages(self):
        self.assertEqual(self.pins, json.loads((HERE / "source_pins.json").read_text()))
        self.assertEqual(check.COMMIT, "825caff3a6c618419c49c7da452e009ce86ae8b5")
        down = json.loads((HERE.parent / "transposed_down/source_pins.json").read_text())
        changed = {p for p, digest in down["patched_sources"].items()
                   if self.pins["patched_sources"][p] != digest}
        self.assertEqual(changed, {check.PREFIX + "HostBlockCommands.scala", check.PREFIX + "HostBlockTop.scala"})
        for path, digest in down["patches"].items():
            self.assertEqual(self.pins["patches"][path], digest)

    def test_public_launch_typed_records_and_command_encoding_untouched(self):
        for name in ("HostResidualCommands.scala", "Protocol.scala", "TypedTensorReader.scala"):
            self.assertEqual((self.out / check.PREFIX / name).read_bytes(), check.frozen(check.PREFIX + name))
        self.assertIn("val regions = Vec(4, new Region)", (self.out / check.PREFIX / "HostResidualCommands.scala").read_text())
        self.assertNotIn("bias_index", self.patch)
        self.assertNotIn("new HostCommandLaunch", "\n".join(line for line in self.patch.splitlines() if line.startswith("+") and not line.startswith("+++")))

    def test_new_profile_is_explicit_and_default_off(self):
        self.assertIn("enableTransposedDown:Boolean=false) extends Module", self.commands)
        self.assertEqual(self.top.count("enableTransposedDown:Boolean=false) extends Module"), 2)
        self.assertIn("if(enableTransposedDown)Some(Output(new TransposedPrefixWorkspace(2560)))else None", self.commands)
        self.assertIn("enableTransposedDense=enableTransposedDown,enableTransposedSeed=enableTransposedDown,enableTransposedDown=enableTransposedDown", self.top)
        self.assertIn("pipelined && weightReadBeats==16 && !bf16Gdn && !bf16QkNormRope", self.top)
        self.assertIn("bf16AttentionCore,bf16AttentionBlock,enableTransposedDown));val port=IO", self.top)

    def test_workspace_isolated_from_every_ordinary_permission_path(self):
        self.assertIn("tensor.io.request.bits.regions:=cfg.regions", self.commands)
        self.assertIn("tensor.io.request.bits.regions(3):=0.U.asTypeOf(new Region)", self.commands)
        self.assertIn("val ordinaryRegions=cfg.regions.take(if(enableTransposedDown)3 else 4)", self.commands)
        self.assertEqual(self.commands.count("ordinaryRegions.map(r=>r.read"), 3)
        self.assertNotIn("cfg.regions.map(r=>r.read", self.commands)
        self.assertIn("l.regions.take(if(enableTransposedDown)3 else 4).map(r=>r.read && !r.write", self.commands)

    def test_launch_lease_bounds_and_all_region_collisions(self):
        launch = self.commands.split("when(io.launch.fire){", 1)[1].split("when(state===fetch", 1)[0]
        for token in ("for(i<-0 until 4;j<-i+1 until 4)",
                      "lease.read && lease.write && lease.base<lease.limit",
                      "lease.base(5,0)===0.U && lease.limit(5,0)===0.U",
                      "lease.limit<=(BigInt(1)<<56).U && lease.limit-lease.base>=64.U",
                      "!overlap(lease.base,lease.limit,l.commandBase,l.commandLimit)",
                      "!overlap(lease.base,lease.limit,l.descriptorBase,l.descriptorLimit)",
                      "when(!workspaceOK){status:=Status.Bounds.U;state:=finish}"):
            self.assertIn(token, launch)
        self.assertIn("(r.base===r.limit && !r.read && !r.write)", launch)

    def test_lease_comes_only_from_launch_snapshot_until_terminal_ack(self):
        lease = self.commands.split("val workspace=io.prefixWorkspace.get", 1)[1].split("when(io.job.fire)", 1)[0]
        self.assertNotIn("io.launch.bits", lease)
        self.assertIn("workspace.base:=cfg.regions(3).base", lease)
        self.assertIn("workspace.extent:=cfg.regions(3).limit-cfg.regions(3).base", lease)
        self.assertIn("workspace.generation:=cfg.epoch.pad(32)+1.U(32.W)", lease)
        self.assertIn("workspace.splitK:=2560.U(12.W)", lease)
        self.assertIn("workspace.valid:=state=/=idle && state=/=locked && status===0.U && !poison", lease)
        self.assertEqual(self.commands.count("cfg:="), 1)
        self.assertIn("identity tag only", self.commands)
        self.assertIn("when(io.result.fire)", self.commands)

    def test_actual_dense_dimensions_rejected_before_owner_issue(self):
        admission = self.commands.split("val downM=", 1)[1].split("// cfg is captured", 1)[0]
        for token in ("Mux(nativeProjection,tokenCount,m)", "Mux(nativeProjection,projectionN,n)",
                      "Mux(nativeProjection,1024.U,a.dims(1))", "downM===16.U || downM===128.U",
                      "downN>0.U && downN(4,0)===0.U", "downK>0.U && downK<=8960.U",
                      "downK(3,0)===0.U", "!downActivationBf16 || downK(4,0)===0.U",
                      "downK<=2560.U || workspaceExtent>=(downN.pad(64)>>5)*16384.U",
                      "when(opcode===0x20.U && (!downShapeOK || !workspaceCapacityOK)){fail(Status.Bounds.U)}"):
            self.assertIn(token, admission)
        self.assertLess(self.commands.index("val downM="), self.commands.index("when(io.job.fire)"))
        self.assertIn("a.dtype===7.U&&d.dtype===7.U", self.commands)
        self.assertIn("b.dtype===5.U && n(4,0)===0.U", self.commands)

    def test_composite_poison_gates_both_launch_handshake_sides_only(self):
        gate = self.top.split("if(enableTransposedDown){", 1)[1].split("io.result<>cmd.io.result", 1)[0]
        self.assertIn("cmd.io.resetRequired||owner.io.resetRequired||hub.io.resetRequired||dmaPoison", gate)
        self.assertIn("cmd.io.launch.valid:=io.launch.valid && !launchPoison", gate)
        self.assertIn("io.launch.ready:=cmd.io.launch.ready && !launchPoison", gate)
        self.assertIn("owner.io.prefixWorkspace.get:=cmd.io.prefixWorkspace.get", gate)
        self.assertIn("}else{cmd.io.launch<>io.launch}", gate)
        self.assertNotIn("response.ready", gate)
        self.assertNotIn("abort:=", gate)
        self.assertIn("coordinated root reset", gate)

    def test_original_owner_dma_and_banks_unchanged(self):
        self.assertEqual(self.top.count("Module(new QwenOwnerKernel("), 1)
        self.assertEqual(self.top.count("Module(new SharedMemoryArbiter(2))"), 1)
        self.assertEqual(self.top.count("Module(new RetainedIdmaWeightBurstAdapter("), 1)
        self.assertNotIn("SyncReadMem", self.commands)
        self.assertNotIn("SyncReadMem", self.top)
        self.assertIn("Module(new TransposedDenseDownOwner(burstWrites=burstWrites)).io", self.kernel)
        self.assertIn("if(enableTransposedSeed){dense.prefixWorkspace.get:=io.prefixWorkspace.get}", self.kernel)

    def test_baseline_is_exact_actual_frozen_parser_with_only_name_override(self):
        path = check.make_baseline(self.out)
        actual = path.read_text().replace("class HostBlockCommandsBaseline(", "class HostBlockCommands(", 1)
        actual = actual.replace('  override def desiredName = "HostBlockCommands"\n', "", 1)
        self.assertEqual(actual.encode(), check.frozen(check.PREFIX + "HostBlockCommands.scala"))
        elaborator = (HERE / "HostWorkspaceElaboration.scala").read_text()
        self.assertIn("emitCHIRRTL", elaborator)
        self.assertNotIn("emitSystemVerilog", elaborator)
        self.assertNotIn("new HostBlockTop", elaborator)
        self.assertNotIn("new QwenOwnerKernel", elaborator)

    def test_register_inventory_counts_nested_regions_and_rejects_unknown_widths(self):
        fir = "  module HostBlockCommands :\n    reg cfg : { epoch : UInt<16>, regions : { base : UInt<64>, read : UInt<1>}[4]}, clock\n"
        self.assertEqual(check.register_inventory(fir)["HostBlockCommands"]["cfg"]["bits"], 276)
        with self.assertRaises(ValueError):
            check.register_inventory("  module X :\n    reg cfg : Analog<3>, clock\n")


if __name__ == "__main__":
    unittest.main()
