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
static constexpr uint64_t SCRATCH=13763307456ULL;
static constexpr uint64_t LIMIT=13763484992ULL;
static constexpr unsigned TOKENS=32,DESCRIPTORS=215,COMMANDS=21;
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
static constexpr uint64_t A_N0=13763307520ULL;
static constexpr uint64_t A_QRAW=13763315776ULL;
static constexpr uint64_t A_QR=13763324032ULL;
static constexpr uint64_t A_Q=13763332288ULL;
static constexpr uint64_t A_KRAW=13763340544ULL;
static constexpr uint64_t A_KR=13763344704ULL;
static constexpr uint64_t A_K=13763348864ULL;
static constexpr uint64_t A_VRAW=13763353024ULL;
static constexpr uint64_t A_V=13763357184ULL;
static constexpr uint64_t A_KV=13763361344ULL;
static constexpr uint64_t A_CACHE_K=13763361344ULL;
static constexpr uint64_t A_CACHE_V=13763365440ULL;
static constexpr uint64_t A_SCORES=13763369600ULL;
static constexpr uint64_t A_PROBABILITIES=13763377856ULL;
static constexpr uint64_t A_ATT=13763386112ULL;
static constexpr uint64_t A_O=13763394368ULL;
static constexpr uint64_t A_R=13763402624ULL;
static constexpr uint64_t A_N1=13763410880ULL;
static constexpr uint64_t A_GATE=13763419136ULL;
static constexpr uint64_t A_UP=13763435584ULL;
static constexpr uint64_t A_ACT=13763452032ULL;
static constexpr uint64_t A_DOWN=13763468480ULL;
static constexpr uint64_t A_Y=13763476736ULL;
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
{"x",13763299200ULL,2048ULL,true,false},
{"n0",13763307520ULL,2048ULL,false,false},
{"qraw",13763315776ULL,2048ULL,false,false},
{"qr",13763324032ULL,2048ULL,false,false},
{"q",13763332288ULL,2048ULL,false,false},
{"kraw",13763340544ULL,1024ULL,false,false},
{"kr",13763344704ULL,1024ULL,false,false},
{"k",13763348864ULL,1024ULL,false,false},
{"vraw",13763353024ULL,1024ULL,false,false},
{"v",13763357184ULL,1024ULL,false,false},
{"kv",13763361344ULL,2048ULL,false,false},
{"scores",13763369600ULL,2048ULL,false,true},
{"probabilities",13763377856ULL,2048ULL,false,true},
{"att",13763386112ULL,2048ULL,false,false},
{"o",13763394368ULL,2048ULL,false,false},
{"r",13763402624ULL,2048ULL,false,false},
{"n1",13763410880ULL,2048ULL,false,false},
{"gate",13763419136ULL,4096ULL,false,false},
{"up",13763435584ULL,4096ULL,false,false},
{"act",13763452032ULL,4096ULL,false,false},
{"down",13763468480ULL,2048ULL,false,false},
{"y",13763476736ULL,2048ULL,false,false},
};
