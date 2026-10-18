"""Host93 fixed emitted-SV lexical structure only. No SV elaboration or behavior proof.
Raw input is supplied by the reviewed wrapper; this module never opens the SV.
Only observed ANSI headers, wire/reg/assign, always-begin/end, named direct
instances, and SYNTHESIS assertion guards are admitted. Datapath expressions
and procedural semantics remain opaque except 30 fixed binary concat initializers. Unknown structural forms fail closed.
"""
import collections
import hashlib
import re

MAX_BYTES = 128 * 1024 * 1024
MAX_DEFINITIONS = 768
MAX_PATHS = 20000
MAX_DEPTH = 128
MAX_STATEMENT = 2 * 1024 * 1024
# Only the 17 double-packed wire dimension pairs observed in this fixed SV.
DOUBLE_PACKED_WIRE_SHAPES = {(31,7), (3,23), (15,127), (7,31), (3,2), (3,511), (15,63), (15,31), (255,31), (3,7), (3,10), (3,31), (3,15), (15,15), (15,255), (7,63), (15,511)}
EXPECTED_SHA256 = '2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'
EXPECTED_BYTES = 76366612
DOUBLE_PACKED_WIRE_MODULES = {'HostBlockCommands','BlockScalarFloat','SharedL2Fabric','SharedL2Fabric_1','ElementwiseMemoryEngine','Qwen2ContinuousBlock','TransposedDownDenseBanks','TransposedDenseDownOwner','RetainedIdmaWeightBurstAdapter'}
ID = r'[A-Za-z_$][A-Za-z0-9_$]*'

