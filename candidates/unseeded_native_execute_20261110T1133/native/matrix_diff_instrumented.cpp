#include "unseeded_matrix_v2.h"
#include "Vqwen2_matrix_command_endpoint.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <stdexcept>
void ok(int x){if(x)throw std::runtime_error("ABI "+std::to_string(x));}
int main(){try{VerilatedContext c;c.threads(1);Vqwen2_matrix_command_endpoint d(&c);d.clk_i=0;void*h=retained_matrix_unseeded_v2_create();if(!h)throw std::runtime_error("create");std::array<uint32_t,37>w{};std::array<uint32_t,521>a{},b{};unsigned completions=0,outputs=0;bool command=false,step=false;uint64_t compared=0;
for(unsigned tick=0;tick<400;++tick){if(tick%20==0)std::cerr<<"tick "<<tick<<std::endl;unsigned cycle=tick/2,level=tick%2;w.fill(0);w[0]=cycle>=3;w[1]=cycle>=4&&!command;w[2]=0x20;w[3]=0x123400;w[6]=command&&!step;w[8]=1;w[9]=1;w[10]=1;for(unsigned i=11;i<35;++i)w[i]=0x3f803f80;w[35]=cycle>=32;w[36]=cycle>=36;
 d.rst_ni=w[0];d.cmd_valid_i=w[1];for(int j=0;j<4;j++)d.cmd_i[j]=w[2+j];d.step_valid_i=w[6];d.step_context_i=w[7];d.step_clear_i=w[8];d.step_last_i=w[9];d.command_last_tile_i=w[10];for(int j=0;j<8;j++)d.step_a_i[j]=w[11+j];for(int j=0;j<16;j++)d.step_b_i[j]=w[19+j];d.out_ready_i=w[35];d.completion_ready_i=w[36];d.eval();ok(retained_matrix_unseeded_v2_drive(h,w.data(),37));ok(retained_matrix_unseeded_v2_eval(h));
 bool takeCmd=level&&d.cmd_valid_i&&d.cmd_ready_o,takeStep=level&&d.step_valid_i&&d.step_ready_o;bool out=level&&d.out_valid_o&&d.out_ready_i,comp=level&&d.completion_valid_o&&d.completion_ready_i;
 if(out)for(int j=0;j<512;j++)if(d.out_acc_o[j]!=0x3f800000)throw std::runtime_error("preedge 1x1 result");
 if(tick)c.timeInc(1);d.clk_i=level;d.eval();ok(retained_matrix_unseeded_v2_clock(h,level));ok(retained_matrix_unseeded_v2_read(h,a.data(),521));
 b[0]=d.cmd_ready_o;b[1]=d.step_ready_o;b[2]=d.out_valid_o;b[3]=d.out_context_o;b[4]=d.out_last_o;for(int j=0;j<512;j++)b[5+j]=d.out_acc_o[j];b[517]=d.completion_valid_o;b[518]=uint32_t(d.completion_data_o);b[519]=uint32_t(d.completion_data_o>>32);b[520]=d.protocol_error_o;
 if(a!=b)throw std::runtime_error("snapshot mismatch at tick "+std::to_string(tick));compared+=521;
 if(out){outputs++;}if(comp)completions++;command|=takeCmd;step|=takeStep;
}
uint64_t rise=0,fall=0;ok(retained_matrix_unseeded_v2_edge_counts(h,&rise,&fall));std::cerr<<"before_destroy"<<std::endl;ok(retained_matrix_unseeded_v2_destroy(h));std::cerr<<"after_destroy"<<std::endl;if(!command||!step||outputs!=1||completions!=1||rise!=200||fall!=199)throw std::runtime_error("coverage");std::cout<<"PASS C_ABI_VS_DIRECT_REAL_RTL ticks=400 words="<<compared<<" rises="<<rise<<" falls="<<fall<<" output_beats="<<outputs<<" completions="<<completions<<" one512_MAC_slice_only_not_full4096\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
