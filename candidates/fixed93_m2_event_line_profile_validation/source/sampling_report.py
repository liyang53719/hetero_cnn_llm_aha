"""Strict safety/accounting gate; sampling quality never grants model PASS."""
CAPS={'hz':100,'max_samples':12000,'max_stacks':4096,'max_depth':48,'max_codes':2048}
LOSSES=('overflow_samples','overflow_stacks','overflow_codes','truncated_stacks','reentrant_dropped')

def classify(report):
    def need(ok,message):
        if not ok: raise ValueError(message)
    need(type(report) is dict and report.get('schema')=='fixed93-main-loop-sigprof-report-v1' and
         report.get('diagnostic_only') is True and report.get('speed_measurement') is False,
         'exact diagnostic report schema')
    need(report.get('restored') is True and report.get('active') is False,
         'unsafe or active SIGPROF state cannot pass main evidence')
    need(all(type(report.get(k)) is int and report[k]==v for k,v in CAPS.items()),'sampling cap drift')
    need(report.get('status') in ('PASS_BOUNDED_MAIN_LOOP_SAMPLING','INCOMPLETE_SAMPLING'), 'sampler status')
    for key in (*LOSSES,'samples','unique_stacks','pending_drained'):
        need(type(report.get(key)) is int and report[key]>=0,'invalid sampling counter '+key)
    need(report['samples']<=12000 and report['unique_stacks']<=4096 and
         type(report.get('stacks')) is list and len(report['stacks'])==report['unique_stacks'] and
         type(report.get('code_table')) is list and len(report['code_table'])<=2048,'bounded sample stores')
    stored=0
    for row in report['stacks']:
        need(type(row) is dict and type(row.get('count')) is int and row['count']>0 and
             type(row.get('stack')) is list and len(row['stack'])<=48,'invalid stack row')
        for item in row['stack']:
            need(type(item) is list and len(item)==2 and all(type(x) is int for x in item) and
                 0<=item[0]<len(report['code_table']) and item[1]>=0,'invalid sampled code index/line')
        stored+=row['count']
    need(stored+report['overflow_stacks']+report['overflow_codes']==report['samples'], 'sample count accounting')
    return 'PARTIAL' if report['samples']==0 or any(report[k] for k in LOSSES) else 'COMPLETE_BOUNDED_SAMPLES'
