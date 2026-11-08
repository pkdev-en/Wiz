#!/usr/bin/env python3
"""patch_menu.py - put a Wiz program into the menu of a Casio fx-580VN X (ML620906, 256 KB) ROM.

    python3 patch_menu.py rom.bin app.wz out.bin [--slot 2] [--mode E0] [--force]

What it does (all addresses were read from bro.bin with a disassembler; NOT yet run on the real firmware):
  1. builds app.wz for the 'cwapp' target: code + data at 3:0E40 (ROM offset 30E40h, free flash, all 0xFF)
  2. writes the program there; its first bytes are a trampoline (see template_cwapp.asm)
  3. overwrites firmware 2:5E1E  "CMP R8,03 / BEQ 2:5E88"  (set_mode, 2:5D82)  with  "B 3:0E40"
  4. sets the mode id of menu slot N (menu table at 0x7FF8, 6 bytes per entry: icon ptr, mode id, data ptr)
     to the mode the trampoline answers to (default 0E0h). The slot keeps its icon and name.
  5. overwrites the DEFAULT branch of the OS mode-dispatch loop, 0:29448 "BL 2:E234",
     with "B 3:<_TRAMP2>". The dispatch loop (0:29418) reads D111 and runs the app
     whose mode id matches (02,03,06,07,0C,45,4A,4B,88,89,C4); anything else falls
     into 2:E234 = the main-menu grid. The ON key / a reset reboots WITHOUT touching
     D111, so with D111==0E0h the stock loop used to land in the menu ("ON -> menu 1").
     _TRAMP2 routes 0E0h back into set_mode(0E0h) — exactly how the firmware re-opens
     a native app after ON — so ON/reset re-opens the Wiz app instead.
  6. neutralizes the D0F4 canary inside the boot RAM check 0:9E9E (0:9ED2
     "L R0,D0F4" -> "MOV R0,0000"). That sub-check passes only while F050 bit7
     (the ON key input sampled at init) is set/zero — on emulators F050 reads 0xFF,
     the check then fails on EVERY boot and the firmware wipes the OS state
     (2:6086 -> 1:E5CC -> D111=C1) so nothing can ever resume after ON. The other
     three sub-checks (DBD0 signature, D153 range, D31A blocks) stay active and
     still catch genuinely corrupt RAM, so a real first boot / battery pull is
     unaffected.
  7. -m <ảnh> <thông số...>: chỉnh mục menu như tool web phuvippro_vn (icon 48x23
     từ PNG/JPG, đổi tên, gán chức năng, đổi chỗ, xuất PNG). Lặp được nhiều -m.
       -m logo.png slot=3 name=GAME         icon + tên cho mục 3 (giữ khung máy)
       -m a.png slot=2 thr=150 invert nokeep  ngưỡng 150, đảo màu, bỏ khung
       -m slot=4 func=1                      mục 4 chạy app của mục 1
       -m slot=5 swap=6                      đổi chỗ mục 5 và 6 (icon + chức năng)
       -m slot=2 export=icon.png             xuất icon mục 2 ra PNG
  8. -m slot=K del: XOÁ HẲN mục K (điểm khác tool web — web chỉ làm trống icon/tên
     nên ô vẫn còn, con trỏ vẫn dừng, vẫn hiện nhãn "C:"). Cách làm: dồn các mục
     sau lên 1 ô trong bảng 0x7FF8 và giảm byte đếm tại 0x3EA0 (số mục - 1) —
     mọi ràng buộc của grid (vẽ 2:B9C0, điều hướng 2:D902, phím tắt số/chữ, khôi
     phục con trỏ lúc boot 2:C7B0) đều đọc byte này, nên mục bị xoá biến mất hoàn
     toàn: không ô, không nhãn, con trỏ không dừng, phím của nó thành vô hiệu.
     Nhiều del một lần chạy: slot đánh theo MENU GỐC (công cụ tự xoá từ cuối lên).
       -m slot=12 del                        xoá mục C (Ratio)
  9. THÊM mục: ghi -m với slot > số mục hiện có — đếm tự tăng, mục mới mode chết
     55h (bấm không có gì), icon/tên kế thừa ô đuôi; chỉnh tiếp trong cùng -m:
       -m logo.png slot=12 func=1            thêm mục C chạy app của mục 1
       -m slot=13 dup=1 -m slot=14 dup=2     PHÁ GIỚI HẠN 12: thêm mục D,E là
                                             bản sao y nguyên mục 1,2 (icon+chức năng)
     Lưu ý: sau func=/dup=/thêm mục, tên của mục kế thừa chuỗi tên của mục nguồn
     (dùng chung) — -m sẽ CHẶN name= trên mục đó để không đè tên mục khác.

  PHÁ GIỚI HẠN 12 -> 14 MỤC (cơ chế đã đảo ngược + xác nhận bằng emulator):
  - Menu là lưới generic 4 cột, mọi vòng (vẽ 2:B9C0, điều hướng 2:D902, phím tắt
    2:DBF6, boot-restore 2:C7B4) đều đọc byte đếm tại 0x3EA0 — không có số 12
    cứng nào trong code. Cửa sổ hiển thị 2 hàng x 4 ô, cuộn theo con trỏ
    (hàng_cuộn*4) — tức là ấn DOWN hết hàng 3 sẽ tự load hàng 4.
  - Bảng nhãn 0x7CD2 có sẵn 18 nhãn '123456789ABCDEFM' (nền ClassWiz dùng chung);
    mục 13/14 tự có nhãn D/E, code chỉ bỏ nhãn từ mục 19 trở đi.
  - Bảng menu gốc kín 0x7FF8..0x803F. Ngay sau đó, 12 byte 02 CF 00 02 9A 00
    02 9B 00 02 98 00 tại 0x8040..0x804B là data chết (probe watchpoint trên
    emulator: 0 lần đọc/ghi/fetch qua boot+app+menu+điều hướng) — ghi đè bằng
    entry 13/14 là an toàn, ERx[7FF8+6k] tự nhiên trỏ đúng tới (k=12 -> 0x8040).
  - Giới hạn cứng thực của bảng là 14 (khi đầy 0x804B; nhãn hỗ trợ tới 18 nhưng
    chỉ 14 ô nằm trọn trong vùng đã kiểm chứng).
  - Đỗi chú ý: lúc bật máy, OS dò mục khớp mode đang chạy (D111) TỪ CUỐI lên đầu
    để đặt lại con trỏ — với mục 13 là bản sao Calculate, lần mở menu đầu tiên
    con trỏ sẽ nằm ở mục D (không phải lỗi).
Chọn slot được vá thì chạy chương trình; exit() trong chương trình mở menu gốc (2:AD4C), 100% native.
"""
import argparse
import os
import struct
import sys
import zlib

