// New short Host-only consumer. No old forwarders, RAM, weights or N0 consumer.
#include "VHostBlockTop.h"
#include "verilated.h"
#include "canonical_launch.hpp"
#include <cstdint>
#include <iostream>
#include <stdexcept>

static void need(bool ok, const char* reason) {
    if (!ok) throw std::runtime_error(reason);
}
static void zero_inputs(VHostBlockTop& d) {
    d.clock = 0;
    d.io_axi_ar_ready = 0;
    d.io_axi_aw_ready = 0;
    d.io_axi_b_bits_id = 0;
    d.io_axi_b_bits_resp = 0;
    d.io_axi_b_valid = 0;
    for (unsigned i = 0; i < 16; ++i) d.io_axi_r_bits_data[i] = 0;
    d.io_axi_r_bits_id = 0;
    d.io_axi_r_bits_last = 0;
    d.io_axi_r_bits_resp = 0;
    d.io_axi_r_valid = 0;
    d.io_axi_w_ready = 0;
    d.io_completion_ready = 0;
    d.io_launch_bits_commandBase = 0;
    d.io_launch_bits_commandLimit = 0;
    d.io_launch_bits_commands = 0;
    d.io_launch_bits_descriptorBase = 0;
    d.io_launch_bits_descriptorLimit = 0;
    d.io_launch_bits_descriptors = 0;
    d.io_launch_bits_epoch = 0;
    d.io_launch_bits_regions_0_base = 0;
    d.io_launch_bits_regions_0_limit = 0;
    d.io_launch_bits_regions_0_read = 0;
    d.io_launch_bits_regions_0_write = 0;
    d.io_launch_bits_regions_1_base = 0;
    d.io_launch_bits_regions_1_limit = 0;
    d.io_launch_bits_regions_1_read = 0;
    d.io_launch_bits_regions_1_write = 0;
    d.io_launch_bits_regions_2_base = 0;
    d.io_launch_bits_regions_2_limit = 0;
    d.io_launch_bits_regions_2_read = 0;
    d.io_launch_bits_regions_2_write = 0;
    d.io_launch_bits_regions_3_base = 0;
    d.io_launch_bits_regions_3_limit = 0;
    d.io_launch_bits_regions_3_read = 0;
    d.io_launch_bits_regions_3_write = 0;
    d.io_launch_valid = 0;
    d.io_result_ready = 0;
    d.reset = 0;
}
int main(int argc, char**) {
    if (argc != 1) return 64;
    try {
        VerilatedContext context;
        context.threads(1); context.randReset(0); context.randSeed(1);
        Verilated::threadContextp(&context);
        VHostBlockTop d{&context, "TOP"};
        zero_inputs(d);
        auto evaluate = [&](unsigned clock, unsigned reset) {
            d.clock = clock; d.reset = reset; d.eval();
            need(!context.gotFinish() && !context.gotError(), "model finish/error");
            context.timeInc(1);
        };
        evaluate(0, 1);
        for (unsigned i = 0; i < 4; ++i) {
            evaluate(1, 1); evaluate(0, 1);
        }
        evaluate(0, 0);
        for (unsigned i = 0; i < 4; ++i) {
            evaluate(1, 0); evaluate(0, 0);
        }
        need(!d.io_resetRequired && d.io_pc == 0 && d.io_issuedJobs == 0,
             "reset release state");
        std::cout << "HOST93_RESET_OK asserted_high_edges=4 released_high_edges=4\n";
        canonical_host_wiring_v1::launch_payload(d);
        d.io_launch_valid = 1;
        // All AXI incoming ready/valid/data stay zero. No memory transaction
        // response, data source, or numerical simulation is provided.
        for (unsigned edge = 0; edge < 16; ++edge) {
            evaluate(0, 0);
            need(!d.io_resetRequired && d.io_pc == 0 && d.io_issuedJobs == 0,
                 "pre-launch state");
            const bool fire = d.io_launch_valid && d.io_launch_ready;
            evaluate(1, 0);
            if (fire) {
                // Stop at this first real high edge. No later eval or final
                // call is permitted; ordinary C++ destruction follows.
                std::cout << "HOST93_LAUNCH_OK handshakes=1 high_edge=" << edge
                          << " further_eval_calls=0\n";
                std::cout << "HOST93_SHORT_PASS reset_and_launch_only=1\n";
                return 0;
            }
        }
        throw std::runtime_error("launch handshake bound");
    } catch (const std::exception& error) {
        std::cerr << "HOST93_SHORT_FAIL " << error.what() << '\n';
        return 1;
    }
}
