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
#include <string.h>
#define USE_IMU_ICM42670
#define USE_BARO_SPL06
#define USE_MYBOX_VIB
#define SPL06_USE_SPA06
#define XYZ_AXIS_COUNT 3
enum { BUSTYPE_SPI, BUSTYPE_ANY, DEVHW_ICM42670, DEVHW_SPL06, OWNER_MPU, OWNER_BARO,
       BUS_SPEED_INITIALIZATION, BUS_SPEED_STANDARD };
typedef struct { uint8_t tag; } descriptor_t;
typedef struct {
    const descriptor_t *descriptorPtr;
    uint8_t registers[256];
    uint32_t param;
    bool open;
    bool online;
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

static const descriptor_t descriptors[] = {{0}, {1}};
static busDevice_t imu = { .descriptorPtr = &descriptors[1] };
static busDevice_t pressureSensors[] = {{.descriptorPtr = &descriptors[0]}, {.descriptorPtr = &descriptors[1]}};
static bool gyroCheckDataReady(gyroDev_t *gyro) { return gyro->busDev->online; }
static void delay(unsigned ms) { (void)ms; }
static void busSetSpeed(busDevice_t *dev, unsigned speed) { (void)dev; (void)speed; }
static busDevice_t *getDevice(int kind, uint8_t tag)
{
    if (kind == DEVHW_ICM42670) {
        return tag == 1 ? &imu : NULL;
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
    memcpy(value, dev->registers + reg, length);
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

int main(void)
{
    testImu();
    testBarometers();
}
"""

root = Path(sys.argv[1]).resolve() / "src/main/drivers"
with tempfile.TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "gyro_driver.c").write_text(without_includes(root / "accgyro/accgyro_icm42670.c"))
    (work / "baro_driver.c").write_text(without_includes(root / "barometer/barometer_spl06.c"))
    (work / "check.c").write_text(CHECK)
    subprocess.run(
        ["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(root / "barometer"),
         "check.c", "-lm", "-o", "check"],
        cwd=work, check=True,
    )
    subprocess.run([str(work / "check")], check=True)
print("ICM-42670-P initialization and sampling, plus independent SPA06-003 contexts: OK")