from build import build_source
from u8asm import AsmError
from wizc import WizError

SZ = 262144
MB = 0x7FF8              # menu table
NB = 0x5516              # name pointer table
CNT = 0x3EA0             # byte đếm của grid: chỉ số mục CUỐI (= số mục - 1).
                         # Mọi ràng buộc của menu (vẽ 2:B9C0:02BABE, điều hướng
                         # 2:D902, phím tắt 2:DBF6, boot-restore 2:C7B4) đọc nó.
NSMAX = 14               # giới hạn thực: entry 13/14 ghi vào 0x8040..0x804B
                         # (12 byte data chết của firmware, đã kiểm chứng 0 tham
                         # chiếu; ERx[7FF8+6k] với k=12,13 tự trỏ đúng tới).
DEAD12 = bytes.fromhex('02cf00029a00029b00029800')   # 12 byte chết @0x8040
DMODE = 0x55             # mode "chết": set_mode đi nhánh generic rồi return,
                         # dispatch rơi vào default = mở lại menu → bấm không có gì.
KR = 23                  # icon: số hàng pixel
KBW = 6                  # icon: byte mỗi hàng (48 px)
KIC = KR * KBW           # icon: kích thước trong ROM (138)
NS = 12
HOOK = 0x25E1E           # inside set_mode
HOOK_OLD = bytes([0x03, 0x78, 0x33, 0xC9])      # CMP R8,03 ; BEQ $25E88
HOOK_NEW = bytes([0x00, 0xF3, 0x40, 0x0E])      # B 3:0E40
GRID = 0x02E234         # menu-grid function the dispatch default BLs into
GRID_OLD = bytes([0xCE, 0xF8, 0x6E, 0xF4])      # PUSH LR ; PUSH XR4
SOFT = 0x009ED2          # boot RAM check 0:9E9E: the D0F4 canary sub-check
SOFT_OLD = bytes([0x10, 0x90, 0xF4, 0xD0])      # L R0, D0F4
SOFT_NEW = bytes([0x2E, 0xF4, 0x00, 0x00])      # MOV R0, 0000
BASE = 0x30E40
CH = '123456789ABCDE'   # nhãn slot 1..14 (13/14 = D/E, khớp bảng nhãn 0x7CD2 của firmware)


