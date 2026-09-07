// Generated test fixture with the retained public ISA encoder. No RTL edits.
#pragma once
#include <cstdint>
struct TensorSpec { const char* name; uint64_t address; uint64_t words; bool readonly; bool virtualValue; };
static constexpr uint64_t BASE=4294967296ULL;
static constexpr uint64_t COMMAND_BASE=4294967296ULL;
static constexpr uint64_t COMMAND_LIMIT=4294967680ULL;
static constexpr uint64_t DESC_BASE=4294971392ULL;
static constexpr uint64_t DESC_LIMIT=4294974848ULL;
static constexpr uint64_t META_LIMIT=4295032832ULL;
static constexpr uint64_t SCRATCH=4295575488ULL;
static constexpr uint64_t LIMIT=4317465920ULL;
static constexpr unsigned TOKENS=1024,DESCRIPTORS=215,COMMANDS=21;
static constexpr uint64_t A_WQ=4295032896ULL;
static constexpr uint64_t A_WK=4295049344ULL;
static constexpr uint64_t A_WV=4295057600ULL;
static constexpr uint64_t A_WO=4295065856ULL;
static constexpr uint64_t A_WG=4295082304ULL;
static constexpr uint64_t A_WU=4295115136ULL;
static constexpr uint64_t A_WD=4295147968ULL;
static constexpr uint64_t A_GAMMA0=4295180800ULL;
static constexpr uint64_t A_GAMMA1=4295181120ULL;
static constexpr uint64_t A_BQ=4295181440ULL;
static constexpr uint64_t A_BK=4295181760ULL;
static constexpr uint64_t A_BV=4295181952ULL;
static constexpr uint64_t A_ROPE=4295182144ULL;
static constexpr uint64_t A_X=4295313280ULL;
static constexpr uint64_t A_N0=4295575552ULL;
static constexpr uint64_t A_QRAW=4295837760ULL;
static constexpr uint64_t A_QR=4296099968ULL;
static constexpr uint64_t A_Q=4296362176ULL;
static constexpr uint64_t A_KRAW=4296624384ULL;
static constexpr uint64_t A_KR=4296755520ULL;
static constexpr uint64_t A_K=4296886656ULL;
static constexpr uint64_t A_VRAW=4297017792ULL;
static constexpr uint64_t A_V=4297148928ULL;
static constexpr uint64_t A_KV=4297280064ULL;
static constexpr uint64_t A_CACHE_K=4297280064ULL;
static constexpr uint64_t A_CACHE_V=4297411136ULL;
static constexpr uint64_t A_SCORES=4297542272ULL;
static constexpr uint64_t A_PROBABILITIES=4305930944ULL;
static constexpr uint64_t A_ATT=4314319616ULL;
static constexpr uint64_t A_O=4314581824ULL;
static constexpr uint64_t A_R=4314844032ULL;
static constexpr uint64_t A_N1=4315106240ULL;
static constexpr uint64_t A_GATE=4315368448ULL;
static constexpr uint64_t A_UP=4315892800ULL;
static constexpr uint64_t A_ACT=4316417152ULL;
static constexpr uint64_t A_DOWN=4316941504ULL;
static constexpr uint64_t A_Y=4317203712ULL;
static const TensorSpec ALLOCATIONS[]={
{"wq",4295032896ULL,4096ULL,true,false},
{"wk",4295049344ULL,2048ULL,true,false},
{"wv",4295057600ULL,2048ULL,true,false},
{"wo",4295065856ULL,4096ULL,true,false},
{"wg",4295082304ULL,8192ULL,true,false},
{"wu",4295115136ULL,8192ULL,true,false},
{"wd",4295147968ULL,8192ULL,true,false},
{"gamma0",4295180800ULL,64ULL,true,false},
{"gamma1",4295181120ULL,64ULL,true,false},
{"bq",4295181440ULL,64ULL,true,false},
{"bk",4295181760ULL,32ULL,true,false},
{"bv",4295181952ULL,32ULL,true,false},
{"rope",4295182144ULL,32768ULL,true,false},
{"x",4295313280ULL,65536ULL,true,false},
{"n0",4295575552ULL,65536ULL,false,false},
{"qraw",4295837760ULL,65536ULL,false,false},
{"qr",4296099968ULL,65536ULL,false,false},
{"q",4296362176ULL,65536ULL,false,false},
{"kraw",4296624384ULL,32768ULL,false,false},
{"kr",4296755520ULL,32768ULL,false,false},
{"k",4296886656ULL,32768ULL,false,false},
{"vraw",4297017792ULL,32768ULL,false,false},
{"v",4297148928ULL,32768ULL,false,false},
{"kv",4297280064ULL,65536ULL,false,false},
{"scores",4297542272ULL,2097152ULL,false,true},
{"probabilities",4305930944ULL,2097152ULL,false,true},
{"att",4314319616ULL,65536ULL,false,false},
{"o",4314581824ULL,65536ULL,false,false},
{"r",4314844032ULL,65536ULL,false,false},
{"n1",4315106240ULL,65536ULL,false,false},
{"gate",4315368448ULL,131072ULL,false,false},
{"up",4315892800ULL,131072ULL,false,false},
{"act",4316417152ULL,131072ULL,false,false},
{"down",4316941504ULL,65536ULL,false,false},
{"y",4317203712ULL,65536ULL,false,false},
};
