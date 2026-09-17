"""Ledger tests use synthetic evidence ONLY to test ledger policy, never RTL."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import block_checklist as ledger
PLAN_NAME = 'doc/three_model_typical_block_closure_20260917_zh.yaml'


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'doc').mkdir()
    (tmp_path / PLAN_NAME).write_bytes((ROOT / PLAN_NAME).read_bytes())
    d = yaml.safe_load((ROOT / ledger.DEFAULT).read_text())
    for p in d['任务']:
        for r in [p] + p.get('子项', []):
            r['状态'] = 'to do'; r['负责人'] = ''; r['证据'] = []
    (tmp_path / ledger.DEFAULT).write_text(ledger.dump(d))
    return tmp_path


def proof(repo):
    p = repo / 'proof.json'; p.write_text('{"scope":"unit test only"}')
    return {'文件': 'proof.json', 'SHA256': ledger.sha(p), '设计提交': 'a' * 40, '范围': 'unit test; no numerical/RTL proof'}


def load(repo):
    d = yaml.safe_load((repo / ledger.DEFAULT).read_text())
    p = yaml.safe_load((repo / PLAN_NAME).read_text())
    return d, p


def leaf(doc, ident):
    for p in doc['任务']:
        for r in [p] + p.get('子项', []):
            if r['编号'] == ident: return r
    raise AssertionError(ident)


def change(repo, ident, state, owner='sandbox', ev=None, reason='', expected=None):
    return ledger.transition(repo, ledger.DEFAULT, ident, state, owner,
                             expected or ledger.sha(repo / ledger.DEFAULT), ev, reason)


def test_actual_repository_checklist():
    d, p = ledger.read(ROOT)
    r = ledger.validate(ROOT, d, p)
    assert r['parent_tasks'] == 44 and r['leaf_items'] >= 44
    assert leaf(d, 'P01.1')['状态'] == 'done'
    assert all(x['编号'] != 'P01.1' for x in ledger.queue(d, p, 'all'))


def test_mark_done_unlocks_only_independent_child(repo):
    change(repo, 'C01.1', 'ongoing')
    digest = change(repo, 'C01.1', 'done', ev=proof(repo))
    d, p = ledger.read(repo)
    assert ledger.sha(repo / ledger.DEFAULT) == digest
    assert leaf(d, 'C01')['状态'] == 'ongoing'
    ids = {x['编号'] for x in ledger.queue(d, p, 'sandbox')}
    assert 'C03.1' in ids and 'C01.1' not in ids and 'C02' not in ids
    with pytest.raises(ledger.ChecklistError, match='terminal'):
        change(repo, 'C01.1', 'ongoing')


def test_local_agent_next_is_scoped_not_repeat(repo):
    change(repo, 'C00.1', 'ongoing')
    change(repo, 'C00.1', 'done', ev=proof(repo))
    d, p = ledger.read(repo)
    assert [x['编号'] for x in ledger.queue(d, p, 'local-agent')] == ['C00.2']
    assert 'C00.1' not in {x['编号'] for x in ledger.queue(d, p, 'all')}
    # Marking the remaining parent gate explicitly is required.
    change(repo, 'C00.2', 'ongoing', owner='local-agent')
    change(repo, 'C00.2', 'done', owner='local-agent', ev=proof(repo))
    d, _ = ledger.read(repo)
    assert leaf(d, 'C00')['状态'] == 'done'


@pytest.mark.parametrize('kind', ['unknown_state', 'missing_task', 'duplicate_task', 'wrong_name',
    'extra_task', 'duplicate_child', 'child_prefix', 'child_cycle', 'missing_scope',
    'unmet_prereq', 'parent_done', 'done_without_proof', 'unowned', 'bad_local_map'])
def test_reject_malformed_or_unearned_states(repo, kind):
    d, p = load(repo)
    if kind == 'unknown_state': leaf(d, 'C02')['状态'] = 'blocked'
    elif kind == 'missing_task': d['任务'].pop()
    elif kind == 'duplicate_task': d['任务'].append(deepcopy(d['任务'][0]))
    elif kind == 'wrong_name': d['任务'][0]['名称'] = '替换了任务'
    elif kind == 'extra_task': d['任务'][0]['编号'] = 'Z99'
    elif kind == 'duplicate_child': d['任务'][0]['子项'].append(deepcopy(d['任务'][0]['子项'][0]))
    elif kind == 'child_prefix': d['任务'][0]['子项'][0]['编号'] = 'WRONG.1'
    elif kind == 'child_cycle': leaf(d, 'C00.1')['前置'] = ['C01.1']; leaf(d, 'C01.1')['前置'] = ['C00.1']
    elif kind == 'missing_scope': leaf(d, 'C00.1')['完成边界'] = ''
    elif kind == 'unmet_prereq': leaf(d, 'C03.1')['状态'] = 'ongoing'; leaf(d, 'C03.1')['负责人'] = 'sandbox'; leaf(d, 'C03')['状态'] = 'ongoing'
    elif kind == 'parent_done': leaf(d, 'C00')['状态'] = 'done'
    elif kind == 'done_without_proof': leaf(d, 'C01.1')['状态'] = 'done'; leaf(d, 'C01.1')['负责人'] = 'sandbox'; leaf(d, 'C01')['状态'] = 'ongoing'
    elif kind == 'unowned': leaf(d, 'C01.1')['状态'] = 'ongoing'; leaf(d, 'C01')['状态'] = 'ongoing'
    else: d['本地事项'].append('MISSING')
    with pytest.raises(ledger.ChecklistError): ledger.validate(repo, d, p)


@pytest.mark.parametrize('case', ['sha', 'owner', 'proof', 'direct_done', 'parent', 'release'])
def test_failed_transition_does_not_modify_file(repo, case):
    if case not in ('direct_done', 'parent'): change(repo, 'C01.1', 'ongoing')
    path = repo / ledger.DEFAULT; before = path.read_bytes()
    with pytest.raises(ledger.ChecklistError):
        if case == 'sha': change(repo, 'C01.1', 'done', ev=proof(repo), expected='0' * 64)
        elif case == 'owner': change(repo, 'C01.1', 'done', ev=proof(repo), owner='other-agent')
        elif case == 'proof': change(repo, 'C01.1', 'done')
        elif case == 'direct_done': change(repo, 'C01.1', 'done', ev=proof(repo))
        elif case == 'parent': change(repo, 'C01', 'ongoing')
        else: change(repo, 'C01.1', 'to do')
    assert path.read_bytes() == before and not path.with_suffix('.yaml.lock').exists()


def test_no_stealing_existing_lock(repo):
    lock = repo / (ledger.DEFAULT + '.lock'); lock.write_text('other process')
    with pytest.raises(FileExistsError): change(repo, 'C01.1', 'ongoing')
    assert lock.read_text() == 'other process'


def test_release_reason_preserved(repo):
    change(repo, 'C01.1', 'ongoing')
    change(repo, 'C01.1', 'to do', reason='本机缺依赖，释放占用但不声称完成')
    d, _ = ledger.read(repo)
    assert leaf(d, 'C01.1')['状态'] == 'to do'
    assert d['变更记录'][-1]['说明'].startswith('本机缺依赖')


@pytest.mark.parametrize('kind', ['missing', 'tampered', 'traversal', 'absolute', 'linked_source', 'scope'])
def test_proof_checks_fail_closed(repo, kind):
    ev = proof(repo)
    if kind == 'missing': ev['文件'] = 'gone.json'
    elif kind == 'tampered': ev['SHA256'] = '0' * 64
    elif kind == 'traversal': ev['文件'] = '../escape.json'
    elif kind == 'absolute': ev['文件'] = str(repo / 'proof.json')
    elif kind == 'linked_source': ev['关联文件'] = [{'文件': 'gone.py', 'SHA256': 'a' * 64}]
    else: ev['范围'] = ''
    with pytest.raises(ledger.ChecklistError): ledger.check_proof(repo, ev)


def test_plan_drift_rejected(repo):
    p = repo / PLAN_NAME; p.write_bytes(p.read_bytes() + b'\n')
    with pytest.raises(ledger.ChecklistError, match='plan bytes'): ledger.read(repo)


def test_ongoing_not_in_queue_and_render_is_deterministic(repo):
    change(repo, 'C01.1', 'ongoing')
    d, p = ledger.read(repo)
    assert 'C01.1' not in {x['编号'] for x in ledger.queue(d, p, 'all')}
    assert ledger.render(d, p) == ledger.render(d, p)
    assert '| C01.1 | P0 |' in ledger.render(d, p)
