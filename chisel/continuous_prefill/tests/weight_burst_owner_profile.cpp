// SPDX-License-Identifier: Apache-2.0
// Observe public DUT counters at existing completion checks. No DUT changes,
// alternate scheduling, shortened run, or arithmetic callbacks are introduced.
#define main original_host_block_main
#include "host_block_commands.cpp"
#undef main
#include <sstream>
#include <streambuf>

class CompletionProfile final : public std::streambuf {
  std::streambuf* target;
  Test& dut;
  std::ofstream csv;
  std::string line;
  unsigned rows=0;
  void consume(const char* data,std::streamsize n) {
    for(std::streamsize i=0;i<n;++i) {
      if(data[i]!='\n'){line.push_back(data[i]);continue;}
      if(line.rfind("OWNER_COMPLETION pc=",0)==0) {
        unsigned pc=std::stoul(line.substr(20));
        check(pc==rows,"profile completion order");
        csv<<pc<<','<<dut.cycles<<','<<dut.d.io_idmaTransfers<<','<<dut.d.io_idmaReadBursts
           <<','<<dut.d.io_idmaReadBeats<<','<<dut.d.io_idmaCacheHits
           <<','<<dut.d.io_usefulMacs<<','<<dut.d.io_executedMacs<<','<<dut.d.io_writeBytes
           <<','<<dut.d.io_memoryAccepted_0<<','<<dut.d.io_memoryAccepted_1<<'\n';
        check(bool(csv),"profile output failed");++rows;
      }
      line.clear();
    }
  }
protected:
  std::streamsize xsputn(const char* p,std::streamsize n) override {
    auto done=target->sputn(p,n);consume(p,done);return done;
  }
  int overflow(int c) override {
    if(c==traits_type::eof())return traits_type::not_eof(c);
    char ch=char(c);if(target->sputc(ch)==traits_type::eof())return traits_type::eof();
    consume(&ch,1);return c;
  }
  int sync() override {csv.flush();return target->pubsync();}
public:
  CompletionProfile(std::streambuf* p,Test& t,const std::filesystem::path& output):target(p),dut(t) {
    check(!std::filesystem::exists(output),"preserve profile file");csv.open(output);
    check(bool(csv),"cannot open profile");
    csv<<"pc,cycle,idma_transfers,read_bursts,read_beats,cache_hits,useful_macs,executed_macs,write_ack_bytes,metadata_requests,payload_requests\n";
  }
  void finish(){check(rows==COMMANDS,"incomplete profile");csv.flush();check(bool(csv),"incomplete profile file");}
};

int main(int argc,char**argv){try {
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  check(argc==3,"FIXTURE NEW_OUTPUT");
  check(OWNER_MATRIX_MACS==4096&&OWNER_WEIGHT_READ_BEATS==16&&TOKENS==16&&LAYERS==2,"fixed profile");
  std::filesystem::path fixture=argv[1],out=argv[2];check(!std::filesystem::exists(out),"preserve old evidence");
  std::filesystem::create_directories(out);
  auto t=std::make_unique<Test>("pass",out/"tensors");t->initialize(fixture);
  auto original=std::cout.rdbuf();CompletionProfile profile(original,*t,out/"owner_counters.csv");
  std::cout.rdbuf(&profile);
  try {t->launch();profile.finish();std::cout.rdbuf(original);}
  catch(...){std::cout.rdbuf(original);throw;}
  std::cout<<"WEIGHT_BURST_OWNER_PROFILE_PASS commands="<<COMMANDS
    <<" checked_fp32="<<t->checked<<" same_hardware=1 changed_schedule=0"<<std::endl;
  return 0;
}catch(const std::exception&e){std::cerr<<"WEIGHT_BURST_OWNER_PROFILE_FAIL: "<<e.what()<<std::endl;return 1;}}
