; Build tags: a line ending in ";@2p" is kept only for 2-bitplane targets (cwii), ";@1p" only for
; 1-bitplane targets (cw). The plane loops step R12 = 0,4 (and select the plane through 0F037H) on cwii;
; on cw the same loop runs once and never touches 0F037H.
; ---- Wiz runtime. Convention: args ER0,ER2,ER4 ; result ER0 (ER2 = remainder for div).
; Routines may clobber ER2-ER14. Leaf routines return with RT; the few that BL to another
; routine (__buffered, __key_hit) do PUSH LR ... POP PC like compiled functions.
;
; Runtime RAM (above the variable area 0x9000-0xDFFF, below the stack that grows down from 0xF000):
;   0xE000-0xE7FF  back buffer (same layout as LCD VRAM: y*32 + x/8, one plane, black/white)
;   0xE800         draw mode: 0 = draw straight to the LCD, 1 = draw to back buffer (see buffered/flip)
;   0xE808-0xE80F  key_hit edge-detect bitmap (1 bit per scan index)

; ER0 * ER2 -> ER0 (low 16 bits)
__mul16:
    MOV ER4, ER0
    MOV ER0, #0
    MOV R6, #16
__mul16_l:
    TB R2.0
    BEQ __mul16_s
    ADD ER0, ER4
__mul16_s:
    ADD ER4, ER4
    SRLC R2, #1
    SRL R3, #1
    ADD R6, #-1
    BNE __mul16_l
    RT

; signed ER0 / ER2 -> ER0 quotient (trunc to zero), ER2 remainder (sign of dividend)
__div16:
    MOV R6, R2
    OR R6, R3
    BNE __div16_ok
    MOV ER0, #0
    MOV ER2, #0
    RT
__div16_ok:
    MOV R7, #0
    TB R1.7
    BEQ __div16_a
    MOV ER4, #0
    SUB R4, R0
    SUBC R5, R1
    MOV ER0, ER4
    MOV R7, #3
__div16_a:
    TB R3.7
    BEQ __div16_b
    MOV ER4, #0
    SUB R4, R2
    SUBC R5, R3
    MOV ER2, ER4
    XOR R7, #1
__div16_b:
    MOV ER4, #0
    MOV R6, #16
__div16_l:
    ADD ER0, ER0
    ADDC R4, R4
    ADDC R5, R5
    CMP R4, R2
    CMPC R5, R3
    BLT __div16_n
    SUB R4, R2
    SUBC R5, R3
    OR R0, #1
__div16_n:
    ADD R6, #-1
    BNE __div16_l
    MOV ER2, ER4
    TB R7.0
    BEQ __div16_q
    MOV ER4, #0
    SUB R4, R0
    SUBC R5, R1
    MOV ER0, ER4
__div16_q:
    TB R7.1
    BEQ __div16_r
    MOV ER4, #0
    SUB R4, R2
    SUBC R5, R3
    MOV ER2, ER4
__div16_r:
    RT

; ER0 << R2
__shl16:
    CMP R2, #0
    BEQ __shl16_e
__shl16_l:
    ADD ER0, ER0
    ADD R2, #-1
    BNE __shl16_l
__shl16_e:
    RT

; ER0 >> R2 (arithmetic)
__sra16:
    CMP R2, #0
    BEQ __sra16_e
__sra16_l:
    SRLC R0, #1
    SRA R1, #1
    ADD R2, #-1
    BNE __sra16_l
__sra16_e:
    RT

; pixel(x=ER0, y=ER2, c=R4) : c=0 clears, nonzero sets. Off-screen coordinates are ignored.
; mode 0: both LCD bitplanes (black).  mode 1: the back buffer at 0xE000.
__pixel:
    CMP R1, #0
    BNE __pixel_x
    CMP R0, #0C0H
    BGE __pixel_x
    CMP R3, #0
    BNE __pixel_x
    CMP R2, #_ROWS
    BGE __pixel_x
    MOV R9, R4
    MOV R10, #32
    MOV R6, R2
    MUL ER6, R10
    MOV R10, R0
    SRL R10, #3
    MOV R11, #0
    ADD ER6, ER10
    ADD ER6, #32 ;@off
    MOV R8, #80H
    MOV R10, R0
    AND R10, #7
    SRL R8, R10
    MOV R11, R8
    XOR R11, #0FFH
    L R10, 0E800H
    CMP R10, #0
    BNE __pixel_b
    ADD R7, #0F8H
    MOV R12, #0
