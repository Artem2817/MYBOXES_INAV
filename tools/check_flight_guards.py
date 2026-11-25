#!/usr/bin/env python3
"""Fault injection of the real r17 SPI/SD/CAN/GPS/IMU/OSD guards on the host."""
from pathlib import Path
import hashlib, json, re, subprocess, sys, tempfile

root=Path(sys.argv[1]).resolve()
baseline=json.loads(Path(__file__).with_name("r17-flight-behavior-baseline.json").read_text())
for name, expected in baseline.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected, "Flight behaviour source changed: "+name
print("Flight logic: 14 core files unchanged from r16; no new disarm/IMU switching/watchdog")
def function(path, signature):
    text=(root/path).read_text(); start=text.index(signature);brace=text.index("{",start);end,depth=brace+1,1
    while depth:
        depth+=(text[end]=="{")-(text[end]=="}");end+=1
    return text[start:end]
def stripped(path):
    return re.sub(r'^\s*#include.*$', '', (root/path).read_text(), flags=re.M)
def compile_run(work,name,code,extra=()):
    file=work/(name+".c");file.write_text(code)
    binary=work/name
    subprocess.run(["gcc","-std=gnu11","-O1","-g","-Wall","-Wextra","-Wno-unused-function","-Werror",
        "-fsanitize=address,undefined,float-cast-overflow","-fno-sanitize-recover=all",
        "-I",str(work),"-I",str(root/"src/main"),str(file),*extra,"-lm","-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)

with tempfile.TemporaryDirectory(prefix="mybox-r17-guards-") as folder:
    work=Path(folder)
    (work/"platform.h").write_text("#define USE_DRONECAN\n")
    spi=r'''
#include <stdbool.h>
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define STM32H7
typedef struct{int unused;}SPI_TypeDef;
static int fault;
static unsigned errors,disabled,cleared,calls;
static void LL_SPI_SetTransferSize(SPI_TypeDef*p,int n){(void)p;(void)n;}
static void LL_SPI_Enable(SPI_TypeDef*p){(void)p;}
static void LL_SPI_StartMasterTransfer(SPI_TypeDef*p){(void)p;}
static bool LL_SPI_IsActiveFlag_TXP(SPI_TypeDef*p){(void)p;calls++;return fault!=1;}
static bool LL_SPI_IsActiveFlag_RXP(SPI_TypeDef*p){(void)p;calls++;return fault!=2;}
static bool LL_SPI_IsActiveFlag_EOT(SPI_TypeDef*p){(void)p;calls++;return fault!=3;}
static void LL_SPI_TransmitData8(SPI_TypeDef*p,uint8_t n){(void)p;(void)n;}
static uint8_t LL_SPI_ReceiveData8(SPI_TypeDef*p){(void)p;return 42;}
static void LL_SPI_ClearFlag_TXTF(SPI_TypeDef*p){(void)p;cleared++;}
static void LL_SPI_ClearFlag_EOT(SPI_TypeDef*p){(void)p;cleared++;}
static void LL_SPI_ClearFlag_OVR(SPI_TypeDef*p){(void)p;cleared++;}
static void LL_SPI_Disable(SPI_TypeDef*p){(void)p;disabled++;}
static void spiTimeoutUserCallback(SPI_TypeDef*p){(void)p;errors++;}
'''+function("src/main/drivers/bus_spi_hal_ll.c","bool spiTransfer(SPI_TypeDef *instance,")+r'''
int main(void){SPI_TypeDef bus={0};uint8_t bytes[6];
 assert(!spiTransfer(&bus,bytes,0,-1));assert(spiTransfer(&bus,bytes,0,0));
 for(int i=1;i<=3;i++){
  fault=i;unsigned e=errors,d=disabled;calls=0;
  assert(!spiTransfer(&bus,bytes,0,6));
  assert(errors==e+1&&disabled==d+1&&calls<1100);
  fault=0;assert(spiTransfer(&bus,bytes,0,6)&&bytes[5]==42);
 }
 puts("SPI: TXP/RXP/EOT faults bounded; disabled/cleared on error; next transfer succeeds");
}
'''
    compile_run(work,"spi",spi)
    # Reuse real HAL/startup harness, then add runtime CMD13/reset integration.
    sd=Path(__file__).with_name("check_sdmmc_startup.c").read_text().replace("int main(void)","int baseline_main(void)")
    hal=(root/"src/main/drivers/sdcard/sdmmc_sdio_hal.c").read_text()
    header=(root/"src/main/drivers/sdcard/sdmmc_sdio.h").read_text()
    types=header[header.rindex("typedef struct {",0,header.index("const char *phase;")):header.index("sdmmcDiagnostics_t SD_GetDiagnostics(void);")]
    diagnostics=hal[hal.index("static sdmmcDiagnostics_t sdDiagnostics"):];diagnostics=diagnostics[:diagnostics.index("#endif")]
    transfer=hal[hal.index("#define SDMMC_TRANSFER_ERRORS"):hal.index("void sdioPinConfigure(void)")];transfer=transfer[:transfer.rindex("#endif")]
    startup=hal[hal.index("static bool sdInitCard("):hal.index("SD_Error_t SD_GetCardInfo(void)")]
    (work/"sd_types.inc").write_text(types)
    (work/"sd_startup.inc").write_text(diagnostics+transfer+startup)
    (work/"sd_power_on.inc").write_text(function("lib/main/STM32H7/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_sd.c","static uint32_t SD_PowerON(SD_HandleTypeDef *hsd)\n{"))
    sd=sd.replace("static int HAL_SD_Init(", "static int HAL_SD_Init(",1)
    sd=sd.replace("static uint32_t halError;","static uint32_t halError;\nstatic uint64_t micros(void);",1)
    sd+=r'''
#include <stdio.h>
enum {SDMMC_FLAG_CTIMEOUT=1U<<16,SDMMC_FLAG_CCRCFAIL=1U<<17,SDMMC_FLAG_CMDACT=1U<<18,
 SDMMC_FLAG_CMDREND=1U<<19,SDMMC_CMD_SEND_STATUS=13,SDMMC_RESPONSE_SHORT=1,SDMMC_WAIT_NO=0,
 SDMMC_CPSM_ENABLE=1,HAL_SD_CARD_TRANSFER=4,HAL_SD_ERROR_GENERAL_UNKNOWN_ERR=1U<<20,
 SDMMC_OCR_ERRORBITS=0xfdf9e008};
#define SDMMC_STATIC_CMD_FLAGS (SDMMC_FLAG_CTIMEOUT|SDMMC_FLAG_CCRCFAIL|SDMMC_FLAG_CMDREND)
#define __HAL_SD_CLEAR_FLAG(sd,flags) ((sd)->Instance->STA&=~(flags))
#define __DSB() ((void)0)
typedef struct{uint32_t Argument,CmdIndex,Response,WaitForInterrupt,CPSM;}SDMMC_CmdInitTypeDef;
static uint64_t nowUs;
static uint64_t micros(void){return nowUs;}
static unsigned commands;
static void SDMMC_SendCommand(SDMMC_TypeDef*reg,const SDMMC_CmdInitTypeDef*cmd){reg->CMD=cmd->CmdIndex;commands++;}
'''+function("src/main/drivers/sdcard/sdmmc_sdio_hal.c","void SD_Disable(void)")+"\n"+function("src/main/drivers/sdcard/sdmmc_sdio_hal.c","bool SD_GetState(void)")+r'''
enum {SDCARD_STATE_NOT_PRESENT,SDCARD_STATE_RESET,SDCARD_MAX_CONSECUTIVE_FAILURES=8};
static struct{int state;unsigned failureCount;uint32_t operationStartTime;}sdcard;
static bool sdcard_isInserted(void){return true;}
static uint32_t millis(void){return nowUs/1000;}
'''+function("src/main/drivers/sdcard/sdcard_sdio.c","static void sdcardSdio_reset(void)")+r'''
int main(void){
 baseline_main();resetTest(OK,OK);assert(SD_Init()==SD_OK);
 assert(!SD_GetState()&&commands==1);
 instance.RESPCMD=13;instance.RESP1=4U<<9;instance.STA=SDMMC_FLAG_CMDREND;
 assert(SD_GetState());assert(!sdStatusPending);
 assert(!SD_GetState());nowUs+=2001;assert(!SD_GetState()&&sdTransferFailed);
 assert(!irqEnabled&&instance.IDMACTRL==0&&instance.DCTRL==0);
 unsigned initCalls=attempts;sdcardSdio_reset();assert(attempts==initCalls&&sdcard.state==SDCARD_STATE_NOT_PRESENT);
 resetTest(OK,OK);assert(SD_Init()==SD_OK);assert(!SD_GetState());
 instance.RESPCMD=24;instance.STA=SDMMC_FLAG_CMDREND;instance.RESP1=4U<<9;
 assert(!SD_GetState()&&sdTransferFailed);
 puts("SD: CMD13 async success/error/timeout; IDMA stopped; runtime reset never initializes card");
}
'''
    compile_run(work,"sd",sd)

    gps=r'''
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <assert.h>
#include <dronecan_msgs.h>
#define USE_DRONECAN
enum{X,Y,Z,GPS_NO_FIX=0,GPS_FIX_2D,GPS_FIX_3D};
#define M_PIf 3.14159265358979323846f
#define RADIANS_TO_DECIDEGREES(x) ((x)*(1800/M_PIf))
static float calc_length_pythagorean_2D(float x,float y){return sqrtf(x*x+y*y);}
static float atan2_approx(float y,float x){return atan2f(y,x);}
static uint16_t gpsConstrainEPE(uint32_t n){return n>9999?9999:n;}
static uint16_t gpsConstrainHDOP(uint32_t n){return n>9999?9999:n;}
static unsigned updates;
static void gpsProcessNewDriverData(void){updates++;}
static void gpsProcessNewSolutionData(bool b){(void)b;}
static struct{int fixType;uint8_t numSat;struct{int32_t lon,lat,alt;}llh;
 int16_t velNED[3],groundSpeed,groundCourse;uint16_t hdop,eph,epv;
 struct{bool validVelNE,validVelD,validEPE,validTime;}flags;}gpsSolDRV;
'''+stripped("src/main/io/gps_dronecan.c")+r'''
static uint32_t seed=0x36ca947b;static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;return seed^=seed<<5;}
int main(void){
 struct uavcan_equipment_gnss_Fix2 fix={0};fix.status=3;fix.ned_velocity[0]=1;fix.pdop=1;
 dronecanGPSReceiveGNSSFix2(&fix);assert(updates==1&&gpsSolDRV.velNED[0]==100);
 fix.ned_velocity[0]=NAN;dronecanGPSReceiveGNSSFix2(&fix);assert(updates==1);
 fix.ned_velocity[0]=INFINITY;dronecanGPSReceiveGNSSFix2(&fix);assert(updates==1);
 fix.ned_velocity[0]=300;fix.ned_velocity[1]=300;dronecanGPSReceiveGNSSFix2(&fix);assert(updates==1);
 fix.ned_velocity[0]=fix.ned_velocity[1]=0;fix.latitude_deg_1e8=9000000001LL;
 dronecanGPSReceiveGNSSFix2(&fix);assert(updates==1);
 fix.latitude_deg_1e8=0;fix.covariance.len=6;fix.covariance.data[0]=-1;
 dronecanGPSReceiveGNSSFix2(&fix);assert(updates==2&&!gpsSolDRV.flags.validEPE);
 fix.status=0;fix.ned_velocity[0]=NAN;dronecanGPSReceiveGNSSFix2(&fix);
 assert(updates==3&&gpsSolDRV.fixType==GPS_NO_FIX&&!gpsSolDRV.flags.validVelNE);
 struct uavcan_equipment_gnss_Fix legacy={0};legacy.status=3;legacy.ned_velocity[0]=1;legacy.pdop=INFINITY;
 dronecanGPSReceiveGNSSFix(&legacy);assert(updates==4&&gpsSolDRV.hdop==9999);
 struct uavcan_equipment_gnss_Auxiliary aux={0};aux.hdop=-INFINITY;dronecanGPSReceiveGNSSAuxiliary(&aux);assert(lastHDOP==9999);
 for(unsigned i=0;i<200000;i++){
  uint32_t bits=next();memcpy(&fix.ned_velocity[0],&bits,4);
  bits=next();memcpy(&fix.pdop,&bits,4);
  bits=next();memcpy(&fix.covariance.data[0],&bits,4);
  fix.status=3;dronecanGPSReceiveGNSSFix2(&fix);
  memcpy(&legacy.ned_velocity[0],&bits,4);dronecanGPSReceiveGNSSFix(&legacy);
 }
 puts("GPS: Fix/Fix2 reject NaN/Inf/overflow/range errors; no-fix clears stale fix; optional covariance safe; 400000 fuzz calls");
}
'''
    compile_run(work,"gps",gps,["-I",str(root/"lib/main/Dronecan/dsdlc_generated/include")])

    osd=r'''
#include <stdbool.h>
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
typedef uint32_t timeMs_t;
static uint32_t now;
static uint32_t millis(void){return now++;}
static unsigned readCount;static int fault;
enum{MAX7456ADD_STAT=1,STAT_NVR_BUSY=32};
static struct{void*dev;}state;
#define LED0_TOGGLE ((void)0)
static bool busRead(void*d,int a,uint8_t*s){(void)d;(void)a;*s=fault==1||readCount++<3?32:0;return fault!=2;}
'''+function("src/main/drivers/max7456.c","static bool max7456IsBusy(void)")+"\n"+function("src/main/drivers/max7456.c","static bool max7456WaitUntilNoBusy(void)")+r'''
int main(void){assert(max7456WaitUntilNoBusy());
 for(int f=1;f<=2;f++){fault=f;now=0;assert(!max7456WaitUntilNoBusy()&&now<40);}
 puts("OSD: stuck NVM busy/read error returns within the deadline");
}
'''
    compile_run(work,"osd",osd)

    can=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <inttypes.h>
typedef uint64_t timeUs_t;
typedef int CanardCANFrame;
typedef struct{uint32_t BusOff,ErrorPassive;}canardProtocolStatus_t;
typedef enum{STATE_DRONECAN_INIT,STATE_DRONECAN_NORMAL,STATE_DRONECAN_BUS_OFF,STATE_DRONECAN_FAILED}dronecanState_e;
static dronecanState_e dronecanState=STATE_DRONECAN_INIT;
static uint32_t txErrCount,busOffCount;
static int canard;
static bool busOff;
static unsigned countRX,recoveries;
#define NVIC_PRIO_CAN 4
#define ATOMIC_BLOCK(x) for(bool once=true;once;once=false)
#define LOG_WARNING(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
static void processCanardTxQueueSafe(void){}
static int canardSTM32GetRxFifoFillLevel(void){return 30;}
static uint32_t millis(void){return 0;}
static int16_t canardSTM32Receive(CanardCANFrame*f){*f=0;return 1;}
static void canardHandleRxFrame(int*p,CanardCANFrame*f,uint64_t ts){(void)p;(void)f;(void)ts;countRX++;}
static void dronecanAsyncCheckTimeout(void){}
static void process1HzTasks(timeUs_t ts){(void)ts;}
static void canardSTM32GetProtocolStatus(canardProtocolStatus_t*s){s->BusOff=busOff;s->ErrorPassive=0;}
static uint32_t canardSTM32GetAndClearRxDropCount(void){return 0;}
static void canardSTM32RecoverFromBusOff(void){recoveries++;}
'''+function("src/main/drivers/dronecan/dronecan.c","void dronecanUpdate(timeUs_t currentTimeUs)")+r'''
int main(void){
 dronecanUpdate(0);
 for(unsigned i=0;i<10000;i++)dronecanUpdate((timeUs_t)i*100);
 assert(countRX==300000);
 busOff=true;timeUs_t t=2000000;dronecanUpdate(t);
 for(unsigned i=0;i<50;i++){t+=20001;dronecanUpdate(t);}
 assert(dronecanState==STATE_DRONECAN_FAILED&&recoveries==50);
 t+=1000001;dronecanUpdate(t);assert(dronecanState==STATE_DRONECAN_FAILED&&recoveries==51);
 busOff=false;t+=1000001;dronecanUpdate(t);assert(dronecanState==STATE_DRONECAN_NORMAL);
 puts("CAN: 300000 bounded RX dispatches; prolonged bus-off cools down and resumes after bus repair");
}
'''
    compile_run(work,"can",can)
    i2c=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#define USE_MYBOX_IO_TIMEOUTS
enum{ARMED=1};static bool armed;
#define ARMING_FLAG(f) (armed)
typedef int IO_t;
enum{IOCFG_OUT_OD=1};
static unsigned delayUs;
static void IOHi(IO_t pin){(void)pin;}
static void IOLo(IO_t pin){(void)pin;}
static void IOConfigGPIO(IO_t pin,int mode){(void)pin;(void)mode;}
static bool IORead(IO_t pin){(void)pin;return false;}
static void delayMicroseconds(unsigned n){delayUs+=n;}
'''+function("src/main/drivers/bus_i2c_hal.c","static void i2cUnstick(IO_t scl, IO_t sda)\n{")+r'''
enum{I2CINVALID=-1,I2CDEV_1=0,HAL_OK=0,HAL_ERROR=1,I2C_MEMADD_SIZE_8BIT=1,I2C_DEFAULT_TIMEOUT=1};
typedef int I2CDevice;typedef int HAL_StatusTypeDef;
typedef struct{bool initialised,retryPending;uint32_t lastFailureMs;int handle;}i2cState_t;
static i2cState_t i2cState[1]={{.initialised=true}};
static uint16_t i2cErrorCount;
static uint32_t nowMs;
static uint32_t millis(void){return nowMs;}
static unsigned resets,transactions;static bool error=true;
static void i2cInit(I2CDevice d){assert(d==0);resets++;}
static int fakeHAL(unsigned timeout){assert(timeout==1);transactions++;return error?HAL_ERROR:HAL_OK;}
#define HAL_I2C_Master_Transmit(h,a,d,l,t) ((void)(h),(void)(a),(void)(d),(void)(l),fakeHAL(t))
#define HAL_I2C_Mem_Write(h,a,r,s,d,l,t) ((void)(h),(void)(a),(void)(r),(void)(s),(void)(d),(void)(l),fakeHAL(t))
#define HAL_I2C_Master_Receive(h,a,d,l,t) ((void)(h),(void)(a),(void)(d),(void)(l),fakeHAL(t))
#define HAL_I2C_Mem_Read(h,a,r,s,d,l,t) ((void)(h),(void)(a),(void)(r),(void)(s),(void)(d),(void)(l),fakeHAL(t))
'''+function("src/main/drivers/bus_i2c_hal.c","static bool i2cHandleHardwareFailure(")+"\n"+function("src/main/drivers/bus_i2c_hal.c","bool i2cWriteBuffer(")+"\n"+function("src/main/drivers/bus_i2c_hal.c","bool i2cRead(")+r'''
int main(void){
 armed=true;i2cUnstick(0,1);assert(delayUs==150);
 uint8_t byte=0;assert(!i2cRead(0,0x28,0,1,&byte,false));assert(resets==1&&transactions==1);
 for(unsigned i=0;i<10000;i++)assert(!i2cRead(0,0x28,0,1,&byte,false));
 assert(resets==1&&transactions==1);
 nowMs=100;assert(!i2cWriteBuffer(0,0x28,0,1,&byte,false));assert(resets==2&&transactions==2);
 nowMs=200;error=false;assert(i2cRead(0,0x28,0,1,&byte,false));assert(transactions==3);
 puts("I2C: SCL-low recovery delay 150us when armed; 10000 retry calls skipped without bus access; recovery after cooldown");
}
'''
    compile_run(work,"i2c",i2c)

print("r17 flight guards: all checks passed")
