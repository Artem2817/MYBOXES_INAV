// SPDX-License-Identifier: GPL-3.0-or-later
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define USE_MYBOX_SDMMC_RECOVERY
#define SDMMC_CLK_DIV 4
enum {
    SDMMC_CLOCK_EDGE_RISING, SDMMC_CLOCK_POWER_SAVE_DISABLE, SDMMC_BUS_WIDE_1B, SDMMC_BUS_WIDE_4B,
    SDMMC_HARDWARE_FLOW_CONTROL_ENABLE, HAL_OK, HAL_ERROR, HAL_SD_ERROR_TIMEOUT = 0x8000,
    CARD_SDSC = 1, CARD_SDHC_SDXC = 2, CARD_V1_X = 1, CARD_V2_X = 2,
    SD_STD_CAPACITY_V1_1 = 1, SD_STD_CAPACITY_V2_0, SD_HIGH_CAPACITY,
};
typedef enum { SD_OK, SD_BUSY, SD_ERROR } SD_Error_t;
typedef struct {
    const char *startupFailure;
    uint32_t startupError, transferError;
    uint8_t busWidth;
} sdmmcDiagnostics_t;
typedef struct {
    void *Instance;
    struct { uint32_t ClockEdge, ClockPowerSave, BusWide, HardwareFlowControl, ClockDiv; } Init;
    struct { uint32_t BlockNbr, CardType, CardVersion; } SdCard;
    uint32_t CSD[4], CID[4];
} SD_HandleTypeDef;
static SD_HandleTypeDef hsd;
static struct { uint32_t CSD[4], CID[4], RXCplt, TXCplt; } SD_Handle;
static int SD_CardType;
static const struct { void *instance; int irqn; } hardware;
static const void *instance;
#define sdioHardware (&hardware)

enum fault { OK, INIT_ERROR, WIDE_ERROR, DMA_ERROR, DMA_TIMEOUT };
static enum fault faults[2];
static unsigned attempts, probes, wideSwitches, tick;
static uint32_t dividers[3];

static void HAL_NVIC_DisableIRQ(int irq) { (void)irq; }
static void HAL_NVIC_ClearPendingIRQ(int irq) { (void)irq; }
static int HAL_SD_Init(SD_HandleTypeDef *sd)
{
    instance = sd->Instance;
    assert(attempts < 3 && sd->Init.ClockEdge == SDMMC_CLOCK_EDGE_RISING);
    assert(sd->Init.BusWide == SDMMC_BUS_WIDE_1B && SD_Handle.RXCplt == 0 && SD_Handle.TXCplt == 0);
    dividers[attempts] = sd->Init.ClockDiv;
    ++attempts;
    sd->SdCard.BlockNbr = 72000;
    sd->SdCard.CardType = CARD_SDHC_SDXC;
    return faults[attempts == 1 ? 0 : 1] == INIT_ERROR ? HAL_ERROR : HAL_OK;
}
static uint32_t HAL_SD_GetError(SD_HandleTypeDef *sd)
{
    assert(sd == &hsd && sd->Instance == instance);
    return 0x04;
}
static int HAL_SD_ConfigWideBusOperation(SD_HandleTypeDef *sd, uint32_t width)
{
    assert(sd == &hsd && width == SDMMC_BUS_WIDE_4B);
    ++wideSwitches;
    return faults[attempts == 1 ? 0 : 1] == WIDE_ERROR ? HAL_ERROR : HAL_OK;
}
static uint32_t millis(void) { return ++tick; }
static SD_Error_t SD_ReadBlocks_DMA(uint64_t index, uint32_t *buffer, uint32_t bytes, uint32_t count);
static SD_Error_t SD_CheckRead(void);
#include "sd_startup.inc"

static SD_Error_t SD_ReadBlocks_DMA(uint64_t index, uint32_t *buffer, uint32_t bytes, uint32_t count)
{
    assert(index == 0 && (uintptr_t)buffer % 32 == 0 && bytes == 512 && count == 1);
    ++probes;
    const enum fault fault = faults[attempts == 1 ? 0 : 1];
    sdTransferFailed = fault == DMA_ERROR;
    if (sdTransferFailed) {
        sdTransferError = 0x02;
    }
    SD_Handle.RXCplt = fault == DMA_TIMEOUT;
    return SD_OK;
}

static void resetTest(enum fault primary, enum fault retry)
{
    attempts = probes = wideSwitches = tick = 0;
    faults[0] = primary;
    faults[1] = retry;
    sdStartupFailure = NULL;
    sdStartupError = sdTransferError = 0;
    sdTransferFailed = false;
    sdBusWidth = 4;
    sdStartupProbeDone = false;
}

int main(void)
{
    resetTest(OK, OK);
    assert(SD_Init() == SD_OK && attempts == 1 && probes == 1 && wideSwitches == 1);
    assert(dividers[0] == 4 && SD_GetDiagnostics().busWidth == 4);

    const enum fault recoverable[] = {INIT_ERROR, WIDE_ERROR, DMA_ERROR, DMA_TIMEOUT};
    for (unsigned i = 0; i < sizeof(recoverable) / sizeof(recoverable[0]); ++i) {
        resetTest(recoverable[i], OK);
        assert(SD_Init() == SD_OK && attempts == 2 && SD_GetDiagnostics().busWidth == 1);
        assert(dividers[1] == 8 && SD_GetDiagnostics().startupFailure);
        const unsigned startupProbes = probes;
        assert(SD_Init() == SD_OK && attempts == 3 && probes == startupProbes && dividers[2] == 8);
    }

    resetTest(DMA_ERROR, DMA_TIMEOUT);
    assert(SD_Init() != SD_OK && attempts == 2 && probes == 2);
    assert(SD_GetDiagnostics().startupError == HAL_SD_ERROR_TIMEOUT);
    assert(SD_GetDiagnostics().transferError == 0x02);
    return 0;
}
