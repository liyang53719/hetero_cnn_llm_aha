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
static constexpr uint64_t SCRATCH=13950839744ULL;
static constexpr uint64_t LIMIT=13953863104ULL;
static constexpr unsigned TOKENS=17,DESCRIPTORS=215,COMMANDS=21;
static constexpr uint64_t A_WQ=13763018816ULL;
static constexpr uint64_t A_WK=13772456064ULL;
static constexpr uint64_t A_WV=13774028992ULL;
static constexpr uint64_t A_WO=13775601920ULL;
static constexpr uint64_t A_WG=13785039168ULL;
static constexpr uint64_t A_WU=13840089472ULL;
static constexpr uint64_t A_WD=13895139776ULL;
static constexpr uint64_t A_GAMMA0=13950190080ULL;
static constexpr uint64_t A_GAMMA1=13950196288ULL;
static constexpr uint64_t A_BQ=13950202496ULL;
static constexpr uint64_t A_BK=13950208704ULL;
static constexpr uint64_t A_BV=13950209792ULL;
static constexpr uint64_t A_ROPE=13950210880ULL;
static constexpr uint64_t A_X=13950735232ULL;
static constexpr uint64_t A_N0=13950839808ULL;
static constexpr uint64_t A_QRAW=13950944320ULL;
static constexpr uint64_t A_QR=13951048832ULL;
static constexpr uint64_t A_Q=13951153344ULL;
static constexpr uint64_t A_KRAW=13951257856ULL;
static constexpr uint64_t A_KR=13951275328ULL;
static constexpr uint64_t A_K=13951292800ULL;
static constexpr uint64_t A_VRAW=13951310272ULL;
static constexpr uint64_t A_V=13951327744ULL;
static constexpr uint64_t A_KV=13951345216ULL;
static constexpr uint64_t A_CACHE_K=13951345216ULL;
static constexpr uint64_t A_CACHE_V=13951362624ULL;
static constexpr uint64_t A_SCORES=13951380096ULL;
static constexpr uint64_t A_PROBABILITIES=13951394048ULL;
static constexpr uint64_t A_ATT=13951408000ULL;
static constexpr uint64_t A_O=13951512512ULL;
static constexpr uint64_t A_R=13951617024ULL;
static constexpr uint64_t A_N1=13951721536ULL;
static constexpr uint64_t A_GATE=13951826048ULL;
static constexpr uint64_t A_UP=13952435392ULL;
static constexpr uint64_t A_ACT=13953044736ULL;
static constexpr uint64_t A_DOWN=13953654080ULL;
static constexpr uint64_t A_Y=13953758592ULL;
static const TensorSpec ALLOCATIONS[]={
{"wq",13763018816ULL,2359296ULL,true,false},
{"wk",13772456064ULL,393216ULL,true,false},
{"wv",13774028992ULL,393216ULL,true,false},
{"wo",13775601920ULL,2359296ULL,true,false},
{"wg",13785039168ULL,13762560ULL,true,false},
{"wu",13840089472ULL,13762560ULL,true,false},
{"wd",13895139776ULL,13762560ULL,true,false},
{"gamma0",13950190080ULL,1536ULL,true,false},
{"gamma1",13950196288ULL,1536ULL,true,false},
{"bq",13950202496ULL,1536ULL,true,false},
{"bk",13950208704ULL,256ULL,true,false},
{"bv",13950209792ULL,256ULL,true,false},
{"rope",13950210880ULL,131072ULL,true,false},
{"x",13950735232ULL,26112ULL,true,false},
{"n0",13950839808ULL,26112ULL,false,false},
{"qraw",13950944320ULL,26112ULL,false,false},
{"qr",13951048832ULL,26112ULL,false,false},
{"q",13951153344ULL,26112ULL,false,false},
{"kraw",13951257856ULL,4352ULL,false,false},
{"kr",13951275328ULL,4352ULL,false,false},
{"k",13951292800ULL,4352ULL,false,false},
{"vraw",13951310272ULL,4352ULL,false,false},
{"v",13951327744ULL,4352ULL,false,false},
{"kv",13951345216ULL,8704ULL,false,false},
{"scores",13951380096ULL,3468ULL,false,true},
{"probabilities",13951394048ULL,3468ULL,false,true},
{"att",13951408000ULL,26112ULL,false,false},
{"o",13951512512ULL,26112ULL,false,false},
{"r",13951617024ULL,26112ULL,false,false},
{"n1",13951721536ULL,26112ULL,false,false},
{"gate",13951826048ULL,152320ULL,false,false},
{"up",13952435392ULL,152320ULL,false,false},
{"act",13953044736ULL,152320ULL,false,false},
{"down",13953654080ULL,26112ULL,false,false},
{"y",13953758592ULL,26112ULL,false,false},
};
