// Fixed M17 driver mapping, independent of reference iterator/table generation.
// Uses accepted-group ordinal only, never DUT token/key/selected for payload.
#pragma once
#include <cstdint>
#include <stdexcept>
namespace stimulus {
struct Group {std::uint32_t token,head,base,count;};
inline Group descriptor(std::uint64_t ordinal) {
  if(ordinal>=216)throw std::runtime_error("fixed M17 group ordinal bound");
  if(ordinal<192) {
    const auto token=std::uint32_t(ordinal/12);
    return {token,std::uint32_t(ordinal%12),0,token+1};
  }
  const auto tail=std::uint32_t(ordinal-192);
  return {16,tail/2,(tail%2)*16,(tail%2)?1u:16u};
}
inline std::uint32_t tile_word(const Group& group,unsigned row,unsigned col) {
  if(row>=16 || col>=256 || group.count<1 || group.count>16)
    throw std::runtime_error("fixed M17 tile descriptor range");
  return (col/16>=group.count || col%16!=row)?0x7fc00000u:0u;
}
}
