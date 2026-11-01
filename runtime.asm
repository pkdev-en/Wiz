; Build tags: a line ending in ";@2p" is kept only for 2-bitplane targets (cwii), ";@1p" only for
; 1-bitplane targets (cw). The plane loops step R12 = 0,4 (and select the plane through 0F037H) on cwii;
; on cw the same loop runs once and never touches 0F037H.
; ---- Wiz runtime. Convention: args ER0,ER2,ER4 ; result ER0 (ER2 = remainder for div).
; Routines may clobber ER2-ER14. Leaf routines return with RT; the few that BL to another
; routine (__buffered, __key_hit) do PUSH LR ... POP PC like compiled functions.
;
; Runtime RAM (above the variable area, below the stack that grows down from 0xF000):
;   0xE000-0xE7FF  back buffer (same layout as LCD VRAM: y*32 + x/8, one plane, black/white)
;   0xE800         draw mode: 0 = draw straight to the LCD, 1 = draw to back buffer (see buffered/flip)
;   0xE808-0xE80F  key_hit edge-detect bitmap (1 bit per scan index)
;   0xE810-0xE817  __copy_rect scratch (x, y, w, h, x2, y2, col, row)
;   0xE818-0xE81B  heap bounds: __HEAP_LO / __HEAP_HI words (written by __rt_init)
;   0xE81C-0xE81D  RAM file system list head
; DYNAMIC HEAP: alloc() blocks and the RAM file system nodes live in EVERYTHING
; between the program's last variable (__HEAP_LO, an EQU wizc emits per build)
; and 0xE000 (__HEAP_HI). On cw that is ~3.5 KB for a typical program, on cwii
; up to ~20 KB. The allocator itself (first-fit + free + merge) is PRELUDE Wiz
; code in wizc.py; runtime only bootstraps the bounds and the first free block.

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
    PUSH LR
    MOV R0, #0
    ST R0, 0E800H
    ST R0, 0E805H
    ST R0, 0E808H
    ST R0, 0E809H
    ST R0, 0E80AH
    ST R0, 0E80BH
    ST R0, 0E80CH
    ST R0, 0E80DH
    ST R0, 0E80EH
    ST R0, 0E80FH
    ; clip window (0xE801-0xE804) = full screen 0..192 x 0..64, the same
    ; defaults as clip(): hline/vline/fillrect (PRELUDE) read it, and without
    ; this boot init every hline-based draw is clipped away (RAM garbage on
    ; hw, all-zero window in sim). Ported from the wiz7 line.
    ST R0, 0E801H
    ST R0, 0E803H
    MOV R0, #0C0H
    ST R0, 0E802H
    MOV R0, #040H
    ST R0, 0E804H
    ; ---- dynamic heap bootstrap ----
    ; 0xE818/0xE81A = __HEAP_LO/__HEAP_HI, 0xE81C = file list head. The EQUs come
    ; from wizc (LO = right after the last variable, HI = 0xE000); pure-asm builds
    ; (kernel) define their own. Seed ONE free block covering the whole heap:
    ; header bit 15 set = free, bits 0-14 = size incl. the 2-byte header.
    MOV R0, #0
    ST R0, 0E81CH          ; file-system list head lo
    ST R0, 0E81DH          ; file-system list head hi
    MOV R0, #(__HEAP_LO & 255)
    ST R0, 0E818H
    MOV R0, #((__HEAP_LO >> 8) & 255)
    ST R0, 0E819H
    MOV R0, #(__HEAP_HI & 255)
    ST R0, 0E81AH
    MOV R0, #((__HEAP_HI >> 8) & 255)
    ST R0, 0E81BH
    ; if the heap is smaller than one block (header + 2 data bytes), make the
    ; heap empty (lo := hi) so the PRELUDE alloc() walks nothing and fails fast
    MOV R2, #(__HEAP_LO & 255)
    MOV R3, #((__HEAP_LO >> 8) & 255)
    MOV R4, #(__HEAP_HI & 255)
    MOV R5, #((__HEAP_HI >> 8) & 255)
    ADD ER2, #4
    CMP ER2, ER4
    BGT __rti_nohp
    MOV R0, #((__HEAP_HI - __HEAP_LO) & 255)
    ST R0, __HEAP_LO
    MOV R0, #(((__HEAP_HI - __HEAP_LO) >> 8 & 127) | 128)
    ST R0, __HEAP_LO + 1
    BAL __rti_hpd