def u16(r, o):
    return r[o] | r[o + 1] << 8


def cstr(r, a):
    s = ''
    while r[a] and len(s) < 40:
        s += chr(r[a])
        a += 1
    return s


def mentry(r, mb, k):
    o = mb + 6 * k
    return o, u16(r, o), u16(r, o + 2), u16(r, o + 4)   # offset, icon ptr, mode id, data ptr


def check_menu(r, mb=MB, nb=NB):
    n = r[CNT] + 1
    if not 2 <= n <= NSMAX:
        return 'menu count byte at %05X is %02X (=> %d muc), khong hop le' % (CNT, r[CNT], n)
    for k in range(n if mb == MB else min(n, NS)):
        o, ip, _, dp = mentry(r, mb, k)
        if not (0x100 <= ip <= SZ - KIC) or r[o + 3] or r[dp] != 2 or r[dp + 2] or r[dp + 3]:
            return 'menu entry %s does not look right' % CH[k]
        if not 2 <= r[dp + 1] <= 30:
            return 'menu entry %s: name id out of range' % CH[k]
        s = cstr(r, u16(r, nb + 2 * (r[dp + 1] - 2)))
        if len(s) < 3 or not all(32 <= ord(c) < 127 for c in s):
            return 'menu entry %s: cannot read its name' % CH[k]
    return ''


def slot_name(r, k, mb=MB, nb=NB):
    return cstr(r, u16(r, nb + 2 * (r[mentry(r, mb, k)[3] + 1] - 2)))


# ---- xoá hẳn / thêm mục (dồn bảng + byte đếm CNT) ----

def menu_count(r):
    """Số mục menu hiện có (byte đếm tại CNT = chỉ số mục cuối)."""
    return r[CNT] + 1


def menu_del(r, mb, k):
    """Xoá HẲN mục k (0-based): dồn các mục sau lên 1 ô (6 byte), giảm byte đếm.
    Khác với làm trống icon/tên (tool web): con trỏ không còn dừng ở ô trống,
    không còn nhãn, phím tắt của mục đó thành vô hiệu. Ô đuôi thành bản sao mục
    cuối với mode chết DMODE — vẫn hợp lệ cấu trúc cho check_menu, không bao giờ
    được vẽ vì mọi vòng của grid giới hạn k <= byte đếm."""
    n = menu_count(r)
    if not 0 <= k < n:
        sys.exit('error: -m del: menu chi con %d muc, khong co muc %s' % (n, CH[k]))
    name = slot_name(r, k, mb)
    for i in range(k, n - 1):
        r[mb + 6 * i: mb + 6 * i + 6] = r[mb + 6 * (i + 1): mb + 6 * (i + 1) + 6]
    r[mb + 6 * (n - 1) + 2: mb + 6 * (n - 1) + 4] = bytes([DMODE, 0x00])
    r[CNT] = n - 2
    return name


def menu_extend(r, mb, upto):
    """Tăng số mục lên tới slot upto (0-based): mục mới mode chết DMODE (bấm
    không có gì), icon/tên kế thừa ô đuôi; chỉnh tiếp bằng func=/dup=/name=/img=.
    Slot 13/14 (k>=12) ghi vào 0x8040..0x804B — chỉ cho khi đó là 12 byte chết
    đã biết hoặc entry hợp lệ ghi từ lần chạy trước."""
    n = menu_count(r)
    if upto < n:
        return
    if upto + 1 > NSMAX:
        sys.exit('error: menu toi da %d muc (bang chi cho 14 o da kiem chung)' % NSMAX)
    for j in range(n, upto + 1):
        o = mb + 6 * j
        if j >= NS and mb == MB:
            cur = bytes(r[o:o + 6])
            dead = DEAD12[6 * (j - NS): 6 * (j - NS) + 6]
            ok = cur == dead or (r[o + 3] == 0 and 0x100 <= u16(r, o) <= SZ - KIC
                                 and r[u16(r, o + 4)] == 2)
            if not ok:
                sys.exit('error: vung 0x%05X khong phai 12 byte chet da kiem chung'
                         ' hoac entry hop le — khong ghi de (ROM khac?)' % o)
        r[o + 2: o + 4] = bytes([DMODE, 0x00])
    r[CNT] = upto


