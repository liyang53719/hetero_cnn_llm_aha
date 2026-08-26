import pytest
from heteronpu.kv_idma_basic import IdmaTransfer, KvIdmaBasicModel


def test_basic_bf16_append_gather_free_idma_trace() -> None:
    model=KvIdmaBasicModel(staging_base=0x100000)
    assert model.alloc(sequence_id=0,layer_id=0,head_dim=128)==()
    assert model.append(token_start=0,token_count=2,k_addr=0x80000000,v_addr=0x80001000)==(
        IdmaTransfer(0x80000000,0x100000,512),IdmaTransfer(0x80001000,0x140000,512))
    assert model.gather(token_start=1,token_count=1,output_addr=0x90000000)==(
        IdmaTransfer(0x100100,0x90000000,256),IdmaTransfer(0x140100,0x90000100,256))
    assert model.free()==() and not model.allocated


def test_basic_kv_rejects_gap_overflow_and_use_after_free() -> None:
    model=KvIdmaBasicModel(staging_bytes=1024)
    model.alloc(sequence_id=0,layer_id=0,head_dim=128)
    with pytest.raises(ValueError,match="non-contiguous"):model.append(token_start=1,token_count=1,k_addr=0,v_addr=1)
    with pytest.raises(MemoryError):model.append(token_start=0,token_count=3,k_addr=0,v_addr=1)
    model.append(token_start=0,token_count=1,k_addr=0,v_addr=1);model.free()
    with pytest.raises(ValueError,match="not allocated"):model.gather(token_start=0,token_count=1,output_addr=0)