__pixel_p:
    ST R12, 0F037H ;@2p
    L R10, [ER6]
    CMP R9, #0
    BEQ __pixel_c
    OR R10, R8
    BAL __pixel_w
__pixel_c:
    AND R10, R11
__pixel_w:
    ST R10, [ER6]
    ADD R12, #4
    CMP R12, #8 ;@2p
    CMP R12, #4 ;@1p
    BNE __pixel_p
    RT
__pixel_b:
    ADD R7, #0E0H
    L R10, [ER6]
    CMP R9, #0
    BEQ __pixel_bc
    OR R10, R8
    BAL __pixel_bw
__pixel_bc:
    AND R10, R11
__pixel_bw:
    ST R10, [ER6]
__pixel_x:
    RT

; clear the LCD (mode 0, both bitplanes) or the back buffer (mode 1)
__clear:
    L R10, 0E800H
    CMP R10, #0
    BNE __clear_b
    MOV R12, #0
__clear_p:
    ST R12, 0F037H ;@2p
    MOV R6, #0
    MOV R7, #0F8H
    MOV R8, #0
    MOV R9, #4
    MOV ER10, #0
__clear_l:
    ST ER10, [ER6]
    ADD ER6, #2
    ADD ER8, #-1
    BNE __clear_l
    ADD R12, #4
    CMP R12, #8 ;@2p
    CMP R12, #4 ;@1p
    BNE __clear_p
    RT
__clear_b:
    MOV R6, #0
    MOV R7, #0E0H
    MOV R8, #0
    MOV R9, #4
    MOV ER10, #0
__clear_bl:
    ST ER10, [ER6]
    ADD ER6, #2
    ADD ER8, #-1
    BNE __clear_bl
    RT

; buffered(on): on != 0 -> draw into the back buffer (cleared now); on == 0 -> draw straight to the LCD
__buffered:
    ST R0, 0E800H
    CMP R0, #0
    BEQ __buffered_e
    PUSH LR
    BL __clear
    POP PC
__buffered_e:
    RT

; flip(): copy the back buffer to both LCD bitplanes (shows the finished frame)
__flip:
    MOV R12, #0
__flip_p:
    ST R12, 0F037H ;@2p
    MOV R6, #0
    MOV R7, #0E0H
    MOV R10, #0
    MOV R11, #0F8H
    MOV R8, #0
    MOV R9, #4
__flip_l:
    L ER4, [ER6]
    ST ER4, [ER10]
    ADD ER6, #2
    ADD ER10, #2
    ADD ER8, #-1
    BNE __flip_l
    ADD R12, #4
    CMP R12, #8 ;@2p
    CMP R12, #4 ;@1p
    BNE __flip_p
    RT

; runtime state init (called once at entry, before top-level code)
__rt_init:
    MOV R0, #0
    ST R0, 0E800H
    ST R0, 0E808H
    ST R0, 0E809H
    ST R0, 0E80AH
    ST R0, 0E80BH
    ST R0, 0E80CH
    ST R0, 0E80DH
    ST R0, 0E80EH
    ST R0, 0E80FH
    RT

; key_down(k=ER0) -> ER0 = 1 while scan index k is held, else 0
__key_down:
    AND R0, #3FH
    MOV R2, R0
    SRL R2, #3
    MOV R3, #80H
    SRL R3, R2
    AND R0, #7
    MOV R4, #80H
    SRL R4, R0
    ST R3, 0F046H
    L R5, 0F040H
    AND R5, R4
    BNE __key_down_n
    MOV ER0, #1
    RT
__key_down_n:
    MOV ER0, #0
    RT

; key_hit(k=ER0) -> ER0 = 1 only on the call where k went from released to held
; (call it every loop iteration for every key you care about)
__key_hit:
    PUSH LR
    PUSH ER0
    BL __key_down
    POP ER2
    AND R2, #3FH
    MOV R4, R2
    SRL R4, #3
    MOV R5, #0
    MOV R6, #8
    MOV R7, #0E8H
    ADD ER6, ER4
    AND R2, #7
    MOV R8, #80H
    SRL R8, R2
    L R9, [ER6]
    CMP R0, #0
    BEQ __key_hit_up
    MOV R10, R9
    AND R10, R8
    BNE __key_hit_no
    OR R9, R8
    ST R9, [ER6]
    MOV ER0, #1
    POP PC
__key_hit_up:
    MOV R10, R8
    XOR R10, #0FFH
    AND R9, R10
    ST R9, [ER6]
__key_hit_no:
    MOV ER0, #0
    POP PC