HOST_PORTS = {'clock': ['input', 1], 'io_axi_ar_bits_addr': ['output', 64], 'io_axi_ar_bits_burst': ['output', 2], 'io_axi_ar_bits_id': ['output', 8], 'io_axi_ar_bits_len': ['output', 8], 'io_axi_ar_bits_size': ['output', 3], 'io_axi_ar_ready': ['input', 1], 'io_axi_ar_valid': ['output', 1], 'io_axi_aw_bits_addr': ['output', 64], 'io_axi_aw_bits_burst': ['output', 2], 'io_axi_aw_bits_id': ['output', 8], 'io_axi_aw_bits_len': ['output', 8], 'io_axi_aw_bits_size': ['output', 3], 'io_axi_aw_ready': ['input', 1], 'io_axi_aw_valid': ['output', 1], 'io_axi_b_bits_id': ['input', 8], 'io_axi_b_bits_resp': ['input', 2], 'io_axi_b_ready': ['output', 1], 'io_axi_b_valid': ['input', 1], 'io_axi_r_bits_data': ['input', 512], 'io_axi_r_bits_id': ['input', 8], 'io_axi_r_bits_last': ['input', 1], 'io_axi_r_bits_resp': ['input', 2], 'io_axi_r_ready': ['output', 1], 'io_axi_r_valid': ['input', 1], 'io_axi_w_bits_data': ['output', 512], 'io_axi_w_bits_last': ['output', 1], 'io_axi_w_bits_strb': ['output', 64], 'io_axi_w_ready': ['input', 1], 'io_axi_w_valid': ['output', 1], 'io_completion_bits': ['output', 56], 'io_completion_ready': ['input', 1], 'io_completion_valid': ['output', 1], 'io_executedMacs': ['output', 64], 'io_idmaCacheHits': ['output', 64], 'io_idmaReadBeats': ['output', 64], 'io_idmaReadBursts': ['output', 64], 'io_idmaStreamedBeats': ['output', 64], 'io_idmaStreamedWriteBeats': ['output', 64], 'io_idmaTransfers': ['output', 64], 'io_issuedJobs': ['output', 16], 'io_launch_bits_commandBase': ['input', 64], 'io_launch_bits_commandLimit': ['input', 64], 'io_launch_bits_commands': ['input', 16], 'io_launch_bits_descriptorBase': ['input', 64], 'io_launch_bits_descriptorLimit': ['input', 64], 'io_launch_bits_descriptors': ['input', 25], 'io_launch_bits_epoch': ['input', 16], 'io_launch_bits_regions_0_base': ['input', 64], 'io_launch_bits_regions_0_limit': ['input', 64], 'io_launch_bits_regions_0_read': ['input', 1], 'io_launch_bits_regions_0_write': ['input', 1], 'io_launch_bits_regions_1_base': ['input', 64], 'io_launch_bits_regions_1_limit': ['input', 64], 'io_launch_bits_regions_1_read': ['input', 1], 'io_launch_bits_regions_1_write': ['input', 1], 'io_launch_bits_regions_2_base': ['input', 64], 'io_launch_bits_regions_2_limit': ['input', 64], 'io_launch_bits_regions_2_read': ['input', 1], 'io_launch_bits_regions_2_write': ['input', 1], 'io_launch_bits_regions_3_base': ['input', 64], 'io_launch_bits_regions_3_limit': ['input', 64], 'io_launch_bits_regions_3_read': ['input', 1], 'io_launch_bits_regions_3_write': ['input', 1], 'io_launch_ready': ['output', 1], 'io_launch_valid': ['input', 1], 'io_memoryAccepted_0': ['output', 64], 'io_memoryAccepted_1': ['output', 64], 'io_memoryReturned_0': ['output', 64], 'io_memoryReturned_1': ['output', 64], 'io_pc': ['output', 16], 'io_pipelineIssues': ['output', 64], 'io_pipelineStalls': ['output', 64], 'io_resetRequired': ['output', 1], 'io_result_bits_completed': ['output', 16], 'io_result_bits_epoch': ['output', 16], 'io_result_bits_failedPc': ['output', 16], 'io_result_bits_status': ['output', 8], 'io_result_ready': ['input', 1], 'io_result_valid': ['output', 1], 'io_usefulMacs': ['output', 64], 'io_writeBytes': ['output', 64], 'reset': ['input', 1]}
EXPECTED_PATHS = {'cmd': 'HostBlockCommands', 'cmd.reader': 'Record128Reader', 'cmd.tensor': 'TypedTensorReader', 'dma': 'RetainedIdmaWeightBurstAdapter', 'dma.backend': 'idma_backend_rw_axi_flat_wrap', 'hub': 'SharedMemoryArbiter', 'owner': 'QwenOwnerKernel', 'owner.core': 'Qwen2ContinuousBlock', 'owner.qkvRouter': 'Public21QkvReductionRouter', 'owner.resident': 'FfnResidentCoordinator', 'owner.resident.bridge': 'FfnTileSiluBridge', 'owner.silu': 'ScheduledSiluOwner', 'owner.silu.dut': 'VectorSiluOwner', 'owner.silu.dut.vector': 'SiluVectorUnit', 'owner.matrix': 'MatrixPipelineService'}
TAPS = {'Qwen2ContinuousBlock': {'canonicalScoreTap_head': 16, 'canonicalScoreTap_keyBase': 16, 'canonicalScoreTap_ownerTag': 32, 'canonicalScoreTap_packedSelected': 4, 'canonicalScoreTap_token': 16, 'canonicalScoreTap_valid': 1, 'canonicalScoreTap_value': 32, 'canonicalProbTap_col': 16, 'canonicalProbTap_head': 16, 'canonicalProbTap_key': 16, 'canonicalProbTap_ownerTag': 32, 'canonicalProbTap_token': 16, 'canonicalProbTap_valid': 1, 'canonicalProbTap_value': 16, 'canonicalCosTap_col': 16, 'canonicalCosTap_head': 16, 'canonicalCosTap_ownerTag': 32, 'canonicalCosTap_token': 16, 'canonicalCosTap_valid': 1, 'canonicalCosTap_value': 512, 'canonicalSinTap_col': 16, 'canonicalSinTap_head': 16, 'canonicalSinTap_ownerTag': 32, 'canonicalSinTap_token': 16, 'canonicalSinTap_valid': 1, 'canonicalSinTap_value': 512, 'canonicalPvRequestTap_col': 16, 'canonicalPvRequestTap_head': 16, 'canonicalPvRequestTap_ownerTag': 32, 'canonicalPvRequestTap_token': 16, 'canonicalPvRequestTap_valid': 1, 'canonicalPvAckTap_valid': 1}, 'FfnTileSiluBridge': {'canonicalTileTap_cols': 8, 'canonicalTileTap_identity': 32, 'canonicalTileTap_index': 11, 'canonicalTileTap_ng': 16, 'canonicalTileTap_rows': 8, 'canonicalTileTap_slot': 2, 'canonicalTileTap_valid': 1, 'canonicalTileTap_value_0': 32, 'canonicalTileTap_value_10': 32, 'canonicalTileTap_value_11': 32, 'canonicalTileTap_value_12': 32, 'canonicalTileTap_value_13': 32, 'canonicalTileTap_value_14': 32, 'canonicalTileTap_value_15': 32, 'canonicalTileTap_value_1': 32, 'canonicalTileTap_value_2': 32, 'canonicalTileTap_value_3': 32, 'canonicalTileTap_value_4': 32, 'canonicalTileTap_value_5': 32, 'canonicalTileTap_value_6': 32, 'canonicalTileTap_value_7': 32, 'canonicalTileTap_value_8': 32, 'canonicalTileTap_value_9': 32}, 'VectorSiluOwner': {'canonicalLoanContextTap_abort': 1, 'canonicalLoanContextTap_active': 1, 'canonicalLoanContextTap_poison': 1}, 'SiluVectorUnit': {'canonicalSiluTap_valid': 1, 'canonicalSiluTap_value_0': 32, 'canonicalSiluTap_value_10': 32, 'canonicalSiluTap_value_11': 32, 'canonicalSiluTap_value_12': 32, 'canonicalSiluTap_value_13': 32, 'canonicalSiluTap_value_14': 32, 'canonicalSiluTap_value_15': 32, 'canonicalSiluTap_value_1': 32, 'canonicalSiluTap_value_2': 32, 'canonicalSiluTap_value_3': 32, 'canonicalSiluTap_value_4': 32, 'canonicalSiluTap_value_5': 32, 'canonicalSiluTap_value_6': 32, 'canonicalSiluTap_value_7': 32, 'canonicalSiluTap_value_8': 32, 'canonicalSiluTap_value_9': 32}}
# Exact observed helper wires, separate from the original 75 primary tap leaves.
# Values are (declared width, ordered {high_identifier, low_identifier}).
# No expression evaluation, alias inference, or generic lo/hi filtering.
TAP_CONCAT_MODULE = 'Qwen2ContinuousBlock'
AUX_TAPS = {'canonicalCosTap_value_hi': (256, ('canonicalCosTap_value_hi_hi', 'canonicalCosTap_value_hi_lo')),
 'canonicalCosTap_value_hi_hi': (128, ('canonicalCosTap_value_hi_hi_hi', 'canonicalCosTap_value_hi_hi_lo')),
 'canonicalCosTap_value_hi_hi_hi': (64, ('cv_15', 'cv_14')),
 'canonicalCosTap_value_hi_hi_lo': (64, ('cv_13', 'cv_12')),
 'canonicalCosTap_value_hi_lo': (128, ('canonicalCosTap_value_hi_lo_hi', 'canonicalCosTap_value_hi_lo_lo')),
 'canonicalCosTap_value_hi_lo_hi': (64, ('cv_11', 'cv_10')),
 'canonicalCosTap_value_hi_lo_lo': (64, ('cv_9', 'cv_8')),
 'canonicalCosTap_value_lo': (256, ('canonicalCosTap_value_lo_hi', 'canonicalCosTap_value_lo_lo')),
 'canonicalCosTap_value_lo_hi': (128, ('canonicalCosTap_value_lo_hi_hi', 'canonicalCosTap_value_lo_hi_lo')),
 'canonicalCosTap_value_lo_hi_hi': (64, ('cv_7', 'cv_6')),
 'canonicalCosTap_value_lo_hi_lo': (64, ('cv_5', 'cv_4')),
 'canonicalCosTap_value_lo_lo': (128, ('canonicalCosTap_value_lo_lo_hi', 'canonicalCosTap_value_lo_lo_lo')),
 'canonicalCosTap_value_lo_lo_hi': (64, ('cv_3', 'cv_2')),
 'canonicalCosTap_value_lo_lo_lo': (64, ('cv_1', 'cv_0')),
 'canonicalSinTap_value_hi': (256, ('canonicalSinTap_value_hi_hi', 'canonicalSinTap_value_hi_lo')),
 'canonicalSinTap_value_hi_hi': (128, ('canonicalSinTap_value_hi_hi_hi', 'canonicalSinTap_value_hi_hi_lo')),
 'canonicalSinTap_value_hi_hi_hi': (64, ('dv_15', 'dv_14')),
 'canonicalSinTap_value_hi_hi_lo': (64, ('dv_13', 'dv_12')),
 'canonicalSinTap_value_hi_lo': (128, ('canonicalSinTap_value_hi_lo_hi', 'canonicalSinTap_value_hi_lo_lo')),
 'canonicalSinTap_value_hi_lo_hi': (64, ('dv_11', 'dv_10')),
 'canonicalSinTap_value_hi_lo_lo': (64, ('dv_9', 'dv_8')),
 'canonicalSinTap_value_lo': (256, ('canonicalSinTap_value_lo_hi', 'canonicalSinTap_value_lo_lo')),
 'canonicalSinTap_value_lo_hi': (128, ('canonicalSinTap_value_lo_hi_hi', 'canonicalSinTap_value_lo_hi_lo')),
 'canonicalSinTap_value_lo_hi_hi': (64, ('dv_7', 'dv_6')),
 'canonicalSinTap_value_lo_hi_lo': (64, ('dv_5', 'dv_4')),
 'canonicalSinTap_value_lo_lo': (128, ('canonicalSinTap_value_lo_lo_hi', 'canonicalSinTap_value_lo_lo_lo')),
 'canonicalSinTap_value_lo_lo_hi': (64, ('dv_3', 'dv_2')),
 'canonicalSinTap_value_lo_lo_lo': (64, ('dv_1', 'dv_0'))}
