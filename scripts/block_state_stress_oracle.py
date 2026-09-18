#!/usr/bin/env python3
"""Independent full-state E0 oracle. Normal and python -O checks stay enabled."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.block_state_transactions import BlockStateTransactions, StateDomain, WordWrite
from heteronpu.state_commit_protocol import protocol_stress

DOMAINS = tuple(StateDomain)


def seed_words():
    return {(d, k): 1000 + 10*int(d) + k for d in DOMAINS for k in range(3)}


def run_stress(transactions=1000, seed=0xC071):
    """Independent oracle: does not use the implementation's commit selection."""
    def check(ok):
        if not ok:
            raise AssertionError('independent state/ACK oracle mismatch')

    rng = random.Random(seed); model = BlockStateTransactions(); expected = {}; generations = {}
    for request in range(3):
        for layer in range(4):
            scope = request, layer; expected[scope] = seed_words(); generations[scope] = 3
            model.seed(*scope, expected[scope], generation=3)
    digest = hashlib.sha256(); successful_bytes = 0; modes = dict(success=0, last_error=0, poison=0, reset=0)
    for txn_id in range(transactions):
        scope = rng.randrange(3), rng.randrange(4); mode = tuple(modes)[txn_id % 4]; modes[mode] += 1
        ws = tuple(WordWrite(step*10+i, step, d, rng.randrange(3), rng.getrandbits(32))
                   for step in range(2) for i, d in enumerate(DOMAINS))
        owner = model.begin(*scope, txn_id, 2, ws); order = list(ws); rng.shuffle(order)
        old = expected[scope].copy(); prefix = rng.randrange(3)
        reset_position = rng.randrange(len(order))
        if mode == 'poison':
            model.poison(owner)
        for i, w in enumerate(order):
            if mode == 'reset' and i == reset_position:
                model.reset(scope[0])
            okay = not (mode == 'last_error' and i == len(order)-1)
            consumed = model.acknowledge(owner, w.tag, okay=okay, byte_count=4 if okay else 0)
            if consumed and okay:
                successful_bytes += 4
            check(model.snapshot(*scope) == old)
            check(model.generation(*scope) == generations[scope])
        if mode != 'reset':
            result = model.finish(owner, prefix)
            check(result.committed == (mode == 'success'))
            check(result.successful_ack_bytes == (76 if mode == 'last_error' else 80))
            if result.committed:
                for w in ws:
                    if w.step < prefix:
                        expected[scope][w.domain, w.key] = w.value
                generations[scope] += 1
        # Check ALL scopes/domains after each transaction, not only touched cells.
        for address in expected:
            check(model.snapshot(*address) == expected[address])
            check(model.generation(*address) == generations[address])
        check(model.active_count == 0 and not model._core.active)
        check(model.counters['successful_ack_bytes'] == successful_bytes)
        state = [(r, l, int(d), k, v) for (r, l), s in sorted(expected.items()) for (d, k), v in sorted(s.items())]
        digest.update(json.dumps(state, separators=(',', ':')).encode())
    return dict(transactions=transactions, seed=seed, modes=modes, counters=model.counters,
                oracle_sha256=digest.hexdigest(), status='PASS', evidence_class='E0_word_event_contract',
                hardware_execution_verified=False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transactions', type=int, default=4000)
    parser.add_argument('--seed', type=lambda x: int(x, 0), default=0xC071)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.transactions < 1:
        parser.error('transactions must be positive')
    result = {'word_state_oracle': run_stress(args.transactions, args.seed),
              'legacy_barrier': protocol_stress(args.transactions),
              'note': 'random event ordering, not timing or RTL measurement'}
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')
