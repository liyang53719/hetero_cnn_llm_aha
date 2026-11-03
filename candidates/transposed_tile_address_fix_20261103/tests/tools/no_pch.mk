# Verilator's supported VM_DEFAULT_RULES=0 extension point.
# Preserve generated object sets, flag order, user compile rules, archive and
# final Chiseltest link target. Only omit .gch prerequisites and PCH flags.
# Generated __pch.h remains an ordinary, real textual header, never an empty
# stand-in; there is no .gch production or compiler forced-PCH include.
ifneq ($(VM_DEFAULT_RULES),0)
$(error no_pch.mk requires VM_DEFAULT_RULES=0)
endif

%.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<

ifneq ($(strip $(VK_OBJS_FAST)),)
$(VK_OBJS_FAST): %.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<
endif

ifneq ($(strip $(VK_OBJS_SLOW)),)
$(VK_OBJS_SLOW): %.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_SLOW) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<
endif

ifneq ($(strip $(VK_GLOBAL_OBJS)),)
$(VK_GLOBAL_OBJS): %.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_GLOBAL) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<
endif
