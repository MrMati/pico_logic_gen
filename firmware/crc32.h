#pragma once

#include <stddef.h>
#include <stdint.h>

/* CRC-32 (IEEE 802.3, reflected, poly 0xEDB88320), matches zlib.crc32.
 * Known answer: crc32 of "123456789" is 0xCBF43926. */
uint32_t crc32_update(uint32_t crc, const void *data, size_t len);

static inline uint32_t crc32_init(void) { return 0; }
