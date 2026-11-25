// SPDX-License-Identifier: GPL-3.0-or-later
#include "platform.h"
#ifdef USE_MYBOX_VIB
#include <math.h>
#include <string.h>
#include "mybox_imu_failover.h"
#include "common/calibration.h"
#include "common/vector.h"
#include "config/parameter_group_ids.h"
#include "drivers/bus.h"
#include "drivers/time.h"
#include "fc/runtime_config.h"
#include "fc/settings.h"
#include "sensors/acceleration.h"
#include "sensors/gyro.h"
#include "sensors/sensors.h"

PG_REGISTER_WITH_RESET_TEMPLATE(myboxImuFailoverConfig_t, myboxImuFailoverConfig, PG_MYBOX_IMU_FAILOVER_CONFIG, 0);
PG_RESET_TEMPLATE(myboxImuFailoverConfig_t, myboxImuFailoverConfig,
    .enabled = SETTING_MYBOX_IMU_FAILOVER_DEFAULT,
);

enum {
    IMU_TIMEOUT_US = 20000,       // 32 missed samples at the common 1600 Hz rate.
    RESERVE_GYRO_FRESH_US = 5000,
    RESERVE_ACC_FRESH_US = 10000,
    IDENTITY_PERIOD_US = 10000,
    STANDBY_ACC_PERIOD_US = 4000,
};

typedef struct {
    gyroDev_t gyro;
    accDev_t acc;
    zeroCalibrationVector_t calibration;
    uint32_t gyroAt, accAt, identityAt, accPollAt;
    bool present, identityValid, identitySeen, gyroSeen, accSeen, calibrated;
} myboxImuSource_t;

static myboxImuSource_t sources[2];
static gyroDev_t *servedGyro;
static accDev_t *servedAcc;
static uint8_t activeIndex, switches;
static bool attached;
static uint32_t attachedAt;

static bool profileValid(uint8_t index)
{
    if (index > 1 || !(myboxImuFailoverConfig()->validMask & (1U << index))) return false;
    for (unsigned axis = 0; axis < 3; axis++) {
        if (myboxImuFailoverConfig()->accGain[index][axis] <= 0 ||
            myboxImuFailoverConfig()->accGain[index][axis] > 16384) return false;
    }
    return isfinite(myboxImuFailoverConfig()->accTempCorrection[index]);
}

void myboxImuStoreAccCalibration(uint8_t index)
{
    if (index > 1 || accelerometerConfig()->calibrationImu != index + 1) return;
    myboxImuFailoverConfig_t *config = myboxImuFailoverConfigMutable();
    for (unsigned axis = 0; axis < 3; axis++) {
        config->accZero[index][axis] = accelerometerConfig()->accZero.raw[axis];
        config->accGain[index][axis] = accelerometerConfig()->accGain.raw[axis];
    }
    config->accTempCorrection[index] = accelerometerConfig()->acc_temp_correction;
    config->validMask |= 1U << index;
}

bool myboxImuLoadAccCalibration(uint8_t index)
{
    if (!profileValid(index)) return false;
    accelerometerConfig_t *config = accelerometerConfigMutable();
    for (unsigned axis = 0; axis < 3; axis++) {
        config->accZero.raw[axis] = myboxImuFailoverConfig()->accZero[index][axis];
        config->accGain.raw[axis] = myboxImuFailoverConfig()->accGain[index][axis];
    }
    config->acc_temp_correction = myboxImuFailoverConfig()->accTempCorrection[index];
    config->calibrationImu = index + 1;
    return true;
}

void myboxImuPrepareAccCalibration(uint8_t index)
{
    // Import the old single profile into its own sensor slot before selecting another.
    const uint8_t previous = accelerometerConfig()->calibrationImu;
    if (previous >= 1 && previous <= 2) myboxImuStoreAccCalibration(previous - 1);
    if (!myboxImuLoadAccCalibration(index)) {
        accelerometerConfigMutable()->calibrationImu = 0;
    }
}

static bool axesFinite(const float data[3])
{
    return isfinite(data[0]) && isfinite(data[1]) && isfinite(data[2]);
}