# ---- chỉnh mục menu (tính năng -m, chuyển từ tool web của phuvippro_vn) ----

def icon_bits(r, a):
    b = bytearray(48 * KR)
    for y in range(KR):
        row = a + y * KBW
        for x in range(48):
            b[y * 48 + x] = (r[row + (x >> 3)] >> (7 - (x & 7))) & 1
    return b


def icon_putb(r, a, b):
    for y in range(KR):
        row = a + y * KBW
        for i in range(KBW):
            v = 0
            for j in range(8):
                v |= b[y * 48 + i * 8 + j] << (7 - j)
            r[row + i] = v


def menu_chrome(r, mb):
    """Khung chung của 12 icon gốc (ô số, gạch chân) — giữ khi đặt icon mới."""
    c = bytearray(b'\x01' * (48 * KR))
    for k in range(NS):
        b = icon_bits(r, mentry(r, mb, k)[1])
        for i in range(len(c)):
            c[i] &= b[i]
    return c


def png_to_icon(path, thr, invert, keep, frame):
    try:
        from PIL import Image
    except ImportError:
        sys.exit('error: cần Pillow để đọc ảnh:  pip install pillow')
    im = Image.open(path).convert('RGB')
    if im.size != (48, KR):
        im = im.resize((48, KR), Image.LANCZOS)
    px = im.load()
    b = bytearray(48 * KR)
    for y in range(KR):
        for x in range(48):
            pr, pg, pb = px[x, y]
            v = 1 if (0.299 * pr + 0.587 * pg + 0.114 * pb) < thr else 0
            if invert:
                v ^= 1
            if keep:
                v |= frame[y * 48 + x]
            b[y * 48 + x] = v
    return b


def write_icon_png(path, b, scale=4):
    """Xuất icon ra PNG 1-bit (không cần Pillow)."""
    w, h = 48 * scale, KR * scale
    stride = (w + 7) // 8
    raw = bytearray()
    for y in range(h):
        raw.append(0)                                  # filter: none
        row = bytearray(stride)
        for x in range(w):
            if not b[(y // scale) * 48 + x // scale]:  # 0 = pixel sáng = đen trên LCD
                row[x >> 3] |= 0x80 >> (x & 7)
        raw += row
    def chunk(tag, data):
        return len(data).to_bytes(4, 'big') + tag + data + (zlib.crc32(tag + data) & 0xffffffff).to_bytes(4, 'big')
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 1, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(bytes(raw), 9))
        + chunk(b'IEND', b''))


def find_menu_table(r):
    """Tự dò địa chỉ bảng menu (12 entry hợp lệ, 12 mã tên khác nhau)."""
    for o in range(0, SZ - 6 * NS, 2):
        ids = set()
        for k in range(NS):
            _, ip, _, dp = mentry(r, o, k)
            if ip < 0x100 or ip + KIC > SZ or r[o + 6 * k + 3] or dp + 4 > SZ \
                    or r[dp] != 2 or r[dp + 2] or r[dp + 3] or r[dp + 1] in ids:
                break
            ids.add(r[dp + 1])
        if len(ids) == NS:
            return o
    return None


PKEYS = ('slot', 'name', 'thr', 'func', 'swap', 'dup', 'export', 'mb', 'nb')


def parse_menu_spec(tokens, default_slot):
    sp = {'img': None, 'slot': default_slot, 'name': None, 'thr': 128,
          'invert': False, 'keep': True, 'func': None, 'swap': None, 'dup': None,
          'export': None, 'mb': None, 'nb': None, 'del': False}
    for t in tokens:
        key, sep, val = t.partition('=')
        if not sep:
            if t in ('invert', 'nokeep', 'keep', 'del'):
                sp['keep'] = (t != 'nokeep')
                if t == 'invert':
                    sp['invert'] = True
                if t == 'del':
                    sp['del'] = True
                continue
            if sp['img'] is None:
                sp['img'] = t
                continue
            sys.exit('error: -m: không hiểu tham số %r' % t)
        if key not in PKEYS:
            sys.exit('error: -m: không hiểu thông số "%s=" (đủ: %s)' % (key, ','.join(PKEYS)))
        sp[key] = val
    for key in ('slot', 'func', 'swap', 'dup'):
        if sp[key] is not None:
            sp[key] = int(sp[key])
            if not 1 <= sp[key] <= NSMAX:
                sys.exit('error: -m %s phải là 1..%d' % (key, NSMAX))
    sp['thr'] = int(sp['thr'])
    if not 20 <= sp['thr'] <= 235:
        sys.exit('error: -m thr phải 20..235')
    if sp['mb']:
        sp['mb'] = int(sp['mb'], 16)
    if sp['nb']:
        sp['nb'] = int(sp['nb'], 16)
    return sp


