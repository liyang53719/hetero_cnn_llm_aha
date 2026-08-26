// Generated reciprocal mantissa coefficients
function automatic logic[63:0] recip_pwl_coeff(input logic[3:0]index);
case(index)
4'd0:recip_pwl_coeff=64'hbf70f0f13ff87878;
4'd1:recip_pwl_coeff=64'hbf562b813fea3f95;
4'd2:recip_pwl_coeff=64'hbf3fa0303fdd9137;
4'd3:recip_pwl_coeff=64'hbf2c76923fd23082;
4'd4:recip_pwl_coeff=64'hbf1c09c13fc7ec7f;
4'd5:recip_pwl_coeff=64'hbf0dda523fbe9d5e;
4'd6:recip_pwl_coeff=64'hbf01848e3fb62267;
4'd7:recip_pwl_coeff=64'hbeed73043fae6077;
4'd8:recip_pwl_coeff=64'hbeda740e3fa740db;
4'd9:recip_pwl_coeff=64'hbec9a6343fa0b071;
4'd10:recip_pwl_coeff=64'hbebab6563f9a9eff;
4'd11:recip_pwl_coeff=64'hbead602b3f94fea5;
4'd12:recip_pwl_coeff=64'hbea16b313f8fc378;
4'd13:recip_pwl_coeff=64'hbe96a8503f8ae32a;
4'd14:recip_pwl_coeff=64'hbe8cf0093f8654c8;
4'd15:recip_pwl_coeff=64'hbe8421083f821084;
default:recip_pwl_coeff=64'd0;
endcase
endfunction
