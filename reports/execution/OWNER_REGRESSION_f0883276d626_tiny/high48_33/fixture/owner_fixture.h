// Generated test fixture with the retained public ISA encoder. No RTL edits.
#pragma once
#include <cstdint>
struct TensorSpec { const char* name; uint64_t address; uint64_t words; bool readonly; bool virtualValue; };
static constexpr uint64_t BASE=281479271677952ULL;
static constexpr uint64_t COMMAND_BASE=281479271677952ULL;
static constexpr uint64_t COMMAND_LIMIT=281479271678336ULL;
static constexpr uint64_t DESC_BASE=281479271682048ULL;
static constexpr uint64_t DESC_LIMIT=281479271685504ULL;
static constexpr uint64_t META_LIMIT=281479271743488ULL;
static constexpr uint64_t SCRATCH=281479272032448ULL;
static constexpr uint64_t LIMIT=281479272216128ULL;
static constexpr unsigned TOKENS=33,DESCRIPTORS=215,COMMANDS=21;
static constexpr uint64_t A_WQ=281479271776512ULL;
static constexpr uint64_t A_WK=281479271760000ULL;
static constexpr uint64_t A_WV=281479271768256ULL;
static constexpr uint64_t A_WO=281479271743552ULL;
static constexpr uint64_t A_WG=281479271792960ULL;
static constexpr uint64_t A_WU=281479271825792ULL;
static constexpr uint64_t A_WD=281479271858624ULL;
static constexpr uint64_t A_GAMMA0=281479271891456ULL;
static constexpr uint64_t A_GAMMA1=281479271891776ULL;
static constexpr uint64_t A_BQ=281479271892096ULL;
static constexpr uint64_t A_BK=281479271892416ULL;
static constexpr uint64_t A_BV=281479271892608ULL;
static constexpr uint64_t A_ROPE=281479271892800ULL;
static constexpr uint64_t A_X=281479272023936ULL;
static constexpr uint64_t A_N0=281479272032512ULL;
static constexpr uint64_t A_QRAW=281479272049536ULL;
static constexpr uint64_t A_QR=281479272041024ULL;
static constexpr uint64_t A_Q=281479272058048ULL;
static constexpr uint64_t A_KRAW=281479272066560ULL;
static constexpr uint64_t A_KR=281479272070848ULL;
static constexpr uint64_t A_K=281479272075136ULL;
static constexpr uint64_t A_VRAW=281479272079424ULL;
static constexpr uint64_t A_V=281479272083712ULL;
static constexpr uint64_t A_KV=281479272088000ULL;
static constexpr uint64_t A_CACHE_K=281479272088000ULL;
static constexpr uint64_t A_CACHE_V=281479272092224ULL;
static constexpr uint64_t A_SCORES=281479272096512ULL;
static constexpr uint64_t A_PROBABILITIES=281479272105344ULL;
static constexpr uint64_t A_ATT=281479272122688ULL;
static constexpr uint64_t A_O=281479272114176ULL;
static constexpr uint64_t A_R=281479272131200ULL;
static constexpr uint64_t A_N1=281479272139712ULL;
static constexpr uint64_t A_GATE=281479272148224ULL;
static constexpr uint64_t A_UP=281479272165184ULL;
static constexpr uint64_t A_ACT=281479272182144ULL;
static constexpr uint64_t A_DOWN=281479272199104ULL;
static constexpr uint64_t A_Y=281479272207616ULL;
static const TensorSpec ALLOCATIONS[]={
{"wq",281479271776512ULL,4096ULL,true,false},
{"wk",281479271760000ULL,2048ULL,true,false},
{"wv",281479271768256ULL,2048ULL,true,false},
{"wo",281479271743552ULL,4096ULL,true,false},
{"wg",281479271792960ULL,8192ULL,true,false},
{"wu",281479271825792ULL,8192ULL,true,false},
{"wd",281479271858624ULL,8192ULL,true,false},
{"gamma0",281479271891456ULL,64ULL,true,false},
{"gamma1",281479271891776ULL,64ULL,true,false},
{"bq",281479271892096ULL,64ULL,true,false},
{"bk",281479271892416ULL,32ULL,true,false},
{"bv",281479271892608ULL,32ULL,true,false},
{"rope",281479271892800ULL,32768ULL,true,false},
{"x",281479272023936ULL,2112ULL,true,false},
{"n0",281479272032512ULL,2112ULL,false,false},
{"qraw",281479272049536ULL,2112ULL,false,false},
{"qr",281479272041024ULL,2112ULL,false,false},
{"q",281479272058048ULL,2112ULL,false,false},
{"kraw",281479272066560ULL,1056ULL,false,false},
{"kr",281479272070848ULL,1056ULL,false,false},
{"k",281479272075136ULL,1056ULL,false,false},
{"vraw",281479272079424ULL,1056ULL,false,false},
{"v",281479272083712ULL,1056ULL,false,false},
{"kv",281479272088000ULL,2112ULL,false,false},
{"scores",281479272096512ULL,2178ULL,false,true},
{"probabilities",281479272105344ULL,2178ULL,false,true},
{"att",281479272122688ULL,2112ULL,false,false},
{"o",281479272114176ULL,2112ULL,false,false},
{"r",281479272131200ULL,2112ULL,false,false},
{"n1",281479272139712ULL,2112ULL,false,false},
{"gate",281479272148224ULL,4224ULL,false,false},
{"up",281479272165184ULL,4224ULL,false,false},
{"act",281479272182144ULL,4224ULL,false,false},
{"down",281479272199104ULL,2112ULL,false,false},
{"y",281479272207616ULL,2112ULL,false,false},
};