__rti_nohp:
    MOV R0, #(__HEAP_HI & 255)
    ST R0, 0E818H
    MOV R0, #((__HEAP_HI >> 8) & 255)
    ST R0, 0E819H
__rti_hpd:
    POP PC

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

; _hspan(x0=ER0, x1=ER2, y=ER4, c=R6): fill pixels x0..x1-1 on row y. Caller guarantees 0<=x0<x1<=192.
; y is clipped here like in __pixel(): 0<=y<_ROWS, else nothing is drawn (cw has 63 rows,
; cwii 64; a row past the screen plus the row offset would wrap 0xF800+64*32 to 0x0000).
; c=0 clears, else sets. Works on the LCD (both bitplanes) or the back buffer, like pixel().
__hspan:
    CMP R1, #0
    BNE __hs_r
    CMP R3, #0
    BNE __hs_r
    CMP R5, #0
    BNE __hs_r
    CMP R4, #_ROWS
    BGE __hs_r
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
__hs_r:
    RT

; =========================================================================
; NEW RUNTIME STUBS (added for Wiz feature set expansion)
; =========================================================================

; getpixel(x=ER0, y=ER2) -> ER0 = 1 if pixel lit (checks back buffer in buffered mode, else LCD plane 0)
__getpixel:
    CMP R1, #0
    BNE __getpixel_0
    CMP R0, #0C0H
    BGE __getpixel_0
    CMP R3, #0
    BNE __getpixel_0
    CMP R2, #_ROWS
    BGE __getpixel_0
    MOV R9, #32
    MOV R6, R2
    MUL ER6, R9
    MOV R10, R0
    SRL R10, #3
    MOV R11, #0
    ADD ER6, ER10
    ADD ER6, #32 ;@off
    MOV R8, #80H
    MOV R10, R0
    AND R10, #7
    SRL R8, R10
    L R3, 0E800H
    CMP R3, #0
    BNE __getpixel_buf
    ADD R7, #0F8H
    L R10, [ER6]
    AND R10, R8
    BEQ __getpixel_0
    MOV ER0, #1
    RT
__getpixel_buf:
    ADD R7, #0E0H
    L R10, [ER6]
    AND R10, R8
    BEQ __getpixel_0
    MOV ER0, #1
    RT
__getpixel_0:
    MOV ER0, #0
    RT

; ---- ticks()/delay_ms() via Timer0 (TM0), following libcw (u68/libcw) ----
; TM0D = 0xF020 (16-bit interval), TM0C = 0xF022 (16-bit counter),
; TM0CON = 0xF024 (CS bits) / 0xF025 (E bit); libcw arms it as 0x0101 and
; the timer then runs at ~8000 Hz -> 8 ticks per ms (TICKS_PER_MS = 8).
; FCON (0xF00A) bit 1 is cleared first, exactly like libcw __delay().
; The OLD code read 0xF00D ("HTBR") - no such register exists on the
; ML620906, so ticks()/delay_ms() froze forever on real hardware (the
; "clock opens but is dead" bug).
__tm0_start:
    PUSH LR
    L R0, 0F00AH            ; FCON: normalise clock select (libcw __delay)
    AND R0, #0FDH
    ST R0, 0F00AH
    MOV R0, #0FFH
    ST R0, 0F020H           ; TM0D = 0xFFFF
    ST R0, 0F021H
    MOV R0, #0
    ST R0, 0F022H           ; TM0C = 0
    ST R0, 0F023H
    MOV R0, #1
    ST R0, 0F024H           ; TM0CON = 0x01 (CS = 1)
    ST R0, 0F025H           ; TM0CON1 E = 1: run at ~8 kHz
    POP PC

