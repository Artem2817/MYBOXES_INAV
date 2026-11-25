// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config/parameter_group.h"
#include "drivers/accgyro/accgyro.h"

typedef struct {
    int16_t accZero[2][3];
    int16_t accGain[2][3];
    float accTempCorrection[2];
    uint8_t validMask;
    uint8_t enabled;
} myboxImuFailoverConfig_t;
PG_DECLARE(myboxImuFailoverConfig_t, myboxImuFailoverConfig);

#ifdef USE_MYBOX_VIB
void myboxImuAttach(gyroDev_t *primary, accDev_t *primaryAcc, const gyroDev_t *standby, const accDev_t *standbyAcc, bool standbyPresent);
void myboxImuStartCalibration(void);
void myboxImuStoreAccCalibration(uint8_t index);
bool myboxImuLoadAccCalibration(uint8_t index);
void myboxImuPrepareAccCalibration(uint8_t index);
bool myboxImuTemperature(uint8_t index, int16_t *temperature);
bool myboxImuIsHealthy(void);
const char *myboxImuFailoverState(void);
uint8_t myboxImuFailoverCount(void);
#endif
