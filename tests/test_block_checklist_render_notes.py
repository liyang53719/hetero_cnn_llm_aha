"""Cold presentation checks only; no model, native, or hardware execution."""
from copy import deepcopy
from pathlib import Path
import sys
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import block_checklist as ledger

def test_render_existing_description_without_changing_task_state():
    doc = yaml.safe_load((ROOT / ledger.DEFAULT).read_text())
    plan = yaml.safe_load((ROOT / doc['计划']).read_text())
    before = deepcopy(doc)
    doc['说明'] = '当前证据：软件 PASS | 硬件 INCOMPLETE\n旧 FAIL 保留'
    output = ledger.render(doc, plan)
    assert '## 当前证据说明' in output
    assert '软件 PASS \\| 硬件 INCOMPLETE 旧 FAIL 保留' in output
    assert doc['任务'] == before['任务']
    del doc['说明']
    assert '## 当前证据说明' not in ledger.render(doc, plan)


def test_current_evidence_index_proofs_and_acceptance_limits():
    doc, plan = ledger.read(ROOT)
    index = doc['当前证据索引20261024']
    proofs = [index['Qwen2历史完整M128'], index['Qwen35_0p8B_L0完整软件']] + index['局部源码与证据']
    for proof in proofs:
        ledger.check_proof(ROOT, proof)
    nodes, _, _ = ledger.index_state(doc, plan)
    assert nodes['U00.2']['状态'] == 'ongoing'
    assert nodes['U01']['状态'] == 'to do'
    assert '0/5' in index['任务与验收边界']
    assert 'INCOMPLETE' in index['Qwen2当前新模式']
    assert 'passed=null' in index['Qwen35_0p8B_L0完整软件']['范围']


def test_render_historical_appendix_is_byte_exact():
    import hashlib
    doc, plan = ledger.read(ROOT)
    appendix = doc['历史只读附录20261012至20261013']
    raw = appendix['原文'].encode('utf-8')
    assert hashlib.sha256(raw).hexdigest() == appendix['原文SHA256']
    assert appendix['来源文件SHA256'] == '3052ceb06503417aac6bf1e40173daf5caa8f3d4b58f95f63c75bb33fc7006bf'
    output = ledger.render(doc, plan)
    assert output.endswith(appendix['原文'])
    assert '以下说明引自唯一状态源 [doc/block_checklist.yaml](block_checklist.yaml)' in output
    assert 'dated 当前证据索引也位于该 YAML' in output
    assert '此文件是唯一执行状态来源' not in output
    assert '本文件末尾' not in output
    assert 'doc/block_checklist.yaml是唯一执行状态来源' in output
    assert '仅保全历史，不代表当前运行或新的验收' in output
    del doc['历史只读附录20261012至20261013']
    assert '## 历史附录：' not in ledger.render(doc, plan)
