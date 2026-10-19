// Included inside RuntimeOwner. Authority is never public or callback supplied.
    class Pc1RetirementAdapter final {
        friend class RuntimeOwner;
        friend class Pc1ModelScheduler;
        RuntimeOwner& owner_;
        bool accepted_=false,done_=false,pending_=false,have_edge_=false,held_b_=false;
        std::uint64_t edge_=0,serial_=0,committed_=0,b_count_=0;
        canonical_host::Sample pre_{};
        std::optional<Address> aw_;
        std::deque<WriteBeat> queue_;
        std::vector<WriteBeat> staged_;
        explicit Pc1RetirementAdapter(RuntimeOwner& owner):owner_(owner) {
            require(owner_.phase_==Phase::Runtime&&owner_.adapter_&&owner_.published_&&
                    !owner_.outstanding_&&!owner_.pc1_adapter_&&!owner_.qraw_published_,
                    "PC1 adapter requires same live ACK0 RAM");
            owner_.pc1_adapter_=this;
        }
        ~Pc1RetirementAdapter() noexcept {
            if(owner_.pc1_adapter_==this){owner_.pc1_adapter_=nullptr;owner_.phase_=Phase::Poisoned;}
        }
        Pc1RetirementAdapter(const Pc1RetirementAdapter&)=delete;
        Pc1RetirementAdapter& operator=(const Pc1RetirementAdapter&)=delete;
        void identity()const {
            require(owner_.phase_==Phase::Runtime&&owner_.pc1_adapter_==this&&owner_.adapter_&&owner_.published_,
                    "PC1 dead or foreign same-RAM capability");
        }
        void accept_job(std::uint32_t tag,std::uint16_t epoch) {
            identity();require(!accepted_&&!done_&&tag==((7U<<16)|1U)&&epoch==7,
                               "PC1 unique accepted job identity");accepted_=true;
        }
        void capture_low(std::uint64_t edge,const canonical_host::Sample& s) {
            identity();require(!pending_&&(!have_edge_||edge==edge_+1),"PC1 consecutive low snapshot");
            require(s.aw_ready==(!aw_&&!held_b_&&edge%5!=0)&&
                    s.w_ready==(queue_.size()<256&&!held_b_&&edge%3!=0)&&s.b_valid==held_b_,
                    "PC1 fixed AXI ready and B source");
            if(held_b_)require(aw_&&s.b.id==aw_->id&&s.b.resp==0,"PC1 held B identity");
            if(s.aw_valid||s.w_valid)require(accepted_&&!done_,"PC1 write before accepted job or after done");
            pre_=s;edge_=edge;pending_=true;
        }
        void require_retired()const {
            require(!aw_&&!held_b_&&queue_.empty()&&staged_.empty()&&!owner_.pc1_outstanding_,
                    "PC1 local write debt remains");
        }
        void owner_done(std::uint64_t bytes,unsigned status) {
            identity();require_retired();
            require(accepted_&&!done_&&status==0&&bytes==pc01::qraw_bytes&&committed_==bytes&&b_count_>0,
                    "PC1 owner done before complete successful writes");
            owner_.require_mask(owner_.qraw().base,owner_.qraw().bytes);done_=true;
        }
        void check_ack()const {
            identity();require_retired();require(accepted_&&done_&&!owner_.qraw_published_&&
                committed_==pc01::qraw_bytes,"PC1 ACK before done or duplicate publication");
            owner_.require_mask(owner_.qraw().base,owner_.qraw().bytes);
        }
        void publish_noexcept()noexcept {owner_.qraw_published_=true;}
        void retire_high(std::uint64_t edge) {
            identity();require(pending_&&edge==edge_,"PC1 matching high snapshot");
            if(pre_.bf()) {
                require(accepted_&&!done_&&aw_&&held_b_&&!pre_.awf()&&!pre_.wf()&&
                        pre_.b.id==aw_->id&&pre_.b.resp==0,"PC1 successful isolated B gate");
                const auto tx=owner_.pc1_preflight_commit(this,*aw_,staged_,serial_);
                require(tx.count==64ULL*(aw_->len+1)&&committed_<=pc01::qraw_bytes-tx.count&&
                        b_count_<pc01::qraw_bytes/64,"PC1 B coverage counter bound");
                const auto count=tx.count;
                owner_.commit_prevalidated(tx); // same payload/mask, noexcept; N0 outstanding stays empty
                owner_.pc1_outstanding_.reset();committed_+=count;++b_count_;
                held_b_=false;aw_.reset();staged_.clear();pending_=false;have_edge_=true;
                return; // no fallible code after RAM mutation
            }
            if(pre_.awf()) {
                require(accepted_&&!done_&&!aw_&&!held_b_,"PC1 AW unique active owner");
                owner_.pc1_stage_aw(this,pre_.aw);aw_=pre_.aw;serial_=owner_.pc1_outstanding_->serial;
            }
            if(pre_.wf()) {
                require(accepted_&&!done_&&!held_b_&&queue_.size()<256&&pre_.w.strb==UINT64_MAX,
                        "PC1 full 64B W staging bound");queue_.push_back(pre_.w);
            }
            if(aw_&&queue_.size()>=std::size_t(aw_->len)+1) {
                require(!held_b_&&staged_.empty(),"PC1 duplicate staged B");
                std::vector<WriteBeat> candidate;candidate.reserve(aw_->len+1);
                for(unsigned i=0;i<=aw_->len;++i) {
                    require(queue_[i].last==(i==aw_->len)&&queue_[i].strb==UINT64_MAX,"PC1 exact WLAST and full strobe");
                    candidate.push_back(queue_[i]);
                }
                for(unsigned i=0;i<=aw_->len;++i)queue_.pop_front();
                staged_=std::move(candidate);held_b_=true;
            }
            pending_=false;have_edge_=true;
        }
    };
