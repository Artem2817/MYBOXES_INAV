// SPDX-License-Identifier: GPL-3.0-or-later
#include "platform.h"

#ifdef USE_MYBOX_RCIN
#include "mybox_rcin.h"
#include "mybox_sbus_pulse.h"
#include "config/parameter_group_ids.h"
#include "drivers/io.h"
#include "fc/settings.h"
#include "stm32h7xx_ll_tim.h"

PG_REGISTER_WITH_RESET_TEMPLATE(myboxRcinConfig_t, myboxRcinConfig, PG_MYBOX_RCIN_CONFIG, 0);
PG_RESET_TEMPLATE(myboxRcinConfig_t, myboxRcinConfig,
    .sbusEnabled = SETTING_MYBOX_SBUS_RCIN_DEFAULT,
);

#if defined(MYBOXH743MINI)
static const timerHardware_t rcinHardware = DEF_TIM(TIM2, CH4, PA3, TIM_USE_ANY, 0, 0);
#define RCIN_LL_CHANNEL LL_TIM_CHANNEL_CH4
#define RCIN_CAPTURE_FLAG TIM_SR_CC4IF
#define RCIN_OVERCAPTURE_FLAG TIM_SR_CC4OF
#else
static const timerHardware_t rcinHardware = DEF_TIM(TIM2, CH2, PB3, TIM_USE_ANY, 0, 0);
#define RCIN_LL_CHANNEL LL_TIM_CHANNEL_CH2
#define RCIN_CAPTURE_FLAG TIM_SR_CC2IF
#define RCIN_OVERCAPTURE_FLAG TIM_SR_CC2OF
#endif

// CH3 supplies a stop-bit deadline without driving a pin.
static const timerHardware_t rcinDeadlineHardware = { .tim = TIM2, .channelIndex = 2 };
static timerCallbacks_t rcinCallbacks;
static timerCallbacks_t deadlineCallbacks;
static myboxSbusWord_t word;
static IO_t rcinIO;
static serialReceiveCallbackPtr receiveByte;
static void *receiveContext;
static bool invertedSignal;

void myboxConfigureTimer2(TCH_t *channel)
{
    // Both channels are reserved outside the motor mapping, so timerInit doesn't enable TIM2.
    __HAL_RCC_TIM2_CLK_ENABLE();
    timerConfigure(channel, 0, MYBOX_TIM2_HZ);
    if (TIM2->ARR != MYBOX_TIM2_PERIOD - 1) {
        // TIM2 is 32-bit. Keep the heater's 1 Hz period at the 1 us capture resolution.
        TIM2->ARR = MYBOX_TIM2_PERIOD - 1;
        TIM2->EGR = TIM_EGR_UG;
    }
}

static void rcinFinishWord(void)
{
    uint8_t data;
    if (myboxSbusFinish(&word, &data)) {
        receiveByte(data, receiveContext);
    }
}

static void rcinDeadline(TCH_t *channel, uint32_t compare)
{
    UNUSED(channel);
    UNUSED(compare);

    // A capture already pending may contain a transition before the deadline.
    if (word.active && !(TIM2->SR & (RCIN_CAPTURE_FLAG | RCIN_OVERCAPTURE_FLAG))
        && myboxSbusElapsed(TIM2->CNT, word.start) >= SBUS_STOP_SAMPLE_US) {
        rcinFinishWord();
    }
}

static void rcinCapture(TCH_t *channel, uint32_t capture)
{
    const bool high = IORead(rcinIO) != invertedSignal;
    const uint32_t flags = TIM2->SR;
    if (flags & (RCIN_OVERCAPTURE_FLAG | RCIN_CAPTURE_FLAG)) {
        TIM2->SR = ~RCIN_OVERCAPTURE_FLAG;
        word.active = false;
        return;
    }

    if (word.active && myboxSbusElapsed(capture, word.start) >= SBUS_STOP_SAMPLE_US) {
        rcinFinishWord();
    }
    if (word.active) {
        myboxSbusEdge(&word, capture, high);
    } else if (!high) {
        myboxSbusStart(&word, capture);
        const uint32_t deadline = capture + SBUS_STOP_SAMPLE_US;
        TIM2->CCR3 = deadline < MYBOX_TIM2_PERIOD ? deadline : deadline - MYBOX_TIM2_PERIOD;
    }

    rcinDeadline(channel, 0);
}

bool myboxRcinSbusInit(serialReceiveCallbackPtr receive, void *context, bool inverted)
{
    TCH_t *capture = timerGetTCH(&rcinHardware);
    TCH_t *deadline = timerGetTCH(&rcinDeadlineHardware);
    if (!capture || !deadline) {
        return false;
    }

    receiveByte = receive;
    receiveContext = context;
    invertedSignal = inverted;
    rcinIO = IOGetByTag(rcinHardware.tag);
    IOInit(rcinIO, OWNER_SERIAL, RESOURCE_UART_RX, 0);
    IOConfigGPIOAF(rcinIO, inverted ? IOCFG_AF_PP_PD : IOCFG_AF_PP_UP, rcinHardware.alternateFunction);

    myboxConfigureTimer2(capture);
    timerChConfigIC(capture, true, 8);
    LL_TIM_IC_SetPolarity(TIM2, RCIN_LL_CHANNEL, LL_TIM_IC_POLARITY_BOTHEDGE);
    TIM2->SR = ~(RCIN_CAPTURE_FLAG | RCIN_OVERCAPTURE_FLAG | TIM_SR_CC3IF);
    timerChInitCallbacks(&rcinCallbacks, NULL, rcinCapture, NULL);
    timerChInitCallbacks(&deadlineCallbacks, NULL, rcinDeadline, NULL);
    timerChConfigCallbacks(capture, &rcinCallbacks);
    timerChConfigCallbacks(deadline, &deadlineCallbacks);
    timerChCaptureEnable(capture);
    return true;
}
#endif
