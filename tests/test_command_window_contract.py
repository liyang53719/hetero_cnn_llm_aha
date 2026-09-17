"""C06.1 control specification tests; no model arithmetic or RTL is simulated."""
from dataclasses import replace
import random
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.command_window_contract import (
    Tensor, Command, Program, WindowMachine, ControlError, compile_program, chain_program)


def drive(spec, seed):
    d = WindowMachine(spec); d.start(1); rng = random.Random(seed)
    published = []
    while d.state != 'done':
        if d.state == 'fetch':
            held = d.window_request()
            for _ in range(rng.randrange(5)):
                assert d.window_request() == held
            d.accept_window(*held)
        if d.state == 'offer':
            held = d.offer()
            for _ in range(rng.randrange(5)):
                assert d.issue(False) is None and d.offer() == held
            sent = d.issue(True)
            assert sent.pc == len(published)
        if d.state == 'wait_ack':
            before = dict(d.live)
            for _ in range(rng.randrange(5)):
                assert d.offer() is None and d.completion() is None and d.live == before
            d.acknowledge(d.epoch, d.pc, d.held.size)
            assert d.live == before  # ACK does not release the producer prematurely
        if d.state == 'completion':
            held = d.completion(); before = dict(d.live)
            for _ in range(rng.randrange(5)):
                assert not d.retire(False) and d.completion() == held and d.live == before
            published.append(d.pc)
            assert d.retire(True)
    assert published == list(range(len(spec.program.commands)))
    assert d.completed == len(spec.program.commands)
    assert d.acked_bytes == sum(c.output.size for c in spec.program.commands)
    assert set(d.live) == {c.output.name for c in spec.program.commands if c.output.keep}
    return d


@pytest.mark.parametrize('count', [63, 64, 65, 255, 256, 588])
@pytest.mark.parametrize('seed', range(20))
def test_window_boundaries(count, seed):
    spec = compile_program(chain_program(count))
    assert spec.peak_live == 2
    d = drive(spec, seed)
    assert [x[1:] for x in d.trace if x[0] == 'window'] == list(spec.windows)
    assert max(d.generations) > count // 2 - 1


def test_65535_no_8bit_or_16bit_count_wrap():
    d = drive(compile_program(chain_program(65535)), 1)
    assert d.pc == 65535
    with pytest.raises(ControlError): chain_program(65536)


@pytest.mark.parametrize('value', [0, -1, True, 65536, 1.5])
def test_invalid_count(value):
    with pytest.raises(ControlError): chain_program(value)


def test_long_lived_skip_connection_crosses_windows():
    p = chain_program(588)
    cmds = list(p.commands)
    cmds[0] = Command(('input',), Tensor('t0', 0x200000000, 64))
    cmds[-1] = replace(cmds[-1], inputs=('t586', 't0'))
    p = replace(p, commands=tuple(cmds), slots=3)
    spec = compile_program(p)
    assert spec.last_use['t0'] == 587 and spec.peak_live == 3
    drive(spec, 123)
    cmds[64] = replace(cmds[64], output=replace(cmds[64].output, address=0x200000000))
    with pytest.raises(ControlError, match='live address alias'):
        compile_program(replace(p, commands=tuple(cmds)))


@pytest.mark.parametrize('mutation', ['capacity', 'readonly', 'duplicate', 'future', 'self_alias', 'keep_alias'])
def test_reject_unsafe_lifetime(mutation):
    p = chain_program(65); cs = list(p.commands)
    if mutation == 'capacity': p = replace(p, slots=1)
    if mutation == 'readonly': cs[0] = replace(cs[0], output=replace(cs[0].output, address=p.readonly[0].address))
    if mutation == 'duplicate': cs[1] = replace(cs[1], output=replace(cs[1].output, name='t0'))
    if mutation == 'future': cs[0] = replace(cs[0], inputs=('t64',))
    if mutation == 'self_alias': cs[1] = replace(cs[1], output=replace(cs[1].output, address=cs[0].output.address))
    if mutation == 'keep_alias': cs[0] = replace(cs[0], output=replace(cs[0].output, keep=True))
    with pytest.raises(ControlError): compile_program(replace(p, commands=tuple(cs)))


@pytest.mark.parametrize('address,size', [(1,64), (0,0), (0,63), ((1<<56)-64,128), (-64,64), (True,64)])
def test_extent_errors(address,size):
    with pytest.raises(ControlError): Tensor('x',address,size).check()


def waiting():
    d=WindowMachine(compile_program(chain_program(65))); d.start(5)
    d.accept_window(*d.window_request()); d.issue(True); return d


@pytest.mark.parametrize('epoch,pc,n,error', [(4,0,64,False),(5,1,64,False),(5,0,0,False),(5,0,64,True)])
def test_fault_does_not_publish(epoch,pc,n,error):
    d=waiting(); before=dict(d.live)
    with pytest.raises(ControlError): d.acknowledge(epoch,pc,n,error)
    assert d.state=='locked' and d.live==before and d.completed==0
    with pytest.raises(ControlError): d.start(6)
    d.reset(); d.start(6); d.accept_window(*d.window_request()); d.issue(True)
    d.acknowledge(6,0,64); assert d.retire(True)


def test_duplicate_ack_epoch_reuse_and_old_window():
    d=waiting(); d.acknowledge(5,0,64)
    with pytest.raises(ControlError): d.acknowledge(5,0,64)
    d.reset()
    with pytest.raises(ControlError): d.start(5)
    d.start(6)
    with pytest.raises(ControlError): d.accept_window(5,0,64)


def test_unused_output_is_reclaimed_and_kept_output_not_lost():
    base=0x100000000
    p=Program((Tensor('x',base,64),), tuple(Command(('x',),Tensor(f'o{i}',base+64,64,keep=i==587)) for i in range(588)),2)
    drive(compile_program(p),5)
