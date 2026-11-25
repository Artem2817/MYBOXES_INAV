// SPDX-License-Identifier: GPL-3.0-or-later
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef uint64_t timeUs_t;
#define USE_MYBOX_SDMMC_RECOVERY
#define MYBOXH743MINI
#define USE_SD_TRANSCEIVER 0
#define __IO volatile
#define SDMMC_CHECK_PATTERN 0x1aaU
#define SDMMC_HIGH_CAPACITY (1U << 30)
#define SDMMC_CMD_CMDINDEX 0x3fU
#define SDMMC_RESPCMD_RESPCMD 0x3fU
#define SDMMC_CLK_DIV 4
enum {
    SDMMC_CLOCK_EDGE_RISING, SDMMC_CLOCK_POWER_SAVE_DISABLE, SDMMC_BUS_WIDE_1B, SDMMC_BUS_WIDE_4B,
    SDMMC_HARDWARE_FLOW_CONTROL_ENABLE, HAL_OK, HAL_ERROR, HAL_SD_ERROR_TIMEOUT = 0x8000,
    CARD_SDSC = 1, CARD_SDHC_SDXC = 2, CARD_V1_X = 1, CARD_V2_X = 2,
    SD_STD_CAPACITY_V1_1 = 1, SD_STD_CAPACITY_V2_0, SD_HIGH_CAPACITY,
};
typedef enum { SD_OK, SD_BUSY, SD_ERROR } SD_Error_t;
#include "sd_types.inc"

enum {
    SDMMC_FLAG_IDMATE = 1U << 0, SDMMC_FLAG_DCRCFAIL = 1U << 1, SDMMC_FLAG_DTIMEOUT = 1U << 2,
    SDMMC_FLAG_RXOVERR = 1U << 3, SDMMC_FLAG_TXUNDERR = 1U << 4, SDMMC_FLAG_DATAEND = 1U << 5,
    SDMMC_STATIC_DATA_FLAGS = 0x3f, SDMMC_DCTRL_FIFORST = 1U << 6,
    HAL_SD_ERROR_DMA = 1U << 8, HAL_SD_ERROR_DATA_CRC_FAIL = 1U << 9, HAL_SD_ERROR_DATA_TIMEOUT = 1U << 10,
    HAL_SD_ERROR_RX_OVERRUN = 1U << 11, HAL_SD_ERROR_TX_UNDERRUN = 1U << 12,
};
typedef struct {
    uint32_t STA, MASK, DCOUNT, DCTRL, IDMACTRL, IDMABASE0, ICR;
    uint32_t CMD, RESPCMD, RESP1;
} SDMMC_TypeDef;
typedef struct {
    SDMMC_TypeDef *Instance;
    struct { uint32_t ClockEdge, ClockPowerSave, BusWide, HardwareFlowControl, ClockDiv; } Init;
    struct { uint32_t BlockNbr, LogBlockNbr, CardType, CardVersion, RelCardAdd; } SdCard;
    uint32_t CSD[4], CID[4];
} SD_HandleTypeDef;
static SD_HandleTypeDef hsd;
static struct { uint32_t CSD[4], CID[4], RXCplt, TXCplt; } SD_Handle;
static int SD_CardType;
static SDMMC_TypeDef instance;
static const struct { SDMMC_TypeDef *instance; int irqn; } hardware = { &instance, 1 };
#define sdioHardware (&hardware)

enum fault { OK, INIT_ERROR, WIDE_ERROR, POLL_ERROR, POLL_TIMEOUT };
static enum fault faults[2];
static unsigned attempts, probes, wideSwitches, transferCallbacks;
static uint32_t dividers[3];
static uint32_t halError;
static bool irqEnabled;
static bool irqBeforeDisable;

static void sdServiceTransfer(bool fromIrq);

