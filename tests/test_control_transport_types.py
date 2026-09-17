"""Wire-tag field validation of the software oracle, not an RTL test."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from heteronpu.command_window_contract import WindowMachine, compile_program, chain_program, ControlError


@pytest.mark.parametrize('which', ['window_epoch','window_start','ack_epoch','ack_pc'])
def test_boolean_transport_fields_are_not_integer_tags(which):
    d=WindowMachine(compile_program(chain_program(65)));d.start(1)
    if which.startswith('window'):
        args=[1,0,64];args[0 if which=='window_epoch' else 1]=True if which=='window_epoch' else False
        with pytest.raises(ControlError): d.accept_window(*args)
    else:
        d.accept_window(1,0,64);d.issue(True)
        args=[1,0,64];args[0 if which=='ack_epoch' else 1]=True if which=='ack_epoch' else False
        with pytest.raises(ControlError): d.acknowledge(*args)
