/* Minimal freestanding RV64 smoke; no libc/libgloss dependency. */
.section .text
.globl _start
_start:
  li   a0, 1
  addi a0, a0, 41
1:
  j    1b