static bool checkIdentity(myboxImuSource_t *source, uint8_t index, uint32_t now)
{
    if (!source->present) return false;
    if (!source->identitySeen || (uint32_t)(now - source->identityAt) >= IDENTITY_PERIOD_US) {
        source->identityAt = now;
        source->identitySeen = true;
        uint8_t id;
        source->identityValid = source->gyro.busDev &&
            busRead(source->gyro.busDev, index == 1 ? 0x75 : 0x72, &id) &&
            id == (index == 1 ? 0x67 : 0xe9);
    }
    return source->identityValid;
}

static bool readGyro(uint8_t index, uint32_t now)
{
    myboxImuSource_t *source = &sources[index];
    if (!checkIdentity(source, index, now) ||
        !source->gyro.readFn(&source->gyro) || !axesFinite(source->gyro.gyroADCRaw)) return false;
    source->gyroSeen = true;
    source->gyroAt = now;
    return true;
}

static bool readAcc(uint8_t index, uint32_t now)
{
    myboxImuSource_t *source = &sources[index];
    if (!checkIdentity(source, index, now) ||
        !source->acc.readFn(&source->acc) || !axesFinite(source->acc.ADCRaw)) return false;
    source->accSeen = true;
    source->accAt = now;
    return true;
}

static void calibrateReserve(uint8_t index)
{
    myboxImuSource_t *source = &sources[index];
    if (ARMING_FLAG(ARMED) || source->calibrated ||
        source->calibration.params.state != ZERO_CALIBRATION_IN_PROGRESS) return;
    fpVector3_t value;
    memcpy(value.v, source->gyro.gyroADCRaw, sizeof(value.v));
    zeroCalibrationAddValueV(&source->calibration, &value);
    if (zeroCalibrationIsCompleteV(&source->calibration)) {
        if (zeroCalibrationIsSuccessfulV(&source->calibration) &&
            source->calibration.params.sampleCount >= 100) {
            zeroCalibrationGetZeroV(&source->calibration, &value);
            memcpy(source->gyro.gyroZero, value.v, sizeof(value.v));
            source->calibrated = true;
        } else {
            // A slow boot must not consume the calibration window before sampling starts.
            zeroCalibrationStartV(&source->calibration, CALIBRATING_GYRO_TIME_MS,
                source->calibration.params.stdDevThreshold, false);
        }
    }
}

static bool reserveReady(uint8_t index, uint32_t now)
{
    const myboxImuSource_t *source = &sources[index];
    return attached && myboxImuFailoverConfig()->enabled && source->present &&
        source->identityValid && source->calibrated && gyroIsCalibrationComplete() &&
        source->gyroSeen && source->accSeen &&
        (uint32_t)(now - source->gyroAt) <= RESERVE_GYRO_FRESH_US &&
        (uint32_t)(now - source->accAt) <= RESERVE_ACC_FRESH_US;
}

static bool managedGyroRead(gyroDev_t *device);
static bool managedAccRead(accDev_t *device);
static bool managedTemperature(gyroDev_t *device, int16_t *temperature);

static void selectReserve(uint8_t index)
{
    // No I/O, flash write, sensor reset, mode change or actuator inhibition here.
    *servedGyro = sources[index].gyro;
    servedGyro->readFn = managedGyroRead;
    servedGyro->temperatureFn = managedTemperature;
    *servedAcc = sources[index].acc;
    servedAcc->readFn = managedAccRead;
    activeIndex = index;
    if (!myboxImuLoadAccCalibration(index)) {
        // No cross-sensor reuse of the primary trim. Use the backup's factory scale.
        accelerometerConfig_t *config = accelerometerConfigMutable();
        for (unsigned axis = 0; axis < 3; axis++) {
            config->accZero.raw[axis] = 0;
            config->accGain.raw[axis] = 4096;
        }
        config->acc_temp_correction = 0;
        config->calibrationImu = index + 1;
    }
    accRefreshCalibrationCoefficients();
    switches++;
}

