// Testbench-only exact IEEE754 widening. Never use bitstoshortreal in Verilator.
function automatic logic[63:0] fp32_ieee_to_fp64_bits(input logic[31:0] bits);
 logic[63:0] wide;logic[23:0] significand;integer shifts;
 begin
  wide='0;wide[63]=bits[31];significand={1'b0,bits[22:0]};shifts=0;
  if(bits[30:23]==8'hff)begin
   wide[62:52]=11'h7ff;wide[51:0]={bits[22:0],29'b0};
  end else if(bits[30:23]!=0)begin
   wide[62:52]=11'(bits[30:23])+11'd896;wide[51:0]={bits[22:0],29'b0};
  end else if(bits[22:0]!=0)begin
   for(integer i=0;i<23;i++)if(!significand[23])begin significand=significand<<1;shifts++;end
   wide[62:52]=11'(897-shifts);wide[51:0]={significand[22:0],29'b0};
  end
  fp32_ieee_to_fp64_bits=wide;
 end
endfunction
function automatic real fp32_ieee_real(input logic[31:0] bits);
 fp32_ieee_real=$bitstoreal(fp32_ieee_to_fp64_bits(bits));
endfunction
