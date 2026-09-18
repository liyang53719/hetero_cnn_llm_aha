"""C07.1 E0 ACK/state publication gates, including an independent dictionary oracle."""
from dataclasses import replace
import itertools

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from block_state_stress_oracle import run_stress

from heteronpu.block_state_transactions import (
    BlockStateTransactions, Owner, StateContractError, StateDomain, WordWrite,
)

DOMAINS = tuple(StateDomain)


def seed_words():
    return {(d, k): 1000 + 10*int(d) + k for d in DOMAINS for k in range(3)}


def new_model(**kwargs):
    model = BlockStateTransactions(**kwargs)
    model.seed(5, 7, seed_words(), generation=9)
    return model


def writes():
    return tuple(WordWrite(i, 0, d, 0, 2000+i) for i, d in enumerate(DOMAINS))


def ack_all(model, owner, requests):
    for w in reversed(requests):
        assert model.acknowledge(owner, w.tag, okay=True, byte_count=4)


@pytest.mark.parametrize('failure_position', range(10))
def test_any_error_including_final_ack_keeps_nonzero_old_state(failure_position):
    model = new_model(); ws = writes(); old = model.snapshot(5, 7)
    owner = model.begin(5, 7, 1, 1, ws)
    for i, w in enumerate(ws):
        model.acknowledge(owner, w.tag, okay=i != failure_position,
                          byte_count=4 if i != failure_position else 0)
        assert model.snapshot(5, 7) == old and model.generation(5, 7) == 9
        if i < 9:
            with pytest.raises(StateContractError, match='outstanding'):
                model.finish(owner)
    result = model.finish(owner)
    assert not result.committed and result.reason == 'poisoned'
    assert result.successful_ack_bytes == 36 and result.acknowledgements == 10
    assert result.writes_committed == 0 and result.generation == 9
    assert model.snapshot(5, 7) == old and model.active_count == 0


@pytest.mark.parametrize('poison_after', range(11))
def test_successful_acks_after_numerical_poison_still_count(poison_after):
    model = new_model(); old = model.snapshot(5, 7); ws = writes()
    owner = model.begin(5, 7, 1, 1, ws)
    for i in range(11):
        if i == poison_after:
            model.poison(owner)
        if i < 10:
            model.acknowledge(owner, ws[i].tag, okay=True, byte_count=4)
    result = model.finish(owner)
    assert not result.committed and result.successful_ack_bytes == 40
    assert model.counters['successful_ack_bytes'] == 40
    assert model.snapshot(5, 7) == old and result.generation == 9


@pytest.mark.parametrize('order', list(itertools.permutations(range(3))))
def test_prefix_last_write_wins_independent_of_ack_order(order):
    model = new_model()
    ws = (WordWrite(0, 0, StateDomain.KV, 0, 11),
          WordWrite(1, 1, StateDomain.KV, 0, 22),
          WordWrite(2, 2, StateDomain.KV, 0, 33))
    owner = model.begin(5, 7, 1, 3, ws)
    for tag in order:
        model.acknowledge(owner, tag, okay=True, byte_count=4)
    result = model.finish(owner, 2)
    assert result.committed and result.writes_committed == 1
    assert result.successful_ack_bytes == 12 and result.generation == 10
    assert model.snapshot(5, 7)[StateDomain.KV, 0] == 22


@pytest.mark.parametrize('field', ['request', 'layer', 'epoch', 'generation', 'txn_id', 'ticket'])
def test_owner_dimensions_cannot_consume_another_ack(field):
    model = new_model(); owner = model.begin(5, 7, 1, 1, writes())
    wrong = replace(owner, **{field: getattr(owner, field)+1})
    assert not model.acknowledge(wrong, 0, okay=True, byte_count=4)
    assert model.counters['successful_ack_bytes'] == 0
    ack_all(model, owner, writes())
    assert model.finish(owner).committed


