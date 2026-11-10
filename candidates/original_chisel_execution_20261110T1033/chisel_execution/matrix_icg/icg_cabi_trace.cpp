#include "passive_native_mapping.h"
#include "retained_icg_leaf.h"
#include "trace_io.h"
#include <memory>
static void check(int x){if(x!=0)throw std::runtime_error("native ICG API error "+std::to_string(x));}
struct Cleanup{void operator()(void* p)const{retained_icg_destroy(p);}};
int main(int argc,char** argv){try{
 require_argc(argc,2);auto rows=read_rows(argv[1],3,4096);
 std::unique_ptr<void,Cleanup> h(retained_icg_create());if(!h)throw std::runtime_error("create");passive_native_mapping::capture("icg_cabi");
 for(size_t i=0;i<rows.size();++i){const auto& r=rows[i];check(retained_icg_drive(h.get(),r[1],r[2]));check(retained_icg_eval(h.get()));check(retained_icg_clock(h.get(),r[0]));uint32_t out,repeat;uint64_t p,n,gp,gn;
  check(retained_icg_read(h.get(),&out));check(retained_icg_read(h.get(),&repeat));if(out!=repeat)throw std::runtime_error("read mutated state");check(retained_icg_edge_counts(h.get(),&p,&n,&gp,&gn));
  std::cout<<i<<" "<<r[0]<<" "<<out<<" "<<p<<" "<<n<<" "<<gp<<" "<<gn<<"\n";
 }
 void* p=h.release();check(retained_icg_destroy(p));return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}}
