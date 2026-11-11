from pathlib import Path
import subprocess
import sys
import tempfile


driver = Path(sys.argv[1]).resolve() / "src/main/drivers/sdcard/sdmmc_sdio_hal.c"
source = driver.read_text()
diagnostics = source[source.index("static const char *sdStartupFailure;"):]
diagnostics = diagnostics[:diagnostics.index("#endif")]
startup = source[source.index("static bool sdInitCard("):source.index("SD_Error_t SD_GetCardInfo(void)")]
read_check = source[source.index("SD_Error_t SD_CheckRead(void)"):source.index("SD_Error_t SD_WriteBlocks_DMA(")]

with tempfile.TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "sd_startup.inc").write_text(diagnostics + startup + read_check)
    binary = work / "check"
    subprocess.run(
        ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I", str(work),
         str(Path(__file__).with_suffix(".c").resolve()), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True, timeout=10)
print("SDMMC: normal startup, 1-bit fallback on init/ACMD6/DMA failure, bounded timeout, recovery profile retained: OK")
