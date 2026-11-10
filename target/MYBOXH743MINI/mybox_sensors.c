// SPDX-License-Identifier: GPL-3.0-or-later
#include "platform.h"

#ifdef USE_MYBOX_V2_SENSORS
#include "mybox_sensors.h"
#include "common/maths.h"
#include "config/parameter_group_ids.h"
#include "drivers/accgyro/accgyro_icm42670.h"
#include "drivers/accgyro/accgyro_icm45686.h"
#include "drivers/io.h"
#include "drivers/timer.h"
#include "fc/settings.h"
#include "sensors/gyro.h"

PG_REGISTER_WITH_RESET_TEMPLATE(myboxSensorConfig_t, myboxSensorConfig, PG_MYBOX_SENSOR_CONFIG, 0);
PG_RESET_TEMPLATE(myboxSensorConfig_t, myboxSensorConfig,
    .heaterTargetC = SETTING_MYBOX_HEATER_TARGET_DEFAULT,
    .barometerIndex = 0,
);

enum {
    HEATER_PERIOD = 10000,
    HEATER_TIMER_HZ = 10000,
    HEATER_MAX_DUTY = HEATER_PERIOD / 5,
    HEATER_MAX_TEMP_DECIC = 500,
    HEATER_MIN_TEMP_DECIC = -400,
    ICM45686_ID_REGISTER = 0x72,
    ICM45686_ID = 0xe9,
    ICM42670_ID_REGISTER = 0x75,
    ICM42670_ID = 0x67,
};

// Keep PA15 out of the motor/servo timer list so timer overrides cannot reassign the heater.
static const timerHardware_t heaterHardware = DEF_TIM(TIM2, CH1, PA15, TIM_USE_ANY, 0, 0);
static volatile timCCR_t *heaterCompare;
static bool imuValid[2];
static int16_t imuTemperature[2];
static uint8_t activeImu;
#ifdef USE_MYBOX_VIB
static gyroDev_t standbyGyro;
static accDev_t standbyAcc;
static bool standbyPresent;
#endif

static bool myboxImuResponds(uint8_t index)
{
    const bool module = index == 1;
    busDevice_t *device = busDeviceOpen(BUSTYPE_SPI, module ? DEVHW_ICM42670 : DEVHW_ICM45686, index);
    uint8_t id;
    return device && busRead(device, module ? ICM42670_ID_REGISTER : ICM45686_ID_REGISTER, &id)
        && id == (module ? ICM42670_ID : ICM45686_ID);
}

void myboxSensorsInit(void)
{
#ifdef USE_MYBOX_VIB
    activeImu = gyroConfig()->gyro_to_use;
    const uint8_t standbyImu = activeImu == 1 ? 0 : 1;
    standbyGyro.imuSensorToUse = standbyImu;
    standbyAcc.imuSensorToUse = standbyImu;
    const bool gyroDetected = standbyImu == 1 ? icm42670GyroDetect(&standbyGyro) : icm45686GyroDetect(&standbyGyro);
    if (gyroDetected) {
        standbyGyro.lpf = GYRO_LPF_256HZ;
        standbyGyro.requestedSampleIntervalUs = 625;
        standbyGyro.initFn(&standbyGyro);
        standbyPresent = standbyImu == 1 ? icm42670AccDetect(&standbyAcc) : icm45686AccDetect(&standbyAcc);
        if (standbyPresent) {
            standbyAcc.initFn(&standbyAcc);
        }
    }
#endif
    TCH_t *heater = timerGetTCH(&heaterHardware);
    if (heater) {
        timerConfigBase(heater, HEATER_PERIOD, HEATER_TIMER_HZ);
        timerPWMConfigChannel(heater, 0);
        timerPWMStart(heater);
        timerEnable(heater);
        heaterCompare = timerCCR(heater);
        IOConfigGPIOAF(IOGetByTag(IO_TAG(PA15)), IOCFG_AF_PP, heaterHardware.alternateFunction);
    }
}

bool myboxImuSample(uint8_t index, int16_t *temperatureDeciC)
{
    if (index >= 2 || !imuValid[index]) {
        return false;
    }
    *temperatureDeciC = imuTemperature[index];
    return true;
}

void myboxSensorsUpdate(void)
{
    if (activeImu >= 2) {
        return;
    }
    imuValid[activeImu] = myboxImuResponds(activeImu) && gyroReadTemperature();
    if (imuValid[activeImu]) {
        imuTemperature[activeImu] = gyroGetTemperature();
    }

#ifdef USE_MYBOX_VIB
    const uint8_t standbyImu = 1 - activeImu;
    imuValid[standbyImu] = standbyPresent && myboxImuResponds(standbyImu)
        && standbyGyro.readFn(&standbyGyro) && standbyAcc.readFn(&standbyAcc)
        && standbyGyro.temperatureFn(&standbyGyro, &imuTemperature[standbyImu]);
    const uint8_t heatedImu = 1;
#else
    const uint8_t heatedImu = 0;
#endif

    if (!heaterCompare) {
        return;
    }
    unsigned duty = 0;
    const uint8_t target = myboxSensorConfig()->heaterTargetC;
    const int16_t temperature = imuTemperature[heatedImu];
    if (target > 0 && target <= 45 && imuValid[heatedImu]
        && temperature >= HEATER_MIN_TEMP_DECIC && temperature < HEATER_MAX_TEMP_DECIC) {
        const int error = target * 10 - temperature;
        duty = constrain(error * 100, 0, HEATER_MAX_DUTY);
    }
    *heaterCompare = duty;
}
#endif