static bool managedGyroRead(gyroDev_t *device)
{
    const uint32_t now = (uint32_t)micros();
    const uint8_t reserve = 1U - activeIndex;
    bool received = readGyro(activeIndex, now);
    if (sources[reserve].present) {
        if (readGyro(reserve, now)) calibrateReserve(reserve);
        if (!sources[reserve].accSeen ||
            (uint32_t)(now - sources[reserve].accPollAt) >= STANDBY_ACC_PERIOD_US) {
            sources[reserve].accPollAt = now;
            readAcc(reserve, now);
        }
    }
    // One failover per boot prevents a noisy/recovering source from causing oscillation.
    // A brief missing DRDY is normal; only a sustained loss permits a switch.
    const bool gyroLost = sources[activeIndex].gyroSeen &&
        (uint32_t)(now - sources[activeIndex].gyroAt) >= IMU_TIMEOUT_US;
    const bool accLost = (uint32_t)(now - attachedAt) >= 40000U &&
        (!sources[activeIndex].accSeen || (uint32_t)(now - sources[activeIndex].accAt) >= 40000U);
    if (!switches && (gyroLost || accLost) && reserveReady(reserve, now)) {
        selectReserve(reserve);
        received = true;
    }
    if (received) memcpy(device->gyroADCRaw, sources[activeIndex].gyro.gyroADCRaw, sizeof(device->gyroADCRaw));
    return received;
}

static bool managedAccRead(accDev_t *device)
{
    if (!readAcc(activeIndex, (uint32_t)micros())) return false;
    memcpy(device->ADCRaw, sources[activeIndex].acc.ADCRaw, sizeof(device->ADCRaw));
    return true;
}

static bool managedTemperature(gyroDev_t *device, int16_t *temperature)
{
    (void)device;
    return myboxImuTemperature(activeIndex, temperature);
}

void myboxImuAttach(gyroDev_t *primary, accDev_t *primaryAcc, const gyroDev_t *standby, const accDev_t *standbyAcc, bool standbyPresent)
{
    if (!primary || !primaryAcc || primary->imuSensorToUse > 1 || !primary->readFn || !primaryAcc->readFn) return;
    memset(sources, 0, sizeof(sources));
    servedGyro = primary;
    servedAcc = primaryAcc;
    activeIndex = primary->imuSensorToUse;
    switches = 0;
    sources[activeIndex].gyro = *primary;
    sources[activeIndex].acc = *primaryAcc;
    sources[activeIndex].present = true;
    if (standbyPresent && standby && standbyAcc && standby->readFn && standbyAcc->readFn) {
        sources[1U - activeIndex].gyro = *standby;
        sources[1U - activeIndex].acc = *standbyAcc;
        sources[1U - activeIndex].present = true;
    }
    primary->readFn = managedGyroRead;
    primary->temperatureFn = managedTemperature;
    primaryAcc->readFn = managedAccRead;
    attachedAt = (uint32_t)micros();
    attached = true;
}

void myboxImuStartCalibration(void)
{
    if (!attached || ARMING_FLAG(ARMED)) return;
    myboxImuSource_t *source = &sources[1U - activeIndex];
    source->calibrated = false;
    if (!source->present || !(source->gyro.scale > 0)) return;
#ifdef CALIBRATING_GYRO_MORON_THRESHOLD_DPS
    const float thresholdDps = CALIBRATING_GYRO_MORON_THRESHOLD_DPS;
#else
    const float thresholdDps = CALIBRATING_GYRO_MORON_THRESHOLD * servedGyro->scale;
#endif
    zeroCalibrationStartV(&source->calibration, CALIBRATING_GYRO_TIME_MS,
        thresholdDps / source->gyro.scale, false);
}

bool myboxImuTemperature(uint8_t index, int16_t *temperature)
{
    if (!attached || index > 1 || !sources[index].identityValid || !sources[index].gyroSeen ||
        (uint32_t)((uint32_t)micros() - sources[index].gyroAt) > IMU_TIMEOUT_US) return false;
    return sources[index].gyro.temperatureFn &&
        sources[index].gyro.temperatureFn(&sources[index].gyro, temperature);
}

bool myboxImuIsHealthy(void)
{
    return !attached || (sources[activeIndex].identityValid && sources[activeIndex].gyroSeen &&
        (uint32_t)((uint32_t)micros() - sources[activeIndex].gyroAt) <= IMU_TIMEOUT_US);
}

uint8_t myboxImuFailoverCount(void) { return switches; }

const char *myboxImuFailoverState(void)
{
    if (!attached) return "not initialized";
    if (switches) return myboxImuIsHealthy() ? "on reserve" : "no healthy active IMU";
    if (!myboxImuFailoverConfig()->enabled) return "OFF";
    if (!sources[1U - activeIndex].present) return "reserve missing";
    if (!sources[1U - activeIndex].calibrated) return "reserve gyro not calibrated";
    return reserveReady(1U - activeIndex, (uint32_t)micros()) ? "ready" : "reserve data not fresh";
}
#endif
