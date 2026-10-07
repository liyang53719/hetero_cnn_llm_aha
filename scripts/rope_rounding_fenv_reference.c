/*
 * Independent SOFTWARE RoPE rounding-ablation reference.  This is not an RTL
 * implementation, a replacement for the production path, or a HardFloat model.
 *
 * Build:
 *   gcc -std=c11 -O2 -frounding-math -ffp-contract=off -fno-fast-math \
 *       scripts/rope_rounding_fenv_reference.c -lm -o /tmp/rope-fenv-reference
 *
 * stdin: one pair per line, four hexadecimal binary32 words: e o c s.
 * Blank lines are ignored.  Nonempty lines must have exactly four words.
 * stdout: 72 hexadecimal uint32 words per accepted input line.  The four
 * consecutive 18-word traces are fp32_all, cos_bf16_only, sin_bf16_only,
 * both_bf16.  Each trace contains, in order:
 *   raw products ec, os, es, oc (4);
 *   actual host IEEE exception flags for those products (4);
 *   products after the selected optional BF16 RNE round (4);
 *   binary32 sums ec + (-os), es + oc (2);
 *   actual host IEEE exception flags for those sums (2);
 *   terminal BF16 RNE outputs in binary32 containers (2).
 * Flags are mapped to NV=16, DZ=8, OF=4, UF=2, NX=1, independently of the
 * numeric values assigned to the C FE_* constants.  They are never inferred
 * from a Python/RTL oracle or adjusted to agree with hardware.
 *
 * Only finite inputs, products, selected products, sums and terminal outputs
 * are accepted.  Every variant is validated before any part of a row is
 * written.  Overflow, nonfinite data, malformed input, or an unsupported host
 * exits nonzero.  Earlier complete accepted rows may already have been sent.
 * Signed zero and gradual binary32/BF16 subnormals are supported.  BF16 rounds
 * are integer bit operations, so they do not add host FP exception flags.
 *
 * Limit: exception behavior belongs to the host C fenv.  In particular, a
 * binary32 underflow/min-normal rounding boundary can flag differently from
 * a HardFloat tininess-after-rounding oracle.  Such differences must be
 * reported separately; this program does not manufacture hardware flags.
 */

#include <ctype.h>
#include <fenv.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* GCC uses the required command-line flags instead of these C11 pragmas. */
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunknown-pragmas"
#endif
#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic pop
#endif

#if defined(__FAST_MATH__) || (defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__)
#error "Compile without fast-math or finite-math-only assumptions"
#endif
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MIN_EXP != -125 || FLT_MAX_EXP != 128
#error "An IEEE-754 binary32 float implementation is required"
#endif
#if FLT_EVAL_METHOD != 0
#error "Native binary32 evaluation (FLT_EVAL_METHOD == 0) is required"
#endif
#if !defined(FE_TONEAREST) || !defined(FE_INVALID) || !defined(FE_DIVBYZERO) || \
    !defined(FE_OVERFLOW) || !defined(FE_UNDERFLOW) || !defined(FE_INEXACT)
#error "All five IEEE exception flags and round-to-nearest are required"
#endif

_Static_assert(sizeof(float) == sizeof(uint32_t), "float must be 32 bits");
_Static_assert(sizeof(uint32_t) == 4, "uint32_t must occupy four bytes");

enum { TRACE_WORDS = 18, VARIANTS = 4, ROW_WORDS = TRACE_WORDS * VARIANTS };
enum { FLAG_NX = 1, FLAG_UF = 2, FLAG_OF = 4, FLAG_DZ = 8, FLAG_NV = 16 };
enum operation { OP_MUL, OP_ADD };
enum op_status { OP_OK, OP_FENV_ERROR, OP_NONFINITE, OP_OVERFLOW };

static const char *const variant_names[VARIANTS] = {
    "fp32_all", "cos_bf16_only", "sin_bf16_only", "both_bf16"
};

static float from_bits(uint32_t bits)
{
    float result;
    memcpy(&result, &bits, sizeof(result));
    return result;
}

static uint32_t to_bits(float value)
{
    uint32_t result;
    memcpy(&result, &value, sizeof(result));
    return result;
}