def apply_menu_edits(rom, spec_lists, default_slot):
    """Áp các -m vào rom (bytearray). Trả danh sách (addr, mô tả) để in."""
    orig = bytes(rom)
    mb, nb = MB, NB
    specs = [parse_menu_spec(t, default_slot) for t in spec_lists]
    forced = False
    for sp in specs:
        if sp['mb'] or sp['nb']:
            mb, nb = sp['mb'] or mb, sp['nb'] or nb
            forced = True
    if not forced and check_menu(rom, mb, nb):
        f = find_menu_table(orig)
        if f is None:
            sys.exit('error: -m không nhận ra bảng menu — chỉnh bằng mb=<hex> nb=<hex>')
        mb = f
        print('  (-m: tự dò bảng menu tại %05X)' % mb)
    frame = menu_chrome(orig, mb)
    msgs = []
    # xoá mục TRƯỚC (slot đánh theo menu gốc, xoá từ cuối lên để số slot không trôi)
    for sp in sorted((s for s in specs if s['del']), key=lambda s: -s['slot']):
        if sp['img'] or sp['name'] is not None or sp['func'] is not None \
                or sp['swap'] is not None or sp['dup'] is not None or sp['export']:
            sys.exit('error: -m del không đi cùng img/name/func/swap/dup/export trong MỘT -m'
                     ' (đường dẫn out phải đặt TRƯỚC -m nếu ghi sau rom); tách ra nhiều -m')
        k = sp['slot'] - 1
        name = menu_del(rom, mb, k)
        msgs.append((mb + 6 * k, 'menu: XOÁ HẲN mục %s ("%s") — các mục sau dồn lên, còn %d mục'
                     % (CH[k], name, menu_count(rom))))
    for sp in specs:
        if sp['del']:
            continue
        k = sp['slot'] - 1
        if k >= menu_count(rom):
            menu_extend(rom, mb, k)
            msgs.append((CNT, 'menu: THÊM mục %s (số mục -> %d; mode chết 55h — gán chức năng bằng func=)'
                         % (CH[k], menu_count(rom))))
        eo = mb + 6 * k
        if sp['dup'] is not None:
            fo = mb + 6 * (sp['dup'] - 1)
            rom[eo:eo + 6] = orig[fo:fo + 6]
            msgs.append((eo, 'menu slot %s: NHAN BAN nguyen muc %s (icon+mode+data)' % (CH[k], CH[sp['dup'] - 1])))
        if sp['img']:
            ia = u16(rom, eo)
            icon_putb(rom, ia, png_to_icon(sp['img'], sp['thr'], sp['invert'], sp['keep'], frame))
            msgs.append((ia, 'menu slot %s: icon <- %s (thr=%d%s%s)'
                         % (CH[k], sp['img'], sp['thr'],
                            ', invert' if sp['invert'] else '',
                            ', khung bo' if not sp['keep'] else ' giu khung')))
        if sp['name'] is not None:
            na = u16(rom, nb + 2 * (rom[mentry(rom, mb, k)[3] + 1] - 2))
            # chuỗi tên dùng chung? (sau func= hoặc thêm mục kế thừa ô đuôi) — chặn
            same = [j for j in range(menu_count(rom))
                    if u16(rom, nb + 2 * (rom[mentry(rom, mb, j)[3] + 1] - 2)) == na]
            if len(same) > 1:
                sys.exit('error: -m name: tên của mục %s dùng chung với mục %s (sau func=/thêm mục)'
                         ' — không đổi được, tránh đè tên mục kia' % (CH[k], ','.join(CH[j] for j in same if j != k)))
            old = cstr(rom, na)
            s = sp['name']
            if not all(32 <= ord(c) < 127 for c in s):
                sys.exit('error: -m name chi nhan ASCII khong dau')
            if not 3 <= len(s) <= len(old):
                sys.exit('error: -m name dai %d ky tu, slot %s chi chua duoc %d (ten cu: "%s")'
                         % (len(s), CH[k], len(old), old))
            for i, c in enumerate(s):
                rom[na + i] = ord(c)
            rom[na + len(s)] = 0
            msgs.append((na, 'menu slot %s: ten "%s" -> "%s"' % (CH[k], old, s)))
        if sp['func'] is not None:
            fo = mb + 6 * (sp['func'] - 1)
            rom[eo + 2:eo + 6] = orig[fo + 2:fo + 6]
            msgs.append((eo + 2, 'menu slot %s: gan chay app cua slot %s (icon giu nguyen)' % (CH[k], CH[sp['func'] - 1])))
        if sp['swap'] is not None:
            so = mb + 6 * (sp['swap'] - 1)
            rom[eo:eo + 6], rom[so:so + 6] = rom[so:so + 6], rom[eo:eo + 6]
            msgs.append((eo, 'menu slot %s <-> %s: doi cho (icon + chuc nang)' % (CH[k], CH[sp['swap'] - 1])))
        if sp['export']:
            ia = u16(rom, eo)
            write_icon_png(sp['export'], icon_bits(rom, ia))
            msgs.append((ia, 'menu slot %s: xuat icon -> %s' % (CH[k], sp['export'])))
    bad = check_menu(rom, mb, nb)
    if bad:
        sys.exit('error: sau -m bang menu bi hong: ' + bad)
    return msgs


