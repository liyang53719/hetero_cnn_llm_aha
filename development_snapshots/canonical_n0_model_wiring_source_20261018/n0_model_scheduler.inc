// Included INSIDE RuntimeOwner. Complete private template, not a fillable friend.
// No production constructor/factory is exposed in this slice. Generated profile,
// reset/sole-instance and resident-before-N0 admission remain required and absent.
    template<class Model> class N0ModelScheduler final {
#ifdef CANONICAL_RUNTIME_UNIT_TEST
        friend class ::canonical_runtime_v1::RuntimeTestAccess;
#endif
        using Frame=canonical_host_wiring_v1::Frame;
        using Job=canonical_host_wiring_v1::Job;
        RuntimeOwner& owner_;
        Model& model_;
        canonical_host_wiring_v1::N0Fields<Model> fields_;
        N0RetirementAdapter adapter_;
        bool pending_=false,have_edge_=false,launched_=false,completion_held_=false;
        std::uint64_t edge_=0,accepted_epoch_=0,completion_word_=0;
        Job accepted_job_{};
        Frame pre_{};
        bool pre_launch_fire_=false,pre_completion_fire_=false;
        std::array<std::uint64_t,54> inputs_{};
        struct Read { Address address;unsigned beat;Data512 data; };
        std::optional<Read> read_;
        std::optional<Address> stalled_ar_,stalled_aw_;
        std::optional<WriteBeat> stalled_w_;
        canonical_host::IndependentLedger axi_audit_;
        explicit N0ModelScheduler(RuntimeOwner& owner,Model& model)
          :owner_(owner),model_(model),fields_(model),adapter_(owner) {}
        N0ModelScheduler(const N0ModelScheduler&)=delete;
        N0ModelScheduler& operator=(const N0ModelScheduler&)=delete;
        template<class F> auto checked(F&& f)->decltype(f()) {
            return owner_.checked([&]()->decltype(f()) {
                require(!model_.reset&&!model_.io_resetRequired&&model_.rootp!=nullptr,"model reset/root/poison");
                require(!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"model context stopped");
                return f();
            });
        }
        static void healthy(const Frame& f) {
            require(!f.owner_rejected&&!f.owner_poison&&!f.core_poison&&!f.hub_poison&&!f.dma_poison&&
                    !f.router_bad&&!f.router_fault&&!f.writeback_error,"actual N0 model error");
        }
        void active(const Frame& f) const {
            require(adapter_.accepted_&&!adapter_.done_&&f.owner_active&&f.owner_mode==0&&f.router_state==1&&
                f.owner_tag==accepted_job_.tag&&f.retained==accepted_job_&&!f.core_residual&&!f.cmd_pending,
                "accepted real owner/retained job changed");
        }
        Data512 read_beat(std::uint64_t address) const {
            owner_.read_permission(address,64);Data512 result{};
            const auto offset=static_cast<std::size_t>(address-owner_.base_);
            for(unsigned i=0;i<64;++i)result[i/4]|=std::uint32_t(owner_.payload_[offset+i])<<(8*(i%4));
            return result; // copy only from the SAME RuntimeOwner payload allocation
        }
        void drive(std::uint64_t edge) {
            if(launched_)model_.io_launch_valid=0;
            model_.io_completion_ready=1;model_.io_result_ready=0;
            model_.io_axi_ar_ready=!read_&&edge%7!=0;
            model_.io_axi_aw_ready=!adapter_.aw_&&!adapter_.held_b_&&edge%5!=0;
            model_.io_axi_w_ready=adapter_.queue_.size()<256&&!adapter_.held_b_&&edge%3!=0;
            model_.io_axi_r_valid=bool(read_);model_.io_axi_r_bits_id=read_?read_->address.id:0;
            model_.io_axi_r_bits_resp=0;model_.io_axi_r_bits_last=read_&&read_->beat==read_->address.len;
            for(unsigned i=0;i<16;++i)model_.io_axi_r_bits_data[i]=read_?read_->data[i]:0;
            model_.io_axi_b_valid=adapter_.held_b_;
            model_.io_axi_b_bits_id=adapter_.aw_?adapter_.aw_->id:0;model_.io_axi_b_bits_resp=0;
        }
        void check_stalls(const canonical_host::Sample& s) {
            if(stalled_ar_)require(s.ar_valid&&s.ar==*stalled_ar_,"real AR changed during stall");
            if(stalled_aw_)require(s.aw_valid&&s.aw==*stalled_aw_,"real AW changed during stall");
            if(stalled_w_)require(s.w_valid&&s.w==*stalled_w_,"real W changed during stall");
            stalled_ar_=s.ar_valid&&!s.ar_ready?std::optional<Address>(s.ar):std::nullopt;
            stalled_aw_=s.aw_valid&&!s.aw_ready?std::optional<Address>(s.aw):std::nullopt;
            stalled_w_=s.w_valid&&!s.w_ready?std::optional<WriteBeat>(s.w):std::nullopt;
        }
        void advance_reads() {
            const auto& s=pre_.axi;
            if(s.rf()) {
                require(read_&&s.r.id==read_->address.id&&s.r.resp==0&&s.r.data==read_->data&&
                        s.r.last==(read_->beat==read_->address.len),"real R differs from same RAM read debt");
                if(read_->beat==read_->address.len)read_.reset();
                else {++read_->beat;read_->data=read_beat(read_->address.addr+64ULL*read_->beat);}
            }
            if(s.arf()) {
                RuntimeOwner::validate_address(s.ar);require(!read_,"real AR debt overwrite");
                owner_.read_permission(s.ar.addr,64ULL*(s.ar.len+1));
                read_=Read{s.ar,0,read_beat(s.ar.addr)};
            }
        }
        void consume_internal(const Frame& post) {
            healthy(pre_);healthy(post);
            const bool job=pre_.job_valid&&pre_.job_ready;
            require(job==bool(pre_.core_start),"real job/core start disagree");
            if(job) {
                const auto& j=pre_.bound;
                require(launched_&&!adapter_.accepted_&&model_.io_issuedJobs==1&&j.kind==0&&j.tag==(7U<<16)&&
                    j.m==128&&j.n==1536&&j.k==1536&&j.a==expected_inputs[15].base&&
                    j.b==expected_inputs[9].base&&j.c==0&&j.dst==owner_.n0().base&&
                    j.writeBytes==owner_.n0().bytes,"actual canonical N0 job differs");
                accepted_job_=j;adapter_.accept_owner(0,std::uint32_t(j.tag),std::uint16_t(accepted_epoch_));active(post);
            }
            if(pre_.memory_valid&&pre_.memory_ready&&pre_.core.write) {
                active(pre_);require(!adapter_.debt_&&pre_.core.address%64==0&&pre_.core.mask==UINT64_MAX&&
                    (pre_.core.tag>>32)==accepted_epoch_,"actual scalar request shape/epoch");
                require(pre_.hub_capture_ready&&pre_.hub_capture_valid&&post.hub_state==1&&post.hub_owner==1&&
                    post.hub_original_tag==pre_.core.tag&&post.hub.same_payload(pre_.core),"actual core-to-hub capture differs");
                adapter_.accept_model_request(pre_.core.address,{pre_.core.data,pre_.core.mask,true},pre_.core.tag,post.hub.tag,
                    {0,std::uint32_t(accepted_job_.tag),0,false});
            }
            if(pre_.hub_state==1&&pre_.hub_ready&&pre_.hub.write) {
                active(pre_);require(adapter_.debt_&&pre_.hub_owner==1&&pre_.hub_original_tag==adapter_.debt_->original_tag&&
                    pre_.hub.tag==adapter_.debt_->transport_tag&&pre_.hub.address==adapter_.debt_->request.addr&&
                    pre_.hub.data==adapter_.debt_->payload.data&&pre_.hub.mask==adapter_.debt_->payload.strb&&
                    post.dma.same_payload(pre_.hub)&&post.dma.tag==pre_.hub.tag&&post.hub_state==2&&post.dma_state==1&&
                    !post.dma_stream&&!post.dma_write_burst&&!post.dma_error,"actual hub-to-DMA acceptance differs");
                adapter_.dma_accept(pre_.hub_original_tag,pre_.hub.tag,adapter_.debt_->request,adapter_.debt_->payload);
            }
            if(pre_.axi.bf()) {
                active(pre_);require(adapter_.debt_&&pre_.dma.write&&pre_.dma.address==adapter_.debt_->request.addr&&
                    pre_.dma.mask==adapter_.debt_->payload.strb&&pre_.dma.data==adapter_.debt_->payload.data&&
                    pre_.dma.tag==adapter_.debt_->transport_tag&&!pre_.dma_error&&!pre_.dma_stream&&!pre_.dma_write_burst,
                    "actual DMA retained identity changed before B");
            }
            if(pre_.hub_state==2&&pre_.hub_response_valid&&adapter_.debt_) {
                require(pre_.hub_owner==1&&pre_.dma.tag==adapter_.debt_->transport_tag&&!pre_.dma_error&&post.hub_state==3&&
                    post.hub_reply_tag==adapter_.debt_->original_tag&&!post.hub_reply_error,"actual DMA reply/tag restoration differs");
                adapter_.dma_return(post.hub_reply_tag,pre_.dma.tag);
            }
            if(pre_.response_fire&&adapter_.debt_) {
                active(pre_);require(pre_.hub_state==3&&pre_.hub_owner==1&&pre_.hub_reply_tag==adapter_.debt_->original_tag&&
                    !pre_.hub_reply_error&&pre_.writeback_pending&&pre_.writeback_write&&pre_.writeback_tag==adapter_.debt_->original_tag&&
                    pre_.writeback_byte_count==64&&pre_.writeback_total<=owner_.n0().bytes-64&&
                    post.writeback_total==pre_.writeback_total+64&&!post.writeback_pending,"actual original response/writeback differs");
                adapter_.writeback_ack(pre_.hub_reply_tag,64);
            }
            const bool done=pre_.done_valid&&pre_.done_ready;
            const bool core_done=pre_.core_result_valid&&pre_.core_selected&&pre_.router_state==1&&pre_.done_ready;
            if(done||core_done) {
                require(done&&core_done,"real owner/core done disagree");active(pre_);
                require(pre_.core_status==0&&pre_.done_status==0&&!pre_.writeback_pending&&
                    pre_.writeback_total==owner_.n0().bytes&&!post.owner_active&&post.router_state==0,"actual N0 release differs");
                adapter_.owner_done(pre_.done_bytes,unsigned(pre_.done_status));
            }
            if(adapter_.accepted_&&!adapter_.done_)active(post);
        }
        void offer_launch() {
            checked([&]{require(!pending_&&!launched_&&!model_.io_launch_valid,"one private launch offer");
                canonical_host_wiring_v1::launch_payload(model_);model_.io_launch_valid=1;});
        }
        void settle_low(std::uint64_t edge) {
            checked([&]{
                require(!owner_.published_&&!pending_&&(!have_edge_||(edge_!=UINT64_MAX&&edge==edge_+1)),"one model low/high scheduler");
                drive(edge);model_.clock=0;model_.eval();
                require(!model_.io_resetRequired&&!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"low eval failed");
                pre_=fields_.read(false);healthy(pre_);inputs_=input_snapshot();
                require(model_.io_pc==0&&model_.io_issuedJobs<=1&&!model_.io_result_valid,"PC0-only scope before high");
                if(pre_.job_valid) {
                    const auto& j=pre_.bound;
                    require(model_.io_issuedJobs==0&&!adapter_.accepted_&&j.kind==0&&j.tag==(7U<<16)&&
                        j.m==128&&j.n==1536&&j.k==1536&&j.a==expected_inputs[15].base&&j.b==expected_inputs[9].base&&
                        j.c==0&&j.dst==owner_.n0().base&&j.writeBytes==owner_.n0().bytes,
                        "reject non-N0 or duplicate offered job BEFORE its high edge");
                }
                if(!have_edge_)require(!pre_.owner_active&&!pre_.job_valid&&!pre_.core_start&&pre_.hub_state==0&&pre_.dma_state==0&&
                    model_.io_issuedJobs==0&&model_.io_memoryAccepted_0==0&&model_.io_memoryAccepted_1==0&&
                    model_.io_memoryReturned_0==0&&model_.io_memoryReturned_1==0,"actual idle observation required");
                if(!launched_)require(!pre_.axi.ar_valid&&!pre_.axi.aw_valid&&!pre_.axi.w_valid&&!pre_.job_valid,"traffic before launch");
                if(model_.io_launch_valid)require(!launched_&&launch_matches(),"actual fixed launch differs");
                pre_launch_fire_=model_.io_launch_valid&&model_.io_launch_ready;
                pre_completion_fire_=model_.io_completion_valid&&model_.io_completion_ready;
                typename N0RetirementAdapter::Pins pins{};pins.axi=pre_.axi;
                if(model_.io_completion_valid) {
                    require(adapter_.done_&&!adapter_.debt_&&!read_&&!pre_.owner_active&&!pre_.job_valid&&!pre_.core_start&&
                        !pre_.memory_valid&&!pre_.response_fire&&!pre_.axi.ar_valid&&!pre_.axi.aw_valid&&!pre_.axi.w_valid,
                        "actual completion precedes retired local traffic");
                    axi_audit_.require_retired();require(model_.io_memoryAccepted_0==model_.io_memoryReturned_0&&
                        model_.io_memoryAccepted_1==model_.io_memoryReturned_1,"actual completion has hub debt");
                    const auto word=std::uint64_t(model_.io_completion_bits);
                    canonical_host_wiring_v1::require_pc0_completion_payload(word);
                    require(accepted_epoch_==7&&accepted_job_.tag==(7U<<16),"completion lacks accepted launch/job chain");
                    if(completion_held_)require(word==completion_word_,"actual completion changed while held");
                    completion_held_=true;completion_word_=word;
                    pins.completion_valid=true;pins.completion_ready=bool(model_.io_completion_ready);
                    // No such tag/epoch wires exist: these come from retained accepted events.
                    pins.completion_tag=std::uint32_t(accepted_job_.tag);pins.completion_epoch=std::uint16_t(accepted_epoch_);
                } else require(!completion_held_,"actual completion dropped before ACK");
                check_stalls(pre_.axi);adapter_.capture_low(edge,pins);edge_=edge;pending_=true;
            });
        }
        void rise_and_observe(std::uint64_t edge) {
            checked([&]{
                require(pending_&&edge==edge_&&model_.clock==0,"matching private high edge");unchanged_inputs(false);
                model_.clock=1;model_.eval();
                require(!model_.io_resetRequired&&!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"high eval failed");
                unchanged_inputs(true);const auto post=fields_.read(true);healthy(post);
                if(pre_launch_fire_){require(!launched_,"duplicate accepted launch");accepted_epoch_=inputs_[24];require(accepted_epoch_==7,"accepted launch epoch");launched_=true;}
                if(pre_completion_fire_)require(model_.io_pc==1&&model_.io_issuedJobs==1&&!post.owner_active,
                    "actual ACK0 must stop at post-PC1 with one issued owner");
                consume_internal(post);axi_audit_.consume(pre_.axi);advance_reads();
                // All fallible post/model checks finish BEFORE the adapter's B mutation.
                // Production admission still requires the original resident-before-N0 participant.
                adapter_.retire_high(edge);
                pending_=false;have_edge_=true;
                if(pre_completion_fire_)completion_held_=false; // noexcept bookkeeping only
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
        bool launch_matches() const {
            return model_.io_launch_bits_commandBase==std::uint64_t{4294967296ULL} &&
                model_.io_launch_bits_commandLimit==std::uint64_t{4294967680ULL} &&
                model_.io_launch_bits_commands==std::uint16_t{21} &&
                model_.io_launch_bits_descriptorBase==std::uint64_t{4294971392ULL} &&
                model_.io_launch_bits_descriptorLimit==std::uint64_t{4294974848ULL} &&
                model_.io_launch_bits_descriptors==std::uint32_t{215} &&
                model_.io_launch_bits_epoch==std::uint16_t{7} &&
                model_.io_launch_bits_regions_0_base==std::uint64_t{4295032832ULL} &&
                model_.io_launch_bits_regions_0_limit==std::uint64_t{4483535808ULL} &&
                model_.io_launch_bits_regions_0_read==true &&
                model_.io_launch_bits_regions_0_write==false &&
                model_.io_launch_bits_regions_1_base==std::uint64_t{4483535808ULL} &&
                model_.io_launch_bits_regions_1_limit==std::uint64_t{4507654464ULL} &&
                model_.io_launch_bits_regions_1_read==true &&
                model_.io_launch_bits_regions_1_write==true &&
                model_.io_launch_bits_regions_2_base==std::uint64_t{4294967296ULL} &&
                model_.io_launch_bits_regions_2_limit==std::uint64_t{4295032832ULL} &&
                model_.io_launch_bits_regions_2_read==true &&
                model_.io_launch_bits_regions_2_write==false &&
                model_.io_launch_bits_regions_3_base==std::uint64_t{4507654464ULL} &&
                model_.io_launch_bits_regions_3_limit==std::uint64_t{4508440896ULL} &&
                model_.io_launch_bits_regions_3_read==true &&
                model_.io_launch_bits_regions_3_write==true;
        }
    };
