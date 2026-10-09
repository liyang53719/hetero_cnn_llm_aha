"""Small ABI/preflight tests, with no RTL elaboration or simulation."""
import dataclasses
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_bf16_qkv_descriptor import (HostQkvBinding, COLUMNS, build_host_qkv_descriptor,
    parse_host_qkv_descriptor, build_qkv_commands, validate_qkv_bindings)


class HostQkvDescriptorTests(unittest.TestCase):
    def binding(self, role=0, **kwargs):
        args=dict(role=role, rows=128, token_base=0, token_count=1,
                  activation_ddr=0x100000, weight_ddr=0x200000+role*0x1000000, output_ddr=0x4000000+role*0x200000)
        return HostQkvBinding(**(args | kwargs))

    def test_roundtrip_roles_and_boundaries(self):
        for role, n in enumerate(COLUMNS):
            for rows in (1, 15, 16, 17, 128):
                for base in (0, rows-1):
                    with self.subTest(role=role, rows=rows, base=base):
                        binding=self.binding(role, rows=rows, token_base=base, token_count=rows-base)
                        command, records=build_host_qkv_descriptor(binding, first_index=37, event_wait=2, event_signal=7)
                        self.assertEqual(parse_host_qkv_descriptor(command.pack(), {i:r.pack() for i,r in records.items()}), binding)
                        self.assertEqual(binding.job['writeBytes'], (rows-base)*n*2)
                        self.assertEqual(binding.job['dst'], binding.output_ddr+base*n*2)
                        self.assertEqual(binding.job['a'], binding.activation_ddr+base*2048)

    def test_three_public_commands_fan_out(self):
        bindings=[self.binding(role, token_base=127) for role in range(3)]
        commands, records=build_qkv_commands(bindings)
        self.assertEqual(len(records),63)
        self.assertEqual([c.src0 for c in commands],[0,21,42])
        self.assertEqual([(c.event_wait,c.event_signal) for c in commands],[(0,1),(1,2),(2,3)])
        self.assertEqual([parse_host_qkv_descriptor(c,records) for c in commands],bindings)
        self.assertEqual({b.job['a'] for b in bindings},{bindings[0].activation_ddr+127*2048})

    def test_invalid_role_window_address_and_own_alias(self):
        for args in ({'role':3}, {'rows':0}, {'rows':129}, {'token_count':0}, {'token_count':129},
                     {'token_base':128}, {'activation_ddr':0x100002}, {'output_ddr':0x100000},
                     {'weight_ddr':(1<<56)-64}):
            with self.subTest(args=args), self.assertRaises(ValueError): self.binding(**args)

    def test_cross_command_physical_alias_and_false_chain_rejected(self):
        bindings=[self.binding(role) for role in range(3)]
        for changed in (dataclasses.replace(bindings[1],output_ddr=bindings[0].output_ddr),
                        dataclasses.replace(bindings[1],weight_ddr=bindings[0].weight_ddr),
                        dataclasses.replace(bindings[1],activation_ddr=bindings[0].output_ddr)):
            with self.assertRaises(ValueError):validate_qkv_bindings([bindings[0],changed,bindings[2]])
        with self.assertRaises(ValueError):validate_qkv_bindings(bindings[::-1])

    def test_policy_sentinels_geometry_and_header_rejections(self):
        command, records=build_host_qkv_descriptor(self.binding())
        for payload in (records[5].payload^3, records[5].payload|(3<<8), records[5].payload^(1<<10),
                        records[5].payload|(1<<52), records[5].payload|(1<<71)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_host_qkv_descriptor(command,records|{5:dataclasses.replace(records[5],payload=payload)})
        for index in range(6,15):
            for payload in (records[index].payload|64, records[index].payload|(1<<64), records[index].payload^(1<<56)):
                with self.subTest(index=index,payload=payload), self.assertRaises(ValueError):
                    parse_host_qkv_descriptor(command,records|{index:dataclasses.replace(records[index],payload=payload)})
        for index in range(21):
            with self.subTest(index=index), self.assertRaises(ValueError):
                parse_host_qkv_descriptor(command,records|{index:dataclasses.replace(records[index],flags=1)})
        for index,target in ((5,5),(8,6),(14,15),(4,0xffffff),(7,0xffffff)):
            with self.assertRaises(ValueError):
                parse_host_qkv_descriptor(command,records|{index:dataclasses.replace(records[index],next_index=target)})
        with self.assertRaises(ValueError):parse_host_qkv_descriptor(dataclasses.replace(command,flags=1),records)
        with self.assertRaises(ValueError):parse_host_qkv_descriptor(dataclasses.replace(command,event_signal=0),records)
        with self.assertRaises(ValueError):parse_host_qkv_descriptor(dataclasses.replace(command,src1=command.src0),records)
        # Role K cannot retain Q's wider dimensions.
        with self.assertRaises(ValueError):parse_host_qkv_descriptor(command,records|{5:dataclasses.replace(records[5],payload=records[5].payload|(1<<8))})


if __name__=='__main__':unittest.main()
