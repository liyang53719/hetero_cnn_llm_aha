/*
 * Independent SOFTWARE reference for the all-products-BF16 RoPE candidate.
 * This is a host C/fenv cross-check, not an RTL or HardFloat implementation.
 *
 * Build:
 *   gcc -std=c11 -O2 -frounding-math -ffp-contract=off -fno-fast-math \
 *       scripts/rope_bf16_candidate_reference.c -lm -o /tmp/rope-bf16-reference
 *
 * Input: four arbitrary hexadecimal binary32 words e, o, c, s per line.
 * Output: exactly 25 hexadecimal uint32 words per accepted input row:
 *   [ 0.. 3] separate FP32 products ec, os, es, oc;
 *   [ 4.. 7] their host fenv flags;
 *   [ 8..11] four BF16 RNE converted products, widened to binary32;
 *   [12..15] their conversion flags;
 *   [16..17] separate FP32 sums ec + signflip(os), es + oc;
 *   [18..19] their host fenv flags;
 *   [20..21] terminal BF16 RNE conversions, widened to binary32;
 *   [22..23] terminal conversion flags;
 *   [24]     OR of every operation and conversion flag.
 * --converter takes one word per line and returns converted_word, flags.
 *
 * NaN results are canonical positive 0x7fc00000. Sign inversion for the first
 * sum is bitwise, including zero and NaN. FP32 flags are actual host fenv
 * observations, mapped to NV=16, DZ=8, OF=4, UF=2, NX=1. No flags are derived
 * from a Python/RTL oracle, and no host UF flag is removed. Host tininess at
 * the subnormal/min-normal rounding boundary can differ solely in UF from
 * a tininess-after-rounding implementation; report that difference separately.
 *
 * Conversion uses integer discarded-bit comparison and retained-word parity,
 * independently of an add-a-rounding-bias implementation. It signals NV only
 * for an input sNaN, OF|NX on finite overflow, and UF iff inexact with a rounded
 * destination exponent of zero. Infinity and signed zero are preserved.
 *
 * Requires native binary32 RNE with gradual underflow and correctly observed
 * sNaN exceptions. FTZ/DAZ and unsupported hosts are rejected at startup.
 * Blank lines are ignored. Malformed rows, embedded NULs, and lines longer
 * than 511 bytes (excluding newline) fail. Earlier complete rows may already
 * have been written, but malformed or failed rows produce no partial trace.
 */

#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include <ctype.h>
#include <errno.h>
#include <fenv.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

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

enum { ROW_WORDS = 25, FLAG_NX = 1, FLAG_UF = 2, FLAG_OF = 4,
       FLAG_DZ = 8, FLAG_NV = 16 };
enum operation { OP_MUL, OP_ADD };

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

static int nan_bits(uint32_t bits)
{
    return (bits & UINT32_C(0x7fffffff)) > UINT32_C(0x7f800000);
}

