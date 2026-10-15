"""Negative/admission/source/call-order checks only; no torch or gate arithmetic."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from . import gate_probe as G
from candidates.qwen2_official_platform_fullblock.test_aggregate import fixtures as sample

ROOT=Path(__file__).resolve().parents[2]


def sealed(numeric=False):
    # Start from the prior synthetic receipt fixture, then explicitly adapt
    # new diagnostic scope. This is no actual run or authorization certificate.
    report,launch=sample()
    report.update(status='PASS_DIAGNOSTIC_SOFTWARE_OWNER' if numeric else 'FAIL_DIAGNOSTIC_SOFTWARE_OWNER',
        scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
        diagnostic_numeric_pass=numeric,official_observed_node_pass=numeric,
        diagnostic_acceptance_sealed=numeric,fullblock_pass=False,acceptance_sealed=False,chisel_full_prefill_pass=False,
        local_retention_verified_before_seal=True,local_retention_verified_after_comparison=True,
        diagnostic_backend_debts={k:False for k in G.DIAGNOSTIC_DEBTS},
        diagnostic_identity_initial={k:1 if k!='original_a_payload' else [2,3] for k in G.DIAGNOSTIC_IDENTITIES})
    report['diagnostic_identity_final']=deepcopy(report['diagnostic_identity_initial'])
    for a,b in (('source_sha256_before','source_sha256_after'),('tools_before','tools_after'),
            ('evidence_sha256_before','evidence_sha256_after')):report[a]=report[b]={'source':'a'}
    report['input_identity_before']=report['input_identity_after']={'x':{'sha256':'b'}}
    return report


class Admission(unittest.TestCase):
    def test_default_cold_no_numeric_import(self):
        code='from candidates.qwen2_exact64_diagnostic_fullblock import gate_probe as p; import sys; p.main([]); assert not any(n in sys.modules for n in ("numpy","torch","transformers"))'
        p=subprocess.run([sys.executable,'-B','-c',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
        self.assertEqual(r['status'],'NOT_EXECUTED');self.assertFalse(r['numerical_execution_allowed'])
    def test_missing_review_refuses_before_private_read(self):
        with patch.object(G.job,'authorize',side_effect=ValueError('missing review')),patch.object(G,'_read_json') as read:
            with self.assertRaises(ValueError):G.run()
            read.assert_not_called()
    def test_exact_two_and_all_explicit_budgets(self):
        review={'postseal_gate_invocations':2,**{'postseal_gate_'+n:1 for n in G.LIMIT_KEYS}}
        review['postseal_gate_outer_seconds']=3
        with patch.object(G.job,'authorize',return_value=review):self.assertEqual(G.authorize()[1]['inner_seconds'],1)
        for key in ('postseal_gate_invocations',*('postseal_gate_'+n for n in G.LIMIT_KEYS)):
            r=dict(review);r.pop(key)
            with patch.object(G.job,'authorize',return_value=r):
                with self.assertRaises(ValueError):G.authorize()
    def test_bool_cannot_replace_budget_or_count(self):
        for name in ('postseal_gate_invocations','postseal_gate_inner_seconds'):
            review={'postseal_gate_invocations':2,**{'postseal_gate_'+n:4 for n in G.LIMIT_KEYS},'postseal_gate_outer_seconds':6}
            review[name]=True
            with patch.object(G.job,'authorize',return_value=review):
                with self.assertRaises(ValueError):G.authorize()


class Seal(unittest.TestCase):
    def test_numeric_failure_still_eligible_for_isolation(self):
        for numeric in (False,True):self.assertTrue(G.validate_seal(sealed(numeric)))
    def test_incomplete_failure_drift_or_debt_rejected(self):
        for key,value in (('status','FAILED'),('whole_block_terminal',False),('actual_outputs_sealed',False),
                ('finalfence',False),('fullblock_pass',True),('local_retention_verified_before_seal',False),
                ('local_retention_verified_after_comparison',False),('failure_kind','BUDGET_EXCEEDED')):
            r=sealed();r[key]=value
            with self.assertRaises(ValueError,msg=key):G.validate_seal(r)
        for key in G.DIAGNOSTIC_DEBTS:
            r=sealed();r['diagnostic_backend_debts'][key]=True
            with self.assertRaises(ValueError,msg=key):G.validate_seal(r)
        r=sealed();r['diagnostic_identity_final']['partial']=10
        with self.assertRaises(ValueError):G.validate_seal(r)
        r=sealed();r['tools_after']={'source':'changed'}
        with self.assertRaises(ValueError):G.validate_seal(r)
    def test_supervisor_numeric_failure_allowed_but_failure_cleanup_rejected(self):
        for numeric in (False,True):
            r=sealed(numeric);r['reviewed_source_manifest']='a'*64
            launch=dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
                child_status=r['status'],status='PASS' if numeric else 'FAILED',returncode=0 if numeric else 1,
                failure_kind=None,cleanup_incomplete=False,accepted_final_launch_result=True,automatic_retry=False,
                fullblock_pass=False,acceptance_sealed=False,diagnostic_numeric_pass=numeric,
                diagnostic_acceptance_sealed=numeric,reviewed_source_manifest='a'*64)
            self.assertTrue(G.validate_launch(r,launch))
            for key,value in (('failure_kind','TIMEOUT'),('cleanup_incomplete',True),('returncode',2),
                    ('accepted_final_launch_result',False),('reviewed_source_manifest','b'*64)):
                bad=dict(launch);bad[key]=value
                with self.assertRaises(ValueError,msg=key):G.validate_launch(r,bad)
    def test_forged_terminal_count_and_missing_comparisons_rejected(self):
        r=sealed();r['execution']['host']['launch_result']['jobs']=16
        with self.assertRaises(ValueError):G.validate_seal(r)
        r=sealed();r['tail_comparisons'].pop('gate')
        with self.assertRaises(ValueError):G.validate_seal(r)


class GateCall(unittest.TestCase):
    def test_original_constructor_whole_statement(self):
        raw=json.loads((ROOT/'candidates/qwen2_fullblock_reference_m128/pins.json').read_text())
        source=next(n['source'] for n in raw['model_ast_nodes'] if n.get('label')=='Qwen2MLP unchanged class')
        assignment=G.gate_constructor(ast.parse(source).body)
        expected=ast.parse('self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)').body[0]
        self.assertEqual(ast.dump(assignment,include_attributes=False),ast.dump(expected,include_attributes=False))
    def test_modified_constructor_rejected(self):
        source='class Qwen2MLP:\n def __init__(self):\n  self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=True)'
        with self.assertRaises(ValueError):G.gate_constructor(ast.parse(source).body)
    def test_two_same_linear_calls_in_control_then_actual_order(self):
        calls=[]
        def linear(x):calls.append(x);return {'reference':b'control','actual':b'replay'}[x]
        self.assertEqual(G.replay_pair(linear,'reference','actual',b'control',lambda x:x),(b'control',b'replay'))
        self.assertEqual(calls,['reference','actual'])
    def test_failed_exact_control_prevents_actual_call(self):
        calls=[]
        def linear(x):calls.append(x);return b'wrong'
        with self.assertRaises(ValueError):G.replay_pair(linear,'reference','actual',b'control',lambda x:x)
        self.assertEqual(calls,['reference'])
    def test_only_original_native_metric_authority(self):
        text=Path(G.__file__).read_text()
        self.assertIn('metrics=native.compare(',text);self.assertIn('verdict=native.stage_verdict(',text)
        self.assertNotIn('torch.matmul(',text);self.assertNotIn('nn.functional.linear(',text)
        self.assertNotIn('np.mean(',text)

if __name__=='__main__':unittest.main()
