"""Cross-check published scope and source identities, not source behavior or DUT."""
from pathlib import Path
from collections import Counter
import hashlib,json

def need(x,m):
    if not x:raise ValueError(m)

def verify(root):
    def read(n):return json.loads((root/n).read_text())
    a=read('ACTUAL_FACTS.json');c=read('CLASS_LINEAGE.json');s=read('SOURCE_PINS.json');r=read('REPRODUCTION.json')
    need(a['r1']['exit_code']==1 and a['r1']['classes']==0,'R1 failure')
    v=a['r2'];need(v['exit_code']==0 and v['compiled_sources']==7 and v['new_classes']==32 and v['new_class_bytes']==212672,'R2 scope')
    need(v['preflight_checks']==v['postflight_checks']==1486 and v['baseline_unchanged'] is True,'pin equality')
    need(v['log_sha256']==hashlib.sha256(b'').hexdigest(),'empty log')
    need(v['baseline_classes']==1001 and v['baseline_bytes']==18628292,'baseline')
    for k in ['capture_executed','fma_emission_executed','sv_linked','dut_executed','structural_pass_inherited']:
        need(a[k] is False,k)
    need(a['full_m128_numeric_pass']==a['full_m128_rtl_pass']==0 and a['profile_count']==5,'0/5')
    need(a['cpp']['simulation_branch_compiled'] is False and a['cpp']['generated_vhost_header_used'] is False,'uncompiled DUT branch')
    need(a['cpp']['python_crosscheck_probes']==[96,106,90,143,126] and sum(a['cpp']['python_crosscheck_probes'])==a['cpp']['crosscheck_total']==561,'byte probes')
    b=c['baseline'];need(b['count']==1001 and b['hardware_source_count']==31 and b['hardware_class_count']==159 and b['historical_other_classes']==842 and b['requires_parent'] is True and b['unchanged'] is True,'baseline ancestry')
    need(c['new_tool_sources']==7 and c['new_tool_classes']==32 and c['new_tool_class_bytes']==212672 and c['hardware_recompiled'] is False and c['no_shadow'] is True and c['software_functional_model_absent'] is True,'tool lineage')
    classes=c['classes'];need(len(classes)==32 and len({x['relative'] for x in classes})==32 and sum(x['bytes'] for x in classes)==212672,'class inventory')
    expected={'HostDenseAccMemoryLowering.scala':9,'RetainedServicePhaseObserver.scala':2,'RetainedBackendCircuitGate.scala':2,'RetainedEndpointPortContract.scala':2,'HostMatrixResultFifoMemoryLowering.scala':3,'HostCompiledLatestCapture.scala':11,'PhysicalFmaStageLibrary.scala':3}
    need(dict(Counter(x['source_file'] for x in classes))==expected,'seven source families')
    compiled=[x for x in s['files'] if x['actual_r2_compiler_input']]
    need(len(compiled)==7 and sum(x['projection']=='exact' for x in compiled)==6,'six exact plus template')
    need(s['hardware_sources_unchanged']==31 and s['hardware_parent_missing_sources']==5,'parent gaps')
    for x in s['files']:
        data=(root/x['path']).read_bytes();p={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        need(p==x['public'],'public source pin')
        if x['projection']=='exact':need(p==x['original'],'exact original pin')
        else:
            need(x['path']=='source/HostCompiledLatestCapture.scala' and x['projection']=='one_literal_redacted_uncompiled_template','template scope')
            need(data.count(b'"REQUIRES_PARENT_ORIGINAL_HIGH"')==1 and p!=x['original'],'template distinction')
    need(r['actual_argv_tokens']==23 and len(r['argv_template'])==23 and r['argv_template'][16]=='{ORIGINAL_CAPTURE}','recipe template')
    need(r['tool_pin_counts']=={'sources':38,'dependencies':106,'jdk_tool_pins':314,'baseline_classes':1001,'extra_pins':18},'tool pins')
    need(r['abi']['static_input_widths']==24 and r['abi']['physical_endpoint_ports']==45 and r['abi']['functional_model_body_required'] is False,'ABI metadata only')
    return {'status':'SUMMARY_AND_SOURCE_IDENTITY_ONLY_NOT_DUT','source_files':len(s['files']),'classes':32,'compiled_sources':7,'numeric_rtl':'0/5'}

if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parent)))
