#include "Vmicro_top.h"
#include "Vmicro_top__Dpi.h"
#include "verilated.h"
#include "verilated_dpi.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

static void require(bool ok, const char* why) {
    if (!ok) {
        std::fprintf(stderr, "HOST93_MICRO_FAIL %s\n", why);
        std::exit(2);
    }
}

struct Handle {
    std::unique_ptr<VerilatedContext> context;
    std::unique_ptr<Vmicro_top> model;
    svScope scope = nullptr;
    std::uint32_t expected = 7;
    std::uint32_t delta = 0;

    Handle() : context(new VerilatedContext) {
        context->threads(1);
        activate();
        model.reset(new Vmicro_top(context.get(), "dual"));
        model->clk = 0;
        model->reset = 1;
        evaluate();
        model->clk = 1;
        evaluate();
        model->clk = 0;
        evaluate();
        model->reset = 0;
        evaluate();
        scope = svGetScopeFromName("dual.micro_top");
        require(scope != nullptr, "missing exact top DPI scope");
        require(std::strcmp(svGetNameFromScope(scope), "dual.micro_top") == 0,
                "unexpected top DPI scope name");
        check();
    }

    void activate() { Verilated::threadContextp(context.get()); }

    void evaluate() {
        activate();
        model->eval();
        require(!context->gotError() && !context->gotFinish(), "unexpected model stop");
    }

    void select() {
        activate();
        require(svGetScopeFromName("dual.micro_top") == scope, "context scope lookup drift");
        svSetScope(scope);
        require(svGetScope() == scope, "DPI selected scope mismatch");
    }

    void check() {
        select();
        require(hm_read_delta() == delta, "DPI delta mismatch");
        require(hm_read_count() == expected, "DPI child count mismatch");
        require(model->count == expected, "public child count mismatch");
    }

    void set_delta(std::uint32_t value) {
        select();
        hm_set_delta(value);
        delta = value;
        evaluate();
        check();
    }

    void tick() {
        model->clk = 0;
        evaluate();
        model->clk = 1;
        evaluate();
        expected = std::uint32_t(expected + delta + 3U);
        model->clk = 0;
        evaluate();
        check();
    }

    void reset_only_this() {
        model->reset = 1;
        model->clk = 0;
        evaluate();
        model->clk = 1;
        evaluate();
        expected = 7;
        model->clk = 0;
        evaluate();
        model->reset = 0;
        evaluate();
        check();
    }

    void close() {
        activate();
        svSetScope(nullptr);
        model->final();
        require(!context->gotError(), "final raised model error");
        model.reset();
        scope = nullptr;
        require(context->scopeFind("dual.micro_top") == nullptr, "closed top scope survived");
    }
};

int main() {
    Handle a;
    Handle b;
    require(a.context.get() != b.context.get(), "shared context handle");
    require(a.model.get() != b.model.get(), "shared top model handle");
    require(a.scope != b.scope, "shared DPI scope across contexts");
    std::puts("HOST93_MICRO_SCOPE_OK same_name=dual.micro_top distinct_context=1 distinct_model=1 distinct_scope=1");

    a.set_delta(5);
    b.check();
    b.set_delta(11);
    a.check();
    for (unsigned i = 0; i < 16; ++i) {
        a.tick();
        b.check();
        b.tick();
        a.check();
        b.tick();
        a.check();
    }
    require(a.expected == 135 && b.expected == 455, "scoreboard final constants");
    a.set_delta(0xffffffffU);
    b.check();
    a.tick();
    b.check();
    require(a.expected == 137 && b.expected == 455, "unsigned wrap constants");
    std::puts("HOST93_MICRO_DPI_OK writes=3 export_reads_checked=1");
    std::puts("HOST93_MICRO_STATE_OK steps_a=17 steps_b=32 count_a=137 count_b=455");

    a.reset_only_this();
    b.check();
    require(a.expected == 7 && b.expected == 455, "single-context reset constants");
    a.close();
    b.check();
    b.tick();
    require(b.expected == 469, "surviving model constant");
    std::puts("HOST93_MICRO_LIFETIME_OK reset_a=7 preserved_b=455 closed_a=1 continued_b=469");
    b.close();
    std::puts("HOST93_MICRO_PASS");
    return 0;
}
