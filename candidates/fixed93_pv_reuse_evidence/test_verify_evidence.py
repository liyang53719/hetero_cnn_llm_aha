"""Synthetic fixtures only. No historical stream, model, oracle or native library."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_evidence as v

F, D = v.load_codec()
LIMITS = dict(contexts=1,bank_bytes=64,max_chunk=256,max_metadata=128,max_record=1024,
              max_records=32,max_output=16384,max_raw=8192)
CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'


def dump(obj): return (json.dumps(obj,sort_keys=True,indent=2)+'\n').encode()
def pin(raw): return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def wire(role, *, empty=False, finish=True, bad_terminal=None, unclosed=False, attention_schemas=None):
    """Manual frame construction, not Writer/chain_hash; never generates model values."""
    result = bytearray(F.Limits(**LIMITS).header()); previous=hashlib.sha256(result).digest()
    count=raw_count=0
    frames=[]
    def add(kind, payload, metadata, context=255, epoch=0, ticket=0, base=0, aux=0, rawlen=None):
        nonlocal previous,count,raw_count
        rawlen=len(payload) if rawlen is None else rawlen
        meta=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
        frame=F.FRAME.pack(count,kind,0,context,0,epoch,ticket,base,aux,rawlen,len(meta),len(payload))
        previous=hashlib.sha256(previous+frame+meta+payload).digest()
        frames.append((len(result),frame,meta,payload,previous));result.extend(frame+meta+payload+previous)
        if kind != 255: count+=1;raw_count+=rawlen
    if unclosed:
        add(1,b'',{},context=0,epoch=1,ticket=1)
    elif not empty:
        if role=='wholeblock':
            add(8,b'synthetic opaque bytes; NOT model output',{'schema':'wholeblock-token-envelope-v1','semantic':False})
        else:
            for sequence,schema in enumerate(attention_schemas or ('fixed93-attention-event-v2',)):
                add(8,b'synthetic opaque bytes; NOT model output',{'schema':schema,'sequence':sequence,'kind':'synthetic'})
    seal=None
    if finish:
        terminal=[count,raw_count,len(result),previous]
        if bad_terminal is not None:
            index=bad_terminal
            terminal[index]=b'X'*32 if index==3 else terminal[index]+1
        add(255,F.TERMINAL.pack(*terminal),{},rawlen=0)
        seal=dict(records=count,raw_bytes=raw_count,encoded_bytes=len(result),final_hash=previous.hex())
    return bytes(result),seal,frames


class Fixture:
    def __init__(self, base):
        self.base=Path(base);self.root=self.base/'run';self.root.mkdir()
        self.plan_path=self.base/'plan.json';self.terminal_path=self.base/'terminal.json';self.budget_path=self.base/'budget.json'
        self.budget={'schema':'fixed93-fullblock-resource-proposal-v1','status':'REVIEWED_FIXED93_FULLBLOCK_BUDGET',
                     'wholeblock_trace_limits':{'codec':LIMITS},'attention_trace_limits':{'codec_limits':LIMITS}}
        self.budget_path.write_bytes(dump(self.budget))
        source={'synthetic_source.py':'4'*64}
        self.identity={'source_manifest_sha256':'1'*64,'admission_sha256':'2'*64,
                       'budget_sha256':pin(dump(self.budget))['sha256'],
                       'source_map_sha256':v.digest(json.dumps(source,sort_keys=True).encode()),
                       'reviewed_source_manifest':'1'*64}
        parent={'pid':111,'start_ticks':100};child={'pid':222,'start_ticks':200}
        self.attestation={'schema':'fixed93-original-session-terminal-v1','original_session_id':123,
                          'launcher_exit_code':0,'cleanup_confirmed':True,'ownership_uncertain':False,
                          'run_root':str(self.root),'parent':parent,'child':child,'identity':self.identity}
        diagnostics={'native_record_status':'PASS','exit_code':0,'waitid_code':1,'waitid_status':0,
                     'receipt_timed_out':False,'cleanup_confirmed':True,'failure_code':'NONE','failure_boundary':'NONE',
                     'kill_attempted':True,'kill_result':'SIGNAL_SENT_BEFORE_REAP'}
        ident={k:self.identity[k] for k in ('source_manifest_sha256','admission_sha256','budget_sha256')}
        invocation={'argv':['synthetic-worker','--no-execution'],'cwd':str(self.root)}
        self.docs={
          'launch':dict(ident,status='PASS_FULLBLOCK_PROCESS_SUPERVISION_ONLY',returncode=0,cleanup_confirmed=True,
            actual_arithmetic_accepted=False,M128_acceptance=False,independent_actual_review_required=True,
            actual_output=str(self.root/'run01'),diagnostics=diagnostics),
          'native':dict(status='PASS',stage='native',spawn_handle_acquired=True,expected_exit=0,
            exit_code=0,anchor_confirmed=True,reaped=True,group_state='absent',cleanup_confirmed=True,
            timed_out=False,parent_exception=None,pid=222,pgid=222,exit_observed_while_unreaped={'pid':222,'code':1,'status':0},
            kill_attempted=True,kill_result='signal_sent_before_reap',group_before_reap='present',**invocation),
          'lease':dict(ident,parent=parent,out=str(self.root/'run01')),
          'consumed':dict(source_manifest_sha256='1'*64,admission_sha256='2'*64,parent=parent,child=child),
          'algorithm':dict(schema='fixed93-actual-algorithm-artifact-seal-v1',complete_algorithm_arrays=True),
          'attention':dict(schema='fixed93-fullblock-attention-pv-reuse-observation-v1',complete_observation=True,
             status='COMPLETE_ATTENTION_OBSERVATION_NOT_FULLBLOCK_ACCEPTANCE',observer_error=None,
             event_file='attention-events.lec1',event_codec_source_sha256=v.PINS,control_only=False,
             numerical_acceptance=False,native_acceptance=False,fullblock_acceptance=False,
             source_manifest_sha256='1'*64,source_sha256=source,
             normalization_evaluations_per_causal_key=1,probability_use_repeats=8,
             normalization_reuses_per_causal_key=7,observed_normalization_reuses=693504,
             scalar_schedule_changed=True,both_probability_domains_repeats_verified=True),
          'result':dict(status='PASS_FIXED93_M128_OFFICIAL_OBSERVED_FULLBLOCK_PUBLIC21',official_observed_node_pass=True,
             evidence_contract=CONTRACT,
             acceptance_sealed=True,whole_block_terminal=True,actual_outputs_sealed=True,finalfence=True,fullblock_pass=True,
             reviewed_source_manifest=self.identity['reviewed_source_manifest'],source_sha256_before=source,source_sha256_after=source,
             source_manifest_sha256=self.identity['source_map_sha256'],backend_debts={'synthetic_debt':False},
             same_live_identity_initial={'synthetic':1},same_live_identity_final={'synthetic':1})}
        self.streams={}
        for role,path in v.STREAMS.items(): self.replace_stream(role, wire(role))
        self.plan={'schema':'fixed93-pv-reuse-offline-container-plan-v1','evidence_contract':CONTRACT,
                   'identity':self.identity,'invocation':invocation,
                   'receipts':{},'streams':self.streams,'terminal_attestation':{},'budget':pin(dump(self.budget))}
        self.save()
    def replace_stream(self,role,built):
        raw,seal,_=built;p=self.root/v.STREAMS[role];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.streams[role]=dict(pin(raw),limits=LIMITS)
        if role=='wholeblock':
            self.docs['result']['wholeblock_observation']={'evidence_contract':CONTRACT,
                'lossless_streams_sealed':True,'complete_declared_schedule':True,
                'complete_declared_cache':True,'complete_algorithm_arrays':False,'codec_seal':seal,
                'artifacts':{'wholeblock_events.lec1':dict(path=str(p),**pin(raw))}}
        else:
            self.docs['attention']['event_codec_seal']=seal
            self.docs['attention']['event_count']=seal['records'] if seal else 1
    def save(self):
        self.docs['result']['algorithm_artifact_seal']=self.docs['algorithm']
        self.docs['result']['observation']=self.docs['attention']
        for role,path in v.RECEIPTS.items():
            p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);raw=dump(self.docs[role]);p.write_bytes(raw)
            self.plan['receipts'][role]=pin(raw)
        raw=dump(self.attestation);self.terminal_path.write_bytes(raw);self.plan['terminal_attestation']=pin(raw)
        self.plan_path.write_bytes(dump(self.plan));self.plan_sha=pin(dump(self.plan))['sha256']
    def verify(self):
        return v.verify(self.root,self.plan_path,self.plan_sha,self.terminal_path,self.budget_path,seconds=10)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.fixture=Fixture(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def reject_before_stream(self, fn):
        with patch.object(v,'scan',side_effect=AssertionError('STREAM OPENED')) as mocked:
            with self.assertRaises((v.Rejected,ValueError,FileNotFoundError)):fn()
            self.assertEqual(mocked.call_count,0)
    def test_positive_is_limited_and_natural_anchor_kill_legal(self):
        r=self.fixture.verify();self.assertEqual(r['status'],'PASS_REPORTED_TERMINAL_AND_TWO_STREAM_CONTAINERS_ONLY')
        self.assertFalse(r['fullblock_acceptance']);self.assertFalse(r['numerical_acceptance'])
        self.assertFalse(r['algorithm_artifact_bytes_checked']);self.assertEqual(set(r['streams']),set(v.STREAMS))
        for before,attempted,result,projection in [('absent',False,'not_requested','NOT_REQUESTED'),
                ('unknown',True,'group_already_absent','GROUP_ALREADY_ABSENT')]:
            self.fixture.docs['native'].update(group_before_reap=before,kill_attempted=attempted,kill_result=result)
            self.fixture.docs['launch']['diagnostics'].update(kill_attempted=attempted,kill_result=projection)
            self.fixture.save();self.assertFalse(self.fixture.verify()['fullblock_acceptance'])
    def test_terminal_negative_matrix_opens_no_stream(self):
        for role,key,value in [('launch','status','STARTED_ONE_FULLBLOCK_PROCESS'),('launch','status','FAIL_FULLBLOCK_PROCESS_SUPERVISION'),
           ('launch','status','PASS_STARTUP_PROBE'),('launch','returncode',True),('launch','cleanup_confirmed',False),
           ('launch','ownership_uncertain',True),('native','exit_code',1),('native','reaped',False),('native','group_state','unknown'),
           ('native','timed_out',True),('native','anchor_confirmed',False),('result','status','ACTUAL_OUTPUTS_SEALED_WHOLE_PUBLIC21'),
           ('result','acceptance_sealed',False),('result','finalfence',False),('attention','status','INCOMPLETE'),
           ('result','fullblock_pass',False),('attention','control_only',True),('native','kill_result','PermissionError: denied'),
           ('native','group_before_reap','absent'),('native','anchor_error',{'type':'synthetic'})]:
            with self.subTest(role=role,key=key,value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    f=Fixture(tmp);f.docs[role][key]=value;f.save();self.reject_before_stream(f.verify)
    def test_identity_negative_matrix(self):
        def split_reviewed_digest(f):
            f.identity['reviewed_source_manifest']='8'*64
            f.docs['result']['reviewed_source_manifest']='8'*64
        for mutate in [lambda f:f.docs['consumed']['child'].update(start_ticks=True),
          lambda f:f.docs['consumed'].update(parent={'pid':99,'start_ticks':1}),
          lambda f:f.docs['native'].update(pid=223),lambda f:f.docs['native'].update(argv=['foreign']),
          lambda f:f.docs['launch'].update(admission_sha256='5'*64),
          lambda f:f.docs['lease'].update(out='/foreign'),
          lambda f:f.docs['result'].update(source_manifest_sha256='1'*64),
          lambda f:f.attestation.update(launcher_exit_code=1),lambda f:f.attestation.update(ownership_uncertain=True),
          lambda f:f.attestation.update(run_root='/foreign'),split_reviewed_digest,
          lambda f:f.attestation.update(parent={'pid':True,'start_ticks':100}),
          lambda f:f.docs['consumed'].update(parent={'pid':True,'start_ticks':100}),
          lambda f:f.docs['attention'].update(source_manifest_sha256='9'*64),
          lambda f:f.docs['attention'].update(source_sha256={'foreign.py':'9'*64})]:
            with tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);mutate(f);f.save();self.reject_before_stream(f.verify)
    def test_missing_metadata_and_attestation(self):
        for which in ('terminal','result'):
            with tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);p=f.terminal_path if which=='terminal' else f.root/v.RECEIPTS['result'];p.unlink()
                self.reject_before_stream(f.verify)
    def test_pins_policy_and_json_rejection(self):
        f=self.fixture
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}',b'['*65+b']'*65):
            with self.assertRaises(v.Rejected):v.json_bytes(raw,1024)
        for mutate in [lambda p:p.update(schema='wrong'),lambda p:p['streams']['attention']['limits'].update(max_output=20000),
                       lambda p:p['receipts']['launch'].update(bytes=True),lambda p:p['identity'].update(admission_sha256='bad')]:
            with tempfile.TemporaryDirectory() as tmp:
                a=Fixture(tmp);a.plan=copy.deepcopy(a.plan);mutate(a.plan)
                a.plan_path.write_bytes(dump(a.plan));a.plan_sha=pin(dump(a.plan))['sha256'];self.reject_before_stream(a.verify)
        f.plan_sha='0'*64;self.reject_before_stream(f.verify)
    def test_symlink_hardlink_and_parent_alias(self):
        f=self.fixture;p=f.root/v.RECEIPTS['launch'];raw=p.read_bytes();p.unlink();target=Path(self.temp.name)/'target';target.write_bytes(raw);p.symlink_to(target)
        self.reject_before_stream(f.verify)
        p.unlink();os.link(target,p);self.reject_before_stream(f.verify)
        with self.assertRaises(v.Rejected):v.inside(f.root,'../outside')
        with self.assertRaises(v.Rejected):v.inside(f.root,'run01/./x')
    def test_truncations_and_trailing_bytes(self):
        raw,_,frames=wire('attention')
        cuts={0,1,F.HEADER.size-1,F.HEADER.size,frames[0][0]+1,len(raw)-1,len(raw)-32,len(raw)-F.TERMINAL.size-34}
        for offset,frame,meta,payload,chain in frames:
            cursor=offset
            for part in (frame,meta,payload,chain):
                cuts.add(cursor + max(1,len(part)//2))
                cursor += len(part)
        for candidate in [raw[:n] for n in sorted(cuts)]+[raw+b'x',raw+raw[frames[-1][0]:]]:
            with tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);p=f.root/v.STREAMS['attention'];p.write_bytes(candidate);f.streams['attention'].update(pin(candidate));f.save()
                with self.assertRaises(ValueError):f.verify()
    def test_terminal_forgery_valid_chain_and_unclosed(self):
        for bad in range(4):
            with tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);f.replace_stream('attention',wire('attention',bad_terminal=bad));f.save()
                with self.assertRaises(ValueError):f.verify()
        raw,_,_=wire('wholeblock',unclosed=True)
        d=D.Decoder(io.BytesIO(raw),F.Limits(**LIMITS))
        with self.assertRaises(ValueError):
            for _ in d.records():pass
        self.assertIsNone(d.seal)
    def test_empty_codec_is_not_fullblock_container(self):
        raw,seal,_=wire('wholeblock',empty=True)
        d=D.Decoder(io.BytesIO(raw),F.Limits(**LIMITS));self.assertEqual(sum(1 for _ in d.records()),0);self.assertEqual(vars(d.seal),seal)
        f=self.fixture;f.replace_stream('wholeblock',wire('wholeblock',empty=True));f.save()
        with self.assertRaises(v.Rejected):f.verify()
    def test_external_seal_mismatch_each_field(self):
        for key in ('records','raw_bytes','encoded_bytes','final_hash'):
            with tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);s=f.docs['attention']['event_codec_seal'];s[key]='0'*64 if key=='final_hash' else s[key]+1
                f.save()
                with self.assertRaises(v.Rejected):f.verify()
    def test_stream_swap_and_hash_change(self):
        f=self.fixture;raw,seal,frames=wire('wholeblock');f.replace_stream('attention',(raw,seal,frames));f.save()
        with self.assertRaises(v.Rejected):f.verify()
        with tempfile.TemporaryDirectory() as tmp:
            f=Fixture(tmp);f.plan['streams']['attention']['sha256']='0'*64;f.save()
            with self.assertRaises(v.Rejected):f.verify()
    def test_reader_short_nonbytes_eof_and_bound(self):
        raw,_,_=wire('attention')
        class Reader(io.BytesIO):
            def __init__(self,mode):super().__init__(raw);self.mode=mode
            def read(self,n):
                if self.mode=='short':return super().read(max(0,n-1))
                data=super().read(n)
                return bytearray() if not data else data
        for mode in ('short','nonbytesEOF'):
            d=D.Decoder if mode=='short' else None
            with self.assertRaises(ValueError):
                dec=D.Decoder(Reader(mode),F.Limits(**LIMITS))
                for _ in dec.records():pass
        r=v.HashedReader(io.BytesIO(b'ab'),1,time.monotonic()+1)
        with self.assertRaises(v.Rejected):r.read(2)
        with self.assertRaises(v.Rejected):r.read(69721)
    def test_changed_file_after_first_stream_rejects(self):
        f=self.fixture;original=v.scan
        def change(*args,**kwargs):
            result=original(*args,**kwargs)
            if args[1]=='attention':
                p=f.root/v.STREAMS['wholeblock'];raw=p.read_bytes();p.unlink();p.write_bytes(raw)
            return result
        with patch.object(v,'scan',side_effect=change):
            with self.assertRaises(v.Rejected):f.verify()
    def test_decoder_import_isolation(self):
        foreign=object();old=sys.modules.get('format');sys.modules['format']=foreign
        try:
            fmt,dec=v.load_codec();self.assertIs(dec.Seal,fmt.Seal);self.assertIs(sys.modules['format'],foreign)
        finally:
            if old is None:sys.modules.pop('format',None)
            else:sys.modules['format']=old
    def test_codec_source_cap_before_open(self):
        fake=Path(self.temp.name)/'fake';(fake/'r3').mkdir(parents=True)
        (fake/'r3'/'format.py').write_bytes(b'x'*33000)
        with patch.object(v,'__file__',str(fake/'verify_evidence.py')), patch.object(v,'open_checked',side_effect=AssertionError('SOURCE OPENED')) as opened:
            with self.assertRaises(v.Rejected):v.load_codec()
            self.assertEqual(opened.call_count,0)
    def test_cli_default_no_scan_no_pass(self):
        from contextlib import redirect_stdout
        f=self.fixture;buf=io.StringIO()
        with redirect_stdout(buf):
            code=v.main(['--run-root',str(f.root),'--plan',str(f.plan_path),'--plan-sha256',f.plan_sha,
                         '--terminal-attestation',str(f.terminal_path),'--budget',str(f.budget_path)])
        self.assertEqual(code,1);self.assertEqual(json.loads(buf.getvalue())['status'],'REJECTED_NO_ACCEPTANCE')

    def test_pv_contract_exact_declarations_and_scope(self):
        # 693504 is only a synthetic metadata declaration. It is not generated or observed data.
        f=self.fixture;r=f.verify()
        self.assertEqual(f.docs['attention']['observed_normalization_reuses'],693504)
        for key in ('independently_observed_process_exit','algorithm_artifact_bytes_checked',
                    'token_operand_payload_semantics_checked','schedule_cache_correspondence_checked',
                    'attention_logical_payload_digest_checked','numerical_acceptance','fullblock_acceptance','RTL'):
            self.assertIs(r[key],False)
        self.assertEqual(v.PLAN_SCHEMA,'fixed93-pv-reuse-offline-container-plan-v1')
        self.assertEqual(v.EVIDENCE_CONTRACT,CONTRACT)
        self.assertEqual(v.ATTENTION_SCHEMA,'fixed93-fullblock-attention-pv-reuse-observation-v1')
        self.assertEqual(v.ATTENTION_REUSE_DECLARATIONS,dict(
            normalization_evaluations_per_causal_key=1,probability_use_repeats=8,
            normalization_reuses_per_causal_key=7,observed_normalization_reuses=693504,
            scalar_schedule_changed=True,both_probability_domains_repeats_verified=True))

    def test_v1_plan_summary_and_contract_drift_reject_before_streams(self):
        old='original-algorithm-arrays-plus-true-events-v1'
        cases=[lambda f:f.plan.update(schema='fixed93-offline-container-plan-v1'),
            lambda f:f.plan.pop('evidence_contract'),lambda f:f.plan.update(evidence_contract=old),
            lambda f:f.plan.update(evidence_contract=True),
            lambda f:f.docs['attention'].update(schema='fixed93-fullblock-attention-observation-v1'),
            lambda f:f.docs['result'].update(evidence_contract=old),
            lambda f:f.docs['result'].pop('evidence_contract'),
            lambda f:f.docs['result']['wholeblock_observation'].update(evidence_contract=old),
            lambda f:f.docs['result']['wholeblock_observation'].pop('evidence_contract')]
        def all_contracts_drift(f):
            f.plan['evidence_contract']=old;f.docs['result']['evidence_contract']=old
            f.docs['result']['wholeblock_observation']['evidence_contract']=old
        for index,mutate in enumerate(cases+[all_contracts_drift]):
            with self.subTest(case=index),tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);mutate(f);f.save();self.reject_before_stream(f.verify)

    def test_pv_1_8_7_and_total_exact_types_reject_before_streams(self):
        fields={'normalization_evaluations_per_causal_key':1,'probability_use_repeats':8,
                'normalization_reuses_per_causal_key':7,'observed_normalization_reuses':693504}
        for key,expected in fields.items():
            for value in (expected-1,expected+1,float(expected),str(expected),True,False,None):
                with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as tmp:
                    f=Fixture(tmp);f.docs['attention'][key]=value;f.save();self.reject_before_stream(f.verify)
            with self.subTest(key=key,missing=True),tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);f.docs['attention'].pop(key);f.save();self.reject_before_stream(f.verify)
        for key in ('scalar_schedule_changed','both_probability_domains_repeats_verified'):
            for value in (False,1,'true',None):
                with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as tmp:
                    f=Fixture(tmp);f.docs['attention'][key]=value;f.save();self.reject_before_stream(f.verify)

    def test_embedded_summary_bool_cannot_hide_behind_python_dict_equality(self):
        f=self.fixture;f.docs['result']['observation']=copy.deepcopy(f.docs['attention'])
        f.docs['result']['observation']['normalization_evaluations_per_causal_key']=True
        raw=dump(f.docs['result']);(f.root/v.RECEIPTS['result']).write_bytes(raw)
        f.plan['receipts']['result']=pin(raw)
        f.plan_path.write_bytes(dump(f.plan));f.plan_sha=pin(dump(f.plan))['sha256']
        self.reject_before_stream(f.verify)

    def test_attention_v2_and_exp_v1_only_and_mixed_v1_rejected(self):
        for schemas in [('fixed93-attention-event-v2','fixed93-attention-exp-envelope-v1'),
                        ('fixed93-attention-exp-envelope-v1','fixed93-attention-event-v2')]:
            with self.subTest(accepted=schemas),tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);f.replace_stream('attention',wire('attention',attention_schemas=schemas));f.save()
                r=f.verify();self.assertEqual(r['streams']['attention']['records'],2)
                self.assertIs(r['fullblock_acceptance'],False)
        for schemas in [('fixed93-attention-event-v1',),
                        ('fixed93-attention-event-v2','fixed93-attention-event-v1'),
                        ('fixed93-attention-event-v1','fixed93-attention-exp-envelope-v1'),
                        ('fixed93-attention-event-v2','fixed93-attention-exp-envelope-v2')]:
            with self.subTest(rejected=schemas),tempfile.TemporaryDirectory() as tmp:
                f=Fixture(tmp);f.replace_stream('attention',wire('attention',attention_schemas=schemas));f.save()
                with self.assertRaisesRegex(v.Rejected,'Attention envelope role/schema/sequence'):f.verify()


if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_AS,(256<<20,)*2);resource.setrlimit(resource.RLIMIT_CPU,(15,)*2)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    tempfile.tempdir=str(HERE)
    def alarm(*_):raise TimeoutError('synthetic test wall budget')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,15)
    denied=[]
    def audit(event,args):
        if event in ('subprocess.Popen','os.system','ctypes.dlopen','socket.connect'):
            denied.append(event);raise RuntimeError('test forbids '+event)
    sys.addaudithook(audit)
    started=time.monotonic();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'scope':'SYNTHETIC_VERIFIER_TESTS_ONLY','tests':result.testsRun,
        'success':result.wasSuccessful(),'denied_attempts':denied,'elapsed_seconds':time.monotonic()-started,
        'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'cpu_affinity':sorted(os.sched_getaffinity(0)),'wall_limit_seconds':15,'address_space_limit_bytes':256<<20,
        'synthetic_only':True,'DUT_executed':False,'numerical_acceptance':False,
        'schedule_cache_correspondence_checked':False,'fullblock_acceptance':False},sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
