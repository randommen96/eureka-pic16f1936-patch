#!/usr/bin/env python3
"""Patch PIC16F1936-fresh.hex -> PIC16F1936-patched.hex.

Adds a timer-value validator (from validator.hex, words 0x1855..) into the free
flash gap and hooks it into the boot path at word 0x131A/0x131B.
Only the gap words and the two hook words change; everything else (code, config,
User IDs, EEPROM) stays byte-identical. All modified Intel-HEX lines get a fresh
checksum.
"""
import sys

SRC   = "PIC16F1936-fresh.hex"
VALID = "validator.hex"
OUT   = "PIC16F1936-patched.hex"

HOOK = {0x131A: 0x3198,   # movlp 0x18
        0x131B: 0x2055}   # call  0x1855

GAP_LO, GAP_HI = 0x1855, 0x19AB   # inclusive validator-allowed region (free gap)


def read_words(path):
    """Return {word_addr: 14-bit value} for program-memory data records (ext addr 0)."""
    words = {}
    ext = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            bc = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            rt = int(line[7:9], 16)
            data = line[9:9 + bc * 2]
            if rt == 4:
                ext = int(data, 16)
                continue
            if rt != 0 or ext != 0:
                continue
            for i in range(0, bc, 2):
                lo = int(data[i * 2:i * 2 + 2], 16)
                hi = int(data[i * 2 + 2:i * 2 + 4], 16)
                words[(addr + i) // 2] = lo | (hi << 8)
    return words


def hexline_checksum(byte_list):
    return ((~sum(byte_list) + 1) & 0xFF)


def patch():
    # validator words to inject (only those inside the gap)
    vwords = read_words(VALID)
    inject = {a: v for a, v in vwords.items() if GAP_LO <= a <= GAP_HI}
    if not inject:
        sys.exit("ERROR: no validator words found in gap")
    vmax = max(inject)
    if vmax > GAP_HI:
        sys.exit(f"ERROR: validator overflows gap (ends 0x{vmax:04X} > 0x{GAP_HI:04X})")
    print(f"validator words: 0x{min(inject):04X}..0x{vmax:04X} ({len(inject)} words)")

    # sanity: gap target words in source must currently be 0x3FFF (blank)
    src_words = read_words(SRC)
    for a in inject:
        if src_words.get(a, 0x3FFF) != 0x3FFF:
            sys.exit(f"ERROR: gap word 0x{a:04X} not blank (=0x{src_words[a]:04X})")
    # sanity: hook words match expected originals
    expect_orig = {0x131A: 0x3193, 0x131B: 0x3199}
    for a, ev in expect_orig.items():
        if src_words.get(a) != ev:
            sys.exit(f"ERROR: hook word 0x{a:04X} = 0x{src_words.get(a):04X}, expected 0x{ev:04X}")

    # word_addr -> new 14-bit value
    newvals = dict(inject)
    newvals.update(HOOK)

    ext = 0
    changed = 0
    out_lines = []
    with open(SRC) as f:
        for line in f:
            raw = line.rstrip("\n")
            s = raw.strip()
            if not s.startswith(":"):
                out_lines.append(raw)
                continue
            bc = int(s[1:3], 16)
            addr = int(s[3:7], 16)
            rt = int(s[7:9], 16)
            if rt == 4:
                ext = int(s[9:9 + 4], 16)
                out_lines.append(raw)
                continue
            if rt != 0 or ext != 0:
                out_lines.append(raw)
                continue
            data = bytearray(int(s[9 + i * 2:9 + i * 2 + 2], 16) for i in range(bc))
            touched = False
            for i in range(0, bc, 2):
                waddr = (addr + i) // 2
                if waddr in newvals:
                    v = newvals[waddr]
                    data[i] = v & 0xFF
                    data[i + 1] = (v >> 8) & 0xFF
                    touched = True
                    changed += 1
            if not touched:
                out_lines.append(raw)
                continue
            rec = [bc, (addr >> 8) & 0xFF, addr & 0xFF, 0] + list(data)
            cs = hexline_checksum(rec)
            newline = ":" + "".join(f"{b:02X}" for b in rec) + f"{cs:02X}"
            out_lines.append(newline)

    with open(OUT, "w") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"patched words written: {changed}")
    print(f"output: {OUT}")


if __name__ == "__main__":
    patch()
