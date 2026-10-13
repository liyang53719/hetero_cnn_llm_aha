import unittest
from .calibration import input_record

class CalibrationTests(unittest.TestCase):
    def test_nested_input_schema_and_no_reference_substitution(self):
        value=dict(path='actual.bf16le',bytes=131072,sha256='0'*64)
        p=dict(stage='gated_norm',actual_owner_output_consumed=True,
            reference_input_substitution=False,all_producer_terminals_successful=True,input=value)
        self.assertIs(input_record(dict(input_provenance=p)),value)
        for bad in (dict(input=value),dict(input_provenance=dict(p,reference_input_substitution=True)),
                    dict(input_provenance=dict(p,actual_owner_output_consumed=False))):
            with self.assertRaises(ValueError):input_record(bad)
if __name__=='__main__':unittest.main()