; internal: ER0 = TM0C, stable 16-bit read (re-read the high byte)
__tm0_read:
    PUSH LR
__tm0_read_l:
    L R1, 0F023H
    L R0, 0F022H
    L R2, 0F023H
    CMP R1, R2
    BNE __tm0_read_l
    POP PC

; ticks() -> ER0 = TM0C (16-bit, ~8000/s; wraps ~8.19 s - elapsed() deltas
; of a few seconds stay correct through the wrap). The FIRST call of a run
; does a full __tm0_start (clear FCON bit 1, TM0D=FFFF, TM0C=0, TM0CON=0101)
; exactly like libcw __delay() - flag at 0xE805, zeroed by __rt_init. The old
; E-bit test skipped the arm when the OS left E=1 with a parked counter, so
; ticks() read one frozen value forever and every ticks()-paced loop (the
; waitkey() clock loop) hung on real hardware until a key was pressed.
; Later calls just read; a counter parked at 0xFFFF (one-shot stop) re-arms.
__ticks:
    PUSH LR
    L R0, 0E805H
    BNE __ticks_chk
    MOV R0, #1
    ST R0, 0E805H
    BL __tm0_start
    B __ticks_r
__ticks_chk:
    BL __tm0_read
    CMP R0, #0FFH
    BNE __ticks_r
    CMP R1, #0FFH
    BNE __ticks_r
    BL __tm0_start
__ticks_r:
    BL __tm0_read
    POP PC

; delay_ms(n=ER0): busy-wait ~n ms on TM0C. n <= 0 returns at once; larger
; n is split into 256 ms chunks (final chunk 0..255 ms), so every wait
; target stays <= 2048 ticks, below 0x8000 (signed compare) and - with the
; counter restarted at 0 per chunk - far from the 0xFFFF interval: no
; timer match, no interrupt side effects during the wait.
; The remaining ms live in ER6 across the chunk call - __delay_chunk
; clobbers ER0 (TM0C read result) and ER2, but never touches ER6-ER9.
; Before returning, TM0C is set back to start + n*8 (mod 2^16), so a
; ticks() span that crosses a delay_ms() still measures real elapsed time.
__delay_ms:
    PUSH LR
    CMP R1, #0
    BLTS __delay_ms_out      ; signed: negative n -> return at once
    MOV ER8, ER0             ; ER8 = original n (for the coherent exit)
    MOV R6, R0               ; ER6 = n (remaining ms)
    MOV R7, R1
    BL __tm0_read            ; ER0 = start (TM0C before the delay)
    PUSH ER0                 ; keep start on the stack
__delay_ms_full:
    CMP R7, #0
    BEQ __delay_ms_part
    MOV R2, #0
    MOV R3, #1              ; 256 ms chunk
    BL __delay_chunk
    ADD R7, #0FFH           ; n -= 256 (high byte only)
    B __delay_ms_full
__delay_ms_part:
    CMP R6, #0
    BEQ __delay_ms_fix
    MOV R2, R6              ; final partial chunk: 0..255 ms
    MOV R3, #0
    BL __delay_chunk
__delay_ms_fix:
    POP ER2                 ; ER2 = start
    MOV ER4, ER8            ; ER4 = original n
    ADD ER4, ER4            ; x2
    ADD ER4, ER4            ; x4
    ADD ER4, ER4            ; x8 -> n * 8 ticks
    ADD ER2, ER4            ; start + n*8 (mod 2^16)
    ST R2, 0F022H           ; TM0C = coherent value
    ST R3, 0F023H
__delay_ms_out:
    POP PC

; internal: busy-wait ER2 ms (0..256): restart TM0C at 0, poll until it
; advanced ER2*8 ticks.
__delay_chunk:
    PUSH LR
    BL __tm0_start
    MOV ER4, ER2
    ADD ER4, ER4            ; x2
    ADD ER4, ER4            ; x4
    ADD ER4, ER4            ; x8 -> ticks (8 ticks per ms)
