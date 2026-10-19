// Included inside RuntimeOwner. Only the concrete production driver constructs this.
    class Pc1ModelScheduler final {
        friend class RuntimeOwner;
        using Frame=canonical_host_wiring_v1::Frame;
        using Job=canonical_host_wiring_v1::Job;
        RuntimeOwner& owner_;VHostBlockTop& model_;
        Pc01FailureCapsule& diagnostic_;
        const VHostBlockTop___024root* const diagnostic_root_;
        const VerilatedContext* const diagnostic_context_;
        canonical_host_wiring_v1::N0Fields<VHostBlockTop> fields_;
        Pc1RetirementAdapter adapter_;
        first_n0::Pc1ProductionGuard guard_;
        canonical_host::IndependentLedger audit_;
        Frame pre_{};Job accepted_{};
        std::array<std::uint64_t,54> inputs_{};
        bool pending_=false,have_edge_=false,job_seen_=false,done_seen_=false,completion_held_=false;
        std::uint64_t edge_=0,entry_edge_=0,accept_edge_=0,ack_edge_=0,completion_=0,cycles_=0;
        std::uint64_t jobs_=0,dones_=0,acks_=0,n0_read_bytes_=0,wq_read_bytes_=0;
        struct Read {Address address;unsigned beat;Data512 data;};
        std::optional<Read> read_;
        std::optional<Address> stalled_ar_,stalled_aw_;
        std::optional<WriteBeat> stalled_w_;
        bool completion_fire_=false;
        explicit Pc1ModelScheduler(RuntimeOwner& owner,VHostBlockTop& model,std::uint64_t first_edge,Pc01FailureCapsule& diagnostic)
            :owner_(owner),model_(model),diagnostic_(diagnostic),diagnostic_root_(model.rootp),
             diagnostic_context_(model.contextp()),fields_(model),adapter_(owner),guard_(model),entry_edge_(first_edge) {
            require(owner_.published_&&!owner_.qraw_published_&&model_.io_pc==1&&model_.io_issuedJobs==1&&
                    !model_.io_completion_valid&&!model_.io_result_valid&&model_.io_writeBytes==786432,
                    "PC1 same-model ACK0 successor boundary");
        }
        Pc1ModelScheduler(const Pc1ModelScheduler&)=delete;
        Pc1ModelScheduler& operator=(const Pc1ModelScheduler&)=delete;
        static void healthy(const Frame& f) {
            require(!f.owner_rejected&&!f.owner_poison&&!f.core_poison&&!f.hub_poison&&!f.dma_poison&&
                    !f.router_bad&&!f.router_fault&&!f.writeback_error,"PC1 actual model fault");
        }
        void freeze_identity(const Pc01IdentitySample& sample,Pc01IdentitySite site,std::uint64_t edge)const noexcept {
            if(diagnostic_.present)return; // immutable first-failure snapshot, before checked() poisons
            auto& d=diagnostic_;d.predicates=sample;d.site=site;d.edge=edge;
            d.owner_phase=static_cast<std::uint64_t>(owner_.phase_);
            d.root_valid=diagnostic_root_&&model_.rootp==diagnostic_root_;
            d.context_valid=diagnostic_context_&&model_.contextp()==diagnostic_context_;
            d.entry_edge=entry_edge_;d.accept_edge=accept_edge_;d.ack_edge=ack_edge_;d.pc1_cycles=cycles_;
            d.pc1_jobs=jobs_;d.pc1_dones=dones_;d.pc1_acks=acks_;
            d.qraw_b=adapter_.b_count_;d.qraw_committed=adapter_.committed_;
            d.n0_read_bytes=n0_read_bytes_;d.wq_read_bytes=wq_read_bytes_;
            // No Frame/profile/observer call here: those can throw and replace the first failure.
            // These exact scalar fields were already registered by the unchanged guard.
            if(d.root_valid) {
                const auto& r=*diagnostic_root_;
                d.clock=model_.clock;d.reset=model_.reset;d.reset_required=model_.io_resetRequired;
                d.pc=model_.io_pc;d.issued_jobs=model_.io_issuedJobs;d.write_bytes=model_.io_writeBytes;
                d.useful_macs=model_.io_usefulMacs;d.executed_macs=model_.io_executedMacs;
                d.owner_rejected=r.HostBlockTop__DOT__owner__DOT__rejected;
                d.owner_poison=r.HostBlockTop__DOT__owner__DOT__sharedPoison;
                d.router_state=r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__state;
                d.router_bad=r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__bad;
                d.router_fault=r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__fault;
                d.backend_reset=r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__io_backendReset;
                d.host_abort=r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__io_residentHost_abort;
                d.group_reset_required=r.HostBlockTop__DOT__owner__DOT__resident__DOT__io_group_resetRequired;
                d.core_state=r.HostBlockTop__DOT__owner__DOT__core__DOT__state;
                d.core_poison=r.HostBlockTop__DOT__owner__DOT__core__DOT__poisoned;
                d.core_status=r.HostBlockTop__DOT__owner__DOT__core__DOT__status;
                d.hub_poison=r.HostBlockTop__DOT__hub__DOT__poison;
                d.dma_poison=r.HostBlockTop__DOT__dma__DOT__poison;
                d.writeback_error=r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__error;
                d.matrix_steps=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__steps;
                d.matrix_wide_steps=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__wideSteps;
                d.matrix_stalls=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__stalls;
                d.matrix_state=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__state;
                d.matrix_mask=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__group_sliceMask;
                d.matrix_valid=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__io_port_step_valid;
                d.matrix_ready=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__io_port_step_ready;
                d.matrix_legal=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__legalStep;
                d.matrix_poison=r.HostBlockTop__DOT__owner__DOT__matrix__DOT__poison;
            }
            // Context is never dereferenced by the snapshot. Unevaluated predicates stay unknown.
            d.present=true;
        }
        void identity(Pc01IdentitySite site,std::uint64_t edge)const {
            Pc01IdentitySample sample{};
            const bool ok=sample.probe(0,owner_.phase_==Phase::Runtime)&&sample.probe(1,owner_.published_)&&
                    sample.probe(2,!owner_.qraw_published_)&&sample.probe(3,model_.rootp)&&
                    sample.probe(4,!model_.reset)&&sample.probe(5,!model_.io_resetRequired)&&
                    sample.probe(6,!model_.contextp()->gotError())&&sample.probe(7,!model_.contextp()->gotFinish());
            if(!ok)freeze_identity(sample,site,edge);
            require(ok,"PC1 actual identity or stopped");
        }
        void exact_job(const Job& j)const {
            require(j.kind==1&&j.tag==((7U<<16)|1U)&&j.m==128&&j.n==1536&&j.k==1536&&
                    j.a==owner_.n0().base&&j.b==expected_inputs[2].base&&j.c==0&&j.dst==owner_.qraw().base&&
                    j.writeBytes==pc01::qraw_bytes,"PC1 exact public Dense job");
        }
        void read_permission(std::uint64_t address,std::uint64_t bytes)const {
            owner_.read_permission(address,bytes);
            bool input=false;for(const unsigned i:{0U,1U,2U})
                input=input||contains(expected_inputs[i].base,expected_inputs[i].bytes,address,bytes);
            const bool n0=contains(owner_.n0().base,owner_.n0().bytes,address,bytes);
            require(input||n0,"PC1 AR only metadata Wq or published N0");
            if(n0||contains(expected_inputs[2].base,expected_inputs[2].bytes,address,bytes))
                require(job_seen_&&!done_seen_,"PC1 operand read outside accepted job");
        }
        Data512 read_beat(std::uint64_t address)const {
            read_permission(address,64);Data512 data{};
            for(unsigned i=0;i<64;++i)data[i/4]|=std::uint32_t(owner_.payload_[std::size_t(address-owner_.base_)+i])<<(8*(i%4));
            return data;
        }
        void drive(std::uint64_t edge) {
            model_.io_launch_valid=0;model_.io_completion_ready=1;model_.io_result_ready=0;
            model_.io_axi_ar_ready=!read_&&edge%7!=0;
            model_.io_axi_aw_ready=!adapter_.aw_&&!adapter_.held_b_&&edge%5!=0;
            model_.io_axi_w_ready=adapter_.queue_.size()<256&&!adapter_.held_b_&&edge%3!=0;
            model_.io_axi_r_valid=bool(read_);model_.io_axi_r_bits_id=read_?read_->address.id:0;
            model_.io_axi_r_bits_resp=0;model_.io_axi_r_bits_last=read_&&read_->beat==read_->address.len;
            for(unsigned i=0;i<16;++i)model_.io_axi_r_bits_data[i]=read_?read_->data[i]:0;
            model_.io_axi_b_valid=adapter_.held_b_;model_.io_axi_b_bits_id=adapter_.aw_?adapter_.aw_->id:0;
            model_.io_axi_b_bits_resp=0;
        }
        void check_stalls(const canonical_host::Sample& s) {
            if(stalled_ar_)require(s.ar_valid&&s.ar==*stalled_ar_,"PC1 AR changed under stall");
            if(stalled_aw_)require(s.aw_valid&&s.aw==*stalled_aw_,"PC1 AW changed under stall");
            if(stalled_w_)require(s.w_valid&&s.w==*stalled_w_,"PC1 W changed under stall");
            stalled_ar_=s.ar_valid&&!s.ar_ready?std::optional<Address>(s.ar):std::nullopt;
            stalled_aw_=s.aw_valid&&!s.aw_ready?std::optional<Address>(s.aw):std::nullopt;
            stalled_w_=s.w_valid&&!s.w_ready?std::optional<WriteBeat>(s.w):std::nullopt;
        }
        void advance_reads() {
            const auto& s=pre_.axi;
            if(s.rf()) {
                require(read_&&s.r.id==read_->address.id&&s.r.resp==0&&s.r.data==read_->data&&
                        s.r.last==(read_->beat==read_->address.len),"PC1 R same backing debt");
                if(read_->beat==read_->address.len)read_.reset();
                else {++read_->beat;read_->data=read_beat(read_->address.addr+64ULL*read_->beat);}
            }
            if(s.arf()) {
                validate_address(s.ar);require(!read_,"PC1 AR outstanding overwrite");
                const auto bytes=64ULL*(s.ar.len+1);read_permission(s.ar.addr,bytes);
                if(contains(owner_.n0().base,owner_.n0().bytes,s.ar.addr,bytes))n0_read_bytes_+=bytes;
                if(contains(expected_inputs[2].base,expected_inputs[2].bytes,s.ar.addr,bytes))wq_read_bytes_+=bytes;
                read_=Read{s.ar,0,read_beat(s.ar.addr)};
            }
        }
        void require_retired_low()const {
            require(!read_&&!pre_.axi.ar_valid&&!pre_.axi.aw_valid&&!pre_.axi.w_valid&&!pre_.axi.r_valid&&!pre_.axi.b_valid&&
                    pre_.hub_state==0&&pre_.dma_state==0&&!pre_.owner_active&&!pre_.core_start&&
                    !pre_.memory_valid&&!pre_.response_fire,"PC1 external shared transport not retired");
            audit_.require_retired();adapter_.require_retired();guard_.require_terminal_low();
            require(model_.io_memoryAccepted_0==model_.io_memoryReturned_0&&
                    model_.io_memoryAccepted_1==model_.io_memoryReturned_1,"PC1 Host shared memory debt");
        }
        void settle_low(std::uint64_t edge) {
            owner_.checked([&]{identity(Pc01IdentitySite::SettleEntry,edge);require(!pending_&&(!have_edge_?edge==entry_edge_:edge==edge_+1),"PC1 consecutive scheduler low");
                drive(edge);model_.clock=0;model_.eval();identity(Pc01IdentitySite::LowEvalPost,edge);pre_=fields_.read(false);healthy(pre_);inputs_=input_snapshot();
                require(model_.io_pc==1&&model_.io_issuedJobs==(job_seen_?2U:1U)&&!model_.io_result_valid,
                        "PC1 only scope before high");
                if(pre_.job_valid){require(!job_seen_&&!done_seen_,"PC1 duplicate or later job offer");exact_job(pre_.bound);}
                if(job_seen_){exact_job(pre_.bound);require(pre_.bound==accepted_,"PC1 retained public job drift");}
                require(pre_.router_state==(job_seen_&&!done_seen_?2U:0U),"PC1 exact selected router lifetime");
                guard_.before_rising(edge,job_seen_&&!done_seen_);
                if(pre_.done_valid) {
                    require(job_seen_&&!done_seen_&&pre_.router_state==2&&pre_.done_status==0&&
                            pre_.done_bytes==pc01::qraw_bytes,"PC1 actual selected done payload");
                    require_retired_low();
                }
                completion_fire_=bool(model_.io_completion_valid&&model_.io_completion_ready);
                if(model_.io_completion_valid) {
                    require(job_seen_&&done_seen_&&!pre_.job_valid&&!pre_.done_valid&&pre_.router_state==0,
                            "PC1 completion before selected owner retirement");require_retired_low();adapter_.check_ack();
                    const auto word=std::uint64_t(model_.io_completion_bits);
                    canonical_host_wiring_v1::require_pc1_completion_payload(word);
                    if(completion_held_)require(word==completion_,"PC1 held completion changed");
                    completion_=word;completion_held_=true;
                } else require(!completion_held_,"PC1 completion dropped before ACK");
                check_stalls(pre_.axi);adapter_.capture_low(edge,pre_.axi);edge_=edge;pending_=true;
            });
        }
        void rise_and_observe(std::uint64_t edge) {
            owner_.checked([&]{identity(Pc01IdentitySite::RiseEntry,edge);require(pending_&&edge==edge_&&model_.clock==0,"PC1 matching scheduler high");
                unchanged_inputs(false);model_.clock=1;model_.eval();identity(Pc01IdentitySite::HighEvalPost,edge);unchanged_inputs(true);
                const auto post=fields_.read(true);healthy(post);guard_.after_rising(edge);
                if(pre_.job_valid&&pre_.job_ready) {
                    require(!job_seen_&&post.router_state==2&&model_.io_issuedJobs==2&&model_.io_pc==1,
                            "PC1 actual job accepted by reduction router");exact_job(pre_.bound);
                    accepted_=pre_.bound;adapter_.accept_job(std::uint32_t(accepted_.tag),7);
                    job_seen_=true;accept_edge_=edge;++jobs_;
                }
                if(pre_.done_valid&&pre_.done_ready) {
                    require(job_seen_&&!done_seen_&&post.router_state==0&&model_.io_usefulMacs==pc01::useful_macs&&
                            model_.io_executedMacs==pc01::useful_macs&&model_.io_writeBytes==2*pc01::qraw_bytes,
                            "PC1 actual owner result counters");
                    adapter_.owner_done(pre_.done_bytes,unsigned(pre_.done_status));done_seen_=true;++dones_;
                }
                if(completion_fire_) {
                    require(done_seen_&&model_.io_pc==2&&model_.io_issuedJobs==2&&!post.job_valid&&post.router_state==0&&
                            model_.io_usefulMacs==pc01::useful_macs&&model_.io_executedMacs==pc01::useful_macs,
                            "PC1 ACK1 exact terminal high without PC2 job");
                    adapter_.check_ack();ack_edge_=edge;++acks_;
                } else require(model_.io_pc==1,"PC1 advanced without ACK1");
                audit_.consume(pre_.axi);advance_reads();
                auto& c=audit_.counts();c.ar_stall+=pre_.axi.ar_valid&&!pre_.axi.ar_ready;
                c.aw_stall+=pre_.axi.aw_valid&&!pre_.axi.aw_ready;c.w_stall+=pre_.axi.w_valid&&!pre_.axi.w_ready;
                c.r_stall+=pre_.axi.r_valid&&!pre_.axi.r_ready;c.b_stall+=pre_.axi.b_valid&&!pre_.axi.b_ready;
                ++cycles_;
                // Last fallible call; every actual high check precedes B payload mutation.
                adapter_.retire_high(edge);
                pending_=false;have_edge_=true;
                if(completion_fire_){adapter_.publish_noexcept();completion_held_=false;}
            });
        }
        std::array<std::uint64_t,54> input_snapshot() const {
            return {{model_.clock,model_.reset,model_.io_axi_w_ready,model_.io_axi_r_valid,model_.io_launch_valid,model_.io_launch_bits_regions_0_read,model_.io_launch_bits_regions_0_write,model_.io_launch_bits_regions_1_read,model_.io_launch_bits_regions_1_write,model_.io_launch_bits_regions_2_read,model_.io_launch_bits_regions_2_write,model_.io_launch_bits_regions_3_read,model_.io_launch_bits_regions_3_write,model_.io_result_ready,model_.io_completion_ready,model_.io_axi_aw_ready,model_.io_axi_b_valid,model_.io_axi_b_bits_id,model_.io_axi_b_bits_resp,model_.io_axi_ar_ready,model_.io_axi_r_bits_id,model_.io_axi_r_bits_resp,model_.io_axi_r_bits_last,model_.io_launch_bits_commands,model_.io_launch_bits_epoch,model_.io_launch_bits_descriptors,model_.io_axi_r_bits_data[0],model_.io_axi_r_bits_data[1],model_.io_axi_r_bits_data[2],model_.io_axi_r_bits_data[3],model_.io_axi_r_bits_data[4],model_.io_axi_r_bits_data[5],model_.io_axi_r_bits_data[6],model_.io_axi_r_bits_data[7],model_.io_axi_r_bits_data[8],model_.io_axi_r_bits_data[9],model_.io_axi_r_bits_data[10],model_.io_axi_r_bits_data[11],model_.io_axi_r_bits_data[12],model_.io_axi_r_bits_data[13],model_.io_axi_r_bits_data[14],model_.io_axi_r_bits_data[15],model_.io_launch_bits_commandBase,model_.io_launch_bits_commandLimit,model_.io_launch_bits_descriptorBase,model_.io_launch_bits_descriptorLimit,model_.io_launch_bits_regions_0_base,model_.io_launch_bits_regions_0_limit,model_.io_launch_bits_regions_1_base,model_.io_launch_bits_regions_1_limit,model_.io_launch_bits_regions_2_base,model_.io_launch_bits_regions_2_limit,model_.io_launch_bits_regions_3_base,model_.io_launch_bits_regions_3_limit}};
        }
        void unchanged_inputs(bool high) const {
            const auto now=input_snapshot();
            for(std::size_t i=0;i<now.size();++i)
                require(now[i]==(i==0?std::uint64_t(high):inputs_[i]),"model inputs changed outside private clock");
        }
    };
