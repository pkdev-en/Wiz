; cwapp: chương trình Wiz được vá NGAY VÀO firmware fx-580VN X (ML620906, 256 KB).
; Nằm ở flash trống 3:0E40 (offset ROM 30E40h), được gọi từ menu của máy.
;
; Hook: patch_menu.py đè lệnh tại 2:5E1E (CMP R8,03 / BEQ 2:5E88 — trong set_mode 2:5D82)
;       bằng B 3:0E40. Trampoline dưới đây:
;         R8 = 0E0h (mode của slot menu mình vá) -> chạy app Wiz; khi main() trả về,
;              về menu ĐÚNG theo đường gốc của firmware (đọc từ disassembly rom.bin):
;                D111 = C1h = trạng thái MENU GRID của máy (boot máy xong D111=C1,
;                D10E=FC26h, D114=01, OS loop 0:C7xx vẽ grid 4xN qua 2:C0B0 -> 0:96DE).
;                Gọi BL 2:5D82 = set_mode(ER0 = 0C1h): nhánh C1 của chính set_mode
;                (2:5E7C) + tail 2:5E52 -> 0:AC38; OS loop thấy D111=C1 sẽ vẽ lại grid.
;                Trước đó set D10E = FC26h — y hệt idiom các wrapper mở màn của
;                firmware (2:9D30, 2:EB48) để grid được vẽ (0:C082 chỉ vẽ khi 09AFA(D10E)=0).
;              (88h=Table, 4Ah=Ratio, 4Bh=Inequality, 45h=Equation/Func — đã đối
;               chiếu với bảng 12 slot menu tại 1:7FF8; KHÔNG mode nào trong số đó
;               là menu grid — grid = trạng thái C1h của OS loop.)
;              Ngắt luôn BẬT, stack firmware giữ nguyên.
;         R8 != 0E0h -> chạy lại đúng các lệnh bị đè rồi tiếp tục set_mode như thường.

type(ML620906)
model large

_ROMSEG EQU 3

    ORG 30E40h

_TRAMP:
    cmp r8, #0E0h
    bne _t_old
    b _APP
_t_old:
    cmp r8, #03h
    bne _t_back
    b 25E88h
_t_back:
    b 25E22h

; ---- _TRAMP2: nhánh default của vòng dispatch mode của OS (0:29418).
; patch_menu.py đè "BL 2:E234" tại 0:29448 bằng B _TRAMP2. Vào đây R0 = D111:
;   R0 = E0h -> set_mode(E0h, R1=0): Y HỆT đường người dùng chọn slot mình trong
;               menu (2:AD8C: MOV R1,00; BL 25D82) -> hook 2:5E1E -> app chạy lại.
;               Đây là đường ON/reset: boot KHÔNG đụng D111 (chỉ set_mode 2:5E12 và
;               1:E5DC ghi D111), nên sau reset D111 vẫn = E0h; vòng dispatch gốc
;               không có E0h trong bảng (02,03,06,07,0C,45,4A,4B,88,89,C4) và sẽ
;               rơi vào menu grid 2:E234 = "bấm ON về menu 1". Vá này làm ON/reset
;               mở lại app — cùng hành vi "ở yên trong app" như app gốc của máy.
;   R0 khác  -> BL 2:E234 (menu grid gốc, nguyên trạng) rồi về 0:29418 như cũ.
_TRAMP2:
    cmp r0, #0E0h
    bne _t2_def
    ; ON/reset khi menu (mở bằng exit()) đang bật: D113=1 còn kẹt trong RAM ->
    ; OS coi đang menu và vẽ đè logo lên màn app. Dọn đúng bộ cờ exit() dùng
    ; khi đóng menu về app (D113, D142, D164, D165) rồi mới gọi set_mode.
    mov r1, #0
    mov r0, #0
    st r0, 0D113h
    st r0, 0D142h
    st r0, 0D164h
    st r0, 0D165h
    mov r0, #0E0h
    bl 25D82h
    b 29418h
_t2_def:
    bl 2E234h
    b 29418h