__delay_chunk_w:
    BL __tm0_read
    CMP R0, R4
    CMPC R1, R5
    BLTS __delay_chunk_w    ; TM0C < target
    POP PC

; ---- RTC moved into wizc.py ----
; second()/minute()/hour()/day()/weekday()/month()/year(), set_time(),
; set_date(), rtc_enable()/rtc_disable()/rtc_reset() are now PRELUDE (Wiz
; source inside wizc.py, compiled in only when a program calls them), 1:1 with
; libcw's rtc_* functions: time BCD at 0xF0C0-0xF0C2, day 0xF0C3 / week
; 0xF0C4 / month 0xF0C5 / year 0xF0C6 (binary, year offset from 2026),
; enable 0xF0C7 - all peek/poke register access, no asm helpers needed.
; ticks()/delay_ms() stay native here: they drive Timer0 (TM0, see above).

; copy_rect(x=ER0, y=ER2, w=ER4, h=R6, x2=R8, y2=R10): copy a rectangle of pixels.
;   Pixel-by-pixel: reads the source bit from the VRAM/back buffer, then writes the destination bit
;   with __pixel, so clipping, the cw row offset and both bitplanes behave exactly like pixel().
;   All six args plus the loop counters live in RAM 0xE810-0xE817 because __pixel clobbers
;   ER2-ER14. x, y, w, h, x2, y2 are bytes (0..255). These 8 bytes are
;   copy_rect-private: the heap bounds/file head at 0xE818-0xE81D sit well above
;   them, and the heap itself lives BELOW 0xE000 (after the variables).
__copy_rect:
    PUSH LR
    CMP R1, #0
    BNE __copy_out
    CMP R3, #0
    BNE __copy_out
    CMP R9, #0
    BNE __copy_out
    CMP R11, #0
    BNE __copy_out
    ST R0, 0E810H      ; x
    ST R2, 0E811H      ; y
    ST R4, 0E812H      ; w
    ST R6, 0E813H      ; h
    ST R8, 0E814H      ; x2
    ST R10, 0E815H     ; y2
    MOV R0, #0
    ST R0, 0E817H      ; row = 0
__copy_row:
    MOV R0, #0
    ST R0, 0E816H      ; col = 0
__copy_col:
    ; --- source bit -> R10: ER6 = (srcy+row)*32 + (srcx+col)/8 (+row_off)
    L R6, 0E811H
    L R13, 0E817H
    ADD R6, R13
    MOV R14, #32
    MUL ER6, R14
    L R0, 0E810H
    L R12, 0E816H
    ADD R0, R12
    MOV R9, R0
    SRL R9, #3
    ADD R6, R9
    ADDC R7, #0
    ADD ER6, #32 ;@off
    MOV R14, #80H
    AND R0, #7
    SRL R14, R0        ; mask bit
    L R11, 0E800H      ; draw mode
    CMP R11, #0
    BNE __copy_srcb
    ADD R7, #0F8H
    BAL __copy_srcd
__copy_srcb:
    ADD R7, #0E0H
__copy_srcd:
    L R10, [ER6]
    AND R10, R14       ; R10 = source bit (mask value, or 0)
    ; --- destination bit: __pixel(x2+col, y2+row, c)
    MOV R4, R10
    L R0, 0E814H
    ADD R0, R12
    MOV R1, #0
    L R2, 0E815H
    L R13, 0E817H
    ADD R2, R13
    MOV R3, #0
    BL __pixel
    ; --- next column
    L R12, 0E816H
    ADD R12, #1
    ST R12, 0E816H
    L R4, 0E812H
    CMP R12, R4
    BNE __copy_col
    ; --- next row
    L R13, 0E817H
    ADD R13, #1
    ST R13, 0E817H
    L R5, 0E813H
    CMP R13, R5
    BNE __copy_row
    POP PC
__copy_out:
    POP PC

