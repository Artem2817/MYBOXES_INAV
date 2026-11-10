// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "config/parameter_group.h"
#include "drivers/serial.h"
#include "drivers/timer.h"

typedef struct {
    uint8_t sbusEnabled;
} myboxRcinConfig_t;

PG_DECLARE(myboxRcinConfig_t, myboxRcinConfig);

void myboxConfigureTimer2(TCH_t *channel);
bool myboxRcinSbusInit(serialReceiveCallbackPtr receive, void *context, bool inverted);
