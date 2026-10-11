"""Negative guards for the structure checker; no compiler or emitter runs."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("owner_frontend",HERE/"check_frontend.py")
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


class StructureGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pins=json.loads((HERE/"source_pins.json").read_text())
        cls.abi=subprocess.check_output(["git","show",pins["source_commit"]+":"+gate.PREFIX+"RetainedMatrix.scala"],cwd=gate.ROOT).decode()
        route=json.loads(subprocess.check_output(["git","show",pins["source_commit"]+":candidates/qwen2_resident_matrix/transposed_route/manifest.json"],cwd=gate.ROOT))
        gate.checked(cls.abi.encode(),route["original_sources"]["RetainedMatrix.scala"],"retained ABI source")
        lines=["circuit Test :","  module Banks :"];instances=[]
        for kind,depth in (("aBanks",1376),("bBanks",160)):
            for i in range(16):
                name=f"{kind}_{i}"
                lines += [f"    smem {name} : UInt<256> [{depth}]",
                          f"    read mport r_{name} = {name}[address], clock",
                          f"    write mport w_{name} = {name}[address], clock"]
        for name,defname,prefix in (("RetainedMatrixEndpoint","qwen2_matrix_command_endpoint","leaves_"),
                                    ("RetainedMatrixClockGate","tc_clk_gating","gate")):
            block=cls.abi[cls.abi.index("class "+name):].split("\nclass ",1)[0]
            body=[]
            for port,direction,typ,bits in re.findall(r"val (\w+)=(Input|Output)\((Clock\(\)|Bool\(\)|UInt\((\d+)\.W\))\)",block):
                body.append("    "+direction.lower()+" "+port+" : "+("Clock" if typ=="Clock()" else "UInt<"+(bits or "1")+">"))
            body.append("    defname = "+defname)
            for i in range(8):
                module=defname+("_"+str(i) if i else "")
                instance=prefix+str(i) if prefix=="leaves_" else ("gate_"+str(i) if i else "gate")
                lines += ["  extmodule "+module+" :"]+body+[""]
                instances.append(f"    inst {instance} of {module}")
        lines += ["  module Harness :"]+instances+["    reg finalValue : UInt<32>[256][16], clock",
                  "    cmem ram : { context : UInt<3>} [4]",
                  "    cmem ram : { context : UInt<3>} [8]",
                  "    reg storage : { value : UInt<32>[256][16]}[2], clock",
                  "    inst dense of TransposedDenseOwner",
                  "    reg aHigh : UInt<256>, clock",
                  "    reg rmw : { value : UInt<256>}, clock",
                  "    output io : { flip zero : { valid : UInt<1>, bits : UInt<11>}}"]
        cls.fir="\n".join(lines)+"\n"

    def reject(self,old,new):
        self.assertIn(old,self.fir)
        with self.assertRaises(ValueError):gate.resource_audit(self.fir.replace(old,new,1),True,self.abi)

    def test_exact_expected_structure_passes(self):
        result=gate.resource_audit(self.fir,True,self.abi)
        self.assertEqual(result["sram_bytes"],786432)
        self.assertEqual(len(result["bank_ports"]),32)

    def test_memory_depth_and_port_inflation_fail(self):
        self.reject("UInt<256> [1376]","UInt<256> [1375]")
        self.reject("read mport r_aBanks_0 = aBanks_0[address], clock",
                    "read mport r_aBanks_0 = aBanks_0[address], clock\n    read mport another = aBanks_0[address], clock")

    def test_full_endpoint_abi_is_checked(self):
        self.reject("input step_a_i : UInt<256>","input step_a_i : UInt<257>")
        self.reject("input step_a_i : UInt<256>","output step_a_i : UInt<256>")
        self.reject("defname = qwen2_matrix_command_endpoint","defname = qwen2_matrix_command_endpoint\n    parameter EXTRA = 1")

    def test_missing_or_extra_endpoint_reference_fails(self):
        self.reject("inst leaves_7 of qwen2_matrix_command_endpoint_7","inst leaves_7 of qwen2_matrix_command_endpoint_6")
        self.reject("inst leaves_7 of qwen2_matrix_command_endpoint_7","inst leaves_7 of qwen2_matrix_command_endpoint_7\n    inst extra of qwen2_matrix_command_endpoint_7")

    def test_clockgate_and_unknown_extmodule_fail(self):
        self.reject("defname = tc_clk_gating","defname = wrong_gate")
        with self.assertRaises(ValueError):gate.resource_audit(self.fir+"  extmodule extra :\n    defname = extra\n",True,self.abi)

    def test_second_owner_and_response_buffer_fail(self):
        self.reject("inst dense of TransposedDenseOwner","inst dense of TransposedDenseOwner\n    inst old of StreamingDenseOwner")
        with self.assertRaises(ValueError):gate.resource_audit(self.fir+"    reg hidden : UInt<4096>, clock\n",True,self.abi)

    def test_a_address_and_queue_capacity_fail(self):
        self.reject("bits : UInt<11>","bits : UInt<10>")
        self.reject("context : UInt<3>} [4]","context : UInt<3>} [5]")


if __name__=="__main__":unittest.main()