; invert_rect(x=ER0, y=ER2, w=ER4, h=R6): XOR every pixel in the rectangle.
;   Clips like pixel(). The write follows pixel(): LCD (both bitplanes on cwii) or back buffer,
;   plus the cw VRAM row offset. x, y, w, h are bytes (0..255).
__invert_rect:
    PUSH LR
    CMP R1, #0
    BNE __invert_out
    CMP R3, #0
    BNE __invert_out
    MOV R5, R6         ; h (low byte) survives in R5
    MOV R13, #0        ; row
__invert_row:
    MOV R12, #0        ; col
__invert_col:
    ; bounds: y+row < _ROWS, x+col < 192
    MOV R14, R2
    ADD R14, R13
    CMP R14, #_ROWS
    BGE __invert_next
    MOV R14, R0
    ADD R14, R12
    CMP R14, #0C0H
    BGE __invert_next
    ; ER6 = (y+row)*32 + (x+col)/8 (+row_off)
    MOV R6, R2
    ADD R6, R13
    MOV R14, #32
    MUL ER6, R14
    MOV R9, R0
    ADD R9, R12
    SRL R9, #3
    ADD R6, R9
    ADDC R7, #0
    ADD ER6, #32 ;@off
    ; mask bit in R8
    MOV R8, #80H
    MOV R9, R0
    ADD R9, R12
    AND R9, #7
    SRL R8, R9
    ; write: LCD plane loop (R11), or the back buffer
    L R10, 0E800H
    CMP R10, #0
    BNE __invert_buf
    ADD R7, #0F8H
    MOV R11, #0
__invert_p:
    ST R11, 0F037H ;@2p
    L R10, [ER6]
    XOR R10, R8
    ST R10, [ER6]
    ADD R11, #4
    CMP R11, #8 ;@2p
    CMP R11, #4 ;@1p
    BNE __invert_p
    BAL __invert_next
__invert_buf:
    ADD R7, #0E0H
    L R10, [ER6]
    XOR R10, R8
    ST R10, [ER6]
__invert_next:
    ADD R12, #1
    CMP R12, R4
    BNE __invert_col
    ADD R13, #1
    CMP R13, R5
    BNE __invert_row
    POP PC
__invert_out:
    POP PC

; clear_rect(x=ER0, y=ER2, w=ER4, h=R6): clear rectangle (set to 0)
;   One __hspan per row (so plane/buffer/row-offset handling comes from hspan). Clips x+w and
;   y+h to the screen. x, y, w, h are bytes (0..255).
__clear_rect:
    PUSH LR
    CMP R1, #0
    BNE __cr_out
    CMP R3, #0
    BNE __cr_out
    CMP R2, #_ROWS
    BGE __cr_out
    MOV R12, R2
    ADD R12, R6          ; y + h
    CMP R12, #_ROWS
    BLE __cr_hok
    MOV R6, #_ROWS
    SUB R6, R2           ; h = _ROWS - y
__cr_hok:
    MOV R12, R0
    ADD R12, R4          ; x + w
    CMP R12, #0C0H
    BLE __cr_wok
    MOV R4, #0C0H
    SUB R4, R0           ; w = 192 - x
__cr_wok:
    CMP R4, #0
    BLE __cr_out
    CMP R6, #0
    BLE __cr_out
    MOV R7, #0
    PUSH ER0             ; x
    PUSH ER2             ; y
    PUSH ER4             ; w
    PUSH ER6             ; h (word: R6 low, R7 = 0)
__clear_rect_row:
    POP ER6
    POP ER4
    POP ER2
    POP ER0
    MOV R12, R6
    OR R12, R7
    BEQ __clear_rect_done
    ; stash the next row's values
    MOV ER10, ER2
    ADD ER10, #1
    MOV ER12, ER6
    ADD ER12, #-1
    PUSH ER0
    PUSH ER10
    PUSH ER4
    PUSH ER12
    ; __hspan(x0=x, x1=x+w, y, c=0)
    MOV ER10, ER0
    ADD ER10, ER4        ; x1 = x + w
    MOV ER4, ER2         ; y
    MOV ER2, ER10        ; x1
    MOV R6, #0           ; c = 0
    BL __hspan
    BAL __clear_rect_row
