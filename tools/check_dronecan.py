#!/usr/bin/env python3
"""Exercise real DroneCAN magnetometer code, DSDL payloads and both CAN GPIO maps."""
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
def function(text, name):
    start = text.index(name)
    brace = text.index("{", start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]

with tempfile.TemporaryDirectory(prefix="mybox-can-") as directory:
    tmp = Path(directory)
    (tmp / "platform.h").write_text("#define USE_DRONECAN\n")
    driver = (root / "src/main/drivers/compass/compass_dronecan.c").read_text()
    driver = re.sub(r'^\s*#include.*$', '', driver, flags=re.M)
    route = function((root / "src/main/drivers/dronecan/dronecan.c").read_text(),
                     "static void handle_MagneticField(")
    payload1 = ", ".join(str(v) for v in struct.pack("<3e", .25, -.5, .75))
    payload2 = "7, " + payload1
    payload3 = "7, " + ", ".join(str(v) for v in struct.pack("<3f", .25, -.5, .75))
    code = r'''
#include <stdbool.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <dronecan_msgs.h>
#define USE_MAG_DRONECAN
#define MAG_DRONECAN 99
static uint32_t nowMs;
static uint32_t millis(void) { return nowMs; }
typedef struct magDev_s {
    bool (*init)(struct magDev_s *);
    bool (*read)(struct magDev_s *);
    int16_t magADCRaw[3];
} magDev_t;
static struct { int mag_hardware; } config = { MAG_DRONECAN };
#define compassConfig() (&config)
''' + driver + "\n" + route + r'''
static void checkData(magDev_t *mag) {
    assert(mag->read(mag));
    assert(mag->magADCRaw[0] == 250);
    assert(mag->magADCRaw[1] == -500);
    assert(mag->magADCRaw[2] == 750);
}
int main(void) {
    magDev_t mag = {0};
    assert(dronecanMagDetect(&mag));
    assert(mag.init(&mag));
    assert(!mag.read(&mag));
    float f[3] = {.25f, -.5f, .75f};
    nowMs = 0;
    dronecanMagReceive(42, 7, f);
    checkData(&mag); // A valid sample at millisecond zero is usable.
    nowMs = 500;
    checkData(&mag);
    nowMs = 501;
    assert(!mag.read(&mag));
    // A different node or sensor must not refresh a stale chosen compass.
    dronecanMagReceive(43, 7, f);
    dronecanMagReceive(42, 8, f);
    assert(!mag.read(&mag));
    mag.init(&mag);
    float bad[3] = {NAN, 0, 1};
    dronecanMagReceive(1, 0, bad);
    bad[0] = INFINITY;
    dronecanMagReceive(1, 0, bad);
    bad[0] = 17;
    dronecanMagReceive(1, 0, bad);
    bad[0] = bad[1] = bad[2] = 0;
    dronecanMagReceive(1, 0, bad);
    dronecanMagReceive(0, 0, f);
    assert(!mag.read(&mag));
    dronecanMagReceive(42, 7, f);
    checkData(&mag);
    mag.init(&mag);
    nowMs = UINT32_MAX - 10;
    dronecanMagReceive(42, 7, f);
    nowMs += 500;
    checkData(&mag);
    nowMs++;
    assert(!mag.read(&mag));
    // Independent little-endian float16/float32 wire fixtures, as AP_Periph sends.
    uint8_t one[] = {PAYLOAD1};
    uint8_t two[] = {PAYLOAD2};
    uint8_t hires[] = {PAYLOAD3};
    const uint16_t ids[] = {1001,1002,1043};
    uint8_t *payloads[] = {one,two,hires};
    unsigned lengths[] = {sizeof(one),sizeof(two),sizeof(hires)};
    for (unsigned i=0; i<3; i++) {
        mag.init(&mag);
        CanardRxTransfer transfer = {0};
        transfer.source_node_id = 42;
        transfer.data_type_id = ids[i];
        transfer.payload_head = payloads[i];
        transfer.payload_len = lengths[i];
        handle_MagneticField(&transfer);
        checkData(&mag);
        mag.init(&mag);
        transfer.payload_len = 1;
        handle_MagneticField(&transfer);
        assert(!mag.read(&mag));
    }
    mag.init(&mag);
    config.mag_hardware = 0;
    CanardRxTransfer disabled = {0};
    disabled.source_node_id = 42; disabled.data_type_id = 1001;
    disabled.payload_head = one; disabled.payload_len = sizeof(one);
    handle_MagneticField(&disabled);
    assert(!mag.read(&mag));
    puts("DroneCAN magnetic field: AP_Periph 1001/1002/1043 wire decode, units, expiry, rollover, invalid data and source isolation OK");
}
'''
    code = code.replace("PAYLOAD1", payload1).replace("PAYLOAD2", payload2).replace("PAYLOAD3", payload3)
    (tmp / "mag.c").write_text(code)
    gen = root / "lib/main/Dronecan/dsdlc_generated"
    codec = ["uavcan.equipment.ahrs.MagneticFieldStrength.c",
             "uavcan.equipment.ahrs.MagneticFieldStrength2.c",
             "dronecan.sensors.magnetometer.MagneticFieldStrengthHiRes.c"]
    command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(tmp),
               "-I", str(root / "src/main"), "-I", str(gen / "include"), str(tmp / "mag.c"),
               str(root / "src/main/drivers/dronecan/libcanard/canard.c"),
               *[str(gen / "src" / name) for name in codec], "-lm", "-o", str(tmp / "mag")]
    subprocess.run(command, check=True)
    subprocess.run([str(tmp / "mag")], check=True)

    header = root / "src/main/target/MYBOXH743MINI/target.h"
    gpio = function((root / "src/main/drivers/dronecan/libcanard/canard_stm32h7xx_driver.c").read_text(),
                    "static void canardSTM32GPIO_Init(void)\n{")
    variants = {
        "MYBOXH743MINI": {"CAN1_RX":"PD0", "CAN1_TX":"PD1", "CAN1_STANDBY":"PB3",
                         "CAN2_RX":"PD9", "CAN2_TX":"PD10"},
        "MYBOXH743MINIV2": {"CAN1_RX":"PD0", "CAN1_TX":"PD1", "CAN1_STANDBY":"PA8",
                           "CAN2_RX":"PB5", "CAN2_TX":"PB6", "CAN2_STANDBY":"PD7"},
        "MYBOXH743MINIV2VIB_BENCH": {"CAN1_RX":"PD0", "CAN1_TX":"PD1", "CAN1_STANDBY":"PA8",
                                  "CAN2_RX":"PB5", "CAN2_TX":"PB6", "CAN2_STANDBY":"PD7"},
    }
    for variant, expected in variants.items():
        pp = subprocess.check_output(["gcc","-E","-dM","-x","c","-D"+variant,str(header)],
                                     text=True, stderr=subprocess.DEVNULL)
        macros = dict(re.findall(r"^#define (CAN[12]_(?:RX|TX|STANDBY)) (\w+)$",pp,re.M))
        assert macros == expected, (variant, macros)
        pins = {pin: index+1 for index,pin in enumerate(sorted(set(expected.values())))}
        pre = r'''
#include <stdbool.h>
#include <stdint.h>
#include <assert.h>
typedef int ioTag_t;
static struct {int bus;} cfg;
#define myboxCanConfig() (&cfg)
#define USE_MYBOX_CAN_SELECT
#define IO_TAG(pin) (pin)
#define IOGetByTag(pin) (pin)
#define OWNER_DRONECAN 0
#define RESOURCE_CAN_TX 0
#define RESOURCE_CAN_RX 1
#define RESOURCE_CAN_STANDBY 2
#define IOCFG_AF_PP_FAST_UP 0
#define IOCFG_OUT_PP 1
#define GPIO_AF9_FDCAN1 9
#define GPIO_AF9_FDCAN2 9
static int tx,rx,level[32];
static void IOInit(int pin,int owner,int resource,int index) {(void)owner;(void)index;if(resource==0)tx=pin;if(resource==1)rx=pin;}
static void IOConfigGPIOAF(int pin,int mode,int af){(void)pin;(void)mode;assert(af==9);}
static void IOConfigGPIO(int pin,int mode){(void)pin;(void)mode;}
static void IOWrite(int pin,bool high){level[pin]=high;}
'''
        pre += "\n".join("#define %s %s" % item for item in pins.items()) + "\n"
        pre += "\n".join("#define %s %s" % item for item in expected.items()) + "\n"
        tests = "\nint main(void){\n"
        for bus in (1,2):
            tests += "cfg.bus=%d;canardSTM32GPIO_Init();assert(tx==CAN%d_TX&&rx==CAN%d_RX);assert(level[CAN1_STANDBY]==%d);" % (bus,bus,bus,bus==2)
            if "CAN2_STANDBY" in expected:
                tests += "assert(level[CAN2_STANDBY]==%d);" % (bus==1)
        tests += "}\n"
        (tmp / "gpio.c").write_text(pre+gpio+tests)
        subprocess.run(["gcc","-std=c11","-Wall","-Wextra","-Werror",str(tmp/"gpio.c"),
                        "-o",str(tmp/"gpio")],check=True)
        subprocess.run([str(tmp/"gpio")],check=True)
    print("All three MYBOX targets: CAN1/CAN2 pin maps match hwdef; selected transceiver enabled, other silent OK")
