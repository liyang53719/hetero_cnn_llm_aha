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
static constexpr uint64_t SCRATCH=13763303360ULL;
static constexpr uint64_t LIMIT=13763388736ULL;
static constexpr unsigned TOKENS=16,DESCRIPTORS=215,COMMANDS=21;
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
static constexpr uint64_t A_N0=13763303424ULL;
static constexpr uint64_t A_QRAW=13763307584ULL;
static constexpr uint64_t A_QR=13763311744ULL;
static constexpr uint64_t A_Q=13763315904ULL;
static constexpr uint64_t A_KRAW=13763320064ULL;
static constexpr uint64_t A_KR=13763322176ULL;
static constexpr uint64_t A_K=13763324288ULL;
static constexpr uint64_t A_VRAW=13763326400ULL;
static constexpr uint64_t A_V=13763328512ULL;
static constexpr uint64_t A_KV=13763330624ULL;
static constexpr uint64_t A_CACHE_K=13763330624ULL;
static constexpr uint64_t A_CACHE_V=13763332672ULL;
static constexpr uint64_t A_SCORES=13763334784ULL;
static constexpr uint64_t A_PROBABILITIES=13763336896ULL;
static constexpr uint64_t A_ATT=13763339008ULL;
static constexpr uint64_t A_O=13763343168ULL;
static constexpr uint64_t A_R=13763347328ULL;
static constexpr uint64_t A_N1=13763351488ULL;
static constexpr uint64_t A_GATE=13763355648ULL;
static constexpr uint64_t A_UP=13763363904ULL;
static constexpr uint64_t A_ACT=13763372160ULL;
static constexpr uint64_t A_DOWN=13763380416ULL;
static constexpr uint64_t A_Y=13763384576ULL;
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
{"x",13763299200ULL,1024ULL,true,false},
{"n0",13763303424ULL,1024ULL,false,false},
{"qraw",13763307584ULL,1024ULL,false,false},
{"qr",13763311744ULL,1024ULL,false,false},
{"q",13763315904ULL,1024ULL,false,false},
{"kraw",13763320064ULL,512ULL,false,false},
{"kr",13763322176ULL,512ULL,false,false},
{"k",13763324288ULL,512ULL,false,false},
{"vraw",13763326400ULL,512ULL,false,false},
{"v",13763328512ULL,512ULL,false,false},
{"kv",13763330624ULL,1024ULL,false,false},
{"scores",13763334784ULL,512ULL,false,true},
{"probabilities",13763336896ULL,512ULL,false,true},
{"att",13763339008ULL,1024ULL,false,false},
{"o",13763343168ULL,1024ULL,false,false},
{"r",13763347328ULL,1024ULL,false,false},
{"n1",13763351488ULL,1024ULL,false,false},
{"gate",13763355648ULL,2048ULL,false,false},
{"up",13763363904ULL,2048ULL,false,false},
{"act",13763372160ULL,2048ULL,false,false},
{"down",13763380416ULL,1024ULL,false,false},
{"y",13763384576ULL,1024ULL,false,false},
};
