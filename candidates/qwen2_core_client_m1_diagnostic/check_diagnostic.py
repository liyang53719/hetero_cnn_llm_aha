"""Read-only bounded thread-dump classification. Never grants behavior acceptance."""
import hashlib
import json
from pathlib import Path
import re
import stat

STATUS='DIAGNOSTIC_LOG_CLASSIFIED_NO_ACCEPTANCE'
HEADER=re.compile(r'^Full thread dump .+Server VM .+:\s*$')
END=re.compile(r'^JNI global refs: \d+(?:, weak refs: \d+)?\s*$')
THREAD=re.compile(r'^"([^"\r\n]{1,256})"(?:\s|$)')

def need(ok,why):
    if not ok:raise ValueError(why)

def classify(raw,expectation,sampling_records):
    e=expectation
    need(e['schema']=='qwen2-m1-stack-diagnostic-v1','diagnostic schema')
    need(len(raw)<=e['max_log_bytes'],'bounded diagnostic log')
    text=raw.decode('utf8');lines=text.splitlines(keepends=True)
    need(len(lines)<=e['max_lines'],'bounded diagnostic lines')
    need(all(len(x.encode('utf8'))<=e['max_line_bytes'] for x in lines),'bounded diagnostic line length')
    need(type(sampling_records) is list and len(sampling_records)<=2,'at most two diagnostic sampling records')
    need(len(json.dumps(sampling_records,allow_nan=False).encode())<=65536,'bounded sampling metadata')
    headers=[i for i,x in enumerate(lines) if HEADER.fullmatch(x.rstrip('\r\n'))]
    need(len(headers)<=2,'unexpected extra thread dump headers')
    offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line.encode('utf8')))
    dumps=[]
    for number,start in enumerate(headers):
        stop=headers[number+1] if number+1<len(headers) else len(lines)
        ends=[i for i in range(start+1,stop) if END.fullmatch(lines[i].rstrip('\r\n'))]
        need(len(ends)<=1,'ambiguous dump terminator')
        end=ends[0]+1 if ends else stop
        threads=[];current=None
        for i in range(start+1,end):
            line=lines[i].rstrip('\r\n');m=THREAD.match(line)
            if m:
                need(len(threads)<256,'bounded dump threads')
                current=dict(name=m[1],header=line,state=None,first_frames=[])
                threads.append(current)
            elif current is not None:
                if line.lstrip().startswith('java.lang.Thread.State:'):current['state']=line.strip()
                elif line.lstrip().startswith('at ') and len(current['first_frames'])<8:current['first_frames'].append(line.strip())
        lo,hi=offsets[start],offsets[end]
        complete=bool(ends and threads)
        dumps.append(dict(index=number,line_start=start+1,line_end=end,byte_start=lo,byte_end=hi,
          sha256=hashlib.sha256(raw[lo:hi]).hexdigest(),thread_record_count=len(threads),threads=threads,
          has_jni_table_terminator=bool(ends),classification='COMPLETE_LOOKING_THREAD_TEXT' if complete else 'PARTIAL_THREAD_TEXT',
          not_a_full_jvm_dump_grammar_proof=True,heap_summary_not_required_for_thread_text=True))
    sent=sum(x.get('sent') is True for x in sampling_records)
    unconfirmed=sum(x.get('send_started') is True and x.get('sent') is not True for x in sampling_records)
    complete=sum(x['classification']=='COMPLETE_LOOKING_THREAD_TEXT' for x in dumps)
    partial=len(dumps)-complete
    return dict(status=STATUS,log_bytes=len(raw),log_sha256=hashlib.sha256(raw).hexdigest(),
       sampling_records=sampling_records,send_return_success_record_count=sent,sent_request_count=sent,
       send_started_delivery_not_confirmed_count=unconfirmed,
       sent_false_is_not_proof_of_no_signal=True,dump_header_count=len(headers),
       complete_looking_thread_text_count=complete,partial_thread_text_count=partial,
       missing_dump_observation=max(0,sent-len(headers)),unexpected_dump_without_matching_sent_count=max(0,len(headers)-sent),
       requests_and_dumps_not_one_to_one=True,dumps=dumps,
       phase_observations=dict(class_origin_lines=sum(x.startswith('CORE_CLASS_ORIGIN ') for x in lines),
         body_ready_lines=sum(x.startswith('CORE_SIM_READY ') for x in lines),
         obs_lines=sum(x.startswith('OBS ') for x in lines),case_pass_lines=sum(x.startswith('CORE_CASE_PASS ') for x in lines),
         no_ready_does_not_prove_zero_clocks=True),
       scope=dict(diagnostic_only=True,hardware_behavior_acceptance=False,numerical_acceptance=False,
         fullblock_accepted=False,matrix_mac_utilization=None,hotspot_function_not_automatically_inferred=True,
         sent_is_not_dump_success=True,stack_samples_are_not_cpu_profile=True))

def check(root,expectation,sampling_records):
    p=Path(root)/'worker.log';s=p.lstat()
    need(stat.S_ISREG(s.st_mode) and not p.is_symlink(),'regular diagnostic log')
    need(s.st_size<=expectation['max_log_bytes'],'bounded diagnostic log file')
    raw=p.read_bytes();after=p.lstat()
    need((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'diagnostic log stable after cleanup')
    return classify(raw,expectation,sampling_records)