def test_duplicate_and_unknown_ack_poison_without_double_count():
    for bad_tag in [0, 999]:
        model = new_model(); old = model.snapshot(5, 7)
        owner = model.begin(5, 7, 1, 1, writes())
        model.acknowledge(owner, 0, okay=True, byte_count=4)
        with pytest.raises(StateContractError, match='unknown or duplicate'):
            model.acknowledge(owner, bad_tag, okay=True, byte_count=4)
        for w in writes()[1:]:
            model.acknowledge(owner, w.tag, okay=True, byte_count=4)
        result = model.finish(owner)
        assert not result.committed and result.successful_ack_bytes == 40
        assert model.snapshot(5, 7) == old
        assert not model.acknowledge(owner, 0, okay=True, byte_count=4)
        assert model.counters['successful_ack_bytes'] == 40


def test_concurrent_stale_generation_and_scope_isolation():
    model = new_model()
    for request, layer in [(5, 8), (6, 7)]:
        model.seed(request, layer, seed_words(), generation=9)
    ws = writes()
    owners = [model.begin(5, 7, 1, 1, ws), model.begin(5, 7, 2, 1, ws),
              model.begin(5, 8, 1, 1, ws), model.begin(6, 7, 1, 1, ws)]
    ack_all(model, owners[0], ws); model.finish(owners[0]); current = model.snapshot(5, 7)
    for owner in owners[1:]:
        ack_all(model, owner, ws)
        result = model.finish(owner)
        assert result.committed == (owner != owners[1])
        assert result.successful_ack_bytes == 40
    assert model.snapshot(5, 7) == current and model.generation(5, 7) == 10
    assert model.active_count == 0


@pytest.mark.parametrize('reset_after', range(11))
def test_reset_invalidates_pending_acks_and_retry_identity(reset_after):
    model = new_model(); old = model.snapshot(5, 7); ws = writes()
    owner = model.begin(5, 7, 99, 1, ws)
    for w in ws[:reset_after]:
        model.acknowledge(owner, w.tag, okay=True, byte_count=4)
    assert model.reset(5) == 1 and model.active_count == 0
    assert model.snapshot(5, 7) == old and model.generation(5, 7) == 9
    retry = model.begin(5, 7, 99, 1, ws)
    assert retry.epoch != owner.epoch and retry.ticket != owner.ticket
    for w in ws:
        assert not model.acknowledge(owner, w.tag, okay=True, byte_count=4)
    with pytest.raises(StateContractError, match='inactive'):
        model.finish(owner)
    ack_all(model, retry, ws)
    result = model.finish(retry)
    assert result.committed and result.successful_ack_bytes == 40
    assert model.counters['successful_ack_bytes'] == reset_after*4 + 40


def test_reset_one_request_not_other_request_or_persistent_state():
    model = new_model(); model.seed(6, 7, seed_words()); model.seed(5, 8, seed_words())
    owners = [model.begin(r, l, 1, 1, writes()) for r, l in [(5, 7), (5, 8), (6, 7)]]
    before = [model.snapshot(r, l) for r, l in [(5, 7), (5, 8), (6, 7)]]
    model.reset(5)
    assert model.active_count == 1
    for o in owners[:2]:
        assert not model.acknowledge(o, 0, okay=True, byte_count=4)
    ack_all(model, owners[-1], writes()); assert model.finish(owners[-1]).committed
    for i, layer in enumerate([7, 8]):
        assert model.snapshot(5, layer) == before[i]


def test_poison_then_retry_same_external_txn_needs_new_ticket():
    model = new_model(); ws = writes(); owner = model.begin(5, 7, 1, 1, ws)
    model.poison(owner); ack_all(model, owner, ws); model.finish(owner)
    retry = model.begin(5, 7, 1, 1, ws)
    assert retry.epoch == owner.epoch and retry.generation == owner.generation
    assert retry.ticket != owner.ticket
    assert not model.acknowledge(owner, 0, okay=True, byte_count=4)
    ack_all(model, retry, ws); assert model.finish(retry).committed


@pytest.mark.parametrize('value', [True, False, -1, 1.0, '1', None])
@pytest.mark.parametrize('field', ['request', 'layer', 'epoch', 'generation', 'txn_id', 'ticket'])
def test_owner_integer_contract(field, value):
    fields = dict(request=0, layer=0, epoch=0, generation=0, txn_id=0, ticket=0)
    fields[field] = value
    with pytest.raises(StateContractError):
        Owner(**fields)


