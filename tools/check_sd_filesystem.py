from pathlib import Path
import subprocess
import sys
import tempfile


upstream = Path(sys.argv[1]).resolve() / "src/main"
test = Path(__file__).with_suffix(".c").resolve()
with tempfile.TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "platform.h").write_text("#pragma once\n")
    binary = work / "check"
    subprocess.run(
        ["gcc", "-std=gnu11", "-DSTM32H7", "-I", str(work), "-I", str(upstream),
         str(upstream / "io/asyncfatfs/asyncfatfs.c"),
         str(upstream / "io/asyncfatfs/fat_standard.c"),
         str(upstream / "common/string_light.c"), str(test), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True, timeout=20)
print("SD filesystem: FAT32 without MBR, FAT32/FAT16 in MBR, bounded probing, and log write/remount/read: OK")
