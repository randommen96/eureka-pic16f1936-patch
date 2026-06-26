#!/usr/bin/env python3
"""
Firmware identity checker for PIC16F1936 (Eureka Mignon).

Computes a canonical SHA-256 hash over the *invariant* portions of a firmware
dump — the parts that are the same for every device running the same firmware
revision.  Per-device EEPROM data (timer values, shot counters, contrast, etc.)
is deliberately excluded so two dumps from different boards still match.

Usage:
    python3 checkhash.py [hexfile.hex]

If no file is given it looks for PIC16F1936-fresh.hex in the current directory.

What is hashed (invariant across devices):
  • Program memory          — 0x0000–0x1FFF  words  (the firmware code)
  • User ID words           — 0x8000–0x8003  words  (device / revision ID)
  • Configuration words     — 0x8007–0x8008  words  (oscillator, BOR, WDT, …)

What is NOT hashed (varies per device):
  • EEPROM data             — 0xF000–0xF07F  words  (timers, counters, contrast,
                                                      last mode, lock, …)

Known-good hashes for the firmware revision this fix was developed against:

  Original (unpatched) firmware:
    084e6b23299715aab351da67656764a9c444baf077de3fbcdfeab52fd19cce6c

  Patched firmware (after applying patch.py):
    b1cb19c8cce6cd6675b06d61a1f1ee4f82d8dda0ea3f4b3ce48ed7e2777b6ddf

If your dump matches "original", you can apply the patch.  If it matches
"patched", the fix is already applied.  If it matches neither, your firmware
is a different revision — the safety checks in patch.py will catch this too.
"""

import hashlib
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Known-good canonical hashes (program memory + user IDs + config, no EEPROM)
# ---------------------------------------------------------------------------
KNOWN = {
    "bd6fe765f15b8a3886c399f747f3dadc9aab19b4e0cb0c387c2c9a26c4cd1984": {
        "label": "Original (unpatched) firmware",
        "action": "Safe to apply the patch: gpasm -p p16f1936 validator.asm -o validator.hex && python3 patch.py",
    },
    "4313ac5da0a8937f4f0c5560e8c9e23c0e030bc9a6b8b7ee54ee17f934ee0158": {
        "label": "Patched firmware",
        "action": "Already patched — no further action needed.",
    },
}

# EEPROM byte-address range to exclude (extended-linear-address 1)
EEPROM_LO = 0x01E000
EEPROM_HI = 0x01EFFF


def canonical_hash(path: str) -> str:
    """Return SHA-256 hex digest of the invariant portions of *path*.

    Hashes firmware *content* (word values), not hex-record layout.
    This makes the hash independent of how the assembler splits hex
    records — two hex files with identical firmware content will
    always produce the same hash regardless of whether they came
    from gpasm, MPLAB X, or any other tool.

    Excludes EEPROM (word addresses 0xF000–0xF0FF) which contains
    per-device settings (timer values, counters, contrast, etc.).
    """
    # Pass 1: collect all word values by word address
    words: dict[int, int] = {}
    ext = 0
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line.startswith(":"):
                continue
            bc = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            rt = int(line[7:9], 16)
            data_hex = line[9:9 + bc * 2]

            if rt == 4:                       # extended linear address
                ext = int(data_hex, 16)
                continue
            if rt == 1:                       # EOF
                continue
            if rt != 0:                       # skip non-data records
                continue

            data = bytes.fromhex(data_hex)
            real = (ext << 16) | addr         # flat byte address

            # Decode 16-bit little-endian words from this record
            for i in range(0, len(data), 2):
                byte_addr = real + i
                if EEPROM_LO <= byte_addr <= EEPROM_HI:
                    continue
                if i + 1 < len(data):
                    word_val = data[i] | (data[i + 1] << 8)
                    word_addr = byte_addr // 2
                    words[word_addr] = word_val

    # Pass 2: hash word values in address order (record-layout-independent)
    h = hashlib.sha256()
    for wa in sorted(words):
        h.update(wa.to_bytes(2, "big"))
        h.update(words[wa].to_bytes(2, "little"))
    return h.hexdigest()


def main() -> int:
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = "PIC16F1936-fresh.hex"

    if not Path(path).exists():
        print(f"ERROR: file not found: {path}")
        return 1

    digest = canonical_hash(path)
    info = KNOWN.get(digest)

    print(f"File:  {path}")
    print(f"Hash:  {digest}")
    print()

    if info:
        print(f"✓  Match: {info['label']}")
        print(f"   {info['action']}")
    else:
        print("✗  UNKNOWN — does not match the expected original or patched firmware.")
        print()
        print("   Possible reasons:")
        print("   1. Your firmware is a different revision than this fix targets.")
        print("   2. The hex file was hand-edited outside of patch.py.")
        print("   3. The file is corrupted or from a different device.")
        print()
        print("   Do NOT force the patch — patch.py has its own safety checks and")
        print("   will refuse to run on an unexpected firmware revision anyway.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
