"""Hash-verified adapter for the new auxiliary producer's completed outputs."""
from pathlib import Path
from . import builder as b

EXECUTED_FROZEN_SHA='f75d9775e26ee12478262519946275b5c168591c17a25d9b8144d7cd235406c0'

def verify_source_provenance(frozen,frozen_sha256):
    """Bind old receipts to exact retained source, never relabel current wrappers."""
    preserved=None;locations={};used=False
    for relative,digest in frozen['source_sha256'].items():
        current=b.ROOT/relative
        if current.is_file() and b.file_sha(current)==digest:
            locations[relative]=str(current);continue
        b.require(frozen_sha256==EXECUTED_FROZEN_SHA,'independent reference frozen source drift')
        if preserved is None:
            preserved=b.frozen_json(b.HERE/'executed_m16_v1/FROZEN.json',EXECUTED_FROZEN_SHA)
            b.require(preserved==frozen,'preserved execution receipt differs')
        b.require(relative in preserved['source_sha256'] and preserved['source_sha256'][relative]==digest,
                  'preserved execution source identity differs')
        name=Path(relative).name+('.txt' if relative.endswith('.py') else '')
        snapshot=b.HERE/'executed_m16_v1'/name
        b.require(b.file_sha(snapshot)==digest,'preserved execution source bytes differ')
        locations[relative]=str(snapshot);used=True
    return dict(source_locations=locations,preserved_execution_source_used=used)


def reference_spec(directory, result_sha256):
    """Return comparison-only artifacts; never execute or read actual outputs."""
    directory=Path(directory).resolve()
    result=b.frozen_json(directory/'RESULT.json',result_sha256)
    b.require(result['status']=='COMPLETE_INDEPENDENT_REFERENCE_WITH_ARCHIVED_DIAGNOSTIC'
              and result['version']==b.VERSION and result['rows']==16
              and result['full_reference_executed'] and not result['actual_chain_executed']
              and not result['new_official_forward_executed'] and not result['rtl_executed']
              and not result['implementation_acceptance'] and not result['native_acceptance'],
              'incomplete or incompatible independent reference receipt')
    frozen=b.frozen_json(directory/'FROZEN.json',result['frozen_sha256'])
    prepared=b.frozen_json(directory/'PREPARED.json',result['prepared_sha256'])
    b.require(frozen['prepared_sha256']==result['prepared_sha256'] and
              prepared['version']==frozen['version']==b.VERSION,'reference provenance mismatch')
    b.require(prepared['source_sha256'].items()<=frozen['source_sha256'].items(),
              'prepared sources differ from execution freeze')
    provenance=verify_source_provenance(frozen,result['frozen_sha256'])
    archive,top,cold=b.archive_context(16,archive_directory=prepared['old_archive']['directory'])
    original,_=b.regenerate_original()
    b.verify_transform(original,(directory/'candidate.cpp').read_bytes(),(b.ROOT/b.PROFILE_REL).read_bytes())
    b.require(b.file_sha(directory/'candidate.cpp')==frozen['candidate_cpp_sha256'] and
              b.file_sha(directory/'block_layout.h')==frozen['header_sha256']==b.HEADER_SHA and
              b.file_sha(directory/'candidate')==result['binary_sha256'],'reference build artifact drift')
    b.require(b.file_sha(prepared['readonly_input']['path'])==cold['inputs']['readonly_sha256']==
              prepared['readonly_input']['sha256'],'reference readonly input drift')
    b.require(result['comparison']['producer_outputs_sealed_before_official_read'] and
              not result['comparison']['full_29_node_acceptance'],'reference comparison scope differs')
    artifacts=[]
    for name,record in result['sealed_outputs'].items():
        b.require(Path(name).name==name,'invalid producer artifact path')
        path=directory/'raw_stages'/name
        b.require(not path.is_symlink() and path.stat().st_size==record['bytes'] and
                  b.file_sha(path)==record['sha256'],'independent producer output drift: '+name)
        artifacts.append(dict(path='raw_stages/'+name,**record))
    return dict(schema=1,version=b.VERSION,directory=str(directory),rows=16,past_tokens=0,
                result_sha256=result_sha256,frozen_sha256=result['frozen_sha256'],
                candidate_cpp_sha256=frozen['candidate_cpp_sha256'],binary_sha256=result['binary_sha256'],
                header_sha256=frozen['header_sha256'],profile_sha256=prepared['profile_sha256'],
                readonly_input=prepared['readonly_input'],artifacts=artifacts,source_provenance=provenance,
                threshold_policy=prepared['thresholds'],old_FAIL_preserved=result['old_FAIL_preserved'],
                role='Independent new-arithmetic producer auxiliary; official target remains separately authoritative',
                old_sequential_reference_is_additional_gate=False,actual_chain_executed=False,
                actual_vs_this_reference_not_yet_checked=True,native_acceptance=False)
