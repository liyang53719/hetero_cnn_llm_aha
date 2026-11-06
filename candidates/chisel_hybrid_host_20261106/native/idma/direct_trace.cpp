/* Independent direct-port replay executable, deliberately not linked to the
   C ABI bridge. Build with the SAME pinned actual leaf generated model. */
#include "Vidma_backend_rw_axi_flat_wrap.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <stdexcept>
static void parse(const std::string& text,uint32_t* words,unsigned count,unsigned width) {
  if(text.empty()||text.size()>(width+3)/4)throw std::runtime_error("hex size");
  for(unsigned i=0;i<count;i++)words[i]=0;
  for(unsigned j=0;j<text.size();j++) {
    char c=text[text.size()-1-j];unsigned d;
    if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;
    else if(c>='A'&&c<='F')d=c-'A'+10;else throw std::runtime_error("hex character");
    words[j/8]|=d<<(4*(j%8));
  }
  if((width%32) && (words[count-1]>>(width%32)))throw std::runtime_error("packed width");
}
static std::string hex(const uint32_t* words,unsigned count) {
  std::ostringstream s;s<<std::hex<<std::setfill('0');
  for(unsigned i=count;i>0;i--)s<<std::setw(8)<<words[i-1];return s.str();
}
int main() {
 try {
  auto context=std::make_unique<VerilatedContext>();
  context->threads(1);
  auto dut=std::make_unique<Vidma_backend_rw_axi_flat_wrap>(context.get(),"retained_idma");
  dut->clk_i=0;unsigned previous=0,count=0;std::string line;
  while(std::getline(std::cin,line)) {
    if(++count>4096||line.size()>1024)throw std::runtime_error("trace cap");
    std::istringstream in(line);unsigned clock,reset,request,response;
    uint64_t source,destination;uint32_t length;std::string read,write,extra;
    if(!(in>>clock>>reset>>request>>std::hex>>source>>destination>>length>>
         std::dec>>response>>read>>write)||in>>extra)throw std::runtime_error("trace row");
    if(clock>1||reset>1||request>1||response>1)throw std::runtime_error("boolean");
    dut->rst_ni=reset;dut->req_valid_i=request;dut->src_addr_i=source;
    dut->dst_addr_i=destination;dut->length_i=length;dut->rsp_ready_i=response;
    parse(read,dut->axi_read_rsp_i.data(),17,532);
    parse(write,dut->axi_write_rsp_i.data(),17,532);
    dut->eval(); // settle complete pre-edge inputs before explicit edge
    if(previous!=clock)context->timeInc(1);
    dut->clk_i=clock;previous=clock;dut->eval();
    if(context->gotFinish())throw std::runtime_error("unexpected finish");
    std::cout<<unsigned(dut->req_ready_o)<<' '<<unsigned(dut->rsp_valid_o)<<' '
      <<unsigned(dut->rsp_error_o)<<' '<<unsigned(dut->busy_o)<<' '
      <<hex(dut->axi_read_req_o.data(),25)<<' '<<hex(dut->axi_write_req_o.data(),25)<<'\n';
  }
  dut->final();return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
