"""Regression of stale transaction publishing before its generation check."""
import pytest
from heteronpu.state_commit_protocol import StateCommitModel, StateDomain, StateWrite


@pytest.mark.parametrize('domain', list(StateDomain))
def test_stale_commit_does_not_write_any_domain(domain):
    m = StateCommitModel()
    for tid, value in [(1, 11), (2, 99)]:
        m.start(tid, 7, 1, [domain])
        m.record_write(tid, StateWrite(0, domain, 0, value))
        m.acknowledge(tid, domain)
    m.commit(1, 1)
    before = m.snapshot(7)
    with pytest.raises(RuntimeError, match='stale txn'):
        m.commit(2, 1)
    assert m.snapshot(7) == before
    assert m.generation(7) == 1
    assert m.counters['writes_committed'] == 1
