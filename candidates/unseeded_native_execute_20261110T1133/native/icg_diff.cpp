#include "retained_icg_leaf.h"
#include "Vtc_clk_gating.h"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
void ok(int x){if(x)throw std::runtime_error("ABI status");}
int main(){try{VerilatedContext c;c.threads(1);Vtc_clk_gating d(&c);d.clk_i=0;void*h=retained_icg_create();if(!h)throw std::runtime_error("create");unsigned prior=0,compared=0;for(unsigned i=0;i<128;i++){unsigned level=(i/2)%2,en=(i/3)%2,scan=(i/7)%2;d.en_i=en;d.test_en_i=scan;Verilated::threadContextp(&c);d.eval();ok(retained_icg_drive(h,en,scan));ok(retained_icg_eval(h));uint32_t b;ok(retained_icg_read(h,&b));if(b!=d.clk_o)throw std::runtime_error("combo");compared++;if(level!=prior)c.timeInc(1);d.clk_i=level;Verilated::threadContextp(&c);d.eval();ok(retained_icg_clock(h,level));ok(retained_icg_read(h,&b));if(b!=d.clk_o)throw std::runtime_error("edge");compared++;prior=level;}
ok(retained_icg_destroy(h));Verilated::threadContextp(&c);d.final();std::cout<<"PASS ICG real RTL direct-vs-CABI observations="<<compared<<" includes low-transparent/high-hold enable/test transitions\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
