#include "retained_idma_leaf.h"
#include "Vidma_backend_rw_axi_flat_wrap.h"
#include "verilated.h"
#include <cstdint>
#include <memory>
#include <new>
#include <type_traits>

namespace {
struct Leaf {
  std::unique_ptr<VerilatedContext> context;
  std::unique_ptr<Vidma_backend_rw_axi_flat_wrap> dut;
  bool driven = false;
  bool evaluated = false;
  bool low_evaluated = false;
  uint32_t clock_level = 0;
  Leaf(): context(new VerilatedContext) {
    context->threads(1);
    dut.reset(new Vidma_backend_rw_axi_flat_wrap(context.get(), "retained_idma"));
    dut->clk_i = 0;
  }
};
bool bit(uint32_t value) { return value <= 1; }
constexpr uint32_t response_top_mask = (uint32_t(1) << 20) - 1; // 532 bits
constexpr uint32_t request_top_mask = (uint32_t(1) << 17) - 1; // 785 bits
static_assert(sizeof(uint32_t)==4 && sizeof(uint64_t)==8);
}
extern "C" void* retained_idma_create() {
  try { return new Leaf; } catch (...) { return nullptr; }
}
extern "C" void retained_idma_destroy(void* handle) {
  (void)retained_idma_destroy_checked(handle);
}
extern "C" int retained_idma_destroy_checked(void* handle) {
  if (!handle) return 0;
  std::unique_ptr<Leaf> s(static_cast<Leaf*>(handle));
  try { s->dut->final(); } catch (...) { return -5; }
  return 0;
}
extern "C" uint32_t retained_idma_abi_version(void) { return 1; }
extern "C" uint32_t retained_idma_response_words(void) { return 17; }
extern "C" uint32_t retained_idma_request_words(void) { return 25; }
extern "C" int retained_idma_drive(void* handle, uint32_t reset_n,
  uint32_t request_valid, uint64_t source, uint64_t destination, uint32_t length,
  uint32_t response_ready, const uint32_t* read_response_17,
  const uint32_t* write_response_17) {
  if (!handle || !read_response_17 || !write_response_17 || !bit(reset_n) ||
      !bit(request_valid) || !bit(response_ready) ||
      (read_response_17[16] & ~response_top_mask) ||
      (write_response_17[16] & ~response_top_mask)) return -1;
  Leaf& s=*static_cast<Leaf*>(handle);
  s.dut->rst_ni=reset_n; s.dut->req_valid_i=request_valid;
  s.dut->src_addr_i=source; s.dut->dst_addr_i=destination;
  s.dut->length_i=length; s.dut->rsp_ready_i=response_ready;
  for (unsigned i=0;i<17;i++) {
    s.dut->axi_read_rsp_i[i]=read_response_17[i];
    s.dut->axi_write_rsp_i[i]=write_response_17[i];
  }
  s.driven=true;s.evaluated=false;return 0;
}
extern "C" int retained_idma_eval(void* handle) {
  if (!handle) return -1;
  Leaf& s=*static_cast<Leaf*>(handle);
  if (!s.driven) return -2;
  s.evaluated=false;
  try { s.dut->eval(); } catch (...) { return -5; }
  if (s.context->gotFinish()) return -3;
  s.evaluated=true;
  if (s.clock_level==0) s.low_evaluated=true;
  return 0;
}
extern "C" int retained_idma_clock(void* handle,uint32_t level) {
  if (!handle || !bit(level)) return -1;
  Leaf& s=*static_cast<Leaf*>(handle);
  // Never manufacture an initial edge or clock unsampled current inputs.
  if (!s.evaluated || (level==1 && !s.low_evaluated)) return -2;
  if (s.clock_level!=level) s.context->timeInc(1);
  s.clock_level=level;s.dut->clk_i=level;s.evaluated=false;
  return retained_idma_eval(handle);
}
extern "C" int retained_idma_read(void* handle,uint32_t* request_ready,
  uint32_t* response_valid,uint32_t* response_error,uint32_t* busy,
  uint32_t* read_request_25,uint32_t* write_request_25) {
  if (!handle || !request_ready || !response_valid || !response_error || !busy ||
      !read_request_25 || !write_request_25) return -1;
  Leaf& s=*static_cast<Leaf*>(handle);if (!s.evaluated) return -2;
  *request_ready=s.dut->req_ready_o;*response_valid=s.dut->rsp_valid_o;
  *response_error=s.dut->rsp_error_o;*busy=s.dut->busy_o;
  for(unsigned i=0;i<25;i++) {
    read_request_25[i]=s.dut->axi_read_req_o[i];
    write_request_25[i]=s.dut->axi_write_req_o[i];
  }
  if ((read_request_25[24]&~request_top_mask) ||
      (write_request_25[24]&~request_top_mask)) return -4;
  return 0;
}
