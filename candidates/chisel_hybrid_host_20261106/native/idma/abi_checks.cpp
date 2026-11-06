#include "Vidma_backend_rw_axi_flat_wrap.h"
#include "retained_idma_leaf.h"
#include <cstdint>
#include <type_traits>
using DUT=Vidma_backend_rw_axi_flat_wrap;
static_assert(sizeof(uint32_t)==4 && sizeof(uint64_t)==8);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::clk_i)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::rst_ni)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::req_valid_i)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::req_ready_o)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::rsp_valid_o)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::rsp_ready_i)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::rsp_error_o)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::busy_o)>,CData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::src_addr_i)>,QData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::dst_addr_i)>,QData>);
static_assert(std::is_same_v<std::remove_reference_t<decltype(DUT::length_i)>,IData>);
static_assert(sizeof(DUT::axi_read_rsp_i)==17*sizeof(uint32_t));
static_assert(sizeof(DUT::axi_write_rsp_i)==17*sizeof(uint32_t));
static_assert(sizeof(DUT::axi_read_req_o)==25*sizeof(uint32_t));
static_assert(sizeof(DUT::axi_write_req_o)==25*sizeof(uint32_t));