static void HAL_NVIC_EnableIRQ(int irq) { assert(irq == 1); irqEnabled = true; }
static void HAL_NVIC_DisableIRQ(int irq)
{
    assert(irq == 1);
    if (irqBeforeDisable) {
        assert(irqEnabled);
        irqBeforeDisable = false;
        sdServiceTransfer(true);
    }
    irqEnabled = false;
}
static void HAL_NVIC_ClearPendingIRQ(int irq) { assert(irq == 1); }
static void HAL_SD_IRQHandler(SD_HandleTypeDef *sd)
{
    assert(sd == &hsd && sd->Instance->STA == SDMMC_FLAG_DATAEND);
    sd->Instance->STA = 0;
    SD_Handle.RXCplt = SD_Handle.TXCplt = 0;
    ++transferCallbacks;
}

static int HAL_SD_Init(SD_HandleTypeDef *sd)
{
    assert(sd->Instance == &instance);
    memset(&instance, 0, sizeof(instance));
    irqEnabled = true;
    assert(attempts < 3 && sd->Init.ClockEdge == SDMMC_CLOCK_EDGE_RISING);
    assert(sd->Init.BusWide == SDMMC_BUS_WIDE_1B && SD_Handle.RXCplt == 0 && SD_Handle.TXCplt == 0);
    dividers[attempts] = sd->Init.ClockDiv;
    ++attempts;
    halError = 0x04;
    sd->SdCard.BlockNbr = sd->SdCard.LogBlockNbr = 72000;
    sd->SdCard.RelCardAdd = 0x1234;
    sd->SdCard.CardType = CARD_SDHC_SDXC;
    return faults[attempts == 1 ? 0 : 1] == INIT_ERROR ? HAL_ERROR : HAL_OK;
}
static uint32_t HAL_SD_GetError(SD_HandleTypeDef *sd)
{
    assert(sd == &hsd && sd->Instance == &instance);
    return halError;
}
static int HAL_SD_ConfigWideBusOperation(SD_HandleTypeDef *sd, uint32_t width)
{
    assert(sd == &hsd && width == SDMMC_BUS_WIDE_4B);
    ++wideSwitches;
    return faults[attempts == 1 ? 0 : 1] == WIDE_ERROR ? HAL_ERROR : HAL_OK;
}
static int HAL_SD_ReadBlocks(SD_HandleTypeDef *sd, uint8_t *buffer, uint32_t index, uint32_t count, uint32_t timeout)
{
    assert(sd == &hsd && buffer && index == 0 && count == 1 && timeout == 250);
    ++probes;
    const enum fault fault = faults[attempts == 1 ? 0 : 1];
    if (fault == POLL_TIMEOUT) {
        halError = HAL_SD_ERROR_TIMEOUT;
        return HAL_ERROR;
    }
    if (fault == POLL_ERROR) {
        halError = 0x02;
        return HAL_ERROR;
    }
    buffer[450] = 0x0c;
    buffer[510] = 0x55;
    buffer[511] = 0xaa;
    return HAL_OK;
}

static void delay(uint32_t ms) { assert(ms == 20); }

#include "sd_startup.inc"

enum {
    HAL_SD_ERROR_NONE = 0, SDMMC_ERROR_NONE = 0, SDMMC_ERROR_CMD_RSP_TIMEOUT = 4,
    SDMMC_ERROR_CMD_CRC_FAIL = 1, SDMMC_ERROR_TIMEOUT = HAL_SD_ERROR_TIMEOUT,
    HAL_SD_ERROR_INVALID_VOLTRANGE = 1U << 24, SDMMC_RESP1 = 1,
};
static unsigned idleCount, appCount, ocrCount, delays, ocrReadyAfter;
static uint32_t cmd8Error, cmd55Error, acmd41Error, r7, expectedOcr;

static uint32_t SDMMC_CmdGoIdleState(SDMMC_TypeDef *reg)
{
    assert(reg == &instance);
    ++idleCount;
    return HAL_SD_ERROR_NONE;
}

static uint32_t SDMMC_CmdOperCond(SDMMC_TypeDef *reg)
{
    reg->RESP1 = r7;
    return cmd8Error;
}

