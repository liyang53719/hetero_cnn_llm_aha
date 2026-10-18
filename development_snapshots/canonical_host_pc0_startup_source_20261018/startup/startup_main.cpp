// SOURCE candidate. This executable must only be built/run by a future reviewed gate.
#include "dpi_forwarders.hpp"
int main(int argc,char**) {
    if(argc!=1){std::cerr<<"FAIL: no startup arguments allowed\n";return 1;}
    host_startup::Ledger audit;
    host_startup::active_ledger=&audit;
    try {
        {
            VerilatedContext context;
            context.threads(1);
            context.randReset(0); // bounded deterministic two-state startup, not arbitrary/X-state reset proof
            context.randSeed(1);
            Verilated::threadContextp(&context); // protected create uses this same context
            VHostBlockTop model{&context,"TOP"};
            audit.bind(model);
            host_startup::zero_inputs(model);
            auto step=[&](unsigned phase,unsigned clock,unsigned reset) {
                model.clock=clock;model.reset=reset;
                audit.begin_eval(phase,clock,reset);
                const auto before=host_startup::input_snapshot(model);
                model.eval(); // the only Host eval call site; no direct protected calls
                if(context.gotFinish()||context.gotError()||before!=host_startup::input_snapshot(model))
                    throw std::runtime_error("unexpected finish/error/input mutation");
                audit.end_eval();
                context.timeInc(1);
            };
            step(0,0,1); // actual initial block creates eight independent children, reset asserted
            step(1,0,0); // establish a real rst_n=1 callback for every gated child
            step(2,0,1); // actual child rst_n=1 -> 0 assertion, even with gated clocks
            for(unsigned phase=3;phase<=10;++phase)step(phase,(phase%2==1)?1:0,1);
            step(11,0,0); // actual child rst_n=0 -> 1 release
            for(unsigned phase=12;phase<=19;++phase)step(phase,(phase%2==0)?1:0,0);
            audit.begin_final();model.final();audit.end_final();
        } // model and context destroyed before any successful receipt is emitted
        audit.report(std::cout);
        host_startup::active_ledger=nullptr;
        return 0;
    } catch(const std::exception& error) {
        audit.poison();host_startup::active_ledger=nullptr;
        std::cerr<<"FAIL: "<<error.what()<<'\n';return 1;
    } catch(...) {
        audit.poison();host_startup::active_ledger=nullptr;
        std::cerr<<"FAIL: unknown startup failure\n";return 1;
    }
}