TAP_CONCAT_ROOTS = {'_canonicalCosTap_value_T': (512, ('canonicalCosTap_value_hi', 'canonicalCosTap_value_lo')),
 '_canonicalSinTap_value_T': (512, ('canonicalSinTap_value_hi', 'canonicalSinTap_value_lo'))}
TAP_CONCAT_DECLARATIONS = {**AUX_TAPS, **TAP_CONCAT_ROOTS}
TAP_CONCAT_RHS = re.compile(r'\s*=\s*\{\s*(' + ID + r')\s*,\s*(' + ID + r')\s*\}\s*;')

EXPECTED_MODULES = ['Record128Reader', 'TypedTensorReader', 'HostBlockCommands', 'FfnTileSiluBridge', 'FfnResidentCoordinator', 'DenseTileSumBridge', 'DenseBlockReductionCoordinator', 'Public21QkvReductionRouter', 'AddRawFN', 'RoundAnyRawFNToRecFN_ie8_is26_oe8_os24', 'RoundRawFNToRecFN_e8_s24', 'AddRecFN', 'MulFullRawFN', 'MulRawFN', 'MulRecFN', 'HeteroFP32Alu', 'DivSqrtRawFN_small_e8_s24', 'DivSqrtRecFMToRaw_small_e8_s24', 'DivSqrtRecFM_small_e8_s24', 'RecFNToIN_e8_s24_i32', 'RoundAnyRawFNToRecFN_ie6_is32_oe8_os24', 'INToRecFN_i32_e8_s24', 'BlockScalarFloat', 'banks_bank_2240x128', 'SharedL2Fabric', 'PackedAttentionStreamClient', 'banks_bank_48x128', 'SharedL2Fabric_1', 'ElementwiseMemoryEngine', 'BlockWritebackFence', 'mem_1024x32', 'Qwen2ContinuousBlock', 'aBanks_1376x256', 'bBanks_160x256', 'TransposedDownDenseBanks', 'ram_4x4359', 'Queue4_MatrixStreamStep', 'TransposedDenseDownOwner', 'SiluVectorUnit', 'VectorSiluOwner', 'ScheduledSiluOwner', 'ram_8x6', 'Queue8_Meta', 'MatrixResultFifo', 'MatrixAccumulatorSeedController', 'MatrixPipelineService', 'LegacyMatrixStreamClient', 'QwenOwnerKernel', 'RRArbiter', 'SharedMemoryArbiter', 'RetainedIdmaWeightBurstAdapter', 'HostBlockTop', 'MulAddRecFNToRaw_preMul_e8_s24', 'HeteroBF16FmaPre', 'HeteroBF16FmaMul', 'MulAddRecFNToRaw_postMul_e8_s24', 'HeteroBF16FmaPost', 'HeteroBF16FmaRound', 'HostBlockCollection']
EXTERNAL = {'qwen2_matrix_command_endpoint': {'ports': {'clk_i': ['input', 1], 'rst_ni': ['input', 1], 'cmd_valid_i': ['input', 1], 'cmd_ready_o': ['output', 1], 'cmd_i': ['input', 128], 'step_valid_i': ['input', 1], 'step_ready_o': ['output', 1], 'step_context_i': ['input', 3], 'step_clear_i': ['input', 1], 'step_last_i': ['input', 1], 'command_last_tile_i': ['input', 1], 'step_a_i': ['input', 256], 'step_b_i': ['input', 512], 'out_valid_o': ['output', 1], 'out_ready_i': ['input', 1], 'out_context_o': ['output', 3], 'out_last_o': ['output', 1], 'out_acc_o': ['output', 16384], 'completion_valid_o': ['output', 1], 'completion_ready_i': ['input', 1], 'completion_data_o': ['output', 56], 'protocol_error_o': ['output', 1], 'seed_begin_valid_i': ['input', 1], 'seed_begin_ready_o': ['output', 1], 'seed_context_i': ['input', 3], 'seed_group_tag_i': ['input', 32], 'seed_group_sequence_i': ['input', 32], 'seed_source_generation_i': ['input', 32], 'seed_beat_valid_i': ['input', 1], 'seed_beat_ready_o': ['output', 1], 'seed_cluster_i': ['input', 5], 'seed_data_i': ['input', 512], 'seed_commit_valid_i': ['input', 1], 'seed_commit_ready_o': ['output', 1], 'seed_abort_i': ['input', 1], 'seed_ack_valid_o': ['output', 1], 'seed_ack_ready_i': ['input', 1], 'seed_ack_context_o': ['output', 3], 'seed_ack_group_tag_o': ['output', 32], 'seed_ack_group_sequence_o': ['output', 32], 'seed_ack_source_generation_o': ['output', 32], 'seed_ack_error_o': ['output', 1], 'seed_reset_required_o': ['output', 1], 'arithmetic_busy_o': ['output', 5], 'arithmetic_out_valid_o': ['output', 1]}, 'parameters': {'ENABLE_ACCUMULATOR_SEED': '1'}, 'instance_count': 8}, 'tc_clk_gating': {'ports': {'clk_i': ['input', 1], 'en_i': ['input', 1], 'test_en_i': ['input', 1], 'clk_o': ['output', 1]}, 'parameters': {}, 'instance_count': 8}, 'idma_backend_rw_axi_flat_wrap': {'ports': {'clk_i': ['input', 1], 'rst_ni': ['input', 1], 'req_valid_i': ['input', 1], 'req_ready_o': ['output', 1], 'src_addr_i': ['input', 64], 'dst_addr_i': ['input', 64], 'length_i': ['input', 32], 'rsp_valid_o': ['output', 1], 'rsp_ready_i': ['input', 1], 'rsp_error_o': ['output', 1], 'axi_read_req_o': ['output', 785], 'axi_read_rsp_i': ['input', 532], 'axi_write_req_o': ['output', 785], 'axi_write_rsp_i': ['input', 532], 'busy_o': ['output', 8]}, 'parameters': {}, 'instance_count': 1}}
FMA_PORTS = {'HeteroBF16FmaPre': {'io_a': ['input', 16], 'io_b': ['input', 16], 'io_c': ['input', 32], 'io_mulAddA': ['output', 24], 'io_mulAddB': ['output', 24], 'io_mulAddC': ['output', 48], 'io_meta': ['output', 54]}, 'HeteroBF16FmaMul': {'io_mulAddA': ['input', 24], 'io_mulAddB': ['input', 24], 'io_mulAddC': ['input', 48], 'io_mulAddResult': ['output', 49]}, 'HeteroBF16FmaPost': {'io_meta': ['input', 54], 'io_mulAddResult': ['input', 49], 'io_raw': ['output', 41], 'io_invalid': ['output', 1]}, 'HeteroBF16FmaRound': {'io_raw': ['input', 41], 'io_invalid': ['input', 1], 'io_out': ['output', 32], 'io_exceptionFlags': ['output', 5]}}
SIBLINGS = {'mul': 'HeteroBF16FmaMul', 'post': 'HeteroBF16FmaPost', 'pre': 'HeteroBF16FmaPre', 'round': 'HeteroBF16FmaRound', 'top': 'HostBlockTop'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


# Projected from fixed check_sv.py cleaned/parens/bindings and fma_ports.py ports.
# No historical check() wrapper, Bench root, file reader, imports or qualification.
CLEAN_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*', re.S)
SPACE = re.compile(r'\s*')
DELIMITERS = re.compile(r'[()\[\]{},]')
WORD = re.compile(ID)


def cleaned(text):
    return CLEAN_TOKEN.sub(lambda m: (' @ ' if m[0].startswith('"') else ' ') + '\n' * m[0].count('\n'), text)


def space(s, pos):
    return SPACE.match(s, pos).end()


def parens(s, start):
    need(start < len(s) and s[start] == '(', 'expected parenthesis')
    depth = 1
    for m in re.compile(r'[()]').finditer(s, start+1, min(len(s),start+MAX_STATEMENT+1)):
        depth += 1 if m[0] == '(' else -1
        need(depth <= MAX_DEPTH, 'parenthesis depth cap')
        if depth == 0:
            end = m.start()
            return s[start+1:end], end+1
    raise ValueError('unclosed/oversized parenthesis')


def bindings(s, allow_empty=False):
    result = {}; pos = 0
    while pos < len(s):
        pos = space(s, pos)
        if pos == len(s): break
        m = re.compile(r'\.(' + ID + r')\s*\(').match(s, pos)
        need(m is not None, 'unknown/positional named binding')
        name = m[1]; need(name not in result, 'duplicate named binding ' + name)
        body, pos = parens(s, m.end()-1)
        need(body.strip() or allow_empty, 'empty named binding ' + name)
        result[name] = body.strip(); pos = space(s, pos)
        if pos == len(s): break
        need(s[pos] == ',', 'named binding separator'); pos += 1
        need(s[pos:].strip(), 'trailing binding comma')
    return result


def ports(header):
    result = {}; direction = None; width = None
    for part in header.split(','):
        part = part.strip()
        m = re.fullmatch(r'(?:(input|output)\s+)?(?:(?:wire|logic)\s+)?(?:\[(\d+)\s*:\s*(\d+)\]\s*)?(' + ID + r')', part)
        need(m is not None, 'unknown ANSI port shape ' + part[:100])
        if m[1]: direction = m[1]; width = 1
        if m[2]:
            need(int(m[3]) == 0, 'nonzero ANSI lower bound'); width = int(m[2])+1
        need(direction is not None and width is not None and 0 < width <= 1048576 and m[4] not in result, 'duplicate/untyped ANSI port')
        result[m[4]] = [direction, width]
    return result


def simple_statement(s, pos, single_declaration=False):
    end = s.find(';', pos, min(len(s), pos+MAX_STATEMENT))
    need(end >= 0, 'unclosed/oversized statement')
    stmt = s[pos:end+1]; stack = []; pairs = {')':'(', ']':'[', '}':'{'}
    for m in DELIMITERS.finditer(stmt):
        c = m[0]
        if c == ',':
            need(not single_declaration or bool(stack), 'multiple wire/reg declarators are unsupported')
            continue
        if c in '([{': stack.append(c); need(len(stack) <= MAX_DEPTH, 'delimiter depth cap')
        else: need(bool(stack) and stack.pop() == pairs[c], 'statement delimiter mismatch')
    need(not stack, 'unclosed statement delimiter')
    need(not re.search(r'\b(?:module|endmodule|generate|endgenerate|bind|function|task)\b', stmt), 'unsupported structural token in statement')
    return stmt, end+1


def procedural(s, pos):
    m = re.compile(r'always\s*@\s*\(').match(s, pos)
    need(m is not None, 'unsupported procedural header')
    _, pos = parens(s, m.end()-1); pos = space(s, pos)
    need(re.compile(r'begin\b').match(s, pos) is not None, 'only always-begin profile')
    depth = 0
    token = re.compile(r'\b(begin|end|module|endmodule|generate|endgenerate|bind|function|task)\b')
    for m in token.finditer(s, pos):
        word = m[1]
        need(word in ('begin','end'), 'unsupported structural token in procedural region')
        depth += 1 if word == 'begin' else -1
        need(0 <= depth <= MAX_DEPTH, 'procedural depth cap')
        if depth == 0:
            return m.end()
    raise ValueError('unclosed procedural begin/end')


def parse_body(s, known, headers=None, module_name=None):
    pos = 0; guard = False; edges = []; instances = set(); taps = {}; external = []; tap_concat_bindings = {}
    while True:
        pos = space(s, pos)
        if pos == len(s): break
        if s.startswith('`', pos):
            end = s.find('\n', pos); end = len(s) if end < 0 else end
            directive = s[pos:end].strip()
            if directive == '`ifndef SYNTHESIS': need(not guard, 'nested assertion guard'); guard = True
            elif directive == '`endif': need(guard, 'unmatched assertion guard'); guard = False
            else: raise ValueError('unsupported body preprocessor directive ' + directive[:100])
            pos = end; continue
        word = WORD.match(s, pos); need(word is not None, 'unknown module-body syntax near ' + s[pos:pos+100])
        kind = word[0]
        if kind == 'always':
            pos = procedural(s, pos); continue
        need(not guard, 'only procedural assertions permitted under SYNTHESIS guard')
        if kind in ('wire','reg','assign'):
            stmt, pos = simple_statement(s, pos, single_declaration=kind in ('wire','reg'))
            if kind in ('wire','reg'):
                m = re.match(r'(wire|reg)\s+(?:\[(\d+):0\]\s*)?(' + ID + r')\b', stmt)
                if m is None:
                    packed = re.fullmatch(r'wire\s+\[(\d+):0\]\[(\d+):0\]\s+(' + ID + r')\s*=\s*[^;]+;', stmt, re.S)
                    need(packed is not None, 'unknown wire/reg declaration shape')
                    need(module_name in DOUBLE_PACKED_WIRE_MODULES, 'double-packed wire outside observed Host modules')
                    need((int(packed[1]),int(packed[2])) in DOUBLE_PACKED_WIRE_SHAPES, 'unobserved double-packed wire shape')
                    need(not (packed[3].startswith('canonical') and 'Tap' in packed[3]) and packed[3] not in TAP_CONCAT_DECLARATIONS, 'canonical tap/concat must retain scalar/single-packed declaration')
                    continue # Opaque initialized non-tap wire; no signal/value expansion.
                name = m[3]
                tail = stmt[m.end():]
                need(re.fullmatch(r'\s*(?:\[\d+:\d+\]\s*)?(?:=\s*[^;]+)?;', tail, re.S) is not None, 'non-singleton/unknown wire/reg declaration')
                if name in TAP_CONCAT_DECLARATIONS:
                    need(module_name == TAP_CONCAT_MODULE, 'fixed tap concat in wrong module')
                    need(kind == 'wire' and name not in tap_concat_bindings, 'fixed tap concat wire kind/duplicate')
                    concat = TAP_CONCAT_RHS.fullmatch(tail)
                    need(concat is not None, 'fixed tap concat must be two complete identifiers')
                    observed_concat = (int(m[2])+1 if m[2] else 1, (concat[1],concat[2]))
                    need(observed_concat == TAP_CONCAT_DECLARATIONS[name], 'fixed tap concat width/ordered references ' + name)
                    tap_concat_bindings[name] = observed_concat
                if name.startswith('canonical') and 'Tap' in name:
                    need(kind == 'wire', 'canonical tap must be wire')
                    need(name not in taps, 'duplicate canonical tap leaf')
                    need(re.fullmatch(r'wire\s+(?:\[\d+:0\]\s*)?' + re.escape(name) + r'\s*=\s*[^;]+;', stmt, re.S) is not None, 'unknown canonical tap initializer shape')
                    taps[name] = int(m[2])+1 if m[2] else 1
            continue
        need(kind in known, 'unknown instance/module-body type ' + kind)
        pos = space(s, word.end()); params = {}
        if pos < len(s) and s[pos] == '#':
            pos = space(s, pos+1); raw, pos = parens(s, pos); params = bindings(raw)
        inst = re.compile(r'\s*(' + ID + r')\s*\(').match(s, pos); need(inst is not None, 'unknown instance form ' + kind)
        name = inst[1]; need(name not in instances, 'duplicate instance ' + name); instances.add(name)
        raw, end = parens(s, inst.end()-1); end = space(s, end)
        need(end < len(s) and s[end] == ';', 'unknown instance terminator'); pos = end+1
        binds = bindings(raw, allow_empty=True); edges.append((name, kind))
        if kind in EXTERNAL:
            spec = EXTERNAL[kind]
            need(set(binds) == set(spec['ports']), 'external named-port inventory ' + kind)
            need(set(params) == set(spec['parameters']), 'external parameter inventory ' + kind)
            for key, expected in spec['parameters'].items():
                need(re.fullmatch(r"(?:\d+'[hdb])?" + expected, params[key]) is not None, 'external parameter value ' + key)
            for port, expr in binds.items(): need(expr or (kind == 'idma_backend_rw_axi_flat_wrap' and port == 'busy_o'), 'unapproved empty external binding')
            external.append({'instance':name,'type':kind,'parameters':params,'bindings':binds})
        else:
            need(not params, 'unexpected parameters on generated internal module')
            if headers is not None:
                need(set(binds) == set(headers[kind]), 'internal named-port inventory ' + kind)
                for port, expr in binds.items(): need(expr or headers[kind][port][0] == 'output', 'empty internal input binding')
    need(not guard, 'unclosed assertion guard')
    return {'edges':edges, 'taps':taps, 'external':external, 'tap_concat_bindings':tap_concat_bindings}


def parse_modules(s):
    # Single lexical module partition. Only fixed generated preamble is allowed.
    token = re.compile(r'\b(module|endmodule)\b'); current = None; bounds = []; prior_end = 0
    for m in token.finditer(s):
        if m[1] == 'module':
            need(current is None, 'nested module')
            if bounds: need(not s[prior_end:m.start()].strip(), 'unconsumed inter-module syntax')
            current = m.start()
        else:
            need(current is not None, 'unmatched endmodule')
            bounds.append((current,m.start())); current = None; prior_end = m.end()
    need(current is None and 0 < len(bounds) <= MAX_DEFINITIONS, 'module inventory bound/unclosed')
    need(not s[prior_end:].strip(), 'unconsumed final syntax')
    preamble = s[:bounds[0][0]].strip()
    need(not preamble or preamble == EXPECTED_PREAMBLE.strip(), 'unknown generated preamble')
    headers = {}; bodies = {}
    for start, end in bounds:
        m = re.compile(r'module\s+(' + ID + r')\s*\(').match(s,start,end); need(m is not None, 'unknown module declaration')
        name = m[1]; need(name not in headers, 'duplicate module ' + name)
        header, p = parens(s, m.end()-1); p = space(s, p)
        need(p < end and s[p] == ';', 'module header terminator')
        headers[name] = ports(header)
        need(not any((n.startswith('canonical') and 'Tap' in n) or n in TAP_CONCAT_DECLARATIONS for n in headers[name]), 'canonical tap/concat exposed as port')
        bodies[name] = (p+1,end)
    known = set(headers) | set(EXTERNAL); modules = {}
    for name, (start,end) in bodies.items():
        modules[name] = parse_body(s[start:end], known, headers, module_name=name); modules[name]['ports'] = headers[name]
    return modules


def walk(modules, root):
    paths = {}; counts = collections.Counter()
    def visit(typ, path, ancestors):
        need(typ not in ancestors and len(ancestors) < MAX_DEPTH, 'cyclic/deep instance graph')
        need(len(paths) < MAX_PATHS and path not in paths, 'instance path cap/collision')
        paths[path] = typ; counts[typ] += 1
        if typ in EXTERNAL: return
        need(typ in modules, 'unknown referenced module')
        for name, child in modules[typ]['edges']: visit(child,path+'.'+name,ancestors+(typ,))
    visit(root, root, ())
    return paths, counts


def qualify(modules):
    need(set(modules) == set(EXPECTED_MODULES) and len(modules) == 59, 'exact Host93 SV definition inventory')
    need(not set(modules)&set(EXTERNAL), 'external blackbox substituted locally')
    need(modules['HostBlockTop']['ports'] == HOST_PORTS, 'exact original Host83 interface')
    need(dict(modules['HostBlockCollection']['edges']) == SIBLINGS, 'exact collection five-child namespace')
    for name, expected in FMA_PORTS.items(): need(modules[name]['ports'] == expected, 'FMA sibling interface ' + name)
    collection, collection_counts = walk(modules,'HostBlockCollection')
    host, counts = walk(modules,'HostBlockTop')
    need(set(collection.values())-set(EXTERNAL) == set(modules), 'orphan/unreachable generated definition')
    for path, typ in EXPECTED_PATHS.items(): need(host.get('HostBlockTop.'+path) == typ, 'required Host hierarchy ' + path)
    for typ in ('HostBlockTop','HostBlockCommands','Record128Reader','TypedTensorReader','QwenOwnerKernel','SharedMemoryArbiter','RetainedIdmaWeightBurstAdapter','MatrixPipelineService'):
        need(counts[typ] == 1, 'unique Host resource ' + typ)
    for typ, spec in EXTERNAL.items():
        need(counts[typ] == spec['instance_count'] and collection_counts[typ] == counts[typ], 'Host/collection external count ' + typ)
    need(not set(FMA_PORTS)&set(host.values()), 'FMA sibling inside Host subtree')
    observed = {name:data['taps'] for name,data in modules.items() if data['taps']}
    expected_taps = {name:dict(leaves) for name,leaves in TAPS.items()}
    expected_taps[TAP_CONCAT_MODULE].update({name:spec[0] for name,spec in AUX_TAPS.items()})
    need(observed == expected_taps, 'exact primary and auxiliary canonical tap names/widths/modules')
    concat_bindings = {name:data['tap_concat_bindings'] for name,data in modules.items() if data['tap_concat_bindings']}
    need(concat_bindings == {TAP_CONCAT_MODULE:TAP_CONCAT_DECLARATIONS}, 'exact 28 helper and 2 terminal concat declarations')
    need(len(AUX_TAPS) == 28 and sum(spec[0] for spec in AUX_TAPS.values()) == 3072, 'fixed helper declaration inventory')
    for typ in TAPS: need(counts[typ] == 1, 'tap module must be unique in Host')
    tap_bits = sum(sum(leaves.values()) for leaves in TAPS.values())
    need(tap_bits == 2604, 'tap bit count')
    return {'status':'PASS','scope':'HOST93_SAME_SV_FINITE_LEXICAL_INTERFACE_HIERARCHY_EXTERNAL_TAPS_ONLY',
        'definition_count':len(modules),'host_instance_count_including_generated_memories':len(host),
        'collection_instance_count_including_generated_memories':len(collection),
        'host_resource_counts':dict(counts),'collection_resource_counts':dict(collection_counts),
        'host_port_count':83,'host_input_count':39,'host_output_count':44,'host_ports':HOST_PORTS,
        'external_counts':{name:counts[name] for name in EXTERNAL},
        'external_named_bindings':{name:row['external'] for name,row in modules.items() if row['external']},
        'required_host_paths':EXPECTED_PATHS,'collection_direct_instances':SIBLINGS,
        'observation_bundles':9,'observation_leaf_count':sum(map(len,TAPS.values())),'observation_bits':tap_bits,'tap_leaf_widths':TAPS,
        'auxiliary_tap_declaration_count':len(AUX_TAPS),'auxiliary_tap_declared_bits':sum(spec[0] for spec in AUX_TAPS.values()),
        'auxiliary_tap_declarations':AUX_TAPS,'tap_concat_terminal_count':len(TAP_CONCAT_ROOTS),
        'tap_concat_declaration_bindings':concat_bindings,'tap_concat_initializer_profile':'EXACT_ORDERED_BINARY_IDENTIFIER_ONLY',
        'auxiliary_declared_bits_are_primary_observation_bits':False,'tap_complete_driver_or_value_proof':False,
        'metadata_route_qualification':'PENDING_PRUNED_PORT_MAPPING','dpi_provider_source_and_function_mapping':'PENDING_FOR_HOST93',
        'external_binding_widths_proved':False,'sv_syntax_elaborated':False,'tap_event_semantics_proved':False,
        'generated_cpp_binding_verified':False,'host_executed':False,'numerical_qualification':False,'historical_identity_inherited':False}


def check_bytes(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'bounded immutable bytes required')
    digest = hashlib.sha256(raw).hexdigest()
    need(len(raw) == EXPECTED_BYTES and digest == EXPECTED_SHA256, 'fixed same-SV identity')
    text = raw.decode('utf-8',errors='strict')
    s = cleaned(text); del text
    result = qualify(parse_modules(s))
    result.update(bytes=len(raw),sha256=digest)
    return result

EXPECTED_PREAMBLE = ' \n \n\n \n`ifndef ASSERT_VERBOSE_COND_\n  `ifdef ASSERT_VERBOSE_COND\n    `define ASSERT_VERBOSE_COND_ (`ASSERT_VERBOSE_COND)\n  `else   \n    `define ASSERT_VERBOSE_COND_ 1\n  `endif  \n`endif  \n\n \n`ifndef STOP_COND_\n  `ifdef STOP_COND\n    `define STOP_COND_ (`STOP_COND)\n  `else   \n    `define STOP_COND_ 1\n  `endif  \n`endif  \n\n'
