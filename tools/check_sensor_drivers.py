from pathlib import Path
import subprocess
import sys
import tempfile


def without_includes(path):
    return "\n".join(line for line in path.read_text().splitlines() if not line.startswith("#include"))


CHECK = r"""
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define USE_IMU_ICM42670
#define USE_BARO_SPL06
#define USE_MYBOX_VIB
#define SPL06_USE_SPA06
#define MS4525_PROBE_COUNT 3
#define BUS_SCRATCHPAD_MEMORY_SIZE 16
#define STATIC_ASSERT(condition, name) _Static_assert(condition, #name)
#define ABS(value) abs(value)
#define C_TO_KELVIN(value) ((value) + 273.15f)
#define XYZ_AXIS_COUNT 3
enum { BUSTYPE_SPI, BUSTYPE_ANY, DEVHW_ICM42670, DEVHW_SPL06, OWNER_MPU, OWNER_BARO,
       BUS_SPEED_INITIALIZATION, BUS_SPEED_STANDARD, BUSTYPE_I2C, DEVHW_MS4525, OWNER_AIRSPEED };
typedef struct { uint8_t tag; } descriptor_t;
typedef struct {
    const descriptor_t *descriptorPtr;
    uint8_t registers[256];
    uint32_t param;
    bool open;
    bool online;
    uint32_t scratchpad[BUS_SCRATCHPAD_MEMORY_SIZE / sizeof(uint32_t)];
} busDevice_t;
typedef struct gyroDev {
    busDevice_t *busDev;
    uint8_t imuSensorToUse;
    void (*initFn)(struct gyroDev *);
    bool (*readFn)(struct gyroDev *);
    bool (*intStatusFn)(struct gyroDev *);
    bool (*temperatureFn)(struct gyroDev *, int16_t *);
    uint32_t sampleRateIntervalUs;
    float gyroADCRaw[3];
    float scale;
    uint8_t gyroAlign;
} gyroDev_t;
typedef struct accDev {
    busDevice_t *busDev;
    uint8_t imuSensorToUse;
    void (*initFn)(struct accDev *);
    bool (*readFn)(struct accDev *);
    uint16_t acc_1G;
    uint8_t accAlign;
    float ADCRaw[3];
} accDev_t;
typedef struct baroDev {
    busDevice_t *busDev;
    uint16_t ut_delay, up_delay;
    bool (*start_ut)(struct baroDev *), (*get_ut)(struct baroDev *);
    bool (*start_up)(struct baroDev *), (*get_up)(struct baroDev *);
    bool (*calculate)(struct baroDev *, int32_t *, int32_t *);
} baroDev_t;

typedef struct pitotDev {
    busDevice_t *busDev;
    uint32_t delay;
    float calibThreshold;
    bool (*start)(struct pitotDev *);
    bool (*get)(struct pitotDev *);
    void (*calculate)(struct pitotDev *, float *, float *);
} pitotDev_t;

static const descriptor_t descriptors[] = {{0}, {1}};
static busDevice_t imu = { .descriptorPtr = &descriptors[1] };
static busDevice_t pressureSensors[] = {{.descriptorPtr = &descriptors[0]}, {.descriptorPtr = &descriptors[1]}};
static busDevice_t pitots[MS4525_PROBE_COUNT];
static void *busDeviceGetScratchpadMemory(busDevice_t *dev) { return dev->scratchpad; }
static bool gyroCheckDataReady(gyroDev_t *gyro) { return gyro->busDev->online; }
static void delay(unsigned ms) { (void)ms; }
static void busSetSpeed(busDevice_t *dev, unsigned speed) { (void)dev; (void)speed; }
static busDevice_t *getDevice(int kind, uint8_t tag)
{
    if (kind == DEVHW_ICM42670) {
        return tag == 1 ? &imu : NULL;
    }
    if (kind == DEVHW_MS4525) {
        return tag < MS4525_PROBE_COUNT ? &pitots[tag] : NULL;
    }
    return tag < 2 ? &pressureSensors[tag] : NULL;
}
static busDevice_t *busDeviceInit(int type, int kind, uint8_t tag, int owner)
{
    (void)type;
    (void)owner;
    busDevice_t *dev = getDevice(kind, tag);
    if (dev) { dev->open = true; }
    return dev;
}
static busDevice_t *busDeviceOpen(int type, int kind, uint8_t tag)
{
    (void)type;
    busDevice_t *dev = getDevice(kind, tag);
    return dev && dev->open ? dev : NULL;
}
static void busDeviceDeInit(busDevice_t *dev) { dev->open = false; }
static bool busReadBuf(busDevice_t *dev, uint8_t reg, uint8_t *value, unsigned length)
{
    if (!dev->online) { return false; }
    memcpy(value, dev->registers + (reg == 0xff ? 0 : reg), length);
    return true;
}
static bool busRead(busDevice_t *dev, uint8_t reg, uint8_t *value) { return busReadBuf(dev, reg, value, 1); }
static bool busWrite(busDevice_t *dev, uint8_t reg, uint8_t value)
{
    if (!dev->online) { return false; }
    dev->registers[reg] = value;
    return true;
}

#include "barometer_spl06.h"
#include "gyro_driver.c"
#include "baro_driver.c"
#include "pitot_driver.c"

static void testImu(void)
{
    imu.online = true;
    gyroDev_t gyro = { .imuSensorToUse = 1 };
    accDev_t acc = { .imuSensorToUse = 1 };
    assert(!icm42670GyroDetect(&gyro));
    assert(!icm42670AccDetect(&acc));
    imu.registers[0x75] = 0x67;
    assert(icm42670GyroDetect(&gyro));
    assert(icm42670AccDetect(&acc));
    assert(imu.registers[0x1f] == 0x0f && imu.registers[0x20] == 0x05 && imu.registers[0x21] == 0x05);
    gyro.initFn(&gyro);
    acc.initFn(&acc);
    assert(gyro.sampleRateIntervalUs == 625 && acc.acc_1G == 2048);
    assert(!gyro.readFn(&gyro));
    imu.registers[0x39] = 1;
    imu.registers[0x11] = 0xff;
    imu.registers[0x12] = 0x80;
    assert(gyro.readFn(&gyro) && gyro.gyroADCRaw[0] == -128.0f);
    imu.registers[0x0f] = 8;
    assert(acc.readFn(&acc) && acc.ADCRaw[2] == 2048.0f);
    imu.registers[0x11] = 0x80;
    imu.registers[0x12] = 0x00;
    assert(!gyro.readFn(&gyro) && gyro.gyroADCRaw[0] == -128.0f);
    imu.registers[0x39] = 0xff;
    assert(!gyro.readFn(&gyro));
    imu.registers[0x09] = 0x05;
    int16_t temperature;
    assert(gyro.temperatureFn(&gyro, &temperature) && temperature == 350);
    imu.online = false;
    assert(!gyro.temperatureFn(&gyro, &temperature));
}

static void testBarometers(void)
{
    baroDev_t devices[2] = {{0}};
    for (uint8_t tag = 0; tag < 2; ++tag) {
        busDevice_t *bus = &pressureSensors[tag];
        bus->online = true;
        bus->registers[0x0d] = 0x11;
        bus->registers[0x08] = 0xc0;
        bus->registers[0x13] = 0x18 + tag; // distinct c00
        bus->registers[0x22] = 0x80;
        bus->registers[0x23] = 0x17;
        bus->registers[0x24] = 0xff;
        assert(spl06DetectTag(&devices[tag], tag));
        assert(bus->registers[0x07] == 0x03);
        assert(!devices[tag].get_up(&devices[tag]));
        bus->registers[0x08] = 0xf0;
        assert(devices[tag].get_ut(&devices[tag]));
        assert(devices[tag].get_up(&devices[tag]));
    }
    for (uint8_t tag = 0; tag < 2; ++tag) {
        int32_t pressure, temperature;
        assert(devices[tag].calculate(&devices[tag], &pressure, &temperature));
        assert(pressure == (0x18 + tag) * 4096);
        assert(spl06State[tag].cal.c31 == -2047 && spl06State[tag].cal.c40 == 2047);
    }
    pressureSensors[1].online = false;
    assert(!devices[1].get_up(&devices[1]));
    assert(devices[0].get_up(&devices[0]));
    assert(!spl06DetectTag(&devices[0], 2));
}

static void testPitotProbe(void)
{
    pitotDev_t pitot = {0};
    for (unsigned i = 0; i < MS4525_PROBE_COUNT; ++i) {
        pitots[i].online = true;
    }
    for (unsigned i = 0; i < MS4525_PROBE_COUNT; ++i) {
        assert(ms4525Detect(&pitot));
        assert(pitot.busDev == &pitots[i]);
        for (unsigned j = 0; j < MS4525_PROBE_COUNT; ++j) {
            assert(pitots[j].open == (j == i));
        }

        // The selected bus supplies pressure and temperature through the normal read path.
        pitot.busDev->registers[0] = 0x20;
        pitot.busDev->registers[2] = 0x64;
        assert(pitot.start(&pitot) && pitot.get(&pitot));
        float pressure, temperature;
        pitot.calculate(&pitot, &pressure, &temperature);
        assert(fabsf(pressure) < 1.0f && temperature > 295.0f && temperature < 305.0f);
        busDeviceDeInit(pitot.busDev);
        pitots[i].online = false;
    }

    assert(!ms4525Detect(&pitot) && pitot.busDev == NULL);
    for (unsigned i = 0; i < MS4525_PROBE_COUNT; ++i) {
        assert(!pitots[i].open);
    }
}

int main(void)
{
    testImu();
    testBarometers();
    testPitotProbe();
}
"""

root = Path(sys.argv[1]).resolve() / "src/main/drivers"
with tempfile.TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "gyro_driver.c").write_text(without_includes(root / "accgyro/accgyro_icm42670.c"))
    (work / "baro_driver.c").write_text(without_includes(root / "barometer/barometer_spl06.c"))
    (work / "pitot_driver.c").write_text(without_includes(root / "pitotmeter/pitotmeter_ms4525.c"))
    (work / "check.c").write_text(CHECK)
    subprocess.run(
        ["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(root / "barometer"),
         "check.c", "-lm", "-o", "check"],
        cwd=work, check=True,
    )
    subprocess.run([str(work / "check")], check=True)
print("ICM-42670-P initialization and sampling, independent SPA06-003 contexts, and MS4525 bus fallback and reads: OK")
