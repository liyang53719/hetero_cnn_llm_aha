"""SOURCE ONLY: compare two newly sealed successful M2 capture directories.

Root supplies the pinned original codec and representation decoder classes.
Nothing here imports DUT/native/oracles or reads an unsealed historical stream.
Every scalar, coordinate, tag, epoch, count and value byte is compared. Only the
explicit opaque-object fields below are exempt from cross-process equality;
their original values remain in both sealed streams and in ID_DIFFERENCES.jsonl.
This is behavioral observer equivalence, NOT independent numerical acceptance.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

OPAQUE = frozenset(('job_object','owner_object','matrix_object','scalar_object',
                    'fifo_object','request_object','result_object','done_object',
                    'actual_object_reference','adapter_reference','output_reference'))
MAX_RECORDS = 20000
MAX_DIFFERENCE_BYTES = 4*1024*1024
LONG_LIVED = frozenset(('job_object','owner_object','matrix_object','scalar_object'))
FIELD_SHAPES = {name:(12,2,2) for name in (
    'dot_raw','dot_bf16','scale_fp32','score_bf16','score_difference','exp_fp32','denominator_step')}
FIELD_SHAPES.update({name:(12,2,2,16) for name in ('packed_stripes','fold_before','fold_after')})
FIELD_SHAPES.update({name:(12,2,2,8) for name in ('probability_fp32','probability_bf16')})
FIELD_SHAPES.update(pv_key_raw=(12,2,2,8,16),normalizer=(12,2,3),
                    pv_final_raw=(12,2,128),pv_bf16=(12,2,128))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for raw in iter(lambda:f.read(65536), b''):
            h.update(raw)
    return dict(bytes=Path(path).stat().st_size,sha256=h.hexdigest())


def owned_file(root, relative, cap, exact=None):
    relative = Path(relative)
    need(not relative.is_absolute() and '..' not in relative.parts,'owned relative artifact path')
    p = root/relative
    need(p.resolve()==p and p.is_file() and not p.is_symlink() and p.is_relative_to(root),
         'missing/aliased owned artifact: '+str(p))
    size=p.stat().st_size
    need(size<=cap and (exact is None or size==exact),'artifact byte cap/extent: '+str(p))
    return p


def decode_attention(path, *, Decoder, Limits, limits, decode_exp, expected_seal):
    result = []
    with Path(path).open('rb') as f:
        decoder = Decoder(f,Limits(**limits))
        for record in decoder.records():
            need(len(result)<MAX_RECORDS and record.kind == 8,'attention record count/kind')
            if record.metadata.get('schema') == 'fixed93-attention-exp-envelope-v1':
                meta,raw = decode_exp(record.data,record.metadata)
                result.append(dict(metadata=meta,typed_words_hex=raw.hex()))
            else:
                need(record.metadata.get('schema') == 'fixed93-attention-event-v2','attention event schema')
                value = json.loads(record.data)
                need(canonical(value)==record.data,'noncanonical attention event')
                result.append(dict(metadata=record.metadata,value=value))
        need(decoder.seal is not None and asdict(decoder.seal)==expected_seal,'attention EOF seal differs')
    return result


def decode_whole(path, *, Decoder, Limits, limits, TokenDecoder, OperandDecoder, expected_seal):
    result, semantic = [], 0
    token, operands = TokenDecoder(), OperandDecoder()
    with Path(path).open('rb') as f:
        decoder = Decoder(f,Limits(**limits))
        for record in decoder.records():
            row = token.feed(record)
            if row is None:
                continue
            _,meta,raw = row
            need(len(result)<MAX_RECORDS,'wholeblock logical record count')
            if meta['domain'] == 'operand_definition':
                operands.definition(raw,meta)
                result.append(dict(metadata=meta,typed_words_hex=raw.hex()))
            elif meta['domain'] == 'semantic':
                value = operands.semantic(raw,meta)
                semantic += 1
                result.append(dict(metadata=meta,value=value))
            else:
                # M2-only scope has no Dense, physical, SiLU or public stream.
                raise ValueError('unexpected non-M2 wholeblock domain: '+meta['domain'])
        need(decoder.seal is not None and asdict(decoder.seal)==expected_seal,'wholeblock EOF seal differs')
        token.finish(decoder.seal)
        operands.finish(semantic)
    return result


def compare_pair(old, new, output, *, Decoder, Limits, decode_exp, TokenDecoder, OperandDecoder,
                 attention_limits, whole_limits):
    """Run only after both current-process outputs have successful finite seals."""
    old,new,output = Path(old),Path(new),Path(output)
    need(old!=new and old.is_dir() and new.is_dir() and output.is_dir(),'pair paths')
    need(all(p.is_absolute() and p.resolve()==p and not p.is_symlink() for p in (old,new,output)),
         'absolute nonaliased pair paths')
    reports = [json.loads(owned_file(p,'M2_CASE.json',262144).read_bytes()) for p in (old,new)]
    summaries = [json.loads(owned_file(p,'attention/summary.json',1048576).read_bytes()) for p in (old,new)]
    for report,summary in zip(reports,summaries):
        need(report['status']=='ACTUAL_SUCCESS_M2_CAPTURED_PENDING_PAIR_COMPARISON' and
             report['scope']=='INCOMPLETE_WHOLEBLOCK' and report['m']==2 and
             report['wholeblock']['status']=='SEALED_ACTUAL_M2_SUBCHAIN_ONLY' and
             summary['complete_observation'] is True,'successful newly sealed M2 pair required')
        need(set(summary['fields'])==set(FIELD_SHAPES),'exact sixteen-field inventory')
        for name,shape in FIELD_SHAPES.items():
            count=1
            for extent in shape: count*=extent
            need(summary['fields'][name]['shape']==list(shape) and
                 summary['fields'][name]['total_words']==count,'fixed M2 field shape/extent')
    need(reports[0]['variant']=='old' and reports[1]['variant']=='new','old/new arm order')
    raw_differences, semantic_differences, examples, volatile = Counter(), Counter(), [], Counter()
    raw_pair_identities, checked_fields = {}, []
    difference_bytes = 0
    long_forward, long_reverse = {}, {}
    with (output/'ID_DIFFERENCES.jsonl').open('xb') as idlog:
        def compare(a,b,path):
            nonlocal difference_bytes
            if type(a) is not type(b):
                mismatch(path,a,b); return
            if type(a) is dict:
                if a.keys()!=b.keys():
                    mismatch(path+'.keys',sorted(a),sorted(b)); return
                for key in sorted(a):
                    if key in OPAQUE:
                        need((a[key] is None or type(a[key]) is int) and
                             (b[key] is None or type(b[key]) is int),'opaque identity type changed')
                        if a[key] is not None and b[key] is not None:
                            if key in LONG_LIVED:
                                if ((a[key] in long_forward and long_forward[a[key]]!=b[key]) or
                                    (b[key] in long_reverse and long_reverse[b[key]]!=a[key])):
                                    mismatch(path+'.'+key+'.long_lived_binding',a[key],b[key])
                                long_forward.setdefault(a[key],b[key])
                                long_reverse.setdefault(b[key],a[key])
                            elif ((a[key] in long_forward and long_forward[a[key]]!=b[key]) or
                                  (b[key] in long_reverse and long_reverse[b[key]]!=a[key])):
                                mismatch(path+'.'+key+'.known_long_lived_binding',a[key],b[key])
                        if a[key] != b[key]:
                            # None-vs-object is semantic, never an opaque allowance.
                            if (a[key] is None)!=(b[key] is None):
                                mismatch(path+'.'+key,a[key],b[key]); continue
                            row=canonical(dict(path=path+'.'+key,old=a[key],new=b[key]))+b'\n'
                            difference_bytes+=len(row)
                            need(difference_bytes<=MAX_DIFFERENCE_BYTES,'identity delta output budget')
                            idlog.write(row);volatile[key]+=1
                    else:
                        compare(a[key],b[key],path+'.'+key)
            elif type(a) is list:
                if len(a)!=len(b):
                    mismatch(path+'.length',len(a),len(b)); return
                for i,(x,y) in enumerate(zip(a,b)):
                    compare(x,y,path+'['+str(i)+']')
            elif a!=b:
                mismatch(path,a,b)
        def mismatch(path,a,b):
            semantic_differences[path.split('[',1)[0]]+=1
            if len(examples)<32:
                examples.append(dict(path=path,old=a,new=b))
        compare(reports[0]['inputs'],reports[1]['inputs'],'inputs')
        compare(reports[0]['wholeblock']['counts'],reports[1]['wholeblock']['counts'],'whole_counts')
        compare(reports[0]['wholeblock']['fence'],reports[1]['wholeblock']['fence'],'scope_fence')
        for key in ('job','terminal','accepted_retirement','fields','event_counts','event_count',
                    'observed_normalization_reuses','normalization_evaluations_per_causal_key',
                    'probability_use_repeats','normalization_reuses_per_causal_key'):
            compare(summaries[0][key],summaries[1][key],'attention_summary.'+key)
        compare(json.loads(owned_file(old,'actual_transport.json',1048576).read_bytes()),
                json.loads(owned_file(new,'actual_transport.json',1048576).read_bytes()),'actual_transport')
        need(summaries[0]['fields'].keys()==summaries[1]['fields'].keys(),'field inventory mismatch')
        names=['actual_output.u32le']+[str(Path('attention')/(name+suffix))
            for name in sorted(FIELD_SHAPES) for suffix in ('.u32le','.presence')]
        for relative in names:
            if relative=='actual_output.u32le':
                extent=12288
            else:
                name,suffix=Path(relative).name.rsplit('.',1)
                extent=1
                for size in FIELD_SHAPES[name]: extent*=size
                if suffix=='u32le': extent*=4
            paths=[owned_file(p,relative,extent,extent) for p in (old,new)]
            a,b=[p.read_bytes() for p in paths]
            checked_fields.append(relative)
            raw_pair_identities[relative]=[file_hash(p/relative) for p in (old,new)]
            if relative == 'actual_output.u32le':
                need(raw_pair_identities[relative] == [r['output'] for r in reports],
                     'accepted output bytes changed after case seal')
            else:
                name, suffix = Path(relative).name.rsplit('.',1)
                key = 'raw_sha256' if suffix == 'u32le' else 'frequency_sha256'
                need(all(raw_pair_identities[relative][i]['sha256']==summaries[i]['fields'][name][key]
                         for i in range(2)), 'field/presence bytes changed after observation seal')
            if a!=b:
                mismatch('field.'+relative,hashlib.sha256(a).hexdigest(),hashlib.sha256(b).hexdigest())
        for domain,relative,decode in (
            ('attention','attention/attention-events.lec1',lambda p,i:decode_attention(p,Decoder=Decoder,Limits=Limits,
                limits=attention_limits,decode_exp=decode_exp,expected_seal=summaries[i]['event_codec_seal'])),
            ('wholeblock','wholeblock_events.lec1',lambda p,i:decode_whole(p,Decoder=Decoder,Limits=Limits,
                limits=whole_limits,TokenDecoder=TokenDecoder,OperandDecoder=OperandDecoder,
                expected_seal=reports[i]['wholeblock']['codec_seal']))):
            paths=[owned_file(p,relative,16777216 if domain=='attention' else 20971520) for p in (old,new)]
            raw_pair_identities[relative]=[file_hash(p) for p in paths]
            if domain=='wholeblock':
                need(raw_pair_identities[relative]==[r['wholeblock']['artifact'] for r in reports],
                     'sealed wholeblock bytes changed')
            a,b=decode(paths[0],0),decode(paths[1],1)
            raw_differences[domain+'_record_count_old']=len(a)
            raw_differences[domain+'_record_count_new']=len(b)
            if len(a)!=len(b):
                mismatch(domain+'.length',len(a),len(b))
            for i,(x,y) in enumerate(zip(a,b)):
                if x!=y:
                    raw_differences[domain+'_raw_logical_records_different']+=1
                compare(x,y,domain+'['+str(i)+']')
    result=dict(status='MATCHED_SUCCESS_M2_OBSERVER_EQUIVALENCE_ONLY' if not semantic_differences else 'M2_PAIR_DIFFERENT',
        scope='INCOMPLETE_WHOLEBLOCK',fullblock_pass=False,M128_execution=False,numerical_acceptance=False,
        raw_pair_identities=raw_pair_identities,all_field_and_presence_files_compared=checked_fields,
        decoded_record_differences=dict(raw_differences),semantic_differences=dict(semantic_differences),
        first_semantic_differences=examples,opaque_differences=dict(volatile),
        opaque_allowlist=sorted(OPAQUE),epoch_normalization=False,tag_normalization=False,
        long_lived_identity_pairs=[dict(old=a,new=b) for a,b in sorted(long_forward.items())],
        short_lived_cross_run_alias_equivalence_proven=False,
        excluded_report_keys=['timings','variant','observer_identity','instrumentation_sha256'],
        exclusions_reason='separately retained execution duration and observer source identity, not semantic fields',
        old_timings=reports[0]['timings'],new_timings=reports[1]['timings'],
        identity_delta_file=file_hash(output/'ID_DIFFERENCES.jsonl'))
    with (output/'PAIR_DIFF.json').open('xb') as f:
        f.write(json.dumps(result,indent=2,sort_keys=True).encode()+b'\n')
    return result
