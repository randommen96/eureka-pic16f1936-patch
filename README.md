# Eureka Mignon timer-corruption fix (PIC16F1936)

A fix for the well-known Eureka Mignon bug where adjusting the grind timer and then
powering off with the hard switch can save a corrupted, very high timer value — after
which it can't be adjusted back up.

> **Stuck right now and can't flash?** If the grind time shows a very high / wrong number and
> **+** won't increase it, that's this bug. **Hold the minus (−) button** until the value stops
> going down — that's the bottom (0.2 s); from the worst case it takes ~23 minutes of continuous
> holding. Then dial it back up with **+**. No tools needed. This patch makes the fix happen
> automatically on power-up so you don't have to, but the manual hold always works as a fallback.

This repository contains **only original work**: a small validation routine and a patcher.
It does **not** contain Eureka's firmware. To use it you supply a dump read from your own
chip (see below).

## Why the bug happens

### One timer value, stored in two bytes

Each grind time is **one number split across two bytes**, and that's the heart of the bug.

A single byte only holds 0–255, but the grind time (in tenths of a second) goes up to 500. So each
timer uses **two** bytes read together as one 16-bit number — like a two-digit odometer where each
digit counts 0–255 instead of 0–9:

- **low byte** = the "ones" (0–255)
- **high byte** = how many whole 256s on top

```
value = high × 256 + low
```

The **low byte comes first** (lower address) — the "little-endian" convention:

```
EEPROM address:   0       1         2       3
                [low]   [high]    [low]   [high]
                 3C      00        6E      00
                └── single-shot ┘  └── double-shot ┘
                   60 = 6.0 s         110 = 11.0 s
```

| Bytes (low, high) | Calculation | Value | Time |
|-------------------|-------------|-------|------|
| `3C`, `00` | 0×256 + 60 | 60 | 6.0 s (factory single) |
| `6E`, `00` | 0×256 + 110 | 110 | 11.0 s (factory double) |
| `2C`, `01` | 1×256 + 44 | 300 | 30.0 s (single max) |
| `FF`, `FF` | 255×256 + 255 | 65535 | the corrupt "stuck high" state |

Valid ranges: single dose bytes 0–1 = 2–300 (0.2–30.0 s); double dose bytes 2–3 = 2–500
(0.2–50.0 s).

### The failure

- Saving to EEPROM is intentionally **delayed** (a debounce, to protect the limited EEPROM write
  cycles) and then writes the two bytes **one at a time** (not at the same instant).
- If power is cut between writing the low byte and the high byte, you get a fresh low byte but a
  **stale/garbage high byte** — and because the high byte is multiplied by 256, even a small wrong
  value there throws the number into the thousands (worst case 65535). That's how a normal ~110
  becomes tens of thousands.
- The firmware's boot path loads EEPROM back into RAM **without validating it**, and the minus
  button only refuses to go below 2 — so a huge value decrements by 1 per press, hence the
  ~23-minute hold to recover.