; ---- _TRAMP3: chặn ĐẦU hàm menu grid 2:E234 (cơ chế ON an toàn, thay cho
; vá 0:29448 từng làm máy thật chết nguồn — đường này KHÔNG đụng vào vòng
; lặp chính của OS: dispatch vẫn BL 2:E234 như gốc, chỉ 4 byte đầu của
; 2:E234 được đè bằng B 3:_TRAMP3).
; 2:E234 chỉ có 2 lối vào: BL từ nhánh default của dispatch 0:29448 (khi đó
; R0=D111) và tail-jump B từ runner C4 (2:AB48); đường phím MENU (2:AD4C)
; KHÔNG qua đây. Kiểm tra D111 trực tiếp (chắc hơn R0):
;   D111 = E0h (app mình còn trong RAM sau ON/reset) -> mở lại app:
;   xóa cờ menu (D113/D142/D164/D165 — nếu ON khi menu đang mở, D113=1 kẹt
;   trong RAM làm OS vẽ đè logo lên app) rồi set_mode(E0h, R1=0) — Y HỆT đường
;   người dùng chọn slot trong menu (2:AD8C: MOV R1,00; BL 25D82). set_mode
;   chỉ trả về khi người dùng đã chọn app khác qua menu (lúc đó __exit đặt
;   SP=F000h rồi nhảy 0:29418 — xem __exit) -> vòng dispatch đọc D111 mới và
;   chạy app đó NGUYÊN BẢN với stack sạch.
;   Mọi lệnh gọi đều từ bank 2/3 đúng như các đường ĐÃ CHẠY TỐT trên máy thật
;   (hook 2:5E1E là B từ bank 2 sang bank 3; __exit là BL từ bank 3 về 2:AD4C).
;   D111 khác (VD C1 ở boot lần đầu) -> chạy lại đúng 2 lệnh bị đè
;   (push lr; push xr4) rồi nhảy về 2:E238 — menu grid NGUYÊN BẢN không đổi.
;   LR/lcsr: nhánh D111 khác không BL gì cả nên pop pc ở 2:E244 vẫn về đúng
;   bank 0 (lcsr=0 do BL 2:E234 của dispatch); nhánh E0 kết thúc bằng B, không
;   dùng LR — hủy LR do bl 25D82h gây ra là vô hại (dispatch không dùng LR).
_TRAMP3:
    l r0, 0D111h
    cmp r0, #0E0h
    bne _t3_back
    mov r1, #0
    mov r0, #0
    st r0, 0D113h
    st r0, 0D142h
    st r0, 0D164h
    st r0, 0D165h
    mov r0, #0E0h
    bl 25D82h
    b 29418h
_t3_back:
    push lr
    push er4
    b 2E238h

_APP:
    push ER8            ; giữ R8..R15 của set_mode (ABI firmware: callee phải giữ)
    push ER10
    push ER12
    push ER14
    bl _run             ; chạy chương trình Wiz; main() chỉ kết thúc qua exit()
                        ; (dead code — main() không bao giờ return; phòng hờ:
                        ; nếu có thì về dispatch với stack sạch như exit())
    mov r14, #0
    mov r15, #0F0h
    mov SP, ER14
    b 29418h

_run:
    b _main

