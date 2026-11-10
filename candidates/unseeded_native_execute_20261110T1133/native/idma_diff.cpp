#include "retained_idma_leaf.h"
#include "Vidma_backend_rw_axi_flat_wrap.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <stdexcept>
void ok(int n){if(n)throw std::runtime_error("ABI status");}
int main(){try{VerilatedContext c;c.threads(1);Vidma_backend_rw_axi_flat_wrap d(&c);d.clk_i=0;void*h=retained_idma_create();if(!h)throw std::runtime_error("create");bool accepted=false,sawBusy=false;unsigned compared=0;std::array<uint32_t,17>r{};std::array<uint32_t,54>a{},b{};for(unsigned t=0;t<160;t++){unsigned cy=t/2,l=t%2,reset=cy>=3&&cy<60;unsigned valid=reset&&cy>=4&&!accepted;d.rst_ni=reset;d.req_valid_i=valid;d.src_addr_i=0x1000;d.dst_addr_i=0x2000;d.length_i=64;d.rsp_ready_i=1;for(int j=0;j<17;j++){d.axi_read_rsp_i[j]=0;d.axi_write_rsp_i[j]=0;}Verilated::threadContextp(&c);d.eval();ok(retained_idma_drive(h,reset,valid,0x1000,0x2000,64,1,r.data(),r.data()));ok(retained_idma_eval(h));if(l&&valid&&d.req_ready_o)accepted=true;if(t)c.timeInc(1);d.clk_i=l;Verilated::threadContextp(&c);d.eval();ok(retained_idma_clock(h,l));ok(retained_idma_read(h,&a[0],&a[1],&a[2],&a[3],&a[4],&a[29]));b[0]=d.req_ready_o;b[1]=d.rsp_valid_o;b[2]=d.rsp_error_o;b[3]=d.busy_o;for(int j=0;j<25;j++){b[4+j]=d.axi_read_req_o[j];b[29+j]=d.axi_write_req_o[j];}if(a!=b)throw std::runtime_error("snapshot");sawBusy|=a[3];compared+=54;}
ok(retained_idma_destroy_checked(h));Verilated::threadContextp(&c);d.final();if(!accepted||!sawBusy)throw std::runtime_error("coverage");std::cout<<"PASS iDMA real direct-vs-CABI words="<<compared<<" accepted_req=1 stalled_AXI_and_reset=1 no_transfer_completion_claim\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
