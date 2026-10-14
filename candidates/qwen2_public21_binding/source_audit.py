"""Source-preservation checks; no semantic, RTL or arithmetic acceptance."""
import re
PREFIX="chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
def require(ok,msg):
    if not ok:raise ValueError(msg)

def source_audit(before_text,manifest,source):
    text=lambda name:(source/PREFIX/name).read_text()
    kernel=text('QwenOwnerProtocol.scala');core=text('Qwen2Block.scala');host=text('HostBlockCommands.scala')
    for item in manifest['current_feature_preservation']:
        before=before_text[item['path']].decode().splitlines()
        after=(source/item['path']).read_text().splitlines()
        adaptations={change['current']:change['postimage'] for change in item['explicit_line_adaptations']}
        require(len(item['current_added_line_inventory'])==item['current_added_lines'],'current feature inventory count')
        for line in item['current_added_line_inventory']:
            require(line in before and adaptations.get(line,line) in after,'current feature line lost: '+line)
        for change in item['explicit_line_adaptations']:
            require(change['current'] in before and change['postimage'] in after,'current feature adaptation missing')
    for path in manifest['unchanged_current_new_sources']:
        require(manifest['before_sha256'][path]==manifest['post_sha256'][path],'current H2048/loan source modified')
    for fragment in (
        'enableH2048RmsBorrower:Boolean=false,enableTransposedDense:Boolean=false',
        'externalElementwiseLoan=enableH2048RmsBorrower,numericPolicy=numericPolicy',
        'val rmsNorm:Seq[GdnRmsNormOwnerPort]=if(enableH2048RmsBorrower)',
        '&& !rmsBorrowerUnavailable',
        'val responseSelected=if(enableH2048RmsBorrower && i==8)(!active || mode===8.U)',
        'val selected=if(enableH2048RmsBorrower && i==8)(!active || mode===8.U)',
        'val materializeDenseOutput=Bool()',
        'numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0'):
        require(fragment in kernel,'kernel boundary missing: '+fragment)
    require('externalElementwiseLoan:Boolean=false,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0' in core,'loan/default policy boundary missing')
    require(core.count('new ElementwiseRegisterLoan(elemCfg,elemSram)')==1,'loan lender multiplicity')
    require(core.count('new ElementwiseMemoryEngine(elemCfg,elemSram,numericPolicy=numericPolicy)')==1,'ordinary engine multiplicity')
    require('require(!externalElementwiseLoan || !officialBf16,' in core,'unsupported policy/loan combination guard')
    require('!scalarExternalExclusive && !elementwiseExternalExclusive' in core,'current loan admission missing')
    for fragment in ('enableTransposedDown:Boolean=false,enableResidentFfn:Boolean=false,numericPolicy:',
                     'bound.materializeDenseOutput:=officialMaterializeDense && dense',
                     'j.materializeDenseOutput:=officialMaterializeDense',
                     '!officialBf16.B || l.commands===21.U'):
        require(fragment in host,'actual parser boundary missing: '+fragment)
    role=re.search(r'val officialMaterializeDense=officialBf16.B && \(([^\n]+)\)',host)
    require(role is not None and tuple(map(int,re.findall(r'pc===(\d+).U',role[1])))==(13,16,17,19),'Dense materialization role set')
    for path in ('DenseTileSumBridge.scala','DenseBlockReductionCoordinator.scala'):
        rel='candidates/qwen2_resident_matrix/dense_block_reduce/'+path
        require(manifest['before_sha256'][rel]==manifest['post_sha256'][rel],'reduction source copy drift')
    require('new DenseBlockReductionCoordinator' not in kernel,'unexpected kernel integration scope')
    return dict(current_h2048_loan_sources_byte_identical=True,current_added_feature_lines=92,
                current_added_feature_lines_literal_preserved=84,explicit_feature_line_adaptations=8,
                conflict_resolutions=9,default_policy='LegacyV0',h2048_default=False,
                unsupported_direct_core_official_plus_loan_rejected=True,
                actual_host_parser_overlay_present=True,materialize_dense_pcs=[13,16,17,19],
                dense_reduction_coordinator_copied=True,production_kernel_reduction_connection=False,
                no_historical_kernel_file_copied=True,source_only=True,
                compiled=False,elaborated=False,rtl_generated=False,numerical_acceptance=False)
