#include "VOriginalIdmaAdapterProbe.h"
#include "verilated.h"
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <stdexcept>
#include <memory>
#include <fstream>
#include <exception>
static std::vector<uint32_t> parse(const std::string&s,unsigned w){
 if(s.empty()||s.size()>(w+3)/4)throw std::runtime_error("input width");
 std::vector<uint32_t> v((w+31)/32,0);
 for(size_t j=0;j<s.size();++j){char c=s[s.size()-1-j];unsigned x;
 if(c>='0'&&c<='9')x=c-'0';else if(c>='a'&&c<='f')x=c-'a'+10;else throw std::runtime_error("hex input");
 v[j/8]|=uint32_t(x)<<((j%8)*4);}
 if(w%32 && (v.back()>>(w%32)))throw std::runtime_error("high input bits");return v;
}
static std::string hexwords(const uint32_t*v,unsigned w){
 static const char*d="0123456789abcdef";std::string s;
 for(int i=(w+3)/4-1;i>=0;--i)s+=d[(v[i/8]>>((i%8)*4))&15];return s;
}
int main(int argc,char**argv){
 std::unique_ptr<VerilatedContext> ctx;std::unique_ptr<VOriginalIdmaAdapterProbe> dut;std::string failure;size_t row=0;
 try{
 if(argc!=2)throw std::runtime_error("fresh trace filename required");
 std::ifstream exists(argv[1]);if(exists.good())throw std::runtime_error("fresh trace only");
 std::ofstream trace(argv[1]);trace.exceptions(std::ios::badbit|std::ios::failbit);
 trace<<"CONSTRUCTOR_BEGIN\n"<<std::flush;
 ctx=std::make_unique<VerilatedContext>();ctx->threads(1);ctx->commandArgs(argc,argv);
 dut=std::make_unique<VOriginalIdmaAdapterProbe>(ctx.get());
 trace<<"CONSTRUCTOR_END no_explicit_eval=true\n"<<std::flush;
 std::string line;std::vector<std::string> previous;
 while(std::getline(std::cin,line)){if(line.size()>16384||++row>4096)throw std::runtime_error("bounded transport");
 if(trace.tellp()>8*1024*1024)throw std::runtime_error("incremental trace cap");
 trace<<"INPUT "<<row<<" "<<line<<"\n"<<std::flush;
 std::istringstream in(line);std::vector<std::string> s;std::string x;while(in>>x)s.push_back(x);
 if(s.size()!=37)throw std::runtime_error("complete input snapshot");
 auto ck=parse(s[0],1)[0],rst=parse(s[1],1)[0];
 std::vector<std::string> normalized;for(const auto&token:s){auto k=token.find_first_not_of('0');normalized.push_back(k==std::string::npos?"0":token.substr(k));}
 if(!previous.empty()&&(previous[0]=="1"||normalized[0]=="1"))for(size_t k=1;k<s.size();++k)if(normalized[k]!=previous[k])throw std::runtime_error("only low-to-low frames may change nonclock inputs");
 previous=normalized;
 if(row<=4){const unsigned clocks[4]={0,0,1,0},resets[4]={0,1,1,1};
 if(ck!=clocks[row-1]||rst!=resets[row-1])throw std::runtime_error("original four startup frames");
 for(size_t i=2;i<s.size();++i)if(s[i].find_first_not_of('0')!=std::string::npos)throw std::runtime_error("startup nonclock input must be zero");}

 {auto v=parse(s[2],1);dut->io_axi_ar_ready=v[0];}
 {auto v=parse(s[3],1);dut->io_axi_aw_ready=v[0];}
 {auto v=parse(s[4],8);dut->io_axi_b_bits_id=v[0];}
 {auto v=parse(s[5],2);dut->io_axi_b_bits_resp=v[0];}
 {auto v=parse(s[6],1);dut->io_axi_b_valid=v[0];}
 {auto v=parse(s[7],512);for(unsigned j=0;j<16;++j)dut->io_axi_r_bits_data[j]=v[j];}
 {auto v=parse(s[8],8);dut->io_axi_r_bits_id=v[0];}
 {auto v=parse(s[9],1);dut->io_axi_r_bits_last=v[0];}
 {auto v=parse(s[10],2);dut->io_axi_r_bits_resp=v[0];}
 {auto v=parse(s[11],1);dut->io_axi_r_valid=v[0];}
 {auto v=parse(s[12],1);dut->io_axi_w_ready=v[0];}
 {auto v=parse(s[13],1);dut->io_flush=v[0];}
 {auto v=parse(s[14],64);dut->io_request_bits_address=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[15],512);for(unsigned j=0;j<16;++j)dut->io_request_bits_data[j]=v[j];}
 {auto v=parse(s[16],64);dut->io_request_bits_mask=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[17],64);dut->io_request_bits_tag=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[18],1);dut->io_request_bits_write=v[0];}
 {auto v=parse(s[19],1);dut->io_request_valid=v[0];}
 {auto v=parse(s[20],1);dut->io_response_ready=v[0];}
 {auto v=parse(s[21],64);dut->io_streamRequest_bits_address=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[22],7);dut->io_streamRequest_bits_beats=v[0];}
 {auto v=parse(s[23],64);dut->io_streamRequest_bits_tag=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[24],1);dut->io_streamRequest_valid=v[0];}
 {auto v=parse(s[25],1);dut->io_streamResponse_ready=v[0];}
 {auto v=parse(s[26],512);for(unsigned j=0;j<16;++j)dut->io_streamWriteData_bits_data[j]=v[j];}
 {auto v=parse(s[27],1);dut->io_streamWriteData_bits_last=v[0];}
 {auto v=parse(s[28],1);dut->io_streamWriteData_valid=v[0];}
 {auto v=parse(s[29],64);dut->io_streamWriteRequest_bits_address=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[30],5);dut->io_streamWriteRequest_bits_beats=v[0];}
 {auto v=parse(s[31],64);dut->io_streamWriteRequest_bits_tag=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[32],1);dut->io_streamWriteRequest_valid=v[0];}
 {auto v=parse(s[33],1);dut->io_streamWriteResponse_ready=v[0];}
 {auto v=parse(s[34],64);dut->io_window_base=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 {auto v=parse(s[35],1);dut->io_window_enable=v[0];}
 {auto v=parse(s[36],64);dut->io_window_limit=uint64_t(v[0])|(uint64_t(v[1])<<32);}
 dut->reset=rst;dut->clock=ck;dut->eval();
 if(ctx->gotFinish())throw std::runtime_error("unexpected RTL finish before frame observation");
 std::ostringstream output;output<<"ROW "<<row<<" ";
 {uint64_t z=dut->io_axi_ar_bits_addr;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_axi_ar_bits_burst;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,2)<<" ";}
 {uint64_t z=dut->io_axi_ar_bits_id;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,8)<<" ";}
 {uint64_t z=dut->io_axi_ar_bits_len;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,8)<<" ";}
 {uint64_t z=dut->io_axi_ar_bits_size;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,3)<<" ";}
 {uint64_t z=dut->io_axi_ar_valid;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_axi_aw_bits_addr;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_axi_aw_bits_burst;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,2)<<" ";}
 {uint64_t z=dut->io_axi_aw_bits_id;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,8)<<" ";}
 {uint64_t z=dut->io_axi_aw_bits_len;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,8)<<" ";}
 {uint64_t z=dut->io_axi_aw_bits_size;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,3)<<" ";}
 {uint64_t z=dut->io_axi_aw_valid;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_axi_b_ready;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_axi_r_ready;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 output<<hexwords(dut->io_axi_w_bits_data.data(),512)<<" ";
 {uint64_t z=dut->io_axi_w_bits_last;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_axi_w_bits_strb;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_axi_w_valid;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_cacheHits;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_completedTransfers;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_readBeats;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_readBursts;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_request_ready;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_resetRequired;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_resourcesDrained;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 output<<hexwords(dut->io_response_bits_data.data(),512)<<" ";
 {uint64_t z=dut->io_response_bits_error;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_response_bits_tag;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_response_valid;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamRequest_ready;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 output<<hexwords(dut->io_streamResponse_bits_data.data(),512)<<" ";
 {uint64_t z=dut->io_streamResponse_bits_error;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamResponse_bits_last;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamResponse_bits_tag;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_streamResponse_valid;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamWriteData_ready;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamWriteRequest_ready;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 output<<hexwords(dut->io_streamWriteResponse_bits_data.data(),512)<<" ";
 {uint64_t z=dut->io_streamWriteResponse_bits_error;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamWriteResponse_bits_tag;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_streamWriteResponse_valid;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,1)<<" ";}
 {uint64_t z=dut->io_streamedBeats;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_streamedWriteBeats;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_transfers;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 {uint64_t z=dut->io_writeBeats;uint32_t v[2]={uint32_t(z),uint32_t(z>>32)};output<<hexwords(v,64)<<" ";}
 trace<<"OUTPUT "<<output.str()<<"\n"<<std::flush;std::cout<<output.str()<<std::endl;
 if(!std::cout)throw std::runtime_error("stdout transport failure");
 }
 if(!std::cin.eof()||row<4)throw std::runtime_error("incomplete input stream/startup");
 trace<<"INPUT_EOF rows="<<row<<"\n"<<std::flush;
 }catch(const std::exception&e){failure=e.what();}catch(...){failure="unknown endpoint failure";}
 try{if(dut)dut->final();}catch(const std::exception&e){failure+="; final: ";failure+=e.what();}catch(...){failure+="; final unknown";}
 dut.reset();ctx.reset();
 if(!failure.empty()){std::cerr<<failure<<std::endl;return 2;}
 std::ofstream receipt(std::string(argv[1])+".clean");receipt<<"ORIGINAL_ADAPTER_RTL_FRAME_ENDPOINT_CLEAN_FINISH rows="<<row<<" NO_TRANSACTION_OR_HOST_CLAIM\n";receipt.flush();
 return receipt.good()?0:3;
}
