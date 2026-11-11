// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#if defined(MYBOXH743MINI)
#define TARGET_BOARD_IDENTIFIER "MBM1"
#define USBD_PRODUCT_STRING     "MYBOX H743 Mini"
#elif defined(MYBOXH743MINIV2)
#define TARGET_BOARD_IDENTIFIER "MBM2"
#define USBD_PRODUCT_STRING     "MYBOX H743 Mini V2"
#elif defined(MYBOXH743MINIV2VIB_BENCH)
#define TARGET_BOARD_IDENTIFIER "MBVB"
#define USBD_PRODUCT_STRING     "MYBOX H743 Mini V2 Vib Bench"
#else
#error Unknown MYBOX H743 Mini target
#endif

#define USE_TARGET_CONFIG
#define USE_MYBOX_RCIN
#define LED0                    PE4
#define LED0_INVERTED
#define USE_HARDWARE_PREBOOT_SETUP

#define USE_SPI
#define USE_SPI_DEVICE_2
#define SPI2_SCK_PIN            PB13
#define USE_MAX7456
#define MAX7456_SPI_BUS         BUS_SPI2
#define MAX7456_CS_PIN          PB12

#define USE_I2C
#define USE_I2C_DEVICE_1
#define I2C1_SDA                PB7
#define USE_I2C_DEVICE_2
#define I2C2_SCL                PB10
#define I2C2_SDA                PB11
#define USE_BARO
#define BARO_I2C_BUS            BUS_I2C1
#define USE_MAG
#define USE_MAG_ALL
#define MAG_I2C_BUS             BUS_I2C2

#define USE_VCP
#define USE_UART1
#define UART1_TX_PIN            PA9
#define UART1_RX_PIN            PA10
#define USE_UART2
#define UART2_TX_PIN            PD5
#define UART2_RX_PIN            PD6
#define USE_UART7
#define UART7_TX_PIN            PE8
#define UART7_RX_PIN            PE7
#define USE_UART8
#define UART8_TX_PIN            PE1
#define UART8_RX_PIN            PE0
#define SERIAL_PORT_COUNT       6
#define DEFAULT_RX_TYPE         RX_TYPE_SERIAL
#define SERIALRX_PROVIDER       SERIALRX_CRSF
#define SERIALRX_UART           SERIAL_PORT_USART2

#define USE_ADC
#define ADC_INSTANCE            ADC1
#define ADC_CHANNEL_1_PIN       PC0
#define ADC_CHANNEL_2_PIN       PC1
#define ADC_CHANNEL_3_PIN       PC5
#define ADC_CHANNEL_4_PIN       PC4
#define VBAT_ADC_CHANNEL        ADC_CHN_1
#define CURRENT_METER_ADC_CHANNEL ADC_CHN_2
#define RSSI_ADC_CHANNEL        ADC_CHN_3
#define AIRSPEED_ADC_CHANNEL    ADC_CHN_4
#define DEFAULT_VOLTAGE_METER_SOURCE VOLTAGE_METER_ADC
#define DEFAULT_CURRENT_METER_SOURCE CURRENT_METER_ADC
#define USE_PITOT
#define USE_PITOT_ADC
#define MS4525_I2C_BUS          BUS_I2C2

#define USE_SDCARD
#define USE_SDCARD_SDIO
#define SDCARD_SDIO_DEVICE      SDIODEV_1
#define SDCARD_SDIO_4BIT
#define ENABLE_BLACKBOX_LOGGING_ON_SDCARD_BY_DEFAULT
#define DEFAULT_FEATURES (FEATURE_OSD | FEATURE_VBAT | FEATURE_CURRENT_METER | FEATURE_BLACKBOX)

#define TARGET_IO_PORTA         0xffff
#define TARGET_IO_PORTB         0xffff
#define TARGET_IO_PORTC         0xffff
#define TARGET_IO_PORTD         0xffff
#define TARGET_IO_PORTE         0xffff

#if defined(MYBOXH743MINI)

#define USE_SPI_DEVICE_1
#define SPI1_SCK_PIN            PA5
#define SPI1_MISO_PIN           PA6
#define SPI1_MOSI_PIN           PD7
#define USE_IMU_ICM42605         // INAV detects ICM-42688-P with this driver.
#define ICM42605_SPI_BUS        BUS_SPI1
#define ICM42605_CS_PIN         PC15
#define IMU_ICM42605_ALIGN      CW0_DEG
#define SPI2_MISO_PIN           PB14
#define SPI2_MOSI_PIN           PB15

#define I2C1_SCL                PB6
#define USE_BARO_MS5611
#define MS5611_I2C_ADDR         0x77
#define USE_UART4
#define UART4_TX_PIN            PB9
#define UART4_RX_PIN            PB8
#define GPS_UART                SERIAL_PORT_USART4
#define MS4525_PROBE_COUNT     2
#define MAX_PWM_OUTPUT_PORTS    14
#define VBAT_SCALE_DEFAULT      2000

#else

#define SPI2_MISO_PIN           PC2
#define SPI2_MOSI_PIN           PC3
#define USE_IMU_ICM45686
#define USE_MYBOX_V2_SENSORS
#if defined(MYBOXH743MINIV2VIB_BENCH)
#define USE_MYBOX_VIB
#define USE_DUAL_GYRO
#define USE_IMU_ICM42670
#define USE_SPI_DEVICE_1
#define SPI1_SCK_PIN            PA5
#define SPI1_MISO_PIN           PA6
#define SPI1_MOSI_PIN           PA7
#define MYBOX_MODULE_IMU_ALIGN  CW0_DEG // Temporary until the J19 module is aligned.
#endif
#define ICM45686_SPI_BUS        BUS_SPI2
#define ICM45686_CS_PIN         PB12
#define IMU_ICM45686_ALIGN      CW0_DEG

#undef MAX7456_SPI_BUS
#undef MAX7456_CS_PIN
#define USE_SPI_DEVICE_4
#define SPI4_SCK_PIN            PE12
#define SPI4_MISO_PIN           PE13
#define SPI4_MOSI_PIN           PE14
#define MAX7456_SPI_BUS         BUS_SPI4
#define MAX7456_CS_PIN          PE11

#define I2C1_SCL                PB8
#define USE_BARO_SPL06
#define SPL06_USE_SPA06
#define SPL06_I2C_ADDR          0x76
#define USE_I2C_DEVICE_4
#define I2C4_SCL                PD12
#define I2C4_SDA                PB9
#define USE_UART3
#define UART3_TX_PIN            PD8
#define UART3_RX_PIN            PD9
#define GPS_UART                SERIAL_PORT_USART1
#define BEEPER                  PB4
#define BEEPER_PWM_FREQUENCY    2500
#define MS4525_PROBE_COUNT     3
#define MAX_PWM_OUTPUT_PORTS    13
#define VBAT_SCALE_DEFAULT      2100

#endif

// 12 mV/A, inherited from the ArduPilot power-module setup.
#define CURRENT_METER_SCALE     120