static int finite_bits(uint32_t bits)
{
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static uint32_t ieee_flags(int flags)
{
    uint32_t result = 0;
    if (flags & FE_INVALID) result |= FLAG_NV;
    if (flags & FE_DIVBYZERO) result |= FLAG_DZ;
    if (flags & FE_OVERFLOW) result |= FLAG_OF;
    if (flags & FE_UNDERFLOW) result |= FLAG_UF;
    if (flags & FE_INEXACT) result |= FLAG_NX;
    return result;
}

/* An explicit volatile binary32 store terminates each operation.  Keeping
 * operations in separate non-inlined calls also prevents cross-stage fusion.
 * Neither double arithmetic nor fmaf is used by the actual RoPE evaluator.
 */
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
static enum op_status fp32_operation(enum operation operation,
                                     uint32_t a_bits, uint32_t b_bits,
                                     uint32_t *result_bits, uint32_t *flags)
{
    volatile float a = from_bits(a_bits);
    volatile float b = from_bits(b_bits);
    volatile float result;
    int raised;

    if (!finite_bits(a_bits) || !finite_bits(b_bits)) return OP_NONFINITE;
    if (feclearexcept(FE_ALL_EXCEPT) != 0) return OP_FENV_ERROR;
    if (operation == OP_MUL) result = a * b;
    else result = a + b;
    raised = fetestexcept(FE_ALL_EXCEPT);
    *result_bits = to_bits(result);
    *flags = ieee_flags(raised);
    if (raised & FE_OVERFLOW) return OP_OVERFLOW;
    if (!finite_bits(*result_bits)) return OP_NONFINITE;
    return OP_OK;
}

/* RNE, deliberately expressed as a discarded-bit comparison and high-word
 * parity test, rather than the common add-a-rounding-bias implementation.
 * Negative numbers and signed zero use exactly the same magnitude-bit rule.
 */
static int bf16_rne(uint32_t input, uint32_t *output)
{
    uint32_t high, discarded;
    if (!finite_bits(input)) return 0;
    high = input >> 16;
    discarded = input & UINT32_C(0xffff);
    if (discarded > UINT32_C(0x8000) ||
        (discarded == UINT32_C(0x8000) && (high & 1u))) {
        ++high;
    }
    *output = high << 16;
    return finite_bits(*output);
}

static int evaluate_row(const uint32_t input[4], uint32_t row[ROW_WORDS],
                        char *error, size_t error_size)
{
    static const unsigned lhs[4] = {0, 1, 0, 1};
    static const unsigned rhs[4] = {2, 3, 3, 2};
    uint32_t products[4], product_flags[4];
    unsigned i, variant;

    for (i = 0; i < 4; ++i) {
        if (!finite_bits(input[i])) {
            snprintf(error, error_size, "nonfinite input word %u", i);
            return 0;
        }
    }
    for (i = 0; i < 4; ++i) {
        enum op_status status = fp32_operation(OP_MUL, input[lhs[i]],
            input[rhs[i]], &products[i], &product_flags[i]);
        if (status != OP_OK) {
            snprintf(error, error_size, "FP32 product %u rejected (status %d)",
                     i, (int)status);
            return 0;
        }
    }

    for (variant = 0; variant < VARIANTS; ++variant) {
        uint32_t *trace = row + variant * TRACE_WORDS;
        for (i = 0; i < 4; ++i) {
            int is_cosine = (i == 0 || i == 3);
            int round_product = is_cosine ? (variant & 1u) : (variant & 2u);
            trace[i] = products[i];
            trace[4 + i] = product_flags[i];
            trace[8 + i] = products[i];
            if (round_product && !bf16_rne(products[i], &trace[8 + i])) {
                snprintf(error, error_size, "%s product %u BF16 overflow",
                         variant_names[variant], i);
                return 0;
            }
        }
        for (i = 0; i < 2; ++i) {
            uint32_t a = trace[8 + 2 * i];
            uint32_t b = trace[9 + 2 * i];
            enum op_status status;
            /* A bitwise sign inversion preserves negative and positive zero. */
            if (i == 0) b ^= UINT32_C(0x80000000);
            status = fp32_operation(OP_ADD, a, b, &trace[12 + i], &trace[14 + i]);
            if (status != OP_OK) {
                snprintf(error, error_size, "%s FP32 sum %u rejected (status %d)",
                         variant_names[variant], i, (int)status);
                return 0;
            }
            if (!bf16_rne(trace[12 + i], &trace[16 + i])) {
                snprintf(error, error_size, "%s terminal %u BF16 overflow",
                         variant_names[variant], i);
                return 0;
            }
        }
    }
    return 1;
}

static int expect_operation(enum operation operation, uint32_t a, uint32_t b,
                            uint32_t expected, uint32_t expected_flags,
                            const char *label)
{
    uint32_t actual = 0, flags = 0;
    enum op_status status = fp32_operation(operation, a, b, &actual, &flags);
    if (status != OP_OK || actual != expected || flags != expected_flags) {
        fprintf(stderr, "%s: status=%d value=%08" PRIx32 " flags=%02" PRIx32
                "; expected %08" PRIx32 " flags=%02" PRIx32 "\n",
                label, (int)status, actual, flags, expected, expected_flags);
        return 0;
    }
    return 1;
}

static int setup_environment(void)
{
    if (to_bits(1.0f) != UINT32_C(0x3f800000) ||
        to_bits(-0.0f) != UINT32_C(0x80000000)) {
        fprintf(stderr, "Unsupported float object representation\n");
        return 0;
    }
    if (fesetround(FE_TONEAREST) != 0 || fegetround() != FE_TONEAREST) {
        fprintf(stderr, "Cannot establish FE_TONEAREST\n");
        return 0;
    }
    /* Also reject FTZ/DAZ environments rather than silently changing them. */
    if (!expect_operation(OP_MUL, UINT32_C(0x00800000), UINT32_C(0x3f000000),
                          UINT32_C(0x00400000), 0, "gradual-underflow check") ||
        !expect_operation(OP_MUL, UINT32_C(0x00000001), UINT32_C(0x3f800000),
                          UINT32_C(0x00000001), 0, "subnormal-input check") ||
        !expect_operation(OP_ADD, UINT32_C(0x3f800000), UINT32_C(0x33800000),
                          UINT32_C(0x3f800000), FLAG_NX, "nearest-even check")) {
        return 0;
    }
    return feclearexcept(FE_ALL_EXCEPT) == 0;
}

static int self_test(void)
{
    static const uint32_t bf16_cases[][2] = {
        {0x00000000u, 0x00000000u}, {0x80000000u, 0x80000000u},
        {0x3f807fffu, 0x3f800000u}, {0x3f808000u, 0x3f800000u},
        {0x3f808001u, 0x3f810000u}, {0x3f818000u, 0x3f820000u},
        {0xbf808000u, 0xbf800000u}, {0xbf818000u, 0xbf820000u},
        {0x00000001u, 0x00000000u}, {0x00008000u, 0x00000000u},
        {0x00008001u, 0x00010000u}, {0x00018000u, 0x00020000u},
        {0x80008000u, 0x80000000u}, {0x80008001u, 0x80010000u},
        {0x007f8000u, 0x00800000u}, {0x7f7f0000u, 0x7f7f0000u}
    };
    uint32_t result = 0, flags = 0, product = 0, min_normal_flags = 0;
    uint32_t row[ROW_WORDS];
    const uint32_t zeros[4] = {0x80000000u, 0u, 0x3f800000u, 0u};
    const uint32_t late_overflow[4] = {0x7f7f7fffu, 0u, 0x3f800000u, 0u};
    char error[160];
    size_t i;

    for (i = 0; i < sizeof(bf16_cases) / sizeof(bf16_cases[0]); ++i) {
        if (!bf16_rne(bf16_cases[i][0], &result) || result != bf16_cases[i][1]) {
            fprintf(stderr, "BF16 self-test %zu failed\n", i);
            return 0;
        }
    }
    if (bf16_rne(UINT32_C(0x7f7fffff), &result) ||
        bf16_rne(UINT32_C(0xff7fffff), &result) ||
        bf16_rne(UINT32_C(0x7f800000), &result) ||
        bf16_rne(UINT32_C(0x7fc00000), &result)) {
        fprintf(stderr, "BF16 overflow/nonfinite rejection self-test failed\n");
        return 0;
    }
    if (!expect_operation(OP_MUL, 0x00000001u, 0x3f000000u, 0u,
                          FLAG_UF | FLAG_NX, "subnormal midpoint") ||
        !expect_operation(OP_MUL, 0x80000001u, 0x3f000000u, 0x80000000u,
                          FLAG_UF | FLAG_NX, "negative subnormal midpoint") ||
        !expect_operation(OP_MUL, 0x3f800001u, 0x3f800001u, 0x3f800002u,
                          FLAG_NX, "inexact multiplication")) return 0;
    if (fp32_operation(OP_MUL, 0x7f7fffffu, 0x40000000u, &result, &flags)
            != OP_OVERFLOW || flags != (FLAG_OF | FLAG_NX)) {
        fprintf(stderr, "FP32 overflow rejection self-test failed\n");
        return 0;
    }
    /* Exactly halfway between the largest subnormal and the minimum normal.
     * NX is required; preserve rather than prescribe the host's UF behavior.
     */
    if (fp32_operation(OP_MUL, 0x00800000u, 0x3f7fffffu,
                       &result, &min_normal_flags) != OP_OK ||
        result != UINT32_C(0x00800000) ||
        (min_normal_flags != FLAG_NX && min_normal_flags != (FLAG_UF | FLAG_NX))) {
        fprintf(stderr, "Min-normal midpoint self-test failed\n");
        return 0;
    }

    /* (1 + 2^-23) * (1 - 2^-23) - 1 is +0 with separate binary32
     * multiply/add, but exactly -2^-46 when fused.  fmaf is used only here.
     */
    if (fp32_operation(OP_MUL, 0x3f800001u, 0x3f7ffffeu, &product, &flags)
            != OP_OK || product != 0x3f800000u || flags != FLAG_NX ||
        !expect_operation(OP_ADD, product, 0xbf800000u, 0u, 0,
                          "unfused cancellation")) return 0;
    {
        volatile float a = from_bits(0x3f800001u);
        volatile float b = from_bits(0x3f7ffffeu);
        volatile float c = from_bits(0xbf800000u);
        volatile float fused = fmaf(a, b, c);
        if (to_bits(fused) != UINT32_C(0xa8800000)) {
            fprintf(stderr, "Fused/unfused distinction self-test failed\n");
            return 0;
        }
    }
    if (!evaluate_row(zeros, row, error, sizeof(error))) {
        fprintf(stderr, "Signed-zero row self-test failed: %s\n", error);
        return 0;
    }
    for (i = 0; i < VARIANTS; ++i) {
        if (row[i * TRACE_WORDS + 16] != UINT32_C(0x80000000) ||
            row[i * TRACE_WORDS + 17] != 0u) {
            fprintf(stderr, "Signed-zero output self-test failed\n");
            return 0;
        }
    }
    /* This finite row remains accepted: values just below a BF16 overflow
     * midpoint round down.  The immediately adjacent midpoint is rejected.
     */
    if (!evaluate_row(late_overflow, row, error, sizeof(error))) {
        fprintf(stderr, "Finite BF16 boundary self-test failed: %s\n", error);
        return 0;
    }
    {
        const uint32_t reject[4] = {0x7f7f8000u, 0u, 0x3f800000u, 0u};
        if (evaluate_row(reject, row, error, sizeof(error))) {
            fprintf(stderr, "Whole-row BF16 overflow rejection self-test failed\n");
            return 0;
        }
    }
    if (fegetround() != FE_TONEAREST) {
        fprintf(stderr, "Self-test changed rounding mode\n");
        return 0;
    }
    puts("PASS: BF16 ties-to-even, signed zero, gradual subnormals, FP32 flags,");
    puts("      finite-domain rejection, and fused/unfused distinction.");
    puts("SOFTWARE reference: native binary32 FE_TONEAREST; separate volatile operations.");
    puts("Flags are host fenv observations; min-normal underflow flags may differ from HardFloat.");
    printf("Min-normal tie 00800000 * 3f7fffff -> 00800000: host flags=%02" PRIx32 "\n",
           min_normal_flags);
    return !ferror(stdout);
}

/* 1..8 hexadecimal digits, with an optional 0x prefix.  Signs and trailing
 * tokens are rejected instead of being silently accepted by strtoul/sscanf.
 * Return 0 for blank lines, 1 for a row, -1 for malformed input.
 */
static int parse_line(const char *line, uint32_t input[4])
{
    const unsigned char *p = (const unsigned char *)line;
    unsigned word;
    while (isspace(*p)) ++p;
    if (*p == '\0') return 0;
    for (word = 0; word < 4; ++word) {
        uint32_t value = 0;
        unsigned digits = 0;
        if (p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) p += 2;
        while (isxdigit(*p)) {
            unsigned digit = (*p >= '0' && *p <= '9')
                ? (unsigned)(*p - '0') : (unsigned)(tolower(*p) - 'a' + 10);
            if (++digits > 8) return -1;
            value = (value << 4) | digit;
            ++p;
        }
        if (digits == 0 || (*p != '\0' && !isspace(*p))) return -1;
        input[word] = value;
        while (isspace(*p)) ++p;
    }
    return *p == '\0' ? 1 : -1;
}

/* Read the whole row before parsing it, including detecting embedded NULs.
 * Return 1 for a line, 0 for EOF, -1 for NUL, -2 for too long, -3 for I/O error.
 * The 511-byte limit excludes the newline and includes all other whitespace.
 */
static int read_input_line(char line[512])
{
    size_t used = 0;
    int ch;
    while ((ch = fgetc(stdin)) != EOF) {
        if (ch == '\0') return -1;
        if (ch == '\n') {
            line[used] = '\0';
            return 1;
        }
        if (used == 511) return -2;
        line[used++] = (char)ch;
    }
    if (ferror(stdin)) return -3;
    line[used] = '\0';
    return used != 0;
}

int main(int argc, char **argv)
{
    char line[512], error[160];
    size_t line_number = 0;
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        puts("Usage: rope-fenv-reference [--self-test | --help]");
        puts("Input: e o c s (four hexadecimal finite binary32 words per line).");
        puts("Output: fp32_all, cos_bf16_only, sin_bf16_only, both_bf16; 18 words each.");
        puts("Trace: raw_product[4], product_flags[4], selected_product[4],");
        puts("       fp32_sum[2], sum_flags[2], terminal_bf16_in_fp32[2].");
        puts("Flags: NV=16 DZ=8 OF=4 UF=2 NX=1, observed from host fenv.");
        puts("Requires native binary32, FE_TONEAREST and gradual subnormals.");
        puts("Rejects nonfinite values and FP32/BF16 overflow atomically per row.");
        puts("Blank lines are ignored; input lines are limited to 511 bytes.");
        puts("Host underflow flags at min-normal ties can differ from HardFloat.");
        return ferror(stdout) ? 1 : 0;
    }
    if (argc > 2 || (argc == 2 && strcmp(argv[1], "--self-test") != 0)) {
        fprintf(stderr, "Usage: %s [--self-test | --help]\n", argv[0]);
        return 2;
    }
    if (!setup_environment()) return 1;
    if (argc == 2) return self_test() ? 0 : 1;

    for (;;) {
        uint32_t input[4], row[ROW_WORDS];
        char output[ROW_WORDS * 9 + 1];
        size_t used = 0;
        unsigned i;
        int parsed, line_status = read_input_line(line);
        if (line_status == 0) break;
        ++line_number;
        if (line_status < 0) {
            const char *reason = line_status == -1 ? "embedded NUL byte" :
                line_status == -2 ? "exceeds the 511-byte limit" : "input read failed";
            fprintf(stderr, "Line %zu: %s\n", line_number, reason);
            return line_status == -3 ? 1 : 2;
        }
        parsed = parse_line(line, input);
        if (parsed == 0) continue;
        if (parsed < 0) {
            fprintf(stderr, "Line %zu: expected exactly four uint32 hexadecimal words\n",
                    line_number);
            return 2;
        }
        if (!evaluate_row(input, row, error, sizeof(error))) {
            fprintf(stderr, "Line %zu: %s\n", line_number, error);
            return 1;
        }
        for (i = 0; i < ROW_WORDS; ++i) {
            int written = snprintf(output + used, sizeof(output) - used,
                                   "%08" PRIx32 "%c", row[i],
                                   i + 1 == ROW_WORDS ? '\n' : ' ');
            if (written < 0 || (size_t)written >= sizeof(output) - used) {
                fprintf(stderr, "Output formatting failed\n");
                return 1;
            }
            used += (size_t)written;
        }
        if (fwrite(output, 1, used, stdout) != used) {
            fprintf(stderr, "Output write failed\n");
            return 1;
        }
    }
    if (ferror(stdin)) {
        fprintf(stderr, "Input read failed\n");
        return 1;
    }
    if (fflush(stdout) != 0) {
        fprintf(stderr, "Output flush failed\n");
        return 1;
    }
    return 0;
}
