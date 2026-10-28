; cwapp: a Wiz program that is patched INTO a fx-580VN X (ML620906, 256 KB) firmware ROM.
; It lives in the free flash at 3:0E40 (ROM offset 30E40h) and is entered from the firmware's own menu.
; Written from reading the ROM with a disassembler - NOT yet run on a real calculator.
;
; Hook: patch_menu.py overwrites the firmware instructions at 2:5E1E
;           CMP R8, 03 / BEQ 2:5E88            (inside set_mode, 2:5D82; R8 = mode id, from menu table 0x7FF8 +2)
;       with  B 3:0E40.  _TRAMP below handles our mode id 0E0h and otherwise replays the replaced instructions.

type(ML620906)
model large

_ROMSEG EQU 3

    ORG 30E40h

_TRAMP:
    cmp r8, #0E0h
    bne _t_old
    b _APP
_t_old:
    cmp r8, #3
    bne _t_back
    b 25E88h
_t_back:
    b 25E22h

_APP:
    di
    mov r0, #0
    mov r1, #0F0h
    mov sp, er0
    mov r0, #0
    st r0, 0F041H
    mov r0, #80h
    mov r1, #0FFh
    st er0, 0F044H
    mov er0, #0
    st r0, 0F042H
    st er0, 0F046H
    b _main

; exit(): leave the program, restart the firmware (reset handler at 0:A1CE) which shows its menu again
__exit:
    di
    mov r0, #0
    mov r1, #0F0h
    mov sp, er0
    ; reset key SFRs the firmware's reset handler expects at power-on state
    mov r0, #17h
    st r0, 0F028H        ; BLKCON0: re-enable peripheral clocks
    mov r0, #0
    st r0, 0F042H        ; KIMASKn = 0 (block key input to firmware)
    st er0, 0F046H       ; KOMASKn = 0
    b 0A1CEh
