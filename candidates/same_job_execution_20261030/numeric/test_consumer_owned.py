"""Current two-stage acceptance lifecycle regression entry; synthetic tests only."""
import importlib.util,pathlib,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'acceptance_tests/test_lifecycle.py'
s=importlib.util.spec_from_file_location('consumer_acceptance_lifecycle',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
Tests=m.Tests
if __name__=='__main__':unittest.main()
