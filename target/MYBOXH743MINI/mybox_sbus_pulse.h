// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stdbool.h>
#include <stdint.h>

enum {
    MYBOX_TIM2_HZ = 1000000,
    MYBOX_TIM2_PERIOD = MYBOX_TIM2_HZ,
    SBUS_BIT_US = 10,
    SBUS_WORD_BITS = 12, // Start, eight data bits, even parity, two stop bits.
    SBUS_STOP_SAMPLE_US = 115,
};

typedef struct {
    uint32_t start;
    uint16_t word;
    uint8_t bit;
    bool high;
    bool active;
} myboxSbusWord_t;

static inline uint32_t myboxSbusElapsed(uint32_t tick, uint32_t start)
{
    return tick >= start ? tick - start : MYBOX_TIM2_PERIOD - start + tick;
}

static inline void myboxSbusStart(myboxSbusWord_t *state, uint32_t tick)
{
    *state = (myboxSbusWord_t){ .start = tick, .active = true };
}

static inline void myboxSbusAppendRun(myboxSbusWord_t *state, unsigned end)
{
    if (state->high) {
        state->word |= (1u << end) - (1u << state->bit);
    }
    state->bit = end;
}

static inline void myboxSbusEdge(myboxSbusWord_t *state, uint32_t tick, bool high)
{
    const unsigned bit = (myboxSbusElapsed(tick, state->start) + SBUS_BIT_US / 2) / SBUS_BIT_US;
    if (bit <= state->bit || bit >= SBUS_WORD_BITS || high == state->high) {
        state->active = false;
        return;
    }
    myboxSbusAppendRun(state, bit);
    state->high = high;
}

static inline bool myboxSbusFinish(myboxSbusWord_t *state, uint8_t *data)
{
    myboxSbusAppendRun(state, SBUS_WORD_BITS);
    state->active = false;
    const unsigned stopMask = 3u << 10;
    if ((state->word & stopMask) != stopMask || __builtin_parity((state->word >> 1) & 0x1ff)) {
        return false;
    }
    *data = state->word >> 1;
    return true;
}
