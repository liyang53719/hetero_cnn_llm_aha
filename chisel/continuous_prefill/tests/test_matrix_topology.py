#!/usr/bin/env python3
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_matrix_topology import counts

class TopologyTests(unittest.TestCase):
    def test_deduplicated_module_instantiated_eight_times(self):
        s='module HostBlockTop;\n ScalableMatrixTileAdapter matrix();\n idma_backend_rw_axi_flat_wrap dma();\nendmodule\n'
        s+='module ScalableMatrixTileAdapter;\n'+''.join(f' Slice s{i}();\n' for i in range(8))+'endmodule\n'
        s+='module Slice;\n qwen2_matrix_command_endpoint leaf();\nendmodule\n'
        n=counts(s);self.assertEqual(n['qwen2_matrix_command_endpoint'],8);self.assertEqual(n['ScalableMatrixTileAdapter'],1)
    def test_unused_definition_not_counted(self):
        s='module HostBlockTop;\n idma_backend_rw_axi_flat_wrap dma();\nendmodule\nmodule Unused;\n qwen2_matrix_command_endpoint ep();\nendmodule\n'
        self.assertEqual(counts(s)['qwen2_matrix_command_endpoint'],0)
    def test_comments_not_instances(self):
        s='module HostBlockTop;\n// qwen2_matrix_command_endpoint ep();\n/* idma_backend_rw_axi_flat_wrap dma(); */\nendmodule\n'
        self.assertEqual(counts(s)['qwen2_matrix_command_endpoint'],0)
    def test_recursive_hierarchy_rejected(self):
        with self.assertRaises(ValueError):counts('module HostBlockTop;\n HostBlockTop recursion();\nendmodule\n')
    def test_missing_root_rejected(self):
        with self.assertRaises(ValueError):counts('module Other;\nendmodule\n')
if __name__=='__main__': unittest.main(verbosity=2)