static int snan_bits(uint32_t bits)
{
    return nan_bits(bits) && !(bits & UINT32_C(0x00400000));
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

/* Materialize operands first, clear fenv, then execute exactly one operation.
 * A volatile store terminates binary32 evaluation; non-inlined calls prohibit
 * cross-stage fusion. Canonicalizing a NaN must not quiet it before arithmetic.
 * If a host loses an sNaN exception, reject it instead of manufacturing NV.
 */
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
static int fp32_operation(enum operation operation, uint32_t a_bits,
                          uint32_t b_bits, uint32_t *result_bits, uint32_t *flags)
{
    volatile float a = from_bits(a_bits);
    volatile float b = from_bits(b_bits);
    volatile float result;
    uint32_t raw;
    int raised;

    if (feclearexcept(FE_ALL_EXCEPT) != 0) return 0;
    if (operation == OP_MUL) result = a * b;
    else result = a + b;
    raised = fetestexcept(FE_ALL_EXCEPT);
    raw = to_bits(result);
    *result_bits = nan_bits(raw) ? UINT32_C(0x7fc00000) : raw;
    *flags = ieee_flags(raised);
    if ((snan_bits(a_bits) || snan_bits(b_bits)) && !(raised & FE_INVALID)) {
        return 0;
    }
    return 1;
}

static void bf16_rne(uint32_t input, uint32_t *output, uint32_t *flags)
{
    uint32_t high, discarded;
    *flags = 0;
    if (nan_bits(input)) {
        *output = UINT32_C(0x7fc00000);
        if (snan_bits(input)) *flags = FLAG_NV;
        return;
    }
    if ((input & UINT32_C(0x7fffffff)) == UINT32_C(0x7f800000)) {
        *output = input;
        return;
    }
    high = input >> 16;
    discarded = input & UINT32_C(0xffff);
    if (discarded > UINT32_C(0x8000) ||
        (discarded == UINT32_C(0x8000) && (high & 1u))) {
        ++high;
    }
    *output = high << 16;
    if (discarded != 0) {
        *flags = FLAG_NX;
        if ((high & UINT32_C(0x7f80)) == UINT32_C(0x7f80)) *flags |= FLAG_OF;
        if ((high & UINT32_C(0x7f80)) == 0) *flags |= FLAG_UF;
    }
}

static int evaluate_row(const uint32_t input[4], uint32_t row[ROW_WORDS])
{
    static const unsigned lhs[4] = {0, 1, 0, 1};
    static const unsigned rhs[4] = {2, 3, 3, 2};
    unsigned i;
    row[24] = 0;
    for (i = 0; i < 4; ++i) {
        if (!fp32_operation(OP_MUL, input[lhs[i]], input[rhs[i]],
                            &row[i], &row[4 + i])) return 0;
        bf16_rne(row[i], &row[8 + i], &row[12 + i]);
        row[24] |= row[4 + i] | row[12 + i];
    }
    for (i = 0; i < 2; ++i) {
        uint32_t a = row[8 + 2 * i];
        uint32_t b = row[9 + 2 * i];
        if (i == 0) b ^= UINT32_C(0x80000000);
        if (!fp32_operation(OP_ADD, a, b, &row[16 + i], &row[18 + i])) return 0;
        bf16_rne(row[16 + i], &row[20 + i], &row[22 + i]);
        row[24] |= row[18 + i] | row[22 + i];
    }
    return 1;
}

static int expect_operation(enum operation operation, uint32_t a, uint32_t b,
                            uint32_t expected, uint32_t expected_flags,
                            const char *label)
{
    uint32_t actual = 0, flags = 0;
    int ok = fp32_operation(operation, a, b, &actual, &flags);
    if (!ok || actual != expected || flags != expected_flags) {
        fprintf(stderr, "%s: supported=%d value=%08" PRIx32 " flags=%02" PRIx32
                "; expected %08" PRIx32 " flags=%02" PRIx32 "\n",
                label, ok, actual, flags, expected, expected_flags);
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
    /* Reject FTZ/DAZ rather than silently modifying the host's controls. */
    if (!expect_operation(OP_MUL, 0x00800000u, 0x3f000000u, 0x00400000u, 0,
                          "gradual-underflow/FTZ check") ||
        !expect_operation(OP_MUL, 0x00000001u, 0x3f800000u, 0x00000001u, 0,
                          "subnormal-input/DAZ check") ||
        !expect_operation(OP_ADD, 0x3f800000u, 0x33800000u, 0x3f800000u, FLAG_NX,
                          "nearest-even check") ||
        !expect_operation(OP_MUL, 0x7f800001u, 0x3f800000u, 0x7fc00000u, FLAG_NV,
                          "left signaling-NaN check") ||
        !expect_operation(OP_MUL, 0x3f800000u, 0xff800001u, 0x7fc00000u, FLAG_NV,
                          "right signaling-NaN check") ||
        !expect_operation(OP_ADD, 0x7fc00001u, 0xff800001u, 0x7fc00000u, FLAG_NV,
                          "quiet plus signaling-NaN check") ||
        !expect_operation(OP_MUL, 0xffc00001u, 0x3f800000u, 0x7fc00000u, 0,
                          "quiet-NaN check") ||
        !expect_operation(OP_MUL, 0u, 0x7f800000u, 0x7fc00000u, FLAG_NV,
                          "zero times infinity check") ||
        !expect_operation(OP_ADD, 0x7f800000u, 0xff800000u, 0x7fc00000u, FLAG_NV,
                          "opposite infinity check")) return 0;
    return feclearexcept(FE_ALL_EXCEPT) == 0;
}

static int self_test(void)
{
    static const uint32_t conversions[][3] = {
        {0x00000000u, 0x00000000u, 0}, {0x80000000u, 0x80000000u, 0},
        {0x3f800000u, 0x3f800000u, 0}, {0xbf800000u, 0xbf800000u, 0},
        {0x3f807fffu, 0x3f800000u, FLAG_NX},
        {0x3f808000u, 0x3f800000u, FLAG_NX},
        {0x3f808001u, 0x3f810000u, FLAG_NX},
        {0x3f818000u, 0x3f820000u, FLAG_NX},
        {0xbf808000u, 0xbf800000u, FLAG_NX},
        {0xbf818000u, 0xbf820000u, FLAG_NX},
        {0x00010000u, 0x00010000u, 0}, {0x80010000u, 0x80010000u, 0},
        {0x00000001u, 0x00000000u, FLAG_UF | FLAG_NX},
        {0x00008000u, 0x00000000u, FLAG_UF | FLAG_NX},
        {0x00008001u, 0x00010000u, FLAG_UF | FLAG_NX},
        {0x00018000u, 0x00020000u, FLAG_UF | FLAG_NX},
        {0x80008000u, 0x80000000u, FLAG_UF | FLAG_NX},
        {0x80008001u, 0x80010000u, FLAG_UF | FLAG_NX},
        {0x007f7fffu, 0x007f0000u, FLAG_UF | FLAG_NX},
        {0x007f8000u, 0x00800000u, FLAG_NX},
        {0x807f8000u, 0x80800000u, FLAG_NX},
        {0x00800000u, 0x00800000u, 0},
        {0x7f7f0000u, 0x7f7f0000u, 0},
        {0x7f7f7fffu, 0x7f7f0000u, FLAG_NX},
        {0x7f7f8000u, 0x7f800000u, FLAG_OF | FLAG_NX},
        {0xff7f8000u, 0xff800000u, FLAG_OF | FLAG_NX},
        {0x7f7fffffu, 0x7f800000u, FLAG_OF | FLAG_NX},
        {0xff7fffffu, 0xff800000u, FLAG_OF | FLAG_NX},
        {0x7f800000u, 0x7f800000u, 0}, {0xff800000u, 0xff800000u, 0},
        {0x7f800001u, 0x7fc00000u, FLAG_NV},
        {0x7fbfffffu, 0x7fc00000u, FLAG_NV},
        {0xff800001u, 0x7fc00000u, FLAG_NV},
        {0x7fc00000u, 0x7fc00000u, 0}, {0xffc00000u, 0x7fc00000u, 0},
        {0x7fffffffu, 0x7fc00000u, 0}, {0xffffffffu, 0x7fc00000u, 0}
    };
    /* Hard-coded full rows exercise trace ordering and aggregate semantics. */
    static const uint32_t inputs[][4] = {
        {0x3f800000u, 0x40000000u, 0x40400000u, 0x40800000u},
        {0x80000000u, 0u, 0x3f800000u, 0u},
        {0x7f800001u, 0u, 0x3f800000u, 0u},
        {0x7f7f8000u, 0u, 0x3f800000u, 0u},
        {0x3f818000u, 0u, 0x3f800000u, 0u}
    };
    static const uint32_t expected[][ROW_WORDS] = {
        {0x40400000u,0x41000000u,0x40800000u,0x40c00000u, 0,0,0,0,
         0x40400000u,0x41000000u,0x40800000u,0x40c00000u, 0,0,0,0,
         0xc0a00000u,0x41200000u, 0,0, 0xc0a00000u,0x41200000u, 0,0,0},
        {0x80000000u,0,0x80000000u,0, 0,0,0,0,
         0x80000000u,0,0x80000000u,0, 0,0,0,0,
         0x80000000u,0, 0,0, 0x80000000u,0, 0,0,0},
        {0x7fc00000u,0,0x7fc00000u,0, FLAG_NV,0,FLAG_NV,0,
         0x7fc00000u,0,0x7fc00000u,0, 0,0,0,0,
         0x7fc00000u,0x7fc00000u, 0,0, 0x7fc00000u,0x7fc00000u, 0,0,FLAG_NV},
        {0x7f7f8000u,0,0,0, 0,0,0,0,
         0x7f800000u,0,0,0, FLAG_OF|FLAG_NX,0,0,0,
         0x7f800000u,0, 0,0, 0x7f800000u,0, 0,0,FLAG_OF|FLAG_NX},
        {0x3f818000u,0,0,0, 0,0,0,0,
         0x3f820000u,0,0,0, FLAG_NX,0,0,0,
         0x3f820000u,0, 0,0, 0x3f820000u,0, 0,0,FLAG_NX}
    };
    uint32_t actual, flags, product, min_normal_flags, row[ROW_WORDS];
    size_t i, j;
    for (i = 0; i < sizeof(conversions) / sizeof(conversions[0]); ++i) {
        bf16_rne(conversions[i][0], &actual, &flags);
        if (actual != conversions[i][1] || flags != conversions[i][2]) {
            fprintf(stderr, "BF16 self-test %zu failed: %08" PRIx32
                    " flags=%02" PRIx32 "\n", i, actual, flags);
            return 0;
        }
    }
    if (!expect_operation(OP_MUL, 0x00000001u, 0x3f000000u, 0u,
                          FLAG_UF | FLAG_NX, "subnormal midpoint") ||
        !expect_operation(OP_MUL, 0x80000001u, 0x3f000000u, 0x80000000u,
                          FLAG_UF | FLAG_NX, "negative subnormal midpoint") ||
        !expect_operation(OP_MUL, 0x3f800001u, 0x3f800001u, 0x3f800002u,
                          FLAG_NX, "inexact multiplication") ||
        !expect_operation(OP_MUL, 0x7f7fffffu, 0x40000000u, 0x7f800000u,
                          FLAG_OF | FLAG_NX, "positive overflow") ||
        !expect_operation(OP_MUL, 0xff7fffffu, 0x40000000u, 0xff800000u,
                          FLAG_OF | FLAG_NX, "negative overflow") ||
        !expect_operation(OP_ADD, 0x7f7fffffu, 0x7f7fffffu, 0x7f800000u,
                          FLAG_OF | FLAG_NX, "addition overflow") ||
        !expect_operation(OP_ADD, 0x7fc00000u, 0xffc00000u, 0x7fc00000u, 0,
                          "canonical quiet-NaN addition") ||
        !expect_operation(OP_ADD, 0x7f800001u, 0x3f800000u, 0x7fc00000u, FLAG_NV,
                          "signaling-NaN addition")) return 0;

    /* NX is mandatory; retain the host's choice of tininess boundary. */
    if (!fp32_operation(OP_MUL, 0x00800000u, 0x3f7fffffu,
                        &actual, &min_normal_flags) || actual != 0x00800000u ||
        (min_normal_flags != FLAG_NX && min_normal_flags != (FLAG_UF | FLAG_NX))) {
        fprintf(stderr, "Min-normal midpoint self-test failed\n");
        return 0;
    }
    /* Separate product and add give +0; fmaf alone gives exactly -2^-46. */
    if (!fp32_operation(OP_MUL, 0x3f800001u, 0x3f7ffffeu, &product, &flags) ||
        product != 0x3f800000u || flags != FLAG_NX ||
        !expect_operation(OP_ADD, product, 0xbf800000u, 0, 0,
                          "unfused cancellation")) return 0;
    {
        volatile float a = from_bits(0x3f800001u);
        volatile float b = from_bits(0x3f7ffffeu);
        volatile float c = from_bits(0xbf800000u);
        volatile float fused = fmaf(a, b, c);
        if (to_bits(fused) != 0xa8800000u) {
            fprintf(stderr, "Fused/unfused distinction self-test failed\n");
            return 0;
        }
    }
    for (i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
        if (!evaluate_row(inputs[i], row)) {
            fprintf(stderr, "Trace self-test %zu could not evaluate\n", i);
            return 0;
        }
        for (j = 0; j < ROW_WORDS; ++j) {
            if (row[j] != expected[i][j]) {
                fprintf(stderr, "Trace self-test %zu word %zu: %08" PRIx32
                        "; expected %08" PRIx32 "\n", i, j, row[j], expected[i][j]);
                return 0;
            }
        }
    }
    if (fegetround() != FE_TONEAREST) {
        fprintf(stderr, "Self-test changed rounding mode\n");
        return 0;
    }
    puts("PASS: BF16 RNE conversion values/flags, signed zero, subnormals, NaNs,");
    puts("      infinities, FP32 flags, 25-word traces, and unfused operations.");
    puts("SOFTWARE reference: native binary32 FE_TONEAREST; separate volatile operations.");
    printf("Min-normal tie 00800000 * 3f7fffff -> 00800000: host flags=%02" PRIx32 "\n",
           min_normal_flags);
    puts("Host UF is preserved; min-normal boundary differences must be reported separately.");
    return !ferror(stdout);
}

/* Strict 1..8-digit hex words with optional 0x prefix; no signs or comments. */
static int parse_line(const char *line, uint32_t *input, unsigned words)
{
    const unsigned char *p = (const unsigned char *)line;
    unsigned word;
    while (isspace(*p)) ++p;
    if (*p == '\0') return 0;
    for (word = 0; word < words; ++word) {
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

/* Return line=1, EOF=0, embedded NUL=-1, overlong=-2, read error=-3. */
static int read_input_line(FILE *stream, char line[512])
{
    size_t used = 0;
    int ch;
    while ((ch = fgetc(stream)) != EOF) {
        if (ch == '\0') return -1;
        if (ch == '\n') {
            line[used] = '\0';
            return 1;
        }
        if (used == 511) return -2;
        line[used++] = (char)ch;
    }
    if (ferror(stream)) return -3;
    line[used] = '\0';
    return used != 0;
}

static void usage(FILE *stream, const char *program)
{
    fprintf(stream, "Usage: %s [--converter] [--input FILE] [--output FILE]\n", program);
    fprintf(stream, "       %s --self-test | --help\n", program);
    fputs("Default: four binary32 hex inputs e o c s; exactly 25 hex trace words.\n"
          "Trace: raw_products[4], mul_flags[4], bf16_products[4], conversion_flags[4],\n"
          "       sums[2], add_flags[2], bf16_outputs[2], terminal_flags[2], aggregate[1].\n"
          "--converter (alias --convert): one input word; converted word and flags.\n"
          "Flags: NV=16 DZ=8 OF=4 UF=2 NX=1; FP32 flags are host fenv observations.\n"
          "All uint32 inputs are accepted, including sNaN/qNaN, infinity and signed zero.\n"
          "NaN outputs canonicalize to positive 7fc00000; BF16 is widened to binary32.\n"
          "Requires RNE, native binary32, and gradual underflow; rejects FTZ/DAZ.\n"
          "Files default to stdin/stdout; FILE '-' selects the standard stream.\n"
          "Blank lines are ignored; input lines are limited to 511 bytes.\n"
          "Host min-normal UF differences are retained, never normalized away.\n", stream);
}

/* Compare the opened input, including redirected stdin, with a named output
 * before fopen("wb") can truncate it. stat follows symlinks, so relative,
 * absolute, hard-link and symbolic-link aliases are all checked. Any lookup
 * failure except an output that does not yet exist fails closed. This guards
 * existing aliases; callers must not replace paths concurrently with the run.
 */
static int output_is_separate(FILE *input_stream, const char *output_path)
{
    struct stat input_stat, output_stat;
    if (fstat(fileno(input_stream), &input_stat) != 0) {
        fprintf(stderr, "Cannot inspect input before opening output: %s\n", strerror(errno));
        return 0;
    }
    if (stat(output_path, &output_stat) != 0) {
        if (errno == ENOENT) return 1;
        fprintf(stderr, "Cannot inspect output '%s': %s\n", output_path, strerror(errno));
        return 0;
    }
    if (input_stat.st_dev == output_stat.st_dev &&
        input_stat.st_ino == output_stat.st_ino) {
        fprintf(stderr, "Input and output must not refer to the same file\n");
        return 0;
    }
    return 1;
}

int main(int argc, char **argv)
{
    const char *input_path = NULL, *output_path = NULL;
    FILE *input_stream = stdin, *output_stream = stdout;
    char line[512];
    size_t line_number = 0;
    int converter = 0, mode = 0, status = 0, arg;

    for (arg = 1; arg < argc; ++arg) {
        if (strcmp(argv[arg], "--help") == 0 || strcmp(argv[arg], "--self-test") == 0) {
            if (argc != 2) { usage(stderr, argv[0]); return 2; }
            mode = strcmp(argv[arg], "--help") == 0 ? 1 : 2;
        } else if (strcmp(argv[arg], "--converter") == 0 || strcmp(argv[arg], "--convert") == 0) {
            if (converter) { usage(stderr, argv[0]); return 2; }
            converter = 1;
        } else if (strcmp(argv[arg], "--input") == 0 || strcmp(argv[arg], "--output") == 0) {
            const char **path = strcmp(argv[arg], "--input") == 0 ? &input_path : &output_path;
            if (*path != NULL || ++arg == argc) { usage(stderr, argv[0]); return 2; }
            *path = argv[arg];
        } else {
            usage(stderr, argv[0]);
            return 2;
        }
    }
    if (mode == 1) { usage(stdout, argv[0]); return ferror(stdout) ? 1 : 0; }
    if (!setup_environment()) return 1;
    if (mode == 2) return self_test() ? 0 : 1;
    if (input_path && output_path && strcmp(input_path, output_path) == 0 &&
        strcmp(input_path, "-") != 0) {
        fprintf(stderr, "Input and output paths must differ\n");
        return 2;
    }
    if (input_path && strcmp(input_path, "-") != 0) {
        input_stream = fopen(input_path, "rb");
        if (!input_stream) {
            fprintf(stderr, "Cannot open input '%s': %s\n", input_path, strerror(errno));
            return 1;
        }
    }
    if (output_path && strcmp(output_path, "-") != 0) {
        if (!output_is_separate(input_stream, output_path)) {
            if (input_stream != stdin) fclose(input_stream);
            return 1;
        }
        output_stream = fopen(output_path, "wb");
        if (!output_stream) {
            fprintf(stderr, "Cannot open output '%s': %s\n", output_path, strerror(errno));
            if (input_stream != stdin) fclose(input_stream);
            return 1;
        }
    }
    for (;;) {
        uint32_t input[4], row[ROW_WORDS];
        char output[ROW_WORDS * 9 + 1];
        size_t used = 0;
        unsigned i, input_words = converter ? 1u : 4u;
        unsigned output_words = converter ? 2u : ROW_WORDS;
        int parsed, line_status = read_input_line(input_stream, line);
        if (line_status == 0) break;
        ++line_number;
        if (line_status < 0) {
            const char *reason = line_status == -1 ? "embedded NUL byte" :
                line_status == -2 ? "exceeds the 511-byte limit" : "input read failed";
            fprintf(stderr, "Line %zu: %s\n", line_number, reason);
            status = line_status == -3 ? 1 : 2;
            break;
        }
        parsed = parse_line(line, input, input_words);
        if (parsed == 0) continue;
        if (parsed < 0) {
            fprintf(stderr, "Line %zu: expected exactly %u uint32 hexadecimal word(s)\n",
                    line_number, input_words);
            status = 2;
            break;
        }
        if (converter) bf16_rne(input[0], &row[0], &row[1]);
        else if (!evaluate_row(input, row)) {
            fprintf(stderr, "Line %zu: unsupported host FP32/fenv behavior\n", line_number);
            status = 1;
            break;
        }
        for (i = 0; i < output_words; ++i) {
            int written = snprintf(output + used, sizeof(output) - used,
                                   "%08" PRIx32 "%c", row[i],
                                   i + 1 == output_words ? '\n' : ' ');
            if (written < 0 || (size_t)written >= sizeof(output) - used) {
                fprintf(stderr, "Output formatting failed\n");
                status = 1;
                break;
            }
            used += (size_t)written;
        }
        if (status != 0) break;
        if (fwrite(output, 1, used, output_stream) != used) {
            fprintf(stderr, "Output write failed\n");
            status = 1;
            break;
        }
    }
    if (input_stream != stdin && fclose(input_stream) != 0) {
        fprintf(stderr, "Input close failed\n");
        status = 1;
    }
    if (output_stream == stdout ? fflush(output_stream) != 0 : fclose(output_stream) != 0) {
        fprintf(stderr, "Output flush/close failed\n");
        status = 1;
    }
    return status;
}
