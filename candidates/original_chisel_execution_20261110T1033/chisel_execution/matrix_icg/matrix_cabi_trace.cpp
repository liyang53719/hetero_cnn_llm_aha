#include "passive_native_mapping.h"
#include "retained_matrix_leaf.h"
#include "trace_io.h"
#include <memory>
static void check(int x){if(x!=0)throw std::runtime_error("native API error "+std::to_string(x));}
struct Cleanup{void operator()(void* p)const{retained_matrix_destroy(p);}};
int main(int argc,char** argv){try{
 require_argc(argc,2);auto rows=read_rows(argv[1],64,4096);
 if(retained_matrix_abi_version()!=RETAINED_MATRIX_ABI_VERSION)throw std::runtime_error("ABI version");
 std::unique_ptr<void,Cleanup> h(retained_matrix_create());if(!h)throw std::runtime_error("create");passive_native_mapping::capture("matrix_cabi");
 for(size_t i=0;i<rows.size();++i){const auto& r=rows[i];check(retained_matrix_drive(h.get(),r.data()+1,63));check(retained_matrix_eval(h.get()));check(retained_matrix_clock(h.get(),r[0]));
  std::vector<uint32_t> result(533),repeat(533);uint64_t p,n;
  check(retained_matrix_read(h.get(),result.data(),533));check(retained_matrix_read(h.get(),repeat.data(),533));if(result!=repeat)throw std::runtime_error("read mutated output");
  check(retained_matrix_edge_counts(h.get(),&p,&n));print_row(i,r[0],result,p,n);
 }
 void* raw=h.release();check(retained_matrix_destroy(raw));return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}}
