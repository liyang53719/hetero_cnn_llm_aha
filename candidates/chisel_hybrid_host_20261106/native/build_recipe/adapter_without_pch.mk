# Build-only policy: same generated model and normal compiler flags, no PCH.
# Do not edit Verilator's pinned installed makefile or generated source files.
VM_DEFAULT_RULES := 0
include VOriginalIdmaAdapterProbe.mk

$(VK_OBJS_FAST): %.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<
$(VK_OBJS_SLOW): %.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_SLOW) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<
$(VK_GLOBAL_OBJS): %.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_GLOBAL) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<

# Preserve the original generic rule for aggregated __ALL.cpp builds.
%.o: %.cpp
	$(OBJCACHE) $(CXX) $(OPT_FAST) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<
