// Generated test fixture with the retained public ISA encoder. No RTL edits.
#pragma once
#include <cstdint>
struct TensorSpec { const char* name; uint64_t address; uint64_t words; bool readonly; bool virtualValue; };
static constexpr uint64_t BASE=13762953216ULL;
static constexpr uint64_t COMMAND_BASE=13762953216ULL;
static constexpr uint64_t COMMAND_LIMIT=13762953600ULL;
static constexpr uint64_t DESC_BASE=13762957312ULL;
static constexpr uint64_t DESC_LIMIT=13762960768ULL;
static constexpr uint64_t META_LIMIT=13763018752ULL;
static constexpr uint64_t SCRATCH=13763307712ULL;
static constexpr uint64_t LIMIT=13763491392ULL;
static constexpr unsigned TOKENS=33,DESCRIPTORS=215,COMMANDS=21;
static constexpr uint64_t A_WQ=13763018816ULL;
static constexpr uint64_t A_WK=13763035264ULL;
static constexpr uint64_t A_WV=13763043520ULL;
static constexpr uint64_t A_WO=13763051776ULL;
static constexpr uint64_t A_WG=13763068224ULL;
static constexpr uint64_t A_WU=13763101056ULL;
static constexpr uint64_t A_WD=13763133888ULL;
static constexpr uint64_t A_GAMMA0=13763166720ULL;
static constexpr uint64_t A_GAMMA1=13763167040ULL;
static constexpr uint64_t A_BQ=13763167360ULL;
static constexpr uint64_t A_BK=13763167680ULL;
static constexpr uint64_t A_BV=13763167872ULL;
static constexpr uint64_t A_ROPE=13763168064ULL;
static constexpr uint64_t A_X=13763299200ULL;
static constexpr uint64_t A_N0=13763307776ULL;
static constexpr uint64_t A_QRAW=13763316288ULL;
static constexpr uint64_t A_QR=13763324800ULL;
static constexpr uint64_t A_Q=13763333312ULL;
static constexpr uint64_t A_KRAW=13763341824ULL;
static constexpr uint64_t A_KR=13763346112ULL;
static constexpr uint64_t A_K=13763350400ULL;
static constexpr uint64_t A_VRAW=13763354688ULL;
static constexpr uint64_t A_V=13763358976ULL;
static constexpr uint64_t A_KV=13763363264ULL;
static constexpr uint64_t A_CACHE_K=13763363264ULL;
static constexpr uint64_t A_CACHE_V=13763367488ULL;
static constexpr uint64_t A_SCORES=13763371776ULL;
static constexpr uint64_t A_PROBABILITIES=13763380608ULL;
static constexpr uint64_t A_ATT=13763389440ULL;
static constexpr uint64_t A_O=13763397952ULL;
static constexpr uint64_t A_R=13763406464ULL;
static constexpr uint64_t A_N1=13763414976ULL;
static constexpr uint64_t A_GATE=13763423488ULL;
static constexpr uint64_t A_UP=13763440448ULL;
static constexpr uint64_t A_ACT=13763457408ULL;
static constexpr uint64_t A_DOWN=13763474368ULL;
static constexpr uint64_t A_Y=13763482880ULL;
static const TensorSpec ALLOCATIONS[]={
{"wq",13763018816ULL,4096ULL,true,false},
{"wk",13763035264ULL,2048ULL,true,false},
{"wv",13763043520ULL,2048ULL,true,false},
{"wo",13763051776ULL,4096ULL,true,false},
{"wg",13763068224ULL,8192ULL,true,false},
{"wu",13763101056ULL,8192ULL,true,false},
{"wd",13763133888ULL,8192ULL,true,false},
{"gamma0",13763166720ULL,64ULL,true,false},
{"gamma1",13763167040ULL,64ULL,true,false},
{"bq",13763167360ULL,64ULL,true,false},
{"bk",13763167680ULL,32ULL,true,false},
{"bv",13763167872ULL,32ULL,true,false},
{"rope",13763168064ULL,32768ULL,true,false},
{"x",13763299200ULL,2112ULL,true,false},
{"n0",13763307776ULL,2112ULL,false,false},
{"qraw",13763316288ULL,2112ULL,false,false},
{"qr",13763324800ULL,2112ULL,false,false},
{"q",13763333312ULL,2112ULL,false,false},
{"kraw",13763341824ULL,1056ULL,false,false},
{"kr",13763346112ULL,1056ULL,false,false},
{"k",13763350400ULL,1056ULL,false,false},
{"vraw",13763354688ULL,1056ULL,false,false},
{"v",13763358976ULL,1056ULL,false,false},
{"kv",13763363264ULL,2112ULL,false,false},
{"scores",13763371776ULL,2178ULL,false,true},
{"probabilities",13763380608ULL,2178ULL,false,true},
{"att",13763389440ULL,2112ULL,false,false},
{"o",13763397952ULL,2112ULL,false,false},
{"r",13763406464ULL,2112ULL,false,false},
{"n1",13763414976ULL,2112ULL,false,false},
{"gate",13763423488ULL,4224ULL,false,false},
{"up",13763440448ULL,4224ULL,false,false},
{"act",13763457408ULL,4224ULL,false,false},
{"down",13763474368ULL,2112ULL,false,false},
{"y",13763482880ULL,2112ULL,false,false},
};
