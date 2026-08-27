# Descriptor v3

New metadata records are 0x04 and 0x32-0x35. New model policies are 0x13-0x19:
Attention, MoE, DeltaNet, QSA, Gated Residual, PLE and MTP. Policy records are
recognized but currently non-executable, returning completion status 4. This
allows compiler and runtime development without falsely advertising RTL support.
