// SPDX-License-Identifier: Apache-2.0
// Read-only extractor for the exact AHA test_app parser/map control tables.
#include <stdio.h>
#include <stdlib.h>

#include "gen.h"
#include "map.h"
#include "parser.h"

static void emit_config(const char *name, void *config) {
  const int count = get_configuration_size(config);
  printf("\"%s\":[", name);
  for (int index = 0; index < count; ++index) {
    if (index) printf(",");
    printf("{\"address\":%u,\"data\":%u}",
           (unsigned)get_configuration_addr(config, index),
           (unsigned)get_configuration_data(config, index));
  }
  printf("]");
}

int main(int argc, char **argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s <design_meta.json> <cgra_columns>\n", argv[0]);
    return 2;
  }
  const int columns = atoi(argv[2]);
  if (!initialize_monitor(columns)) {
    fprintf(stderr, "failed to initialize monitor for %d columns\n", columns);
    return 3;
  }
  void *kernel = parse_metadata(argv[1]);
  if (!kernel || !glb_map(kernel, 0)) {
    fprintf(stderr, "official parser/map failed\n");
    return 4;
  }
  void *bitstream = get_bs_info(kernel);
  void *bs_config = get_pcfg_configuration(bitstream);
  void *kernel_config = get_kernel_configuration(kernel);
  printf("AHA_CONTROL_JSON={");
  printf("\"bitstream_tile\":%u,\"bitstream_start_address\":%u,\"bitstream_entries\":%u,",
         (unsigned)get_bs_tile(bitstream), (unsigned)get_bs_start_addr(bitstream),
         (unsigned)get_bs_size(bitstream));
  emit_config("bs_cfg", bs_config);
  printf(",");
  emit_config("kernel_cfg", kernel_config);
  printf(",\"pcfg_start\":{\"address\":%u,\"data\":%u}",
         (unsigned)get_pcfg_pulse_addr(), (unsigned)get_pcfg_pulse_data(bitstream));
  printf(",\"stream_start\":{\"address\":%u,\"data\":%u}",
         (unsigned)get_strm_pulse_addr(), (unsigned)get_strm_pulse_data(kernel));
  printf("}\n");
  return 0;
}
