"""Historical safe-receipt checks only; no native imports or live-source claims.

The ZIP was independently checked when retrieved. These tests pin that archive's
identity and recompute its three embedded JSON-member hashes. Only frozen JSON
contracts are read, never current arithmetic/runner sources or private payloads.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CONTRACT_SHA='3f4703e09f978a11391c3fba8eb69ae857a8171045ab4cce8d708beece016734'
ZIP_SHA='84ec66b585b977e4a31555eda59bd5921c7db4c7d138857460ecbea06a117405'
MEMBER_SHA={
    'summary.json':'6ba181efbaa37895959f52a02ee948594d5c7a88fe3a9043bec1598578a09639',
    'progress.json':'e189bfb912cba975c958ad5e8116982b078845443ae2dd743698e962a7748639',
    'source_hashes.json':'ed991c9d1c18eb1d08f0a3aa5c94101713d789b5216f8703a99e4ee1cde763f2',
}
HASH_FIELDS={'actual_receipt_sha256','actual_source_manifest_sha256','launch_contract_sha256',
    'setup_receipt_sha256','snapshot_sha256','source_manifest_sha256'}
FIXED_SUMMARY=dict(schema=1,status='PASS_FRESH_PUBLIC_M16_OBSERVED_GATES',phase='finalize',rows=16,
    enable_raw_kv=True,fresh_profile=True,rtl_executed=False,scala_executed=False,
    full_29_node_acceptance=False,assigned_official_gates=27,observed_fields=28,
    native_acceptance='PASS_OBSERVED_ONLY',actual_dataflow_pass=True,fixed_arithmetic_pass=True)


def need(value):
    if not value:raise ValueError('M16 evidence identity or scope differs')


def same(actual,expected):
    if type(actual) is not type(expected):return False
    if type(expected) is dict:
        return set(actual)==set(expected) and all(same(actual[k],v) for k,v in expected.items())
    if type(expected) is list:
        return len(actual)==len(expected) and all(same(a,b) for a,b in zip(actual,expected))
    return actual==expected


def encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def check_summary(value):
    need(type(value) is dict and set(value)==set(FIXED_SUMMARY)|HASH_FIELDS|{'elapsed_seconds'})
    need(all(same(value[key],expected) for key,expected in FIXED_SUMMARY.items()))
    need(all(digest(value[key]) for key in HASH_FIELDS))
    need(type(value['elapsed_seconds']) is float and math.isfinite(value['elapsed_seconds']) and
         0<value['elapsed_seconds']<=1680)


def verify_evidence(value,contract,pins):
    fixed=dict(schema=1,kind='verified_safe_ci_evidence',repository='liyang53719/hetero_cnn_llm_aha',
        run_id=38904754050,job_id=116985413928,artifact_id=12047713458,artifact_sha256=ZIP_SHA)
    need(type(value) is dict and set(value)==set(fixed)|{'artifact_file_sha256','summary','progress','source_hashes'})
    need(all(same(value[key],expected) for key,expected in fixed.items()))
    need(same(value['artifact_file_sha256'],MEMBER_SHA))
    check_summary(value['summary'])
    for name,expected in MEMBER_SHA.items():need(sha(encoded(value[name[:-5]]))==expected)
    summary=value['summary'];sources=value['source_hashes']
    need(same(value['progress'],dict(schema=1,status='TERMINAL_RECEIPT_PENDING',phase='finalize',
                                   elapsed_seconds=summary['elapsed_seconds'])))
    need(type(sources) is dict and set(sources)=={'schema','launch_contract_sha256','source_sha256','generated_sha256'})
    need(type(sources['schema']) is int and sources['schema']==1)
    need(summary['launch_contract_sha256']==sources['launch_contract_sha256']==CONTRACT_SHA)
    need(same(sources['source_sha256'],contract['source_sha256']) and len(sources['source_sha256'])==193)
    need(same(sources['generated_sha256'],contract['generated_sha256']) and len(sources['generated_sha256'])==8)
    need(same(sources['generated_sha256'],pins['generated_sha256']['enabled']))
    need(all(digest(v) for v in sources['source_sha256'].values()))
    composed=dict(sources['source_sha256']);composed.update(sources['generated_sha256'])
    names=pins['source_paths']
    need(type(names) is list and len(names)==len(set(names))==183 and set(names)<=set(composed))
    entry={name:composed[name] for name in names}
    need(summary['source_manifest_sha256']==sha(encoded(composed)))
    need(summary['actual_source_manifest_sha256']==sha(encoded(entry)))
    return len(composed),len(sources['generated_sha256']),len(entry)


class M16EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=json.loads((HERE/'M16_EVIDENCE.json').read_bytes())
        raw=(HERE/'launch-contract.json').read_bytes();need(sha(raw)==CONTRACT_SHA)
        cls.contract=json.loads(raw)
        name='candidates/qwen2_resident_matrix/raw_kv_public_fresh/pins.json'
        raw=(ROOT/name).read_bytes()
        need(sha(raw)==cls.value['source_hashes']['source_sha256'][name])
        cls.pins=json.loads(raw)

    def test_exact_artifact_members_and_193_8_183_source_chain(self):
        self.assertEqual(verify_evidence(self.value,self.contract,self.pins),(193,8,183))

    def test_summary_rejects_boolean_integer_aliases(self):
        for name,bad in (('schema',True),('rows',True),('assigned_official_gates',True),
                         ('observed_fields',True),('enable_raw_kv',1),('fresh_profile',1),
                         ('full_29_node_acceptance',0),('rtl_executed',0),('scala_executed',0),
                         ('actual_dataflow_pass',1),('fixed_arithmetic_pass',1)):
            value=copy.deepcopy(self.value['summary']);value[name]=bad
            with self.subTest(name=name),self.assertRaises(ValueError):check_summary(value)

    def test_no_m128_full29_or_provisional_receipt_inheritance(self):
        for name,bad in (('rows',128),('full_29_node_acceptance',True),('assigned_official_gates',29),
                         ('observed_fields',29),('rtl_executed',True),('scala_executed',True),
                         ('status','VALIDATED_ACTUAL_POSTFLIGHT_INCOMPLETE'),
                         ('native_acceptance','PASS_FULL_29')):
            value=copy.deepcopy(self.value['summary']);value[name]=bad
            with self.subTest(name=name),self.assertRaises(ValueError):check_summary(value)
        with self.assertRaises(ValueError):check_summary(self.value['progress'])

    def test_artifact_identity_and_source_overlay_drift_rejected(self):
        for target in ('artifact','run','source','overlay','missing_overlay'):
            value=copy.deepcopy(self.value)
            if target=='artifact':value['artifact_sha256']='0'*64
            elif target=='run':value['run_id']=True
            else:
                field='source_sha256' if target=='source' else 'generated_sha256'
                name=next(iter(value['source_hashes'][field]))
                if target=='missing_overlay':value['source_hashes'][field].pop(name)
                else:value['source_hashes'][field][name]='0'*64
            with self.subTest(target=target),self.assertRaises(ValueError):
                verify_evidence(value,self.contract,self.pins)

    def test_entry_digest_requires_the_exact_183_path_selection(self):
        pins=copy.deepcopy(self.pins)
        replacement=next(name for name in self.value['source_hashes']['source_sha256']
                         if name not in pins['source_paths'])
        pins['source_paths'][0]=replacement
        with self.assertRaises(ValueError):verify_evidence(self.value,self.contract,pins)


if __name__=='__main__':unittest.main()
