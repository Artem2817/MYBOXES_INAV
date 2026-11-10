// SPDX-License-Identifier: GPL-3.0-or-later
#include <assert.h>
#include <stdio.h>

#include "mybox_sbus_pulse.h"

static uint32_t tickAt(uint32_t start, int offset)
{
    return (start + offset) % MYBOX_TIM2_PERIOD;
}

static bool decode(uint16_t bits, uint32_t start, bool jitter, uint8_t *received)
{
    myboxSbusWord_t state;
    myboxSbusStart(&state, start);
    bool high = false;
    for (unsigned bit = 1; bit < SBUS_WORD_BITS; bit++) {
        const bool next = (bits >> bit) & 1u;
        if (next != high) {
            int offset = bit * SBUS_BIT_US;
            if (jitter) {
                offset += bit % 2 ? 2 : -2;
            }
            myboxSbusEdge(&state, tickAt(start, offset), next);
            assert(state.active);
            high = next;
        }
    }
    assert(myboxSbusElapsed(tickAt(start, SBUS_STOP_SAMPLE_US), state.start) == SBUS_STOP_SAMPLE_US);
    return myboxSbusFinish(&state, received);
}

int main(void)
{
    for (unsigned byte = 0; byte <= UINT8_MAX; byte++) {
        const uint16_t word = (byte << 1) | (__builtin_parity(byte) << 9) | (3u << 10);
        uint8_t received;
        assert(decode(word, 100, false, &received) && received == byte);
        assert(decode(word, MYBOX_TIM2_PERIOD - 50, true, &received) && received == byte);
        assert(!decode(word ^ (1u << 9), 100, false, &received));
        assert(!decode(word ^ (1u << 10), 100, false, &received));
        assert(!decode(word ^ (1u << 11), 100, false, &received));
    }

    myboxSbusWord_t state;
    myboxSbusStart(&state, 100);
    myboxSbusEdge(&state, 111, true);
    myboxSbusEdge(&state, 112, false);
    assert(!state.active);

    puts("RCIN SBUS: all 256 bytes, parity, both stop bits, jitter and TIM2 wrap OK");
    return 0;
}
