// SPDX-License-Identifier: GPL-3.0-or-later
#include <stdint.h>

#include "platform.h"
#include "drivers/bus.h"
#include "drivers/io.h"
#include "drivers/io_impl.h"
#include "drivers/pwm_mapping.h"
#include "drivers/sensor.h"
#include "drivers/timer.h"
#include "flight/mixer.h"

#ifdef USE_MYBOX_VIB
BUSDEV_REGISTER_SPI_TAG(myboxModuleImu, DEVHW_ICM42670, BUS_SPI1, PA4, NONE, 1, DEVFLAGS_NONE, MYBOX_MODULE_IMU_ALIGN);
BUSDEV_REGISTER_I2C_TAG(myboxModuleBaro, DEVHW_SPL06, BUS_I2C1, 0x77, NONE, 1, DEVFLAGS_NONE, 0);
#endif

// The common registry provides I2C2 (tag 0). Probe the remaining buses in order.
#ifdef USE_I2C_DEVICE_4
BUSDEV_REGISTER_I2C_TAG(myboxPitotI2c4, DEVHW_MS4525, BUS_I2C4, 0x28, NONE, 1, DEVFLAGS_USE_RAW_REGISTERS, 0);
#endif
BUSDEV_REGISTER_I2C_TAG(myboxPitotI2c1, DEVHW_MS4525, BUS_I2C1, 0x28, NONE,
    MS4525_PROBE_COUNT - 1, DEVFLAGS_USE_RAW_REGISTERS, 0);

void targetConfiguration(void)
{
    motorConfigMutable()->motorPwmProtocol = PWM_TYPE_STANDARD;
}

// The entries follow the numbering of the PWM connector.
timerHardware_t timerHardware[] = {
#if defined(MYBOXH743MINI)
    DEF_TIM(TIM3,  CH1, PB4,  TIM_USE_OUTPUT_AUTO, 0, 0), // PWM1
    DEF_TIM(TIM3,  CH2, PB5,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM8,  CH2, PC7,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM8,  CH1, PC6,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM4,  CH4, PD15, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM4,  CH3, PD14, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM15, CH1, PE5,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM15, CH2, PE6,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM1,  CH4, PE14, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM1,  CH3, PE13, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM1,  CH2, PE11, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH1, PA0,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH2, PA1,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH3, PA2,  TIM_USE_OUTPUT_AUTO, 0, 0), // PWM14
#else
    DEF_TIM(TIM1, CH2N, PB14, TIM_USE_OUTPUT_AUTO, 0, 0), // PWM1
    DEF_TIM(TIM1, CH3N, PB15, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM4,  CH2, PD13, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM4,  CH3, PD14, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM4,  CH4, PD15, TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM8,  CH1, PC6,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM8,  CH2, PC7,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH4, PA3,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH3, PA2,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH2, PA1,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM5,  CH1, PA0,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM15, CH2, PE6,  TIM_USE_OUTPUT_AUTO, 0, 0),
    DEF_TIM(TIM15, CH1, PE5,  TIM_USE_OUTPUT_AUTO, 0, 0), // PWM13
    DEF_TIM(TIM3,  CH1, PB4,  TIM_USE_BEEPER,      0, 0),
#endif
};

const int timerHardwareCount = sizeof(timerHardware) / sizeof(timerHardware[0]);

static void setStartupOutput(IO_t pin, bool high)
{
    IOInit(pin, OWNER_SYSTEM, RESOURCE_OUTPUT, 0);
    IOWrite(pin, high);
    IOConfigGPIO(pin, IOCFG_OUT_PP);
}

void initialisePreBootHardware(void)
{
#if defined(MYBOXH743MINI)
    setStartupOutput(DEFIO_IO(PB3), true);  // CAN1 silent
#else
    setStartupOutput(DEFIO_IO(PA15), false); // Heater off
#ifndef USE_MYBOX_VIB
    setStartupOutput(DEFIO_IO(PA4), true);   // Deselect J19 when the SPI1 driver is disabled.
#endif
    setStartupOutput(DEFIO_IO(PA8), true);   // CAN1 silent
    setStartupOutput(DEFIO_IO(PD7), true);   // CAN2 silent
    setStartupOutput(DEFIO_IO(PD11), true);  // Sensor power enable
#endif
}