; exit(): MỞ MENU GỐC của máy — copy 100% handler phím MENU của firmware (2:F88A,
; disasm rom.bin): D113=1, xóa D142/D164/D165, BL 2:AD4C (vòng menu 2:D902 +
; dispatch set_mode/runner). Menu hiện ra để người dùng TỰ điều hướng chọn app:
;   - cancel (AC trong menu): 2:AD4C trả về, D111 vẫn = E0 -> POP PC, app chạy tiếp
;   - chọn app khác: trong menu lồng, firmware đã tự chạy set_mode(app) (slot
;     02/03/45/other) HOẶC gọi thẳng runner app (06/07/0C/4A/4B — chạy lồng rồi
;     return), D111 đã đổi. Máy gốc lúc này: 2:F88A trả key FC24h cho app host
;     -> app host RETURN hết về vòng dispatch 0:29418 -> dispatch đọc D111 mới
;     và gọi runner app mới với STACK SẠCH (mức SP = spinit F000 của vector
;     reset — boot/ON cũng chạy dispatch đúng ở mức này).
;     App mình KHÔNG có frame runner gốc để return, nên exit() làm ĐÚNG việc
;     máy làm sau khi runner return: đặt SP = F000h rồi nhảy B 29418h. Không
;     dỡ frame thủ công, không chừa frame zombie (NGUYÊN NHÂN BẢN CŨ BỊ LỖI:
;     unwind về 2:AD92/0AC38 khiến grid loop/app host chạy tiếp bên dưới, mỗi
;     lần chuyển app chừa lại cả cụm frame -> stack phình dần -> lắm bug).
; ABI: exit() được gọi bằng BL từ code Wiz; chỉ gọi trực tiếp từ main().
__exit:
    push lr             ; giữ địa chỉ quay về caller Wiz — dùng cho đường cancel
    mov r0, #1
    st r0, 0D113h
    mov r0, #0
    st r0, 0D142h
    st r0, 0D164h
    st r0, 0D165h
    bl 2AD4Ch           ; MENU GỐC: hiện menu, người dùng tự điều hướng/chọn
    mov r0, #0
    st r0, 0D113h       ; D113 = 0 như handler gốc (2:F94A)
    l r0, 0D111h
    cmp r0, #0E0h
    bne _x_switch
    ; ---- cancel / MENU-hoac-AC trong menu (R0=0 tra ve): CHỐNG ĐƠ v3 ----
    ; Bug 1 (ban cu): bam lai phim mo menu trong menu -> 2:D902 tra 0 ->
    ;   __exit pop pc -> main() doc lai phim van DANG GIU -> goi __exit
    ;   lien tuc -> may do.
    ; Bug 2 (AC, may that): vong cho cu chi goi 0:A546 ma khong cho nhả
    ;   phím vật lý — khi AC van giu, ngat quet tiep tuc nap ma phím vao
    ;   queue OS (D180) va main() doc ma tran thay AC con giu -> exit()
    ;   duoc goi lai lien tuc, menu mo la roi cancel ngay -> may nhu TREO.
    ;   (Polarity 0:A546: tra 1 khi D116.6=1 HOAC queue D180 RONG — tra 0
    ;   khi co phim dang nam trong queue; dung no lam dieu kien "sach"
    ;   thi SAI CHIEU, da kiem tra thuc nghiem tren emulator.)
    ; Fix v3:
    ;  (a) CHO NHA PHIM VAT LY truoc — quet ma tran truc tiep qua __key cua
    ;      runtime (BGES so sanh CO DAU; BGE cua nX-U8 la khong dau);
    ;  (b) cho OS "sach" CO GIOI HAN (60x250 vong): D116.6=0 VA do dai
    ;      chuoi queue tai D180 = 0 (goc 2:03B8). Het gio van ve — rac con
    ;      lai se duoc lan mo menu sau tieu thu (nhay 1 lan, khong do may);
    ;  (c) xoa D014 SAU CUNG (ngat co the vua nap lai khi phim con giu).
    mov r0, #0
    st r0, 0D014h       ; xoa ma phim hien tai cua OS
_x_kr:
    bl __key            ; (a) CHO NHA PHIM VAT LY: ER0 = ma phim dang giu
    cmp r0, #0          ;     (0..63), -1 = khong co phim. Quet ma tran truc
    cmpc r1, #0         ;     tiep, KHONG phu thuoc queue OS -> khong the ket.
    bges _x_kr          ;     CHU Y: phai dung BGES (co dau) — BGE cua nX-U8
                        ;     la KHONG DAU, ER0=FFFF se bi coi >= 0 -> loop
                        ;     vo han.
    mov r3, #60         ; (b) gioi han thoi gian cho OS "sach": 60 x 250 vong.
                        ;     Bo dem dung R2/R3 vi 2:03B8 (do dai queue) ghi
                        ;     R0/R1 — neu dem bang R1 thi bi xoa mat.
_x_to:
    mov r2, #250
_x_wk:
    l r0, 0D116h        ; co shift/2nd (D116.6) phai = 0
    and r0, #40h
    bne _x_wk_more
    mov r0, #80h        ; queue phim OS (chuoi tai D180) phai RONG:
    mov r1, #0D1h       ; 2:03B8(D180) = do dai chuoi queue, 0 = rong.
    bl 203B8h
    cmp r0, #0
    cmpc r1, #0
    beq _x_wkd          ; sach: khong shift + queue rong -> thoat
_x_wk_more:
    add r2, #0FFh
    bne _x_wk
    add r3, #0FFh
    bne _x_to           ; het gio van ve — du queue con rac thi lan mo menu
                        ; sau se tieu thu (nhay 1 lan, khong bao gio do may).
_x_wkd:
    mov r0, #0
    st r0, 0D014h       ; (c) xoa D014 SAU CUNG (ngat co the vua nap lai)
    pop pc              ; cancel: ve tiep vong lap app (man duoc main ve lai)
_x_switch:
    mov r14, #0         ; SP = F000h: ER14 = R14(thấp):R15(cao) little-endian
    mov r15, #0F0h
    mov SP, ER14        ; về đúng mức SP của vòng dispatch (spinit vector reset)
    b 29418h            ; dispatch đọc D111 mới, gọi runner app được chọn NGUYÊN BẢN