; key() -> ER0 = scan index 0..63 (8*KO bit + KI bit, MSB first) or -1
__key:
    MOV R0, #0
    MOV R1, #0
    MOV R2, #80H
__key_x:
    ST R2, 0F046H
    MOV R3, #80H
__key_y:
    L R4, 0F040H
    AND R4, R3
    BEQ __key_f
    ADD R0, #1
    SRL R3, #1
    CMP R3, #0
    BNE __key_y
    SRL R2, #1
    CMP R2, #0
    BNE __key_x
    MOV ER0, #-1
__key_f:
    RT

; delay(n): n * ~ (busy loop) -- UNCALIBRATED, units arbitrary until measured on hardware
__delay:
    MOV ER4, ER0
__delay_o:
    MOV R6, #0
    MOV R7, #1
__delay_i:
    ADD ER6, #-1
    BNE __delay_i
    ADD ER4, #-1
    BNE __delay_o
    RT

; peek(addr=ER0) -> ER0 = unsigned byte at addr (RAM, SFR or ROM)
__peek:
    MOV ER2, ER0
    L R0, [ER2]
    MOV R1, #0
    RT

; _rpeek(addr=ER0) -> ER0: like peek, but in data segment _ROMSEG (ROM tables/strings of a program that lives in segment 3)
__rpeek:  ;@seg
    MOV ER2, ER0  ;@seg
    DSRI _ROMSEG  ;@seg
    L R0, [ER2]  ;@seg
    MOV R1, #0  ;@seg
    RT  ;@seg

; poke(addr=ER0, v=ER2): store the low byte of v at addr
__poke:
    ST R2, [ER0]
    RT

; _hspan(x0=ER0, x1=ER2, y=ER4, c=R6): fill pixels x0..x1-1 on row y. Caller guarantees 0<=x0<x1<=192, 0<=y<_ROWS.
; c=0 clears, else sets. Works on the LCD (both bitplanes) or the back buffer, like pixel().
__hspan:
    MOV R8, R4
    MOV R9, #0
    MOV R10, #32
    MUL ER8, R10
    MOV R11, R0
    SRL R11, #3
    MOV R10, R0
    AND R10, #7
    MOV R7, #0FFH
    SRL R7, R10
    MOV R12, R2
    ADD R12, #-1
    MOV R13, R12
    SRL R13, #3
    AND R12, #7
    MOV R3, #7
    SUB R3, R12
    MOV R5, #0FFH
    SLL R5, R3
    SUB R13, R11
    MOV R10, R11
    MOV R11, #0
    ADD ER8, ER10
    ADD ER8, #32 ;@off
    L R3, 0E800H
    CMP R3, #0
    BNE __hs_b
    ADD R9, #0F8H
    BAL __hs_go
__hs_b:
    ADD R9, #0E0H
__hs_go:
    MOV R12, #0
__hs_plane:
    L R3, 0E800H
    CMP R3, #0
    BNE __hs_ns
    ST R12, 0F037H ;@2p
__hs_ns:
    MOV ER10, ER8
    CMP R13, #0
    BNE __hs_multi
    MOV R3, R7
    AND R3, R5
    L R4, [ER10]
    CMP R6, #0
    BEQ __hs_s0
    OR R4, R3
    BAL __hs_s1
__hs_s0:
    XOR R3, #0FFH
    AND R4, R3
__hs_s1:
    ST R4, [ER10]
    BAL __hs_next
__hs_multi:
    L R4, [ER10]
    MOV R3, R7
    CMP R6, #0
    BEQ __hs_f0
    OR R4, R3
    BAL __hs_f1
__hs_f0:
    XOR R3, #0FFH
    AND R4, R3
__hs_f1:
    ST R4, [ER10]
    ADD ER10, #1
    MOV R3, R13
    ADD R3, #-1
    BEQ __hs_last
__hs_mid:
    MOV R4, #0
    CMP R6, #0
    BEQ __hs_m0
    MOV R4, #0FFH
__hs_m0:
    ST R4, [ER10]
    ADD ER10, #1
    ADD R3, #-1
    BNE __hs_mid
__hs_last:
    L R4, [ER10]
    MOV R3, R5
    CMP R6, #0
    BEQ __hs_l0
    OR R4, R3
    BAL __hs_l1
__hs_l0:
    XOR R3, #0FFH
    AND R4, R3
__hs_l1:
    ST R4, [ER10]
__hs_next:
    ADD R12, #4
    L R3, 0E800H
    CMP R3, #0
    BNE __hs_done
    CMP R12, #8 ;@2p
    CMP R12, #4 ;@1p
    BNE __hs_plane
__hs_done:
    RT