static uint32_t SDMMC_CmdAppCommand(SDMMC_TypeDef *reg, uint32_t argument)
{
    assert(reg == &instance && argument == 0);
    ++appCount;
    return cmd55Error;
}

static uint32_t SDMMC_CmdAppOperCommand(SDMMC_TypeDef *reg, uint32_t argument)
{
    assert(reg == &instance && argument == expectedOcr);
    ++ocrCount;
    reg->RESP1 = ocrCount >= ocrReadyAfter ? 0x80000000U | (argument & SDMMC_HIGH_CAPACITY) : 0;
    return acmd41Error;
}

static uint32_t SDMMC_GetResponse(SDMMC_TypeDef *reg, uint32_t response)
{
    assert(response == SDMMC_RESP1);
    return reg->RESP1;
}

static void HAL_Delay(uint32_t ms)
{
    assert(ms == 10);
    ++delays;
}

#include "sd_power_on.inc"

static void resetPowerOn(uint32_t cmd8, uint32_t cmd55, uint32_t acmd41)
{
    hsd.Instance = &instance;
    idleCount = appCount = ocrCount = delays = 0;
    cmd8Error = cmd8;
    cmd55Error = cmd55;
    acmd41Error = acmd41;
    r7 = SDMMC_CHECK_PATTERN;
    expectedOcr = 0x00ff8000U | (cmd8 == SDMMC_ERROR_NONE ? SDMMC_HIGH_CAPACITY : 0);
    ocrReadyAfter = 3;
}

static void checkPowerOn(void)
{
    resetPowerOn(SDMMC_ERROR_CMD_RSP_TIMEOUT, 0, 0);
    assert(SD_PowerON(&hsd) == 0 && idleCount == 2 && delays == 2 && appCount == 3);
    assert(hsd.SdCard.CardVersion == CARD_V1_X && hsd.SdCard.CardType == CARD_SDSC);

    resetPowerOn(0, 0, 0);
    assert(SD_PowerON(&hsd) == 0 && idleCount == 1 && delays == 2 && appCount == 3);
    assert(hsd.SdCard.CardVersion == CARD_V2_X && hsd.SdCard.CardType == CARD_SDHC_SDXC);

    resetPowerOn(SDMMC_ERROR_CMD_CRC_FAIL, 0, 0);
    assert(SD_PowerON(&hsd) == SDMMC_ERROR_CMD_CRC_FAIL && appCount == 0);

    resetPowerOn(0, SDMMC_ERROR_CMD_RSP_TIMEOUT, 0);
    assert(SD_PowerON(&hsd) == SDMMC_ERROR_CMD_RSP_TIMEOUT && ocrCount == 0);

    resetPowerOn(0, 0, SDMMC_ERROR_CMD_RSP_TIMEOUT);
    assert(SD_PowerON(&hsd) == SDMMC_ERROR_CMD_RSP_TIMEOUT && ocrCount == 1);

    resetPowerOn(0, 0, 0);
    r7 = 0xaa;
    assert(SD_PowerON(&hsd) == HAL_SD_ERROR_INVALID_VOLTRANGE && appCount == 0);

    resetPowerOn(0, 0, 0);
    ocrReadyAfter = 101;
    assert(SD_PowerON(&hsd) == HAL_SD_ERROR_TIMEOUT && delays == 100 && ocrCount == 100);
}

static void resetTest(enum fault primary, enum fault retry)
{
    attempts = probes = wideSwitches = transferCallbacks = 0;
    faults[0] = primary;
    faults[1] = retry;
    sdDiagnostics = (sdmmcDiagnostics_t){ .busWidth = 4 };
    sdTransferFailed = false;
    sdStartupProbeDone = false;
    irqBeforeDisable = false;
}