__clear_rect_done:
    POP PC
__cr_out:
    POP PC


; ---- heap byte access (the allocator itself is PRELUDE Wiz code) ----
; The DYNAMIC heap lives between __HEAP_LO (after the program's variables) and
; 0xE000 - see the header at the top of this file and PRELUDE['alloc'] in
; wizc.py. alloc()/free()/f_save()/f_load()/f_exists()/f_remove() are Wiz
; functions; only these byte primitives stay native. The bounds and the file
; list head are bootstrapped by __rt_init at 0xE818-0xE81D, well above the
; __copy_rect scratch at 0xE810-0xE817 (the old layout let __copy_rect store
; x/y right over heap_ptr itself -> the next alloc() wrote its header into ROM
; and halted; caught by test_all.wz: copy_rect on screen 3, alloc on screen 6).

; _hpeek(addr=ER0) -> ER0: byte at addr (heap/RAM, unsigned)
__hpeek:
    MOV ER2, ER0
    L R0, [ER2]
    MOV R1, #0
    RT

; _hpoke(addr=ER0, v=ER2): write byte
__hpoke:
    ST R2, [ER0]
    RT

; ---- getc() -> scan index of next key press (waits), or -1 if AC
; (unused asm stub — getc() is a PRELUDE Wiz function calling wait_key())
__getc:
    RT

; ---- strlen(s=ER0) -> ER0: count bytes until null (RAM or ROM segment)
__strlen:
    MOV ER2, ER0
    MOV ER0, #0
__strlen_l:
    L R4, [ER2]
    CMP R4, #0
    BEQ __strlen_ret
    ADD ER2, #1
    ADD ER0, #1
    BAL __strlen_l
__strlen_ret:
    RT

; ---- strcmp(a=ER0, b=ER2) -> ER0: 0 if equal, nonzero otherwise
__strcmp:
    MOV ER4, ER0
    MOV ER6, ER2
__strcmp_l:
    L R0, [ER4]
    L R2, [ER6]
    CMP R0, R2
    BNE __strcmp_ne
    CMP R0, #0
    BEQ __strcmp_eq
    ADD ER4, #1
    ADD ER6, #1
    BAL __strcmp_l
__strcmp_eq:
    MOV ER0, #0
    RT
__strcmp_ne:
    MOV ER0, #1
    RT

; ---- strcpy(dst=ER0, src=ER2) -> ER0 = dst
__strcpy:
    MOV ER4, ER0
__strcpy_l:
    L R6, [ER2]
    ST R6, [ER0]
    CMP R6, #0
    BEQ __strcpy_ret
    ADD ER0, #1
    ADD ER2, #1
    BAL __strcpy_l
__strcpy_ret:
    MOV ER0, ER4
    RT

; ---- atoi(s=ER0) -> ER0 signed int
__atoi:
    MOV ER2, ER0
    MOV ER0, #0
    MOV R4, #0     ; neg flag
    L R6, [ER2]
    CMP R6, #45    ; '-'
    BNE __atoi_dig
    MOV R4, #1
    ADD ER2, #1
    L R6, [ER2]
__atoi_dig:
    CMP R6, #48
    BLT __atoi_done
    CMP R6, #58
    BGE __atoi_done
    MOV R8, #10
    MUL ER0, R8
    ADD R0, R6
    ADD R0, #-48
    ADD ER2, #1
    L R6, [ER2]
    BAL __atoi_dig
__atoi_done:
    CMP R4, #0
    BEQ __atoi_ret
    MOV ER2, #0
    SUB R2, R0
    SUBC R3, R1
    MOV ER0, ER2
__atoi_ret:
    RT

; ---- RAM file system: REMOVED from asm ----
; f_save/f_load/f_exists/f_remove are PRELUDE Wiz functions now (wizc.py
; PRELUDE['file']): files are linked-list NODES allocated from the dynamic
; heap (list head at 0xE81C), so removing a file returns its memory to
; alloc(). No fixed 1 KB file area, no linear scan, no 255-byte data cap.