def main():
    ap = argparse.ArgumentParser(description='patch a Wiz program into the fx-580VN X menu')
    ap.add_argument('rom')
    ap.add_argument('app', nargs='?', help='chương trình .wz (bỏ qua nếu chỉ chỉnh menu bằng -m)')
    ap.add_argument('out', nargs='?', help='ROM xuất (mặc định: <rom>_patched.bin / <rom>_menu.bin)')
    ap.add_argument('-m', '--menu', dest='menu', action='append', nargs='+', metavar='SPEC',
                    help='chỉnh mục menu, lặp được: -m anh.png slot=3 name=GAME thr=150 invert nokeep func=1 swap=4 export=icon.png del')
    ap.add_argument('--slot', type=int, default=2, help='menu slot 1..12 (default 2)')
    ap.add_argument('--mode', default='E0', help='mode id (hex) the trampoline answers to (default E0)')
    ap.add_argument('--force', action='store_true', help='write even if the target area is not all 0xFF')
    ap.add_argument('--dispatch', action='store_true',
                    help='also patch menu-grid entry 2:E234 (_TRAMP3: ON/reset giu nguyen app)')
    ap.add_argument('--soft', action='store_true',
                    help='also neutralize the D0F4 canary at 0:9ED2 (chi can cho emulator)')
    a = ap.parse_args()

    rom = bytearray(open(a.rom, 'rb').read())
    if len(rom) != SZ:
        sys.exit('error: ROM is %d bytes, an fx-580VN X dump is %d' % (len(rom), SZ))
    if a.app and not a.out and not os.path.exists(a.app) and not a.app.endswith('.wz'):
        a.out, a.app = a.app, None   # chỉ chỉnh menu: positional thứ hai là OUT, không phải app
    bad = check_menu(rom)
    if bad:
        sys.exit('error: this does not look like the ROM these addresses were read from: ' + bad)
    if a.app and not a.out:
        sys.exit('error: cần đường dẫn OUT:  python3 patch_menu.py rom.bin app.wz out.bin ...')
    if not a.app and not a.menu:
        sys.exit('error: cần APP (vá chương trình) hoặc -m (chỉnh menu) — xem: python3 patch_menu.py -h')

    changes = []
    syms = None
    if a.app:
        if bytes(rom[HOOK:HOOK + 4]) != HOOK_OLD:
            sys.exit('error: set_mode at %05X is %s, expected %s (different firmware?)' % (HOOK, bytes(rom[HOOK:HOOK + 4]).hex(' '), HOOK_OLD.hex(' ')))
        if a.dispatch and bytes(rom[GRID:GRID + 4]) != GRID_OLD:
            sys.exit('error: menu-grid entry at %05X is %s, expected %s (different firmware?)' % (GRID, bytes(rom[GRID:GRID + 4]).hex(' '), GRID_OLD.hex(' ')))
        if a.soft and bytes(rom[SOFT:SOFT + 4]) != SOFT_OLD:
            sys.exit('error: D0F4 canary at %05X is %s, expected %s (different firmware?)' % (SOFT, bytes(rom[SOFT:SOFT + 4]).hex(' '), SOFT_OLD.hex(' ')))
        if not 1 <= a.slot <= NSMAX:
            sys.exit('error: --slot must be 1..%d' % NSMAX)
        mode = int(a.mode, 16)
        if not 0x80 <= mode <= 0xFF or mode in (0xC1, 0xC4, 0x88, 0x89):
            sys.exit('error: --mode must be 80..FF and not one the firmware already uses')
        try:
            img, full, variables, syms = build_source(open(a.app, encoding='utf8').read(), 'cwapp', a.app)
        except (WizError, AsmError) as e:
            sys.exit('error: %s' % e)
        code = bytes(img[BASE:])
        if mode != 0xE0:
            # the trampoline compares with 0E0h: assemble again with another constant
            sys.exit('error: only --mode E0 is wired into template_cwapp.asm for now')
        t3 = syms.get('_TRAMP3')
        if t3 is None or (t3 >> 16) != 3:
            sys.exit('error: _TRAMP3 missing from the build (template_cwapp.asm changed?)')
        grid_new = bytes([0x00, 0xF3, t3 & 0xFF, (t3 >> 8) & 0xFF])   # B 3:<_TRAMP3>
        if BASE + len(code) > SZ:
            sys.exit('error: program is %d bytes, only %d fit' % (len(code), SZ - BASE))
        if not a.force and any(b != 0xFF for b in rom[BASE:BASE + len(code)]):
            sys.exit('error: %05X.. is not free flash (not all FF); use --force to overwrite anyway' % BASE)

        rom[BASE:BASE + len(code)] = code
        changes.append((BASE, 'program (%d bytes)' % len(code)))
        rom[HOOK:HOOK + 4] = HOOK_NEW
        changes.append((HOOK, 'hook  %s -> %s' % (HOOK_OLD.hex(' '), HOOK_NEW.hex(' '))))
        if a.dispatch:
            rom[GRID:GRID + 4] = grid_new
            changes.append((GRID, 'menu-grid entry %s -> B 3:%04X (_TRAMP3: ON/reset giu nguyen app; phuong an moi thay cho 0:29448)' % (GRID_OLD.hex(' '), t3 & 0xFFFF)))
        if a.soft:
            rom[SOFT:SOFT + 4] = SOFT_NEW
            changes.append((SOFT, 'RAM check: %s -> %s (D0F4 canary off; chi danh cho emulator)' % (SOFT_OLD.hex(' '), SOFT_NEW.hex(' '))))
        if a.menu:
            changes += apply_menu_edits(rom, a.menu, a.slot)

        o = MB + 6 * (a.slot - 1) + 2
        old = bytes(rom[o:o + 2])
        rom[o:o + 2] = bytes([mode, 0x00])
        changes.append((o, 'menu slot %s (%s) mode id %s -> %02X 00' % (CH[a.slot - 1], slot_name(rom, a.slot - 1), old.hex(' '), mode)))
    elif a.menu:
        changes += apply_menu_edits(rom, a.menu, a.slot)

    if a.app and a.slot > menu_count(rom):
        print('CHÚ Ý: app nằm ở slot %s nhưng menu chỉ còn %d mục — app sẽ không có ô menu.'
              ' Thêm lại bằng: -m slot=%d func=<mức gốc> hoặc bỏ -m del slot đó.'
              % (CH[a.slot - 1], menu_count(rom), a.slot))

    out = a.out or (a.rom.rsplit('.', 1)[0] + ('_patched.bin' if a.app else '_menu.bin'))
    open(out, 'wb').write(rom)

    print('wrote %s' % out)
    for addr, what in changes:
        print('  %05X  %s' % (addr, what))
    if syms:
        print('program entry  %X:%04X   exit() = mo MENU goc (2:AD4C, nhu phim MENU cua may)' % (syms['_APP'] >> 16, syms['_APP'] & 0xFFFF))
        print('slot %s keeps its icon and name; selecting it runs the program.' % CH[a.slot - 1])
    print('NOT tested on the real firmware: try it in an emulator first.')


if __name__ == '__main__':
    main()
