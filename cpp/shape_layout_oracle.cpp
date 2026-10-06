// C03.3 independent arithmetic consumer, not a production tensor/RTL frontend.
//
// Read one tab-separated case per line (no header):
// operation, base, rank, comma-separated dims, comma-separated strides,
// element_bytes/dtype, comma-separated indices/region_base,
// address_bits/region_limit, stride_bits, span_bits.
//
// wide_address uses byte strides and a rank matching the dimensions list.
// tensor_v2 uses four dimensions, three signed24 ELEMENT strides and an explicit
// active rank; the final two fields are ignored. Decimal syntax is -?[0-9]+,
// without whitespace, hexadecimal, exponent notation or floating-point input.
// Empty list fields encode empty lists. Negative zero has integer value zero.
//
// Compile: c++ -std=c++17 -O2 -Wall -Wextra -Werror shape_layout_oracle.cpp
// Accepted rows start with OK and preserve the Python result field order.
// Rejected rows start with REJECT and the first contract error; malformed TSV
// or integer syntax uses input. Every input line produces one output line.

#include <algorithm>
#include <cstddef>
#include <iostream>
#include <string>
#include <vector>

namespace {

using Wide = unsigned __int128;

struct Rejection {
    const char* code;
};

void need(bool condition, const char* code) {
    if (!condition) {
        throw Rejection{code};
    }
}

// Preserve out-of-range integer tokens as such, rather than wrapping them or
// confusing a well-formed huge integer with a decimal syntax error. All actual
// contract arithmetic is bounded below 2^83 after input validation, so Wide is
// sufficient even for the intermediate values that a 64-bit consumer loses.
struct Decimal {
    Wide magnitude = 0;
    bool negative = false;
    bool overflow = false;
};

Decimal decimal(const std::string& token) {
    need(!token.empty(), "input");
    Decimal value;
    std::size_t position = 0;
    if (token.front() == '-') {
        value.negative = true;
        position = 1;
    }
    need(position != token.size(), "input");
    const Wide maximum = ~Wide{0};
    for (; position < token.size(); ++position) {
        const char character = token[position];
        need(character >= '0' && character <= '9', "input");
        const unsigned digit = static_cast<unsigned>(character - '0');
        if (!value.overflow) {
            if (value.magnitude > (maximum - digit) / 10) {
                value.overflow = true;
            } else {
                value.magnitude = value.magnitude * 10 + digit;
            }
        }
    }
    if (!value.overflow && value.magnitude == 0) {
        value.negative = false;
    }
    return value;
}

Wide unsigned_range(const std::string& token, Wide minimum, Wide maximum,
                    const char* code) {
    const Decimal value = decimal(token);
    need(!value.negative && !value.overflow && value.magnitude >= minimum &&
             value.magnitude <= maximum,
         code);
    return value.magnitude;
}

std::vector<std::string> split(const std::string& text, char separator) {
    std::vector<std::string> fields;
    std::size_t begin = 0;
    while (true) {
        const std::size_t end = text.find(separator, begin);
        fields.push_back(text.substr(begin, end == std::string::npos
                                                ? std::string::npos
                                                : end - begin));
        if (end == std::string::npos) {
            return fields;
        }
        begin = end + 1;
    }
}

std::vector<std::string> list(const std::string& text) {
    return text.empty() ? std::vector<std::string>{} : split(text, ',');
}

Wide power_of_two(Wide bits) {
    // The caller has already checked bits in [1, 64]. Never shift a u64 by 64.
    return Wide{1} << static_cast<unsigned>(bits);
}

Wide align64(Wide value) {
    return ((value + 63) / 64) * 64;
}

std::string output_decimal(Wide value) {
    std::string result;
    do {
        result.push_back(static_cast<char>('0' + static_cast<unsigned>(value % 10)));
        value /= 10;
    } while (value != 0);
    std::reverse(result.begin(), result.end());
    return result;
}

std::vector<Wide> wide_address(const std::vector<std::string>& fields) {
    // Follow the Python contract's validation order, including cases with
    // multiple bad fields. Arithmetic is performed only after each input's
    // encoding bounds have been established.
    const Wide address_bits = unsigned_range(fields[7], 1, 64, "address_bits");
    const Wide stride_bits = unsigned_range(fields[8], 1, 64, "stride_bits");
    const Wide span_bits = unsigned_range(fields[9], 1, 64, "span_bits");
    const Wide address_limit = power_of_two(address_bits);
    const Wide base = unsigned_range(fields[1], 0, address_limit - 1, "base_range");
    need(base % 64 == 0, "base_alignment");

    const Wide rank = unsigned_range(fields[2], 1, 4, "rank");
    const auto dimension_fields = list(fields[3]);
    need(dimension_fields.size() == rank, "rank");
    std::vector<Wide> dimensions;
    for (const auto& field : dimension_fields) {
        dimensions.push_back(unsigned_range(field, 1, 65535, "dimension_u16"));
    }

    const auto stride_fields = list(fields[4]);
    need(stride_fields.size() == dimensions.size(), "strides_rank");
    std::vector<Wide> strides;
    const Wide stride_maximum = power_of_two(stride_bits) - 1;
    for (const auto& field : stride_fields) {
        strides.push_back(unsigned_range(field, 1, stride_maximum, "stride_range"));
    }
    const Wide element_bytes = unsigned_range(fields[5], 1, 8, "element_bytes");
    need(element_bytes == 1 || element_bytes == 2 || element_bytes == 4 ||
             element_bytes == 8,
         "element_bytes");
    need(strides.back() == element_bytes, "stride_overlap");
    for (std::size_t index = 0; index + 1 < dimensions.size(); ++index) {
        need(strides[index] >= strides[index + 1] * dimensions[index + 1],
             "stride_overlap");
    }

    const auto index_fields = list(fields[6]);
    need(index_fields.size() == dimensions.size(), "indices_rank");
    std::vector<Wide> indices;
    for (std::size_t index = 0; index < dimensions.size(); ++index) {
        indices.push_back(unsigned_range(index_fields[index], 0,
                                         dimensions[index] - 1, "index_range"));
    }

    Wide elements = 1;
    Wide span = element_bytes;
    Wide offset = 0;
    for (std::size_t index = 0; index < dimensions.size(); ++index) {
        elements *= dimensions[index];
        span += (dimensions[index] - 1) * strides[index];
        offset += indices[index] * strides[index];
    }
    const Wide payload = elements * element_bytes;
    const Wide span_limit = power_of_two(span_bits);
    need(payload < span_limit && span < span_limit && offset < span_limit,
         "span_overflow");
    const Wide end = base + span;
    const Wide padded_end = align64(end);
    need(end <= address_limit && padded_end <= address_limit, "address_overflow");
    return {elements, payload, span, offset, base + offset, end, padded_end};
}

std::vector<Wide> tensor_v2(const std::vector<std::string>& fields) {
    const Wide address_limit = Wide{1} << 56;
    const Wide base = unsigned_range(fields[1], 0, address_limit - 1, "base_range");
    const Wide rank = unsigned_range(fields[2], 1, 4, "rank");
    const auto dimension_fields = list(fields[3]);
    need(dimension_fields.size() == 4, "rank");
    std::vector<Wide> dimensions;
    for (const auto& field : dimension_fields) {
        dimensions.push_back(unsigned_range(field, 1, (Wide{1} << 18) - 1,
                                             "dimension_u18"));
    }
    for (std::size_t index = static_cast<std::size_t>(rank);
         index < dimensions.size(); ++index) {
        need(dimensions[index] == 1, "inactive_dimension");
    }

    const auto stride_fields = list(fields[4]);
    need(stride_fields.size() == 3, "strides_rank");
    std::vector<Decimal> strides;
    for (const auto& field : stride_fields) {
        const Decimal stride = decimal(field);
        const Wide magnitude_limit = stride.negative ? Wide{1} << 23
                                                    : (Wide{1} << 23) - 1;
        need(!stride.overflow && stride.magnitude <= magnitude_limit, "stride_s24");
        strides.push_back(stride);
    }
    const Decimal dtype = decimal(fields[5]);
    need(!dtype.negative && !dtype.overflow &&
             (dtype.magnitude == 5 || dtype.magnitude == 7),
         "dtype");
    const Wide region_base = unsigned_range(fields[6], 0, address_limit - 1,
                                            "region_range");
    const Wide region_limit = unsigned_range(fields[7], 0, address_limit,
                                             "region_range");

    need(region_base % 64 == 0 && region_limit % 64 == 0, "region_alignment");

    Wide elements = 1;
    bool owner_dimensions_fit_u16 = true;
    for (const Wide dimension : dimensions) {
        elements *= dimension;
        owner_dimensions_fit_u16 = owner_dimensions_fit_u16 && dimension <= 65535;
    }
    const Wide payload = elements * (dtype.magnitude == 5 ? 2 : 4);
    const Wide end = base + align64(payload);
    need(elements <= (Wide{1} << 32) - 1 && base % 64 == 0 && base < end &&
             end <= address_limit,
         "bounds");

    const std::vector<Wide> expected_strides = {
        dimensions[1] * dimensions[2] * dimensions[3],
        dimensions[2] * dimensions[3], dimensions[3]};
    for (std::size_t index = 0; index < strides.size(); ++index) {
        need(!strides[index].negative &&
                 strides[index].magnitude == expected_strides[index],
             "stride_unsupported");
    }
    need(region_base < region_limit && region_base <= base && end <= region_limit,
         "region_bounds");
    return {elements, payload, end, owner_dimensions_fit_u16 ? Wide{1} : Wide{0}};
}

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    std::string line;
    while (std::getline(std::cin, line)) {
        // Accept conventional CRLF line endings without permitting whitespace
        // inside decimal fields.
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        try {
            const auto fields = split(line, '\t');
            need(fields.size() == 10, "input");
            std::vector<Wide> result;
            if (fields[0] == "wide_address") {
                result = wide_address(fields);
            } else if (fields[0] == "tensor_v2") {
                result = tensor_v2(fields);
            } else {
                throw Rejection{"unknown_operation"};
            }
            std::cout << "OK";
            for (const Wide value : result) {
                std::cout << '\t' << output_decimal(value);
            }
            std::cout << '\n';
        } catch (const Rejection& error) {
            std::cout << "REJECT\t" << error.code << '\n';
        }
    }
    return std::cin.bad() ? 1 : 0;
}
