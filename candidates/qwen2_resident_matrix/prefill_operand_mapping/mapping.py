"""Integer address/index proof only. No payload, readiness or cycle prediction."""
def integer(x,lo,hi):
    if type(x) is not int or not lo<=x<=hi:raise ValueError('canonical bounded integer')
    return x

def tensor_word(kind,token,head,depth):
    integer(token,0,127);integer(depth,0,127)
    if kind=='q':integer(head,0,11);width=1536
    elif kind in ('k','v'):integer(head,0,1);width=256
    else:raise ValueError('q/k/v only')
    return token*width+head*128+depth

def ddr_word(kind,base,token,head,depth):
    integer(base,0,2**64-1)
    if base%64:raise ValueError('64B-aligned owner pointer required for this mapping')
    addr=base+4*tensor_word(kind,token,head,depth)
    if addr+3>=2**64:raise ValueError('address overflow')
    return dict(byte_address=addr,beat_address=addr//64*64,fp32_lane=(addr%64)//4,
                bank='DDR physical bank unresolved')

def q_local(depth):
    integer(depth,0,127);line,lane=divmod(depth,16)
    return dict(line=line,bank=4*(line%4)+lane//4,word=line//4,bank_fp32_lane=lane%4)

def scratch(kind,row,key):
    integer(row,0,5);integer(key,0,127)
    if kind not in ('score','prob'):raise ValueError('scratch kind')
    line=(4096 if kind=='score' else 4144)+8*row+key//16
    lane=key%16
    return dict(line=line,bank=2*(line%8)+lane//8,word=line//8,bank_fp32_lane=lane%8,beat_lane=lane)

def qk_lane(key_slot,depth_lane):
    integer(key_slot,0,15);integer(depth_lane,0,15)
    col=16*key_slot+depth_lane
    return dict(a_lane=depth_lane,b_register=col,b_lane=col,endpoint=col//32,
                endpoint_col=col%32,result_row=depth_lane,result_col=col)

def panel(row,key_in_block):
    integer(row,0,5);integer(key_in_block,0,15)
    return dict(alias='denseWindow proposed exclusive alias',row=row,col=key_in_block,
                word=row*16+key_in_block)

def inverse(row):
    integer(row,0,5)
    return dict(alias='denseWindow proposed exclusive alias',row=6,col=row,word=96+row)

def pv_lane(row,column):
    integer(row,0,5);integer(column,0,127)
    return dict(a_lane=row,b_register=column,b_lane=column,endpoint=column//32,
                endpoint_col=column%32,result_row=row,result_col=column)

def scope():
    return dict(kind='integer_address_mapping_only',physical_sfu_pools=1,
                panel_words=96,panel_bytes=384,inverse_words=6,total_dense_window_alias_words=102,new_payload_array_declarations_proposed=0,physical_register_retention_verified=False,
                physical_matrix_endpoints=8,physical_mac_lanes=4096,pv_selected_endpoints=4,
                q_staging_heads_existing=1,bank_spaces_distinct=True,
                can_supply=False,rtl_measured=False,numerical_execution=False,
                accepted_80=False,accepted_90=False,
                unresolved=['Selected-composition register retention and synthesis inventory','DDR bank layout','raw scratch owner wiring','denseWindow panel alias RTL',
                            'six-row softmax producer','PV V128 gather and mux','actual returned timing'])
