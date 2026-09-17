#!/usr/bin/env python3
"""Three-state execution ledger; never run task commands or repeat done work.

The frozen plan defines scope/priority/dependencies. The doc/ checklist is the
only mutable state. Local updates use both an exclusive lock and a byte-SHA
precondition; cross-machine concurrency still requires a successful ordinary
Git push BEFORE beginning the claimed task.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_typical_block_plan import UniqueKeyLoader, validate as validate_plan

STATES = {'to do', 'ongoing', 'done'}
DEFAULT = 'doc/block_checklist.yaml'


class ChecklistError(ValueError):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ChecklistError(why)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root: Path, name: Any) -> Path:
    need(isinstance(name, str) and bool(name) and not Path(name).is_absolute(), 'path must be repository-relative')
    need('..' not in Path(name).parts and '\\' not in name, 'path traversal is forbidden')
    p = (root / name).resolve()
    need(p.is_relative_to(root.resolve()) and p.is_file(), 'missing/outside repository file: ' + name)
    return p


def check_proof(root: Path, proof: Any) -> None:
    need(isinstance(proof, dict), 'invalid evidence record')
    need(isinstance(proof.get('范围'), str) and bool(proof['范围'].strip()), 'evidence must declare scope')
    need(re.fullmatch('[0-9a-f]{40}', str(proof.get('设计提交', ''))) is not None, 'evidence needs a fixed commit')
    for item in [proof] + proof.get('关联文件', []):
        need(isinstance(item, dict) and re.fullmatch('[0-9a-f]{64}', str(item.get('SHA256', ''))) is not None,
             'evidence needs a SHA256')
        need(sha(safe_file(root, item.get('文件'))) == item['SHA256'], 'evidence/source hash changed: ' + str(item.get('文件')))


def index_state(doc: dict, plan: dict) -> tuple[dict, dict, dict]:
    tasks = {t['编号']: t for t in plan['任务']}
    rows = doc.get('任务')
    need(isinstance(rows, list), 'missing checklist tasks')
    parents, nodes, parent_of = {}, {}, {}
    for row in rows:
        need(isinstance(row, dict) and isinstance(row.get('编号'), str), 'invalid task')
        ident = row['编号']
        need(ident in tasks and ident not in nodes, 'unknown/duplicate task: ' + ident)
        need(row.get('名称') == tasks[ident]['名称'], 'task title drift: ' + ident)
        parents[ident] = row; nodes[ident] = row
        if '子项' in row:
            children = row['子项']
            need(isinstance(children, list) and bool(children), 'empty child list')
            for child in children:
                cid = child.get('编号', '') if isinstance(child, dict) else ''
                need(re.fullmatch(re.escape(ident) + r'\.[1-9][0-9]*', cid) is not None and cid not in nodes,
                     'invalid/duplicate child ID: ' + str(cid))
                need(isinstance(child.get('前置'), list) and isinstance(child.get('先行依据'), str)
                     and isinstance(child.get('完成边界'), str) and bool(child['完成边界'].strip()), 'incomplete subtask contract')
                need(all(isinstance(x, str) for x in child['前置']) and len(set(child['前置'])) == len(child['前置']), 'duplicate/invalid child prerequisite')
                need('子项' not in child, 'only one subtask level supported')
                nodes[cid] = child; parent_of[cid] = ident
    need(set(parents) == set(tasks), 'checklist must cover every plan task exactly once')
    return nodes, parents, parent_of


def dependencies(ident: str, nodes: dict, plan_tasks: dict, parent_of: dict) -> list[str]:
    row = nodes[ident]
    if ident not in parent_of:
        return list(plan_tasks[ident]['依赖']) + [x['编号'] for x in row.get('子项', [])]
    parent = parent_of[ident]
    # An independent substep may omit the parent's integration prerequisites,
    # but this exception must have an explicit scope and written rationale.
    inherited = [] if row['先行依据'].strip() else plan_tasks[parent]['依赖']
    return sorted(set(inherited + row['前置']))


def aggregate(row: dict, nodes: dict, plan_tasks: dict) -> str:
    children = [x['状态'] for x in row['子项']]
    if all(x == 'to do' for x in children):
        return 'to do'
    if all(x == 'done' for x in children) and all(nodes[d]['状态'] == 'done' for d in plan_tasks[row['编号']]['依赖']):
        return 'done'
    return 'ongoing'


def validate(root: Path, doc: Any, plan: Any, verify_files: bool = True) -> dict:
    validate_plan(plan)
    need(isinstance(doc, dict) and doc.get('版本') == 1, 'unsupported checklist schema')
    need(doc.get('仓库') == plan['仓库'], 'wrong repository')
    need(doc.get('状态集合') == ['to do', 'ongoing', 'done'], 'invalid state vocabulary')
    need(doc.get('默认执行侧') in {'sandbox', 'local-agent'}, 'invalid default executor')
    need(re.fullmatch('[0-9a-f]{40}', str(doc.get('设计基线', ''))) is not None, 'unfrozen checklist baseline')
    nodes, parents, parent_of = index_state(doc, plan)
    tasks = {x['编号']: x for x in plan['任务']}
    locals_ = doc.get('本地事项', [])
    need(isinstance(locals_, list) and len(set(locals_)) == len(locals_) and set(locals_) <= parents.keys(), 'invalid local task map')
    deps = {i: dependencies(i, nodes, tasks, parent_of) for i in nodes}
    for ident, row in nodes.items():
        need(row.get('状态') in STATES, 'invalid task status: ' + ident)
        need(row.get('执行侧', doc['默认执行侧']) in {'sandbox', 'local-agent'}, 'invalid executor: ' + ident)
        need(len(set(deps[ident])) == len(deps[ident]) and set(deps[ident]) <= nodes.keys() and ident not in deps[ident], 'invalid dependency: ' + ident)
        if '子项' in row:
            need(row['状态'] == aggregate(row, nodes, tasks), 'parent status not aggregated: ' + ident)
        else:
            if row['状态'] != 'to do':
                need(isinstance(row.get('负责人'), str) and bool(row['负责人'].strip()), 'unowned active/completed task: ' + ident)
                need(all(nodes[x]['状态'] == 'done' for x in deps[ident]), 'unsatisfied prerequisite: ' + ident)
            proofs = row.get('证据', [])
            need(isinstance(proofs, list), 'invalid evidence list')
            if row['状态'] == 'done':
                need(bool(proofs), 'done without evidence: ' + ident)
                if verify_files:
                    for proof in proofs:
                        check_proof(root, proof)
    # Kahn traversal also catches cross-parent/child cycles.
    pending, emitted = set(nodes), set()
    while pending:
        ready = {i for i in pending if set(deps[i]) <= emitted}
        need(bool(ready), 'checklist dependency cycle')
        emitted |= ready; pending -= ready
    if verify_files:
        need(sha(safe_file(root, doc.get('计划'))) == doc.get('计划SHA256'), 'plan bytes changed without ledger review')
    leaves = {i: r for i, r in nodes.items() if '子项' not in r}
    return {'parent_counts': dict(Counter(r['状态'] for r in parents.values())),
            'leaf_counts': dict(Counter(r['状态'] for r in leaves.values())),
            'parent_tasks': len(parents), 'leaf_items': len(leaves), 'hardware_acceptance_claimed': False}


def read(root: Path, name: str = DEFAULT) -> tuple[dict, dict]:
    doc = yaml.load(safe_file(root, name).read_text(encoding='utf-8'), Loader=UniqueKeyLoader)
    plan = yaml.load(safe_file(root, doc['计划']).read_text(encoding='utf-8'), Loader=UniqueKeyLoader)
    validate(root, doc, plan)
    return doc, plan


def queue(doc: dict, plan: dict, executor: str) -> list[dict]:
    nodes, _, parent_of = index_state(doc, plan)
    tasks = {r['编号']: r for r in plan['任务']}
    ready = []
    for ident, row in nodes.items():
        if '子项' in row or row['状态'] != 'to do':
            continue
        p = parent_of.get(ident, ident)
        assigned = row.get('执行侧', 'local-agent' if p in doc['本地事项'] else doc['默认执行侧'])
        unmet = [d for d in dependencies(ident, nodes, tasks, parent_of) if nodes[d]['状态'] != 'done']
        if not unmet and (executor == 'all' or assigned == executor):
            ready.append({'编号': ident, '名称': row['名称'], '状态': row['状态'],
                          '优先级': tasks[p]['优先级'], '执行侧': assigned,
                          '范围': row.get('完成边界', '按plan同编号全部验收条件')})
    return sorted(ready, key=lambda r: (r['优先级'], r['编号']))


class LedgerDumper(yaml.SafeDumper):
    pass


def _represent(dumper: LedgerDumper, value: dict) -> Any:
    flow = '编号' in value and '子项' not in value and '前置' not in value
    return dumper.represent_mapping('tag:yaml.org,2002:map', value, flow_style=flow)


LedgerDumper.add_representer(dict, _represent)


def dump(doc: dict) -> str:
    return yaml.dump(doc, Dumper=LedgerDumper, allow_unicode=True, sort_keys=False, width=130)


def transition(root: Path, name: str, ident: str, target: str, owner: str,
               expected_sha: str, proof: dict | None = None, reason: str = '') -> str:
    path = safe_file(root, name)
    lock = path.with_name(path.name + '.lock')
    # Atomic local ownership. Never silently remove an existing lock.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temp = None
    try:
        os.close(fd)
        need(sha(path) == expected_sha, 'stale checklist SHA: sync and re-read before retry')
        doc, plan = read(root, name)
        updated = deepcopy(doc)
        nodes, parents, parent_of = index_state(updated, plan)
        need(ident in nodes, 'unknown task')
        row = nodes[ident]; old = row['状态']
        need('子项' not in row, 'parent is derived; update its leaf items')
        need(target in STATES and old != 'done', 'done is terminal; do not repeat completed work')
        need(bool(owner.strip()), 'owner is required')
        need((old, target) in {('to do', 'ongoing'), ('ongoing', 'done'), ('ongoing', 'to do')}, 'invalid state transition')
        if old == 'ongoing':
            need(row.get('负责人') == owner, 'task is owned by another agent')
        if target == 'done':
            need(proof is not None, 'done requires evidence')
            check_proof(root, proof)
            row['证据'] = [proof]
        if target == 'to do':
            need(bool(reason.strip()), 'release requires a reason; do not discard progress silently')
        row['状态'] = target; row['负责人'] = '' if target == 'to do' else owner
        tasks = {r['编号']: r for r in plan['任务']}
        for _ in range(len(parents)):
            for item in parents.values():
                if '子项' in item: item['状态'] = aggregate(item, nodes, tasks)
        updated.setdefault('变更记录', []).append({'编号': ident, '从': old, '到': target, '执行者': owner,
             '时间': datetime.now(timezone.utc).isoformat(), '说明': reason})
        validate(root, updated, plan)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            temp = Path(f.name); f.write(dump(updated)); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path); temp = None
        return sha(path)
    finally:
        if temp is not None: temp.unlink(missing_ok=True)
        lock.unlink()


def render(doc: dict, plan: dict) -> str:
    nodes, parents, _ = index_state(doc, plan)
    def text(x: str) -> str:
        return str(x).replace('|', '\\|').replace('\n', ' ')
    out = ['# Block checklist（只读视图）', '',
           '唯一状态源为 `block_checklist.yaml`；本表由 `scripts/block_checklist.py render` 生成。', '',
           '| 编号 | 优先级 | 事项 | 状态 |', '|---|---|---|---|']
    for task in plan['任务']:
        row = parents[task['编号']]
        for item in [row] + row.get('子项', []):
            out.append('| ' + ' | '.join(map(text, (item['编号'], task['优先级'], item['名称'], item['状态']))) + ' |')
    out.extend(['', '部分子项 done 的父项仍为 ongoing；官方权重、真实RTL/状态连续性按各自完整门禁验收。',
                '队列默认跳过所有 done 和已有负责人正在执行的 ongoing 叶项，不自动重开历史任务。', ''])
    return '\n'.join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--checklist', default=DEFAULT)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('validate')
    nxt = sub.add_parser('next'); nxt.add_argument('--executor', choices=['all', 'sandbox', 'local-agent'], default='all')
    sub.add_parser('render')
    mark = sub.add_parser('mark')
    mark.add_argument('id'); mark.add_argument('state', choices=sorted(STATES))
    mark.add_argument('--owner', required=True); mark.add_argument('--expect-sha', required=True)
    mark.add_argument('--proof', type=Path, help='JSON evidence record with 文件/SHA256/设计提交/范围 and optional 关联文件')
    mark.add_argument('--reason', default='')
    args = p.parse_args()
    try:
        root = args.root.resolve()
        if args.action == 'mark':
            proof = json.loads(args.proof.read_text(encoding='utf-8')) if args.proof else None
            result = {'checklist_sha256': transition(root, args.checklist, args.id, args.state, args.owner,
                                                      args.expect_sha, proof, args.reason)}
        else:
            doc, plan = read(root, args.checklist)
            if args.action == 'render':
                print(render(doc, plan), end=''); return 0
            result = validate(root, doc, plan) if args.action == 'validate' else {'可执行': queue(doc, plan, args.executor)}
            result['checklist_sha256'] = sha(safe_file(root, args.checklist))
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as exc:
        print(f'CHECKLIST_REJECTED: {exc}', file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
