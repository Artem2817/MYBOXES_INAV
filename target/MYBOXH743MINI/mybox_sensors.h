// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "config/parameter_group.h"

typedef struct {
    uint8_t heaterTargetC;
    uint8_t barometerIndex;
} myboxSensorConfig_t;

PG_DECLARE(myboxSensorConfig_t, myboxSensorConfig);

void myboxSensorsInit(void);
void myboxSensorsUpdate(void);
bool myboxImuSample(uint8_t index, int16_t *temperatureDeciC);
bool myboxBarometerSample(uint8_t index, int32_t *pressurePa);