int main(void)
{
    checkPowerOn();
    resetTest(OK, OK);
    assert(SD_Init() == SD_OK && attempts == 1 && probes == 1 && wideSwitches == 1);
    assert(dividers[0] == 4 && SD_GetDiagnostics().busWidth == 4);
    assert(SD_GetDiagnostics().blocks == 72000 && SD_GetDiagnostics().rca == 0x1234);
    assert(SD_GetDiagnostics().bootSignature == 0xaa55 && SD_GetDiagnostics().bootPartitionTypes == 0x0c000000);

    const enum fault recoverable[] = {INIT_ERROR, WIDE_ERROR, POLL_ERROR, POLL_TIMEOUT};
    for (unsigned i = 0; i < sizeof(recoverable) / sizeof(recoverable[0]); ++i) {
        resetTest(recoverable[i], OK);
        assert(SD_Init() == SD_OK && attempts == 2 && SD_GetDiagnostics().busWidth == 1);
        assert(dividers[1] == 8 && SD_GetDiagnostics().startupFailure);
        const unsigned startupProbes = probes;
        assert(SD_Init() == SD_OK && attempts == 3 && probes == startupProbes && dividers[2] == 8);
    }

    resetTest(POLL_ERROR, POLL_TIMEOUT);
    assert(SD_Init() != SD_OK && attempts == 2 && probes == 2);
    assert(SD_GetDiagnostics().startupError == HAL_SD_ERROR_TIMEOUT);
    assert(SD_GetDiagnostics().transferError == 0);

    resetTest(OK, OK);
    assert(SD_Init() == SD_OK);
    sdPrepareTransfer(1);
    assert(instance.ICR == SDMMC_STATIC_DATA_FLAGS && instance.DCTRL == SDMMC_DCTRL_FIFORST);
    SD_Handle.RXCplt = 1;
    sdPollTransfer();
    assert(transferCallbacks == 0 && SD_Handle.RXCplt == 1);
    instance.STA = SDMMC_FLAG_DATAEND;
    sdPollTransfer();
    assert(transferCallbacks == 1 && !SD_Handle.RXCplt && irqEnabled);
    assert(SD_GetDiagnostics().polledCompletions == 1 && !SD_GetDiagnostics().irqCompletions);

    sdPrepareTransfer(2);
    SD_Handle.TXCplt = 1;
    instance.STA = SDMMC_FLAG_DATAEND;
    irqBeforeDisable = true;
    sdPollTransfer();
    assert(transferCallbacks == 2 && !SD_Handle.TXCplt && irqEnabled);
    assert(SD_GetDiagnostics().polledCompletions == 1 && SD_GetDiagnostics().irqCompletions == 1);

    resetTest(OK, OK);
    assert(SD_Init() == SD_OK);
    sdPrepareTransfer(2048);
    SD_Handle.RXCplt = 1;
    instance.STA = SDMMC_FLAG_IDMATE | SDMMC_FLAG_DATAEND;
    instance.MASK = 0xaa;
    instance.DCOUNT = 64;
    instance.IDMACTRL = 1;
    instance.IDMABASE0 = 0x24002000;
    sdPollTransfer();
    assert(sdTransferFailed && !transferCallbacks && !instance.MASK);
    sdmmcFailure_t failure = SD_GetDiagnostics().firstFailure;
    assert(!strcmp(failure.phase, "read hardware error") && failure.error == HAL_SD_ERROR_DMA);
    assert(failure.sector == 2048 && failure.status == (SDMMC_FLAG_IDMATE | SDMMC_FLAG_DATAEND));
    assert(failure.mask == 0xaa && failure.dataCount == 64 && failure.dmaControl == 1 && failure.dmaAddress == 0x24002000);
    assert(SD_Init() == SD_OK && SD_GetDiagnostics().busWidth == 1 && SD_GetDiagnostics().firstFailure.sector == 2048);
    assert(dividers[1] == 8);

    sdPrepareTransfer(4096);
    SD_RecordFailure("read DMA timeout", true);
    assert(SD_GetDiagnostics().firstFailure.error == HAL_SD_ERROR_DMA);
    assert(SD_GetDiagnostics().failures == 2 && SD_GetDiagnostics().transferError == HAL_SD_ERROR_TIMEOUT);
    return 0;
}