**The key asymmetry:** the original firmware protects values *going in* (the adjust handlers clamp
to range, and EEPROM writes use the proper unlock sequence so a write can't fire by accident) but
has **no protection for a value that is already corrupt** — nothing checks a value coming back out
of EEPROM at boot. That missing read-side check is the entire gap this fix closes.

## What the fix does

`validator.asm` is a tiny routine injected into unused (blank) flash. It is called once at
boot, right after the firmware loads the settings from EEPROM. It checks both timer values
and, if either is out of range, resets that one to **3 (0.3 s)**.

Why 3 specifically: the minus button can only take a value down to **2** (the firmware's built-in
floor), so a stored **3** is one step above anything a person can set by hand — a recognizable
"the firmware auto-recovered this" fingerprint. It's also harmlessly short if a grind goes
unnoticed at that setting.

The existing delayed-save (write-cycle protection) is left untouched, so the fix adds no
extra EEPROM wear.

### Footprint

- Injects a ~61-word routine into the firmware's free flash gap (words 0x1855–0x19AB).
- Re-points two words at the boot hook (0x131A/0x131B) to call it; control flow is otherwise
  unchanged.
- Config words, User IDs, and EEPROM contents are left byte-identical.

## How to use it

You need [`gputils`](https://gputils.sourceforge.io/) (`gpasm`, `gpdasm`) and Python 3, plus
a PIC programmer to read/write the chip.

Versions this was developed and verified with:

| Tool | Version |
|------|---------|
| OS | Debian 13.5 (WSL2) |
| gputils (`gpasm`, `gpdasm`) | 1.5.2 #1325 (Jan 7 2025) |
| Python | 3.13.5 |
| Programmer | PICkit 3 |
| MPLAB IPE | from MPLAB X IDE 6.20 — the last X IDE release supporting the PICkit 3 ([free archive download](https://www.microchip.com/en-us/tools-resources/archives/mplab-ecosystem)) |

Other recent gputils/Python versions should work; these are just what was tested.

### MPLAB IPE setup (first use)

1. Set the **Device** to `PIC16F1936`.
2. Under **Tool**, select your PICkit (3 or later).
3. Go to **Settings** → enable **Advanced Mode** (default password is `microchip`).
4. Under **Production**, enable **Allow Export Hex**.
5. Under **Power**, enable **Power target circuit board from PICkit** (5 V).

### Patch steps

1. **Read your own chip** with MPLAB IPE (Connect → Read → File → Export → Hex) and save the dump as
   `PIC16F1936-fresh.hex` next to these files. (This fix was developed against a specific
   firmware revision — see *Compatibility* below.)
2. **Assemble the validator:**
   ```
   gpasm -p p16f1936 validator.asm -o validator.hex
   ```
3. **Apply the patch:**
   ```
   python3 patch.py
   ```
   This writes `PIC16F1936-patched.hex`. `patch.py` refuses to run unless the target flash
   gap is blank and the two hook words match the expected originals, so it will stop rather
   than corrupt an unexpected firmware.
4. **Flash** `PIC16F1936-patched.hex` to your chip with MPLAB IPE (load the file → **Program**).

## Check your firmware revision first

Before applying the patch, verify your dump matches the expected firmware revision:

```
python3 checkhash.py PIC16F1936-fresh.hex
```

This computes a canonical hash over the *invariant* portions of the firmware
(program memory, config words, user IDs) — deliberately excluding per-device
EEPROM data (timer values, counters, contrast, etc.). Two dumps from different
boards running the same firmware revision will produce the **same hash**, even
though their EEPROM contents differ.

If the output says **"Original (unpatched) firmware"** you can proceed to patch.
If it says **"Patched firmware"** the fix is already applied. If it says
**"UNKNOWN"**, your firmware is a different revision — `patch.py` has its own
safety checks and will refuse to run anyway; do not force it.

### Verify before flashing (recommended)

```
gpdasm -p p16f1936 -i PIC16F1936-patched.hex | sed -n '/^1855:/,/^1891:/p'   # validator present
gpdasm -p p16f1936 -i PIC16F1936-patched.hex | grep -E '^131[ab]:'            # hook present
```

### Test the fix end-to-end (no PIC knowledge needed)

You can plant a corrupt value on purpose and watch the fix clean it up. Do this on a chip that
already has the patched firmware:

1. In MPLAB IPE, **Connect** to the chip, then open the **EE Data Memory** view.
2. The single-shot grind time lives in EEPROM at **address 0 and address 1**. Set both cells to
   **`FF`** (this is the "stuck high" corrupt state, 65535). To also test double-shot, set
   **address 2 and address 3** to `FF` as well.
3. Program **EEPROM only** (leave the firmware as-is), then **power-cycle** the grinder.
4. **Expected:** the single-shot time comes up as **0.3 s** and adjusts normally with +/-. (Double
   shot too, if you corrupted it.) Without the fix it would instead be stuck high, needing a
   ~23-minute hold on the minus button to recover.

Note: in the IPE EEPROM panel you set raw bytes (`address 0 = FF`, `address 1 = FF`). If you ever
edit a **.hex file** by hand instead, the same thing looks like `FF 00 FF 00`, because the file
stores each EEPROM byte as a padded 16-bit word — the IPE panel hides that, which is why editing
there is easier.

## Compatibility

The hook address (0x131A), the free-flash location (0x1855), and the EEPROM layout were
determined from one specific Eureka Mignon firmware revision. `patch.py` validates these
before patching. If your dump is a different revision, the safety checks will stop the
patch — open an issue / re-trace the addresses rather than forcing it.

## Files

| File | What it is |
|------|------------|
| `validator.asm` | Source of the timer-validation routine (original work). |
| `patch.py` | Injects the validator + hook into your own dump (original work). |
| `checkhash.py` | Computes a canonical hash so you can confirm your dump matches the expected firmware revision (original work). |
| `README.md` | This file. |

## Sources

The fix was developed independently from a firmware dump. These write-ups provided useful
cross-reference and are credited here:

- EEPROM content / memory map —
  <https://denshaotoko.github.io/blog/2025/03/23/eureka-eeprom-content.html>
- Touchscreen repair (PICkit 3 / MPLAB IPE read & write, ICSP header) —
  <https://denshaotoko.github.io/blog/2024/10/31/eureka-touchscreen-repair.html>
- Toolless repair (the ~23-minute minus-hold workaround) —
  <https://denshaotoko.github.io/blog/2025/09/06/eureka-touchscreen-toolless-repair.html>
- Display problem blog —
  <https://kaffeemacher.de/en/blogs/kaffeewissen/eureka-mignon-display-problem>

## License

The code in this repository (`validator.asm`, `patch.py`, `checkhash.py`, and this README)
is original work. See the `LICENSE` file for terms. It does **not** include any firmware
from the device — each user supplies their own dump read from hardware they own.

Provided as-is, no warranty; flashing firmware can brick a device — proceed at your own risk.
