; Timer-value validator for Eureka Mignon PIC16F1936 firmware patch.
; Placed in the free flash gap at word 0x1855.
; Called from the boot path immediately after the EEPROM->RAM shadow load,
; with the call site re-encoded to reach here (see patch script).
;
; Operates on bank-0 GPRs:
;   single-dose timer = 0x4E (low) / 0x4F (high), valid 2..300  (0x012C)
;   double-dose timer = 0x50 (low) / 0x51 (high), valid 2..500  (0x01F4)
; Any out-of-range pair is reset to 3 (0.3 s).
;
; On entry PCLATH/BSR are arbitrary (we set BSR=0 ourselves).
; On exit we set PCLATH = 0x19 so the caller's following `call 0x01ac`
; (which expects page 0x19) executes correctly, then RETURN.

        list    p=16f1936
        radix   hex
#include <p16f1936.inc>

; ---- file register equates (bank 0) ----
S_LO    equ 0x4E
S_HI    equ 0x4F
D_LO    equ 0x50
D_HI    equ 0x51

        org 0x1855

Validate:
        movlb   0x00            ; bank 0 for direct GPR access

; ---------- single dose: valid range 2..300 (0x012C) ----------
        ; check value > 300  ->  test (300 - value) borrow
        movf    S_HI, W         ; W = hi
        sublw   0x01            ; W = 0x01 - hi ; borrow(C=0) if hi>1
        btfss   STATUS, C       ; C=0 means hi>1 -> definitely >300
        goto    S_bad
        movf    S_HI, W
        sublw   0x01            ; redo to set Z for hi==1 path
        btfss   STATUS, Z       ; hi==1 ?
        goto    S_himid         ; hi==0 (since not >1 and not ==1)
        ; hi==1: compare low against 0x2C  (300 = 0x012C)
        movlw   0x2C
        subwf   S_LO, W         ; W = lo - 0x2C ; C=1 if lo>=0x2C
        btfsc   STATUS, C
        ; if lo>=0x2C and lo!=0x2C -> >300; lo==0x2C is exactly 300 (ok)
        goto    S_hi1chk
        goto    S_lowchk        ; lo<0x2C with hi==1 -> <=299 ok, go check low bound
S_hi1chk:
        ; lo>=0x2C: ok only if lo==0x2C exactly
        movlw   0x2C
        subwf   S_LO, W
        btfss   STATUS, Z
        goto    S_bad           ; lo>0x2C with hi==1 -> >300
        goto    S_lowchk        ; exactly 300 -> in range
S_himid:
        ; hi==0 -> value 0..255, always <=300, fall through to low-bound check
S_lowchk:
        ; check value < 2 : only possible when hi==0
        movf    S_HI, W
        btfss   STATUS, Z       ; hi==0 ?
        goto    S_ok            ; hi>=1 -> >=256 -> >=2, in range
        movlw   0x02
        subwf   S_LO, W         ; C=1 if lo>=2
        btfss   STATUS, C
        goto    S_bad           ; lo<2 -> invalid
        goto    S_ok
S_bad:
        movlw   0x03
        movwf   S_LO
        clrf    S_HI
S_ok:

; ---------- double dose: valid range 2..500 (0x01F4) ----------
        movf    D_HI, W
        sublw   0x01            ; C=0 if hi>1
        btfss   STATUS, C
        goto    D_bad
        movf    D_HI, W
        sublw   0x01
        btfss   STATUS, Z       ; hi==1 ?
        goto    D_himid         ; hi==0
        ; hi==1: compare low against 0xF4 (500 = 0x01F4)
        movlw   0xF4
        subwf   D_LO, W
        btfsc   STATUS, C
        goto    D_hi1chk
        goto    D_lowchk
D_hi1chk:
        movlw   0xF4
        subwf   D_LO, W
        btfss   STATUS, Z
        goto    D_bad           ; lo>0xF4 with hi==1 -> >500
        goto    D_lowchk
D_himid:
D_lowchk:
        movf    D_HI, W
        btfss   STATUS, Z       ; hi==0 ?
        goto    D_ok
        movlw   0x02
        subwf   D_LO, W
        btfss   STATUS, C
        goto    D_bad
        goto    D_ok
D_bad:
        movlw   0x03
        movwf   D_LO
        clrf    D_HI
D_ok:

        movlp   0x19            ; restore caller's expected code page
        return

        end
