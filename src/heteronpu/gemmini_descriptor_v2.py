"""Resolve schema-v2 Matrix descriptor chains into pinned Gemmini programs."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from collections.abc import Mapping

from .command import Command128, Opcode
from .descriptor_chain import (
    DescriptorRecord, MatrixAux, NULL_INDEX, RecordType, validate_descriptor_chain,
)
from .gemmini_rocc_lowering import (
    ConvWsDescriptor, GemminiDataflow, Int8OsTilesDescriptor, LoopWsDescriptor,
    RoCCMicroOp, config_ex, config_load, config_store, lower_int8_os_tiles,
    lower_loop_conv_ws, lower_loop_ws,
)


@dataclass(frozen=True)
class TensorView:
    address: int
    memory_space: int
    dtype: int
    layout: int
    rank: int
    shape: tuple[int, int, int, int]
    strides: tuple[int, int, int]
    quant_payload: int | None = None


@dataclass(frozen=True)
class MatrixOpView:
    m: int
    n: int
    k: int
    dataflow: int
    transpose_a: bool
    transpose_b: bool
    accumulate: bool
    quant_mode: int


@dataclass(frozen=True)
class Conv2dView:
    kernel_h: int
    kernel_w: int
    stride_h: int
    stride_w: int
    dilation_h: int
    dilation_w: int
    pad_top: int
    pad_left: int
    groups: int


def tensor_base_record(address: int, *, dtype: int = 1, layout: int = 0,
                       rank: int = 2, memory_space: int = 0,
                       next_index: int = NULL_INDEX) -> DescriptorRecord:
    if not 0 <= address < (1 << 56):
        raise ValueError("tensor address does not fit in 56 bits")
    payload = ((address & ((1 << 48) - 1)) | memory_space << 48 |
               dtype << 52 | layout << 56 | rank << 60 |
               (address >> 48) << 64)
    return DescriptorRecord(RecordType.TENSOR_BASE, 0, 0, next_index, payload)


def shape4_record(shape: tuple[int, ...], *, next_index: int = NULL_INDEX) -> DescriptorRecord:
    dims = (*shape, 0, 0, 0, 0)[:4]
    if any(not 0 <= dim < (1 << 18) for dim in dims):
        raise ValueError("shape dimension does not fit in 18 bits")
    payload = sum(dim << (18 * index) for index, dim in enumerate(dims))
    return DescriptorRecord(RecordType.SHAPE4, 0, 0, next_index, payload)


def stride3_record(strides: tuple[int, ...], *, next_index: int = NULL_INDEX) -> DescriptorRecord:
    values = (*strides, 0, 0)[:3]
    if any(not -(1 << 23) <= value < (1 << 23) for value in values):
        raise ValueError("stride does not fit in signed 24 bits")
    payload = sum((value & 0xFFFFFF) << (24 * index) for index, value in enumerate(values))
    return DescriptorRecord(RecordType.STRIDE3, 0, 0, next_index, payload)


def matrix_op_record(*, m: int, n: int, k: int, dataflow: int,
                     transpose_a: bool = False, transpose_b: bool = False,
                     accumulate: bool = False, quant_mode: int = 0,
                     next_index: int = NULL_INDEX) -> DescriptorRecord:
    payload = (m | n << 16 | k << 32 | dataflow << 56 |
               int(transpose_a) << 58 | int(transpose_b) << 59 |
               int(accumulate) << 60 | quant_mode << 61)
    return DescriptorRecord(RecordType.MATRIX_OP, 0, 0, next_index, payload)


def conv2d_record(*, kernel_h: int, kernel_w: int, stride_h: int, stride_w: int,
                  dilation_h: int, dilation_w: int, pad_top: int, pad_left: int,
                  groups: int, next_index: int = NULL_INDEX) -> DescriptorRecord:
    payload = (kernel_h | kernel_w << 8 | stride_h << 16 | stride_w << 24 |
               dilation_h << 32 | dilation_w << 40 | pad_top << 48 |
               pad_left << 54 | groups << 60)
    return DescriptorRecord(RecordType.CONV2D, 0, 0, next_index, payload)


def quantization_record(*, scale_address: int, group_size_log2: int = 0,
                        rounding_mode: int = 0, saturation_mode: int = 0,
                        zero_point_bits: int = 0,
                        next_index: int = NULL_INDEX) -> DescriptorRecord:
    payload = (scale_address | group_size_log2 << 48 | rounding_mode << 53 |
               saturation_mode << 56 | zero_point_bits << 58)
    return DescriptorRecord(RecordType.QUANTIZATION, 0, 0, next_index, payload)


def _signed24(value: int) -> int:
    return value - (1 << 24) if value & (1 << 23) else value


def _parse_tensor(chain: tuple[tuple[int, DescriptorRecord], ...]) -> TensorView:
    base = [record for _, record in chain if record.record_type == RecordType.TENSOR_BASE]
    shape = [record for _, record in chain if record.record_type == RecordType.SHAPE4]
    stride = [record for _, record in chain if record.record_type == RecordType.STRIDE3]
    quant = [record for _, record in chain if record.record_type == RecordType.QUANTIZATION]
    if len(base) != 1 or len(shape) < 1 or len(stride) < 1 or len(quant) > 1:
        raise ValueError("tensor chain requires one base, shape and stride and at most one quantization")
    bp, sp, tp = base[0].payload, shape[0].payload, stride[0].payload
    address = (bp & ((1 << 48) - 1)) | ((bp >> 64) & 0xFF) << 48
    return TensorView(
        address=address, memory_space=(bp >> 48) & 0xF,
        dtype=(bp >> 52) & 0xF, layout=(bp >> 56) & 0xF,
        rank=(bp >> 60) & 0xF,
        shape=tuple((sp >> (18 * index)) & 0x3FFFF for index in range(4)),
        strides=tuple(_signed24((tp >> (24 * index)) & 0xFFFFFF) for index in range(3)),
        quant_payload=quant[0].payload if quant else None,
    )


def _parse_matrix_op(record: DescriptorRecord) -> MatrixOpView:
    p = record.payload
    if p >> 69:
        raise ValueError("matrix_op reserved bits must be zero")
    return MatrixOpView(p & 0xFFFF, (p >> 16) & 0xFFFF, (p >> 32) & 0xFFFFFF,
                        (p >> 56) & 3, bool((p >> 58) & 1), bool((p >> 59) & 1),
                        bool((p >> 60) & 1), (p >> 61) & 7)


def _parse_conv(record: DescriptorRecord) -> Conv2dView:
    p = record.payload
    return Conv2dView(p & 0xFF, (p >> 8) & 0xFF, (p >> 16) & 0xFF,
                      (p >> 24) & 0xFF, (p >> 32) & 0xFF, (p >> 40) & 0xFF,
                      (p >> 48) & 0x3F, (p >> 54) & 0x3F, (p >> 60) & 0xFFF)


def lower_matrix_v2(command: Command128, records: Mapping[int, int | DescriptorRecord],
                    *, scale_bits: Mapping[int, int] | None = None) -> tuple[RoCCMicroOp, ...]:
    if command.opcode not in {Opcode.MATRIX_GEMM, Opcode.MATRIX_GEMV,
                              Opcode.MATRIX_CONV, Opcode.MATRIX_QK, Opcode.MATRIX_PV}:
        raise ValueError("command is not a Matrix opcode")
    chains = [validate_descriptor_chain(root, records) for root in
              (command.src0, command.src1, command.dst)]
    src0, src1, dst = (_parse_tensor(chain) for chain in chains)
    operation_records = [record for _, record in chains[0]
                         if record.record_type == RecordType.MATRIX_OP]
    aux_records = [record for _, record in chains[0]
                   if record.record_type == RecordType.MATRIX_AUX]
    conv_records = [record for _, record in chains[0]
                    if record.record_type == RecordType.CONV2D]
    if len(operation_records) != 1 or len(aux_records) != 1:
        raise ValueError("Matrix src0 chain requires exactly one matrix_op and matrix_aux")
    op = _parse_matrix_op(operation_records[0])
    aux = MatrixAux.from_record(aux_records[0])
    bias = None
    if aux.bias_index != NULL_INDEX:
        bias = _parse_tensor(validate_descriptor_chain(aux.bias_index, records))
    for tensor in (src0, src1, dst):
        if tensor.dtype != 1 or tensor.layout != 0 or tensor.rank < 2:
            raise ValueError("L2 Matrix production path requires row-major INT8 tensors")
    if (src0.shape[0], src0.shape[1], src1.shape[0], src1.shape[1],
            dst.shape[0], dst.shape[1]) != (op.m, op.k, op.k, op.n, op.m, op.n):
        if command.opcode is not Opcode.MATRIX_CONV:
            raise ValueError("Matrix tensor shapes do not match M/N/K")
    if command.opcode is Opcode.MATRIX_CONV:
        if len(conv_records) != 1 or bias is None:
            raise ValueError("L2 Conv requires one conv2d and a bias tensor")
        conv = _parse_conv(conv_records[0])
        if not aux.no_pool or conv.kernel_h != conv.kernel_w or conv.stride_h != conv.stride_w:
            raise ValueError("L2 Conv supports no-pool square-kernel/symmetric-stride mode")
        if src0.rank < 4 or src1.rank < 4 or dst.rank < 4:
            raise ValueError("Conv tensors must be rank four")
        batch, in_h, in_w, in_ch = src0.shape
        _, out_h, out_w, out_ch = dst.shape
        scale = 0x3F800000
        if op.quant_mode:
            if dst.quant_payload is None or scale_bits is None:
                raise ValueError("quantized Conv requires a resolved scale value")
            address = dst.quant_payload & ((1 << 48) - 1)
            scale = scale_bits[address]
        descriptor = ConvWsDescriptor(
            batch_size=batch, in_row_dim=in_h, in_col_dim=in_w, in_channels=in_ch,
            out_channels=out_ch, out_row_dim=out_h, out_col_dim=out_w,
            pool_out_row_dim=out_h, pool_out_col_dim=out_w,
            stride=conv.stride_h, padding=conv.pad_top,
            kernel_dim=conv.kernel_h, kernel_dilation=conv.dilation_h,
            pool_size=1, pool_stride=1, pool_padding=0,
            batches=batch, porows=out_h, pocols=out_w, pochs=out_ch,
            krows=conv.kernel_h, kcols=conv.kernel_w, kchs=in_ch,
            lpad=conv.pad_left, rpad=aux.pad_right, upad=conv.pad_top,
            dpad=aux.pad_bottom, plpad=0, prpad=0, pupad=0, pdpad=0,
            orows=out_h, ocols=out_w, weights_addr=src1.address,
            output_addr=dst.address, bias_addr=bias.address, input_addr=src0.address,
            no_bias=False, no_pool=True, downsample=aux.downsample,
            wrot180=aux.wrot180, input_dilated=aux.input_dilated,
            activation=int(aux.activation), trans_output_1203=aux.trans_output_1203,
            trans_weight_1203=aux.trans_weight_1203,
            trans_weight_0132=aux.trans_weight_0132,
            trans_input_3120=aux.trans_input_3120,
            max_pixels_per_row=aux.max_pixels_per_row,
            in_stride=in_ch, weight_stride=out_ch, out_stride=out_ch,
            dw=aux.depthwise, a_spad_id=aux.a_spad_id, b_spad_id=aux.b_spad_id,
        )
        return (config_store(stride_bytes=out_ch, acc_scale_bits=scale,
                             activation=int(aux.activation)),
                config_ex(dataflow=GemminiDataflow.WEIGHT_STATIONARY,
                          c_stride=1, a_stride=1, acc_scale_bits=0),
                *lower_loop_conv_ws(descriptor))
    if op.dataflow == GemminiDataflow.WEIGHT_STATIONARY:
        i, j, k = ceil(op.m / 16), ceil(op.n / 16), ceil(op.k / 16)
        ws = LoopWsDescriptor(
            i=i, j=j, k=k, pad_i=i*16-op.m, pad_j=j*16-op.n, pad_k=k*16-op.k,
            a_addr=src0.address, b_addr=src1.address,
            d_addr=0 if bias is None else bias.address, c_addr=dst.address,
            a_stride=src0.strides[0], b_stride=src1.strides[0],
            d_stride=0 if bias is None else bias.strides[0] // 4,
            c_stride=dst.strides[0], a_transpose=op.transpose_a,
            b_transpose=op.transpose_b, full_c=aux.full_c, low_d=aux.low_d,
            ex_accumulate=op.accumulate, activation=int(aux.activation),
            a_spad_id=aux.a_spad_id, b_spad_id=aux.b_spad_id,
        )
        return (
            config_ex(dataflow=GemminiDataflow.WEIGHT_STATIONARY, c_stride=1, a_stride=1),
            config_store(stride_bytes=dst.strides[0]),
            config_load(stride_bytes=src0.strides[0], channel=0),
            config_load(stride_bytes=src1.strides[0], channel=1),
            config_load(stride_bytes=0 if bias is None else bias.strides[0], channel=2),
            *lower_loop_ws(ws),
        )
    if op.dataflow != GemminiDataflow.OUTPUT_STATIONARY or bias is None:
        raise ValueError("multi-tile OS L2 vector requires an explicit bias tensor")
    i, j, k = ceil(op.m / 16), ceil(op.n / 16), ceil(op.k / 16)
    return lower_int8_os_tiles(Int8OsTilesDescriptor(
        a_addr=src0.address, b_addr=src1.address, d_addr=bias.address,
        c_addr=dst.address, i_tiles=i, j_tiles=j, k_tiles=k,
        pad_i=i*16-op.m, pad_j=j*16-op.n, pad_k=k*16-op.k,
        a_row_stride=src0.strides[0], b_row_stride=src1.strides[0],
        d_row_stride=bias.strides[0]//4, c_row_stride=dst.strides[0],
    ))
