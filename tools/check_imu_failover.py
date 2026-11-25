#!/usr/bin/env python3
"""Exercise the real Vib failover manager with independent virtual IMU devices."""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(sys.argv[1]).resolve()
target=root/"src/main/target/MYBOXH743MINI"
code=re.sub(r'^\s*#include.*$', '', (target/"mybox_imu_failover.c").read_text(), flags=re.M)
header=(target/"mybox_imu_failover.h").read_text()
config=header[header.index("typedef struct {"):header.index("PG_DECLARE")]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#define USE_MYBOX_VIB
#define SETTING_MYBOX_IMU_FAILOVER_DEFAULT 1
#define PG_REGISTER_WITH_RESET_TEMPLATE(...)
#define PG_RESET_TEMPLATE(...)
#define CALIBRATING_GYRO_TIME_MS 2000
#ifdef TEST_INAV9
#define CALIBRATING_GYRO_MORON_THRESHOLD 32
#else
#define CALIBRATING_GYRO_MORON_THRESHOLD_DPS (32.0f/16.4f)
#endif
enum{ARMED=1,ZERO_CALIBRATION_IN_PROGRESS=1,ZERO_CALIBRATION_DONE=2};
static uint64_t nowUs;
static uint32_t flags;
#define ARMING_FLAG(f) (flags&(f))
static uint64_t micros(void){return nowUs;}
typedef union{float v[3];}fpVector3_t;
typedef struct{
 struct{int state;unsigned sampleCount;float stdDevThreshold;uint64_t start;}params;
 double sum[3];
}zeroCalibrationVector_t;
static void zeroCalibrationStartV(zeroCalibrationVector_t*c,uint32_t window,float threshold,bool allow){
 (void)window;(void)allow;memset(c,0,sizeof(*c));c->params.state=1;c->params.start=nowUs;c->params.stdDevThreshold=threshold;
}
static void zeroCalibrationAddValueV(zeroCalibrationVector_t*c,const fpVector3_t*v){
 c->params.sampleCount++;for(unsigned i=0;i<3;i++)c->sum[i]+=v->v[i];
}
static bool zeroCalibrationIsCompleteV(zeroCalibrationVector_t*c){if(nowUs-c->params.start>=2000000)c->params.state=2;return c->params.state==2;}
static bool zeroCalibrationIsSuccessfulV(zeroCalibrationVector_t*c){return c->params.sampleCount>0;}
static void zeroCalibrationGetZeroV(zeroCalibrationVector_t*c,fpVector3_t*v){for(unsigned i=0;i<3;i++)v->v[i]=c->sum[i]/c->params.sampleCount;}
typedef struct{uint8_t tag,id;bool online,gyroOk,accOk;float gyroRaw[3],accRaw[3];}busDevice_t;
typedef struct gyroDev_s{
 busDevice_t*busDev;bool(*readFn)(struct gyroDev_s*);
 bool(*temperatureFn)(struct gyroDev_s*,int16_t*);
 float scale,gyroADCRaw[3],gyroZero[3];
 uint8_t imuSensorToUse,lpf;uint32_t sampleRateIntervalUs;int gyroAlign;
}gyroDev_t;
typedef struct accDev_s{
 busDevice_t*busDev;bool(*readFn)(struct accDev_s*);
 uint16_t acc_1G;float ADCRaw[3];uint8_t imuSensorToUse;int accAlign;
}accDev_t;
static bool busRead(busDevice_t*d,uint8_t reg,uint8_t*v){assert(reg==(d->tag==1?0x75:0x72));*v=d->id;return d->online;}
static bool backendGyro(gyroDev_t*d){if(!d->busDev->online||!d->busDev->gyroOk)return false;memcpy(d->gyroADCRaw,d->busDev->gyroRaw,sizeof(d->gyroADCRaw));return true;}
static bool backendAcc(accDev_t*d){if(!d->busDev->online||!d->busDev->accOk)return false;memcpy(d->ADCRaw,d->busDev->accRaw,sizeof(d->ADCRaw));return true;}
static bool backendTemp(gyroDev_t*d,int16_t*t){*t=250+d->imuSensorToUse;return d->busDev->online;}
typedef struct{struct{int16_t raw[3];}accZero,accGain;float acc_temp_correction;uint8_t calibrationImu;}accelerometerConfig_t;
static accelerometerConfig_t accConfig;
static const accelerometerConfig_t*accelerometerConfig(void){return &accConfig;}
static accelerometerConfig_t*accelerometerConfigMutable(void){return &accConfig;}
static unsigned refreshed;
static void accRefreshCalibrationCoefficients(void){refreshed++;}
static bool gyroIsCalibrationComplete(void){return nowUs>=2000000ULL;}
'''
tests=r'''
static busDevice_t devices[2];
static gyroDev_t primary,spare;
static accDev_t primaryAcc,spareAcc;
static void resetManager(unsigned selected,bool present,bool profiles){
 memset(&config,0,sizeof(config));config.enabled=1;
 memset(&accConfig,0,sizeof(accConfig));
 for(unsigned i=0;i<2;i++){
  devices[i]=(busDevice_t){.tag=i,.id=i==1?0x67:0xe9,.online=true,.gyroOk=true,.accOk=true,
    .gyroRaw={20.0f+i,30.0f+i,40.0f+i},.accRaw={10.0f+i,20.0f+i,2048.0f+i}};
  for(unsigned a=0;a<3;a++){config.accZero[i][a]=100*i+a;config.accGain[i][a]=4096+10*i+a;}
 }
 if(profiles)config.validMask=3;
 primary=(gyroDev_t){.busDev=&devices[selected],.imuSensorToUse=selected,.readFn=backendGyro,.temperatureFn=backendTemp,
 .scale=selected==1?1.0f/16.4f:1.0f/32.8f,.gyroAlign=10+selected};
 unsigned other=1-selected;
 spare=(gyroDev_t){.busDev=&devices[other],.imuSensorToUse=other,.readFn=backendGyro,.temperatureFn=backendTemp,
 .scale=other==1?1.0f/16.4f:1.0f/32.8f,.gyroAlign=10+other};
 primaryAcc=(accDev_t){.busDev=&devices[selected],.imuSensorToUse=selected,.readFn=backendAcc,.acc_1G=2048,.accAlign=10+selected};
 spareAcc=(accDev_t){.busDev=&devices[other],.imuSensorToUse=other,.readFn=backendAcc,.acc_1G=2048,.accAlign=10+other};
 nowUs=0;flags=0;refreshed=0;
 myboxImuAttach(&primary,&primaryAcc,&spare,&spareAcc,present);
 myboxImuStartCalibration();
}
static void tick(void){nowUs+=625;primary.readFn(&primary);primaryAcc.readFn(&primaryAcc);}
static void warm(void){for(unsigned i=0;i<3600;i++)tick();assert(sources[1-activeIndex].calibrated);}
static void failFor(unsigned ticks){for(unsigned i=0;i<ticks;i++)tick();}
static void testSwitch(unsigned selected,bool profiles){
 resetManager(selected,true,profiles);warm();assert(!strcmp(myboxImuFailoverState(),"ready"));
 flags=ARMED;devices[selected].gyroOk=false;failFor(40);
 unsigned reserve=1-selected;
 assert(switches==1&&activeIndex==reserve&&primary.imuSensorToUse==reserve&&primaryAcc.imuSensorToUse==reserve);
 assert(primary.gyroAlign==10+(int)reserve&&primaryAcc.accAlign==10+(int)reserve);
 for(unsigned a=0;a<3;a++)assert(fabsf(primary.gyroZero[a]-devices[reserve].gyroRaw[a])<.001f);
 assert(refreshed==1&&flags==ARMED&&myboxImuIsHealthy());
 if(profiles)assert(accConfig.accZero.raw[0]==(int)(100*reserve));
 else assert(accConfig.accZero.raw[0]==0&&accConfig.accGain.raw[0]==4096);
 devices[selected].gyroOk=true;failFor(1000);assert(activeIndex==reserve&&switches==1);
 devices[reserve].online=false;failFor(100);assert(switches==1&&!myboxImuIsHealthy()&&flags==ARMED);
}
int main(void){
 testSwitch(1,true);testSwitch(0,true);testSwitch(1,false);
 resetManager(1,true,true);warm();flags=ARMED;devices[1].gyroOk=false;failFor(8);assert(!switches);
 devices[1].gyroOk=true;failFor(80);assert(!switches);
 resetManager(1,false,true);for(unsigned i=0;i<3600;i++)tick();flags=ARMED;devices[1].online=false;failFor(100);assert(!switches&&flags==ARMED);
 resetManager(1,true,true);warm();devices[0].online=false;failFor(100);flags=ARMED;devices[1].online=false;failFor(100);assert(!switches&&flags==ARMED);
 resetManager(1,true,true);warm();flags=ARMED;devices[1].id=0xff;failFor(60);assert(switches==1&&activeIndex==0);
 resetManager(1,true,true);warm();flags=ARMED;devices[1].accOk=false;failFor(80);assert(switches==1&&activeIndex==0);
 resetManager(1,true,true);warm();flags=ARMED;config.enabled=0;devices[1].online=false;failFor(100);assert(!switches&&flags==ARMED);
 resetManager(1,true,true);warm();nowUs=UINT32_MAX-5000ULL;tick();flags=ARMED;devices[1].gyroOk=false;failFor(60);assert(switches==1);
 resetManager(1,true,true);nowUs=3000000;tick();assert(!sources[0].calibrated);for(unsigned i=0;i<3600;i++)tick();assert(sources[0].calibrated);
 memset(&config,0,sizeof(config));accConfig.calibrationImu=2;
 for(unsigned a=0;a<3;a++){accConfig.accZero.raw[a]=10+a;accConfig.accGain.raw[a]=4096;}
 myboxImuPrepareAccCalibration(0);assert(config.validMask==2&&accConfig.calibrationImu==0);
 for(unsigned a=0;a<3;a++){accConfig.accZero.raw[a]=20+a;accConfig.accGain.raw[a]=4100;}
 accConfig.calibrationImu=1;myboxImuStoreAccCalibration(0);assert(config.validMask==3);
 assert(myboxImuLoadAccCalibration(1)&&accConfig.accZero.raw[0]==10&&accConfig.accGain.raw[0]==4096);
 assert(myboxImuLoadAccCalibration(0)&&accConfig.accZero.raw[0]==20&&accConfig.accGain.raw[0]==4100);
 puts("Vib IMU failover: both directions; gyro/acc/identity loss; brief faults; missing/stale/both failed; bias, scale, profile isolation; factory fallback; rollover; no disarm; no switch-back");
}
'''
with tempfile.TemporaryDirectory(prefix="mybox-imu-failover-") as folder:
 folder=Path(folder)
 source=folder/"check.c"
 source.write_text(prefix+config+'''
static myboxImuFailoverConfig_t config;
static const myboxImuFailoverConfig_t*myboxImuFailoverConfig(void){return &config;}
static myboxImuFailoverConfig_t*myboxImuFailoverConfigMutable(void){return &config;}
bool myboxImuTemperature(uint8_t,int16_t*);
'''+code+tests)
 for version in (9,10):
  binary=folder/f"check{version}"
  subprocess.run(["gcc","-std=gnu11","-O1","-g","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",
    "-fno-sanitize-recover=all",*(["-DTEST_INAV9"]if version==9 else []),str(source),"-lm","-o",str(binary)],check=True)
  subprocess.run([str(binary)],check=True,timeout=20)
print("Real failover manager: INAV 9 and INAV 10 calibration API variants passed")
