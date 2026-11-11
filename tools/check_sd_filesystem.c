// SPDX-License-Identifier: GPL-3.0-or-later
#include <assert.h>
#include <stdlib.h>
#include <string.h>

#include "common/time.h"
#include "drivers/sdcard/sdcard.h"
#include "io/asyncfatfs/asyncfatfs.h"

enum { BLOCK_SIZE = 512, DISK_SECTORS = 80000, MAX_POLLS = 20000 };
static const sdcardMetadata_t metadata = { .numBlocks = DISK_SECTORS };
static uint8_t *disk;
static unsigned writes;
static struct {
    sdcard_operationCompleteCallback_c callback;
    uint8_t *buffer;
    uint32_t blockIndex;
    uint32_t callbackData;
    sdcardBlockOperation_e operation;
} pending;

bool rtcGetDateTimeLocal(dateTime_t *date)
{
    (void)date;
    return false;
}

static uint8_t *block(uint32_t index)
{
    assert(index < DISK_SECTORS);
    return disk + (size_t)index * BLOCK_SIZE;
}

static bool queueBlock(sdcardBlockOperation_e operation, uint32_t index, uint8_t *buffer,
    sdcard_operationCompleteCallback_c callback, uint32_t callbackData)
{
    if (pending.callback) {
        return false;
    }
    pending.operation = operation;
    pending.blockIndex = index;
    pending.buffer = buffer;
    pending.callback = callback;
    pending.callbackData = callbackData;
    return true;
}

bool sdcard_readBlock(uint32_t index, uint8_t *buffer, sdcard_operationCompleteCallback_c callback, uint32_t callbackData)
{
    return queueBlock(SDCARD_BLOCK_OPERATION_READ, index, buffer, callback, callbackData);
}

sdcardOperationStatus_e sdcard_writeBlock(uint32_t index, uint8_t *buffer,
    sdcard_operationCompleteCallback_c callback, uint32_t callbackData)
{
    return queueBlock(SDCARD_BLOCK_OPERATION_WRITE, index, buffer, callback, callbackData)
        ? SDCARD_OPERATION_IN_PROGRESS : SDCARD_OPERATION_BUSY;
}

sdcardOperationStatus_e sdcard_beginWriteBlocks(uint32_t index, uint32_t count)
{
    assert(index < DISK_SECTORS && count <= DISK_SECTORS - index);
    return SDCARD_OPERATION_SUCCESS;
}

bool sdcard_poll(void)
{
    if (pending.callback) {
        if (pending.operation == SDCARD_BLOCK_OPERATION_READ) {
            memcpy(pending.buffer, block(pending.blockIndex), BLOCK_SIZE);
        } else {
            memcpy(block(pending.blockIndex), pending.buffer, BLOCK_SIZE);
            ++writes;
        }
        sdcard_operationCompleteCallback_c callback = pending.callback;
        pending.callback = NULL;
        callback(pending.operation, pending.blockIndex, pending.buffer, pending.callbackData);
    }
    return true;
}

const sdcardMetadata_t *sdcard_getMetadata(void)
{
    return &metadata;
}

static void writeSignature(uint8_t *sector)
{
    sector[510] = 0x55;
    sector[511] = 0xaa;
}

static void writePartition(unsigned slot, uint8_t type, uint32_t first, uint32_t size)
{
    mbrPartitionEntry_t entry = { .type = type, .lbaBegin = first, .numSectors = size };
    memcpy(block(0) + 446 + slot * sizeof(entry), &entry, sizeof(entry));
    writeSignature(block(0));
}

static uint32_t writeFat(uint32_t first, uint8_t fatCount, bool fat32)
{
    const uint16_t fatSectors = fat32 ? 600 : 40;
    const uint32_t total = fat32 ? 72000 : 10000;
    fatVolumeID_t volume = {
        .jmpBoot = {0xeb, 0x58, 0x90},
        .bytesPerSector = BLOCK_SIZE,
        .sectorsPerCluster = 1,
        .reservedSectorCount = fat32 ? 32 : 1,
        .numFATs = fatCount,
        .media = 0xf8,
    };

    if (fat32) {
        volume.totalSectors32 = total;
        volume.fatDescriptor.fat32.FATSize32 = fatSectors;
        volume.fatDescriptor.fat32.rootCluster = 2;
        const uint32_t reservedEntries[] = {0x0ffffff8, 0xffffffff, 0x0fffffff};
        for (unsigned copy = 0; copy < fatCount; ++copy) {
            memcpy(block(first + volume.reservedSectorCount + copy * fatSectors),
                reservedEntries, sizeof(reservedEntries));
        }
    } else {
        volume.totalSectors16 = total;
        volume.FATSize16 = fatSectors;
        volume.rootEntryCount = 512;
        const uint16_t reservedEntries[] = {0xfff8, 0xffff};
        for (unsigned copy = 0; copy < fatCount; ++copy) {
            memcpy(block(first + volume.reservedSectorCount + copy * fatSectors),
                reservedEntries, sizeof(reservedEntries));
        }
    }
    memcpy(block(first), &volume, sizeof(volume));
    writeSignature(block(first));
    return total;
}