@pytest.mark.parametrize('changes', [{'tag': True}, {'step': -1}, {'key': 1.0},
                                    {'domain': 0}, {'domain': True}, {'value': -1},
                                    {'value': 2**32}, {'value': False}])
def test_word_contract(changes):
    fields = dict(tag=0, step=0, domain=StateDomain.KV, key=0, value=1)
    fields.update(changes)
    with pytest.raises(StateContractError):
        WordWrite(**fields)


@pytest.mark.parametrize('kwargs', [{'okay': 1, 'byte_count': 4}, {'okay': True, 'byte_count': True},
                                   {'okay': True, 'byte_count': 3}, {'okay': False, 'byte_count': 4}])
def test_malformed_ack_is_rejected_before_mutation(kwargs):
    model = new_model(); owner = model.begin(5, 7, 1, 1, writes()); before = model.counters.copy()
    with pytest.raises(StateContractError):
        model.acknowledge(owner, 0, **kwargs)
    assert model.counters == before
    ack_all(model, owner, writes()); assert model.finish(owner).committed


def test_slots_duplicate_request_generation_exhaustion_and_immutability():
    model = new_model(slots=1); owner = model.begin(5, 7, 1, 1, writes())
    with pytest.raises(StateContractError, match='slot'):
        model.begin(5, 8, 1, 1, writes())
    model.reset(5); assert model.active_count == 0
    model.begin(5, 7, 1, 1, writes())
    other = BlockStateTransactions(); other.seed(0, 0, seed_words(), generation=0xFFFFFFFF)
    with pytest.raises(StateContractError, match='generation exhausted'):
        other.begin(0, 0, 1, 1, writes())
    assert other.generation(0, 0) == 0xFFFFFFFF and other.active_count == 0
    snapshot = model.snapshot(5, 7); snapshot.clear()
    assert model.snapshot(5, 7) == seed_words()




@pytest.mark.parametrize('seed', [0, 1, 7, 42, 0xC071])
def test_dictionary_oracle_stress(seed):
    result = run_stress(100, seed)
    assert result['status'] == 'PASS' and result['counters']['committed'] == 25


@pytest.mark.parametrize('case', ['empty', 'duplicate_tag', 'step_outside', 'step_reversed', 'wrong_type'])
def test_bad_program_has_no_accepted_transaction(case):
    model = new_model(); w = WordWrite(0, 0, StateDomain.KV, 0, 11)
    candidates = {'empty': [], 'duplicate_tag': [w, w],
                  'step_outside': [replace(w, step=2)],
                  'step_reversed': [replace(w, step=1), replace(w, tag=1)],
                  'wrong_type': [object()]}
    with pytest.raises(StateContractError):
        model.begin(5, 7, 1, 2, candidates[case])
    assert model.active_count == 0 and model.counters['started'] == 0
    assert model.snapshot(5, 7) == seed_words() and not model._core.active


def test_duplicate_identity_and_bad_prefix_keep_pending():
    model = new_model(); owner = model.begin(5, 7, 1, 1, writes())
    with pytest.raises(StateContractError, match='duplicate active'):
        model.begin(5, 7, 1, 1, writes())
    ack_all(model, owner, writes())
    for prefix in [-1, 2, True, 1.0]:
        with pytest.raises(StateContractError, match='prefix'):
            model.finish(owner, prefix)
        assert model.active_count == 1 and model.generation(5, 7) == 9
    assert model.finish(owner, 0).committed
    assert model.snapshot(5, 7) == seed_words()


def test_seed_replacement_and_invalid_words_never_corrupt_state():
    model = new_model()
    with pytest.raises(StateContractError, match='already exists'):
        model.seed(5, 7, {})
    for invalid in [{(StateDomain.KV, 0): 1, (StateDomain.KV, 1): -1}, {(0, 0): 1}]:
        with pytest.raises(StateContractError):
            model.seed(9, 9, invalid)
        assert (9, 9) not in model._sequences
    assert model.snapshot(5, 7) == seed_words()
