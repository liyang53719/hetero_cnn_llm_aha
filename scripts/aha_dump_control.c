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

static void emit_interrupt_enable(void *kernel) {
  unsigned g2f_mask = 0;
  unsigned f2g_mask = 0;
  const int input_count = get_num_inputs(kernel);
  const int output_count = get_num_outputs(kernel);
  for (int index = 0; index < input_count; ++index) {
    void *io = get_input_info(kernel, index);
    for (int tile = 0; tile < get_num_io_tiles(io, index); ++tile) {
      if (!get_io_tile_is_fake_io(io, tile))
        g2f_mask |= 1u << get_io_tile_map_tile(io, tile);
    }
  }
  for (int index = 0; index < output_count; ++index) {
    void *io = get_output_info(kernel, index);
    for (int tile = 0; tile < get_num_io_tiles(io, index); ++tile) {
      if (!get_io_tile_is_fake_io(io, tile))
        f2g_mask |= 1u << get_io_tile_map_tile(io, tile);
    }
  }
  printf("\"interrupt_enable\":[");
  printf("{\"address\":44,\"data\":7},");
  printf("{\"address\":40,\"data\":1},");
  printf("{\"address\":36,\"data\":%u},", g2f_mask);
  printf("{\"address\":32,\"data\":%u}]", f2g_mask);
}

static void emit_io_layout(const char *name, void *kernel, int output) {
  const int count = output ? get_num_outputs(kernel) : get_num_inputs(kernel);
  printf("\"%s\":[", name);
  for (int index = 0; index < count; ++index) {
    struct IOInfo *io = output ? (struct IOInfo *)get_output_info(kernel, index)
                               : (struct IOInfo *)get_input_info(kernel, index);
    if (index) printf(",");
    printf("{\"file_size\":%d,\"tiles\":[", io->filesize);
    for (int tile_index = 0; tile_index < io->num_io_tiles; ++tile_index) {
      struct IOTileInfo *tile = &io->io_tiles[tile_index];
      if (tile_index) printf(",");
      printf("{\"map_tile\":%d,\"start_address\":%d,"
             "\"gold_check_start_address\":%d,\"tb_write_start_address\":%d,"
             "\"bank_toggle_mode\":%d,\"fake\":%d}",
             tile->tile, tile->start_addr, tile->gold_check_start_addr,
             tile->tb_write_start_addr, tile->bank_toggle_mode, tile->is_fake_io);
    }
    printf("]}");
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
  const unsigned group_start = (unsigned)get_group_start(kernel);
  const unsigned num_groups = (unsigned)get_num_groups(kernel);
  unsigned cgra_stall_mask = 0;
  for (unsigned group = group_start; group < group_start + num_groups; ++group)
    cgra_stall_mask |= 0xFu << (4u * group);
  printf("AHA_CONTROL_JSON={");
  printf("\"bitstream_tile\":%u,\"bitstream_start_address\":%u,\"bitstream_entries\":%u,",
         (unsigned)get_bs_tile(bitstream), (unsigned)get_bs_start_addr(bitstream),
         (unsigned)get_bs_size(bitstream));
  // Match test_app's calculate_cgra_stall_mask after the official glb_map.
  // This frozen flow has a four-column global-controller stall field.
  printf("\"cgra_group_start\":%u,\"cgra_num_groups\":%u,\"cgra_stall_mask\":%u,",
         group_start, num_groups, cgra_stall_mask);
  emit_config("bs_cfg", bs_config);
  printf(",");
  emit_config("kernel_cfg", kernel_config);
  printf(",");
  emit_interrupt_enable(kernel);
  printf(",");
  emit_io_layout("inputs", kernel, 0);
  printf(",");
  emit_io_layout("outputs", kernel, 1);
  printf(",\"pcfg_start\":{\"address\":%u,\"data\":%u}",
         (unsigned)get_pcfg_pulse_addr(), (unsigned)get_pcfg_pulse_data(bitstream));
  printf(",\"stream_start\":{\"address\":%u,\"data\":%u}",
         (unsigned)get_strm_pulse_addr(), (unsigned)get_strm_pulse_data(kernel));
  printf("}\n");
  return 0;
}