static afatfsFilesystemState_e mount(void)
{
    afatfs_init();
    for (unsigned i = 0; i < MAX_POLLS && afatfs_getFilesystemState() == AFATFS_FILESYSTEM_STATE_INITIALIZATION; ++i) {
        afatfs_poll();
    }
    return afatfs_getFilesystemState();
}

static void unmount(void)
{
    for (unsigned i = 0; i < MAX_POLLS; ++i) {
        if (afatfs_destroy(false)) {
            return;
        }
    }
    assert(!"filesystem did not flush and unmount");
}

static afatfsFilePtr_t logFile;
static bool opened;
static void openComplete(afatfsFilePtr_t file)
{
    logFile = file;
    opened = true;
}

static void openLog(const char *mode)
{
    logFile = NULL;
    opened = false;
    assert(afatfs_fopen("TEST.BBL", mode, openComplete));
    for (unsigned i = 0; i < MAX_POLLS && !opened; ++i) {
        afatfs_poll();
    }
    assert(opened && logFile);
}

static void testLog(uint32_t first, uint8_t type, uint8_t fatCount, bool fat32, bool invalidFirst)
{
    memset(disk, 0, (size_t)DISK_SECTORS * BLOCK_SIZE);
    writes = 0;
    const uint32_t size = writeFat(first, fatCount, fat32);
    if (first) {
        if (invalidFirst) {
            writePartition(0, 0x0c, 2048, 2048);
        }
        writePartition(invalidFirst ? 1 : 0, type, first, size);
    }
    uint8_t sectorZero[BLOCK_SIZE];
    memcpy(sectorZero, block(0), sizeof(sectorZero));

    assert(mount() == AFATFS_FILESYSTEM_STATE_READY);
    openLog("w");
    const uint8_t log[] = "H Product: Blackbox flight data recorder\n";
    uint32_t offset = 0;
    for (unsigned i = 0; i < MAX_POLLS && offset < sizeof(log); ++i) {
        offset += afatfs_fwrite(logFile, log + offset, sizeof(log) - offset);
        afatfs_poll();
    }
    assert(offset == sizeof(log));
    unmount();

    assert(writes > 0 && memcmp(sectorZero, block(0), sizeof(sectorZero)) == 0);
    assert(mount() == AFATFS_FILESYSTEM_STATE_READY);
    openLog("r");
    uint8_t restored[sizeof(log)];
    offset = 0;
    for (unsigned i = 0; i < MAX_POLLS && offset < sizeof(restored); ++i) {
        offset += afatfs_fread(logFile, restored + offset, sizeof(restored) - offset);
        afatfs_poll();
    }
    assert(offset == sizeof(log) && memcmp(log, restored, sizeof(log)) == 0);
    unmount();
}

static void testInvalidLayout(void)
{
    memset(disk, 0, (size_t)DISK_SECTORS * BLOCK_SIZE);
    writes = 0;
    writePartition(0, 0x0c, DISK_SECTORS - 1, 10);
    assert(mount() == AFATFS_FILESYSTEM_STATE_FATAL);
    assert(afatfs_getLastError() == AFATFS_ERROR_BAD_MBR && writes == 0);
    unmount();

    memset(disk, 0, (size_t)DISK_SECTORS * BLOCK_SIZE);
    writeFat(2048, 2, true);
    writePartition(0, 0x0c, 2048, 1);
    assert(mount() == AFATFS_FILESYSTEM_STATE_FATAL);
    assert(afatfs_getLastError() == AFATFS_ERROR_BAD_FILESYSTEM_HEADER && writes == 0);
    unmount();
}

int main(void)
{
    disk = calloc(DISK_SECTORS, BLOCK_SIZE);
    assert(disk);

    testLog(0, 0, 2, true, false);
    testLog(0, 0, 1, true, false);
    testLog(2048, 0x0c, 2, true, false);
    testLog(4096, 0x07, 2, true, true);
    testLog(2048, 0x06, 2, false, false);
    testInvalidLayout();

    free(disk);
    return 0;
}
