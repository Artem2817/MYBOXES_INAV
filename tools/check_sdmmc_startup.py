from pathlib import Path
import subprocess
import sys
import tempfile


driver = Path(sys.argv[1]).resolve() / "src/main/drivers/sdcard/sdmmc_sdio_hal.c"
source = driver.read_text()
header = driver.with_name("sdmmc_sdio.h").read_text()
types = header[header.rindex("typedef struct {", 0, header.index("const char *phase;")):
               header.index("sdmmcDiagnostics_t SD_GetDiagnostics(void);")]
diagnostics = source[source.index("static sdmmcDiagnostics_t sdDiagnostics"):]
diagnostics = diagnostics[:diagnostics.index("#endif")]
transfer = source[source.index("#define SDMMC_TRANSFER_ERRORS"):source.index("void sdioPinConfigure(void)")]
transfer = transfer[:transfer.rindex("#endif")]
startup = source[source.index("static bool sdInitCard("):source.index("SD_Error_t SD_GetCardInfo(void)")]

with tempfile.TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "sd_types.inc").write_text(types)
    (work / "sd_startup.inc").write_text(diagnostics + transfer + startup)
    binary = work / "check"
    subprocess.run(
        ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I", str(work),
         str(Path(__file__).with_suffix(".c").resolve()), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True, timeout=10)
print("SDMMC: startup and fallback, DMA completion with and without IRQ, hardware faults and timeout snapshots: OK")
