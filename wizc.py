"""wizc 0.2 - compiler for Wiz, a C-like / Python-easy language for the ML620909 (Casio ClassWiz).

Wiz 0.1 in one screen:
    # comment
    score = 0                      # top-level code runs first (globals)
    def square(n):
        return n * n
    def main():
        clear()
        for i in range(0, 64):
            pixel(i, i)            # pixel(x, y) or pixel(x, y, 0|1)
        while True:
            k = key()              # scan index 0..63, -1 = none
            if k == 21 and score < 3:
                score += 1
            elif k != -1:
                delay(50)
Everything is a signed 16-bit int. No recursion (static frames). `and`/`or`/`not`
yield 0/1.
"""
import re
import sys
import unicodedata

VAR_BASE = 0x9000
VAR_LIMIT = 0xE000
ROM_LIMIT = 0x9000
BUILTINS = {'pixel': (2, 3), 'clear': (0, 0), 'key': (0, 0), 'delay': (1, 1),
            'peek': (1, 1), 'poke': (2, 2), '_hspan': (4, 4),
            'key_down': (1, 1), 'key_hit': (1, 1), 'buffered': (1, 1), 'flip': (0, 0),
            '_rpeek': (1, 1), 'exit': (0, 0),
            # Timer0 (libcw __delay): native asm - the TM0 read/start dance is
            # intricate; the RTC itself is PRELUDE (see PRELUDE['rtc'])
            'ticks': (0, 0), 'delay_ms': (1, 1),
            # graphics extra
            'getpixel': (2, 2),
            'copy_rect': (6, 6), 'invert_rect': (4, 4), 'clear_rect': (4, 4),
            # heap byte access (alloc/free and the RAM file system f_save/... are
            # PRELUDE Wiz code over the DYNAMIC heap - see PRELUDE['word']/['alloc']/['free']/['file'])
            '_hpeek': (1, 1), '_hpoke': (2, 2),
            }
KEYWORDS = {'def', 'if', 'elif', 'else', 'while', 'for', 'in', 'range', 'return', 'break',
            'continue', 'pass', 'global', 'and', 'or', 'not', 'True', 'False', 'const', 'rom', 'rom8',
            'goto', 'asm'}   # WIZ-MOD: goto/label + inline assembly

# Key names -> scan index (8*KO bit + KI bit, MSB first). Values copied from libcw.h
# (enum BUTTON / SPECIAL_CHARS, CWII). NOT yet checked by me on real hardware.
KEY_CONSTS = {
    'K_NONE': -1,
    'K_0': 0x0B, 'K_1': 0x3F, 'K_2': 0x37, 'K_3': 0x2F, 'K_4': 0x3E,
    'K_5': 0x36, 'K_6': 0x2E, 'K_7': 0x3D, 'K_8': 0x35, 'K_9': 0x2D,
    'K_UP': 0x20, 'K_DOWN': 0x22, 'K_LEFT': 0x29, 'K_RIGHT': 0x19, 'K_OK': 0x21,
    'K_HOME': 0x30, 'K_BACK': 0x31, 'K_SETTINGS': 0x39, 'K_SHIFT': 0x3A,
    'K_VAR': 0x32, 'K_FUNC': 0x2A, 'K_CATALOG': 0x1A, 'K_TOOLS': 0x12,
    'K_PGUP': 0x10, 'K_PGDOWN': 0x11,
    'K_X': 0x3B, 'K_FRAC': 0x33, 'K_SQRT': 0x2B, 'K_POWER': 0x23, 'K_SQUARED': 0x1B,
    'K_LOGAB': 0x13, 'K_ANS': 0x3C, 'K_SIN': 0x34, 'K_COS': 0x2C, 'K_TAN': 0x24,
    'K_LPAREN': 0x1C, 'K_RPAREN': 0x14,
    'K_DEL': 0x25, 'K_AC': 0x1D, 'K_MUL': 0x26, 'K_DIV': 0x1E,
    'K_PLUS': 0x27, 'K_MINUS': 0x1F,
    # K_NEG: on cw this is the real (-) key next to the digits; on cwii there is
    # no separate change-sign key, so the name aliases the minus key. Lets shared
    # PRELUDE code accept the natural "make negative" key on both machines.
    'K_NEG': 0x1F,
    'K_DOT': 0x0C, 'K_SCI': 0x0D, 'K_FORMAT': 0x0E, 'K_EXE': 0x0F,
}

# ClassWiz (cw, ML620906) has its OWN key layout - it is not the cwii layout. Scan codes below were
# measured on a real cw (code = KO*8 + KI). K_INTEGRAL = the integral key, next to X.
CW_KEY_CONSTS = {
    'K_NONE': -1,
    'K_SHIFT': 56, 'K_ALPHA': 48, 'K_UP': 40, 'K_DOWN': 33, 'K_LEFT': 41, 'K_RIGHT': 32,
    'K_MENU': 39, 'K_OPTN': 57, 'K_CALC': 49, 'K_INTEGRAL': 25, 'K_X': 17,
    # K_MENU=39: XAC NHAN tren may that (user do bang cach bam tung phim, 11/2025);
    # ban cu 24 SAI — 24 chinh la '+'.
    'K_FRAC': 58, 'K_SQRT': 50, 'K_SQUARED': 42, 'K_LOG': 26, 'K_LN': 18,
    # K_POWER bi bo: tren fx-580VN X khong co phim nguan rieng, AC/ON chinh la no.
    'K_NEG': 59, 'K_DEG': 51, 'K_INV': 43, 'K_SIN': 35, 'K_COS': 27, 'K_TAN': 19,
    'K_STO': 60, 'K_ENG': 52, 'K_LPAREN': 44, 'K_RPAREN': 36, 'K_SD': 28, 'K_MPLUS': 20,
    'K_7': 61, 'K_8': 53, 'K_9': 45, 'K_DEL': 37,
    # K_AC=34: doi chieu tu ROM (0:A18A quet hang F046=10h, cot F040.2 — idiom
    # "bam AC de ngat tinh toan" moi app deu dung). Ban cu 29 SAI (do la '+').
    'K_AC': 34,
    'K_4': 62, 'K_5': 54, 'K_6': 46, 'K_MUL': 38, 'K_DIV': 30,
    'K_1': 63, 'K_2': 55, 'K_3': 47, 'K_PLUS': 24, 'K_MINUS': 31,
    # K_PLUS=24: doi cho voi K_MENU theo xac nhan may that (24 = '+').
    'K_0': 11, 'K_DOT': 12, 'K_EXP': 13, 'K_ANS': 14, 'K_EXE': 15,
}
assert len(set(CW_KEY_CONSTS.values())) == len(CW_KEY_CONSTS)


def key_consts(target_name):
    """key-name table of one machine"""
    return CW_KEY_CONSTS if target_name in ('cw', 'cwapp') else KEY_CONSTS

# Standard library written in Wiz itself. Only the pieces a program actually calls get compiled in;
# a function of the same name defined by the user replaces the library one.
PRELUDE = {
    'math_abs': '''
def abs(n):
    if n < 0:
        return 0 - n
    return n
''',
    'math_min': '''
def min(a, b):
    if a < b:
        return a
    return b
''',
    'math_max': '''
def max(a, b):
    if a > b:
        return a
    return b
''',
    'math_clamp': '''
def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
''',
    'math_sign': '''
def sign(n):
    if n < 0:
        return -1
    if n > 0:
        return 1
    return 0
''',
    'rand': '''
_seed = 12345
def srand(s):
    global _seed
    _seed = s
def rand(n):
    global _seed
    _seed = _seed * 25173 + 13849
    return ((_seed >> 1) & 0x7FFF) % n
''',
    'wait_key': '''
def wait_key():
    while key() != -1:
        pass
    while True:
        k = key()
        if k != -1:
            return k
''',
    'hline': '''
def hline(x0, x1, y, c=1):
    if y < peek(0xE803) or y >= peek(0xE804):
        return 0
    a = peek(0xE801)
    b = peek(0xE802)
    if x0 < a:
        x0 = a
    if x1 > b:
        x1 = b
    if x0 >= x1:
        return 0
    _hspan(x0, x1, y, c != 0)
''',
    'vline': '''
def vline(x, y0, y1, c=1):
    if x < peek(0xE801) or x >= peek(0xE802):
        return 0
    a = peek(0xE803)
    b = peek(0xE804)
    if y0 < a:
        y0 = a
    if y1 > b:
        y1 = b
    for y in range(y0, y1):
        pixel(x, y, c)
''',
    'rect': '''
def rect(x, y, w, h, c=1, thick=1, dash=255):
    line(x, y, x + w - 1, y, c, thick, dash)
    line(x, y + h - 1, x + w - 1, y + h - 1, c, thick, dash)
    line(x, y, x, y + h - 1, c, thick, dash)
    line(x + w - 1, y, x + w - 1, y + h - 1, c, thick, dash)
''',
    'fillrect': '''
def fillrect(x, y, w, h, c=1):
    for j in range(y, y + h):
        hline(x, x + w, j, c)
''',
    'line': '''
def line(x0, y0, x1, y1, c=1, thick=1, dash=255):
    dx = abs(x1 - x0)
    dy = 0 - abs(y1 - y0)
    sx = 1
    if x0 > x1:
        sx = -1
    sy = 1
    if y0 > y1:
        sy = -1
    err = dx + dy
    ph = 0
    while True:
        bit = 128 >> (ph & 7)
        if dash & bit:
            if thick <= 1:
                pixel(x0, y0, c)
            else:
                t = 0 - (thick / 2)
                while t < thick - (thick / 2):
                    if abs(dx) >= abs(dy):
                        pixel(x0, y0 + t, c)
                    else:
                        pixel(x0 + t, y0, c)
                    t += 1
        ph += 1
        if x0 == x1 and y0 == y1:
            break
        e2 = err + err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
''',
    'circle': '''
def circle(cx, cy, r, c=1, thick=1, dash=255):
    x = r
    y = 0
    err = 1 - r
    ph = 0
    while x >= y:
        bit = 128 >> (ph & 7)
        if dash & bit:
            if thick <= 1:
                pixel(cx + x, cy + y, c)
                pixel(cx + y, cy + x, c)
                pixel(cx - y, cy + x, c)
                pixel(cx - x, cy + y, c)
                pixel(cx - x, cy - y, c)
                pixel(cx - y, cy - x, c)
                pixel(cx + y, cy - x, c)
                pixel(cx + x, cy - y, c)
            else:
                t = 0 - (thick / 2)
                while t < thick - (thick / 2):
                    pixel(cx + x, cy + y + t, c)
                    pixel(cx + y + t, cy + x, c)
                    pixel(cx - y + t, cy + x, c)
                    pixel(cx - x, cy + y + t, c)
                    pixel(cx - x, cy - y + t, c)
                    pixel(cx - y + t, cy - x, c)
                    pixel(cx + y + t, cy - x, c)
                    pixel(cx + x, cy - y + t, c)
                    t += 1
        ph += 1
        y += 1
        if err < 0:
            err += y + y + 1
        else:
            x -= 1
            err += (y - x) * 2 + 1
''',
    'disc': '''
def disc(cx, cy, r, c=1):
    r2 = r * r
    for dy in range(0 - r, r + 1):
        for dx in range(0 - r, r + 1):
            if dx * dx + dy * dy <= r2:
                pixel(cx + dx, cy + dy, c)
''',
}


# ---- NEW PRELUDE ENTRIES ----

PRELUDE['ellipse'] = '''
def ellipse(cx, cy, rx, ry, c=1):
    x = rx
    y = 0
    rx2 = rx * rx
    ry2 = ry * ry
    dx2 = ry2 * (1 - rx - rx)
    dy2 = rx2
    err2 = 0
    sx2 = ry2 * rx
    sy2 = 0
    while sx2 >= sy2:
        pixel(cx + x, cy + y, c)
        pixel(cx - x, cy + y, c)
        pixel(cx - x, cy - y, c)
        pixel(cx + x, cy - y, c)
        sy2 += rx2
        err2 += dy2
        dy2 += rx2 + rx2
        y += 1
        if err2 + err2 + dx2 > 0:
            sx2 -= ry2
            err2 += dx2
            dx2 += ry2 + ry2
            x -= 1
    x = 0
    y = ry
    dx2 = ry2
    dy2 = rx2 * (1 - ry - ry)
    err2 = 0
    sy2 = rx2 * ry
    sx2 = 0
    while sx2 <= sy2:
        pixel(cx + x, cy + y, c)
        pixel(cx - x, cy + y, c)
        pixel(cx - x, cy - y, c)
        pixel(cx + x, cy - y, c)
        sx2 += ry2
        err2 += dx2
        dx2 += ry2 + ry2
        x += 1
        if err2 + err2 + dy2 > 0:
            sy2 -= rx2
            err2 += dy2
            dy2 += rx2 + rx2
            y -= 1
'''

PRELUDE['fillellipse'] = '''
def fillellipse(cx, cy, rx, ry, c=1):
    ry2 = ry * ry
    rx2 = rx * rx
    for j in range(0 - ry, ry + 1):
        w = rx2 - rx2 * j * j / ry2
        if w < 0:
            w = 0
        xw = 0
        while xw * xw <= w:
            xw += 1
        hline(cx - xw, cx + xw, cy + j, c)
'''

PRELUDE['tri'] = '''
def tri(x0, y0, x1, y1, x2, y2, c=1):
    line(x0, y0, x1, y1, c)
    line(x1, y1, x2, y2, c)
    line(x2, y2, x0, y0, c)
'''

PRELUDE['filltri'] = '''
def filltri(x0, y0, x1, y1, x2, y2, c=1):
    ax = x0
    ay = y0
    bx = x1
    by = y1
    ex = x2
    ey = y2
    tm = 0
    if ay > by:
        tm = ax
        ax = bx
        bx = tm
        tm = ay
        ay = by
        by = tm
    if ay > ey:
        tm = ax
        ax = ex
        ex = tm
        tm = ay
        ay = ey
        ey = tm
    if by > ey:
        tm = bx
        bx = ex
        ex = tm
        tm = by
        by = ey
        ey = tm
    h = ey - ay
    if h == 0:
        return 0
    for y in range(ay, ey + 1):
        xa = ax + (ex - ax) * (y - ay) / h
        if y < by:
            xb = ax + (bx - ax) * (y - ay) / (by - ay + 1)
        else:
            xb = bx + (ex - bx) * (y - by) / (ey - by + 1)
        if xa > xb:
            tm = xa
            xa = xb
            xb = tm
        hline(xa, xb + 1, y, c)
'''

PRELUDE['roundrect'] = '''
def roundrect(x, y, w, h, r, c=1):
    hline(x + r, x + w - r, y, c)
    hline(x + r, x + w - r, y + h - 1, c)
    vline(x, y + r, y + h - r, c)
    vline(x + w - 1, y + r, y + h - r, c)
    cx0 = x + r
    cy0 = y + r
    cx1 = x + w - 1 - r
    cy1 = y + h - 1 - r
    xc = r
    yc = 0
    er2 = 1 - r
    while xc >= yc:
        pixel(cx1 + xc, cy1 + yc, c)
        pixel(cx1 + yc, cy1 + xc, c)
        pixel(cx0 - yc, cy1 + xc, c)
        pixel(cx0 - xc, cy1 + yc, c)
        pixel(cx0 - xc, cy0 - yc, c)
        pixel(cx0 - yc, cy0 - xc, c)
        pixel(cx1 + yc, cy0 - xc, c)
        pixel(cx1 + xc, cy0 - yc, c)
        yc += 1
        if er2 < 0:
            er2 += yc + yc + 1
        else:
            xc -= 1
            er2 += (yc - xc) * 2 + 1
'''

PRELUDE['elapsed'] = '''
def elapsed(t):
    return ticks() - t
'''

# ---- RTC library, taken from libcw (github.com/u68/libcw) ----
# libcw.h register map (volatile __near byte):
#   0xF0C0 SECONDS, 0xF0C1 MINUTES, 0xF0C2 HOURS   - BCD
#   0xF0C3 DAY (1..31), 0xF0C4 WEEK, 0xF0C5 MONTH (1..12) - binary
#   0xF0C6 YEAR - binary offset from 2026, 0xF0C7 ENABLE (1 = run)
# libcw.c semantics kept 1:1:
#   rtc_get_seconds/minutes/hours -> second()/minute()/hour() (BCD decoded)
#   rtc_get_day/month/year        -> day()/month()/year() (year() adds 2026)
#   rtc_get_date's week           -> weekday() (raw RTC_WEEK byte)
#   rtc_set_time                  -> set_time(): writes BCD directly, never
#                                    touches ENABLE (libcw does not stop the
#                                    RTC to write it)
#   rtc_set_date(y, mo, d, week)  -> set_date(): writes DAY/MONTH/YEAR plus
#                                    the WEEK register (auto-computed, 0 =
#                                    Sunday..6 = Saturday - libcw's example
#                                    rtc_set_date(2026, 2, 5, 4) is the
#                                    Thursday of 2026-02-05)
#   rtc_enable/rtc_disable/reset  -> rtc_enable()/rtc_disable()/rtc_reset()
# poke() stores one byte, so set_date(2127, ...) wraps the year byte exactly
# like libcw's (byte)(year - 2026) cast.
PRELUDE['rtc'] = '''
def _dec(b):
    return ((b >> 4) & 15) * 10 + (b & 15)

def _bcd(v):
    return ((v / 10) << 4) | (v % 10)

def second():
    return _dec(peek(0xF0C0))

def minute():
    return _dec(peek(0xF0C1))

def hour():
    return _dec(peek(0xF0C2))

def day():
    return peek(0xF0C3)

def weekday():
    return peek(0xF0C4)

def month():
    return peek(0xF0C5)

def year():
    return peek(0xF0C6) + 2026

# ---- convenience layer on top of the libcw primitives ----
# _rtc[] holds one full RTC read: [0]h [1]m [2]s [3]day [4]week [5]month [6]year
_rtc = [0, 0, 0, 0, 0, 0, 0]

def _snap():
    _rtc[0] = hour()
    _rtc[1] = minute()
    _rtc[2] = second()
    _rtc[3] = day()
    _rtc[4] = weekday()
    _rtc[5] = month()
    _rtc[6] = year()

def rtc_read():
    # one STABLE read of the whole RTC: two snapshots are compared, so a
    # second/minute/day rollover landing in the middle of the read cannot
    # tear the value (h from 12:59 + s from 13:00).
    _snap()
    while True:
        a0 = _rtc[0]
        a1 = _rtc[1]
        a2 = _rtc[2]
        a3 = _rtc[3]
        a4 = _rtc[4]
        a5 = _rtc[5]
        a6 = _rtc[6]
        _snap()
        if a0 == _rtc[0] and a1 == _rtc[1] and a2 == _rtc[2] and a3 == _rtc[3] and a4 == _rtc[4] and a5 == _rtc[5] and a6 == _rtc[6]:
            return

def rtc_alive():
    # 1 if the RTC is ticking (the second byte moves within ~2.5 s), else 0
    rtc_enable()
    a = second()
    t = ticks()
    while elapsed(t) < 20000:
        if second() != a:
            return 1
    return 0

# granular setters - libcw rtc_set_hours/minutes/seconds/day/month/year:
# change ONE field, every other register keeps its value
def set_hours(h):
    poke(0xF0C2, _bcd(h))

def set_minutes(m):
    poke(0xF0C1, _bcd(m))

def set_seconds(s):
    poke(0xF0C0, _bcd(s))

def set_day(d):
    poke(0xF0C3, d)

def set_month(mo):
    poke(0xF0C5, mo)

def set_year(y):
    poke(0xF0C6, y - 2026)
'''
PRELUDE['set_time'] = '''
def set_time(h, m, s):
    poke(0xF0C0, _bcd(s))
    poke(0xF0C1, _bcd(m))
    poke(0xF0C2, _bcd(h))
'''
PRELUDE['set_date'] = '''
def set_date(y, mo, d):
    poke(0xF0C6, y - 2026)
    poke(0xF0C5, mo)
    poke(0xF0C3, d)
    poke(0xF0C4, _weekday(y, mo, d))
'''
PRELUDE['_weekday'] = '''
def _weekday(y, mo, d):
    # Zeller; 0 = Sunday .. 6 = Saturday (matches libcw rtc_set_date example)
    if mo < 3:
        mo += 12
        y -= 1
    k = y % 100
    j = y / 100
    h = (d + (13 * (mo + 1)) / 5 + k + k / 4 + j / 4 + 5 * j) % 7
    return (h + 6) % 7
'''
PRELUDE['rtc_ctl'] = '''
def rtc_enable():
    poke(0xF0C7, 1)

def rtc_disable():
    poke(0xF0C7, 0)

def rtc_reset():
    rtc_disable()
    poke(0xF0C0, 0)
    poke(0xF0C1, 0)
    poke(0xF0C2, 0)
    poke(0xF0C3, 1)
    poke(0xF0C4, 1)
    poke(0xF0C5, 1)
    poke(0xF0C6, 0)
'''

# waitkey(ms): wait up to ms milliseconds but return the moment a NEW key
# press arrives. Edge semantics - a HELD key is reported once, not once per
# loop, so clock/game loops can drop their manual last-key bookkeeping.
# Returns the scan code of the new press, or -1 when the time ran out.
# The timeout is paced by delay_ms(1) - NOT by ticks()/elapsed(): delay_ms
# re-arms Timer0 from scratch on every chunk (clear FCON bit 1, TM0D, TM0C=0,
# TM0CON=0101, exactly libcw __delay()), which is the one timer dance proven
# to run on real hardware. A raw ticks() read can sit still if the OS leaves
# the timer parked, and that froze the whole loop until a key was pressed.
# Any ms >= 0 works (delay_ms itself chunks at 256 ms).
PRELUDE['waitkey'] = '''
_wkl = -1

def waitkey(ms):
    global _wkl
    if ms < 0:
        ms = 0
    while ms > 0:
        k = key()
        if k != _wkl:
            _wkl = k
            if k != -1:
                return k
        delay_ms(1)
        ms -= 1
    k = key()
    if k != _wkl:
        _wkl = k
        if k != -1:
            return k
    return -1
'''

# draw_time(x, y) / draw_date(x, y): draw HH:MM:SS / DD/MM/YY straight from
# the RTC (stable read inside), 8 px digit pitch - the layout of the clock
# demos. No decode-and-format code needed in the program.
PRELUDE['drawtime'] = '''
def draw_time(x, y):
    rtc_read()
    num(x, y, _rtc[0] / 10)
    num(x + 8, y, _rtc[0] % 10)
    text(x + 18, y, ":")
    num(x + 26, y, _rtc[1] / 10)
    num(x + 34, y, _rtc[1] % 10)
    text(x + 44, y, ":")
    num(x + 52, y, _rtc[2] / 10)
    num(x + 60, y, _rtc[2] % 10)

def draw_date(x, y):
    rtc_read()
    num(x, y, _rtc[3] / 10)
    num(x + 8, y, _rtc[3] % 10)
    text(x + 18, y, "/")
    num(x + 26, y, _rtc[5] / 10)
    num(x + 34, y, _rtc[5] % 10)
    text(x + 44, y, "/")
    num(x + 52, y, _rtc[6] % 100 / 10)
    num(x + 60, y, _rtc[6] % 10)
'''

PRELUDE['strlen'] = '''
def strlen(s):
    n = 0
    while _rpeek(s + n) != 0:
        n += 1
    return n
'''

PRELUDE['strcmp'] = '''
def strcmp(a, b):
    while True:
        ca = _rpeek(a)
        cb = _rpeek(b)
        if ca != cb:
            return ca - cb
        if ca == 0:
            return 0
        a += 1
        b += 1
'''

PRELUDE['strcpy'] = '''
def strcpy(dst, src):
    i = 0
    while True:
        c2 = peek(src + i)
        poke(dst + i, c2)
        if c2 == 0:
            break
        i += 1
    return dst
'''

PRELUDE['atoi'] = '''
def atoi(s):
    n = 0
    neg = 0
    c3 = _rpeek(s)
    if c3 == 45:
        neg = 1
        s += 1
        c3 = _rpeek(s)
    while c3 >= 48 and c3 <= 57:
        n = n * 10 + (c3 - 48)
        s += 1
        c3 = _rpeek(s)
    if neg:
        return 0 - n
    return n
'''

PRELUDE['itoa'] = '''
def itoa(buf, n, base):
    if n == -32768:
        poke(buf, 45)
        poke(buf + 1, 51)
        poke(buf + 2, 50)
        poke(buf + 3, 55)
        poke(buf + 4, 54)
        poke(buf + 5, 56)
        poke(buf + 6, 0)
        return buf
    pos = 0
    neg = 0
    if n < 0:
        neg = 1
        n = 0 - n
    if n == 0:
        poke(buf, 48)
        poke(buf + 1, 0)
        return buf
    d4 = n
    while d4 > 0:
        r4 = d4 % base
        d4 = d4 / base
        if r4 < 10:
            poke(buf + 7 + pos, 48 + r4)
        else:
            poke(buf + 7 + pos, 87 + r4)
        pos += 1
    if neg:
        poke(buf + 7 + pos, 45)
        pos += 1
    i4 = 0
    while i4 < pos:
        poke(buf + i4, peek(buf + 7 + pos - 1 - i4))
        i4 += 1
    poke(buf + pos, 0)
    return buf
'''

PRELUDE['getc'] = '''
def getc():
    return wait_key()
'''

# ---- input_num: type a number on the calculator keypad ----
# The digit keys do NOT have contiguous scan codes (cw: K_0=11, K_9=45, K_1=63),
# so a `k >= K_0 and k <= K_9` range test is wrong twice over: K_1/K_2/K_3/K_4/
# K_5/K_6/K_7/K_8 fall outside [K_0..K_9] and get ignored, while K_DOT/K_MENU/
# K_DIV/K_MINUS/K_RIGHT/K_DOWN/K_DEL/K_MUL/K_PLUS/K_UP/K_LEFT fall inside and
# get read as digits. Keys are matched one by one here, like getc_tap does.
# Display: the field is redrawn in place (clear_rect of its own box only) and
# flip() is used ONLY when the caller draws buffered (draw mode at 0xE800), so
# a direct-draw caller keeps its labels on screen and a buffered caller sees
# the value on every keystroke. flip() in direct mode would push the EMPTY back
# buffer over the LCD and blank the screen.
# K_MINUS (and K_NEG, the (-) key next to the digits on cw) toggles the sign,
# DEL backspaces, EXE confirms, AC cancels with -32768. default != 0 is shown
# and kept; the first typed digit REPLACES it. Values stay within 16 bits:
# digits that would push past 32767 are dropped.
PRELUDE['input_num'] = '''
def _dig(k):
    if k == K_0:
        return 0
    elif k == K_1:
        return 1
    elif k == K_2:
        return 2
    elif k == K_3:
        return 3
    elif k == K_4:
        return 4
    elif k == K_5:
        return 5
    elif k == K_6:
        return 6
    elif k == K_7:
        return 7
    elif k == K_8:
        return 8
    elif k == K_9:
        return 9
    return -1

def input_num(x, y, default=0):
    n5 = default
    sg5 = 0
    if n5 < 0:
        sg5 = 1
        n5 = 0 - n5
        if n5 < 0:
            n5 = 32767
    edit5 = 0
    m5 = peek(0xE800)
    while True:
        clear_rect(x, y, 80, 10)
        if sg5 and n5 != 0:
            char(x, y, 45)
            num(x + 6, y, n5)
        else:
            num(x, y, n5)
        if m5:
            flip()
        k5 = wait_key()
        if k5 == K_AC:
            return -32768
        if k5 == K_EXE:
            if sg5:
                return 0 - n5
            return n5
        if k5 == K_MINUS or k5 == K_NEG:
            sg5 = 1 - sg5
            edit5 = 1
        elif k5 == K_DEL:
            n5 = n5 / 10
            edit5 = 1
        else:
            d5 = _dig(k5)
            if d5 >= 0:
                if edit5 == 0 or n5 == 0:
                    n5 = d5
                elif n5 < 3276:
                    n5 = n5 * 10 + d5
                elif n5 == 3276 and d5 < 8:
                    n5 = n5 * 10 + d5
                edit5 = 1
'''


# ---- clip ----
# clip(x, y, w, h): set the drawing clip window; clip() with no arguments
# (or clip(0, 0, 192, 64)) resets it to the full screen. The window lives in
# the runtime state bytes 0xE801-0xE804 (x0, x1, y0, y1) which hline/vline
# read and __rt_init initialises to the full screen - ported from the wiz7
# line where this design was already proven.
PRELUDE['clip'] = '''
def clip(x=0, y=0, w=192, h=64):
    x1 = x + w
    y1 = y + h
    if x < 0:
        x = 0
    if y < 0:
        y = 0
    if x1 > 192:
        x1 = 192
    if y1 > 64:
        y1 = 64
    poke(0xE801, x)
    poke(0xE802, x1)
    poke(0xE803, y)
    poke(0xE804, y1)
'''

# ---- sprite with rot and flip ----
# sprite(x, y, w, h, data, cao=8, dai=6, rot=0)
# rot: 0=normal, 1=90CW, 2=180, 3=270CW
# w/h in sprite-cells; cao/dai = pixels per cell (height, width)
# negative cao = flip vertical; negative dai = flip horizontal
# data is rom8 or pointer (address of bytes, row-major, 1 bit per pixel packed MSB first)
# This is the "smart" PRELUDE version that interprets data as a pointer to rom data.
PRELUDE['sprite_rot'] = '''
def _sprite_px(sx, sy, pw, ph, data, rot, flipx, flipy):
    bw = (pw + 7) / 8
    for py in range(0, ph):
        for px in range(0, pw):
            byte_idx = py * bw + px / 8
            bit_pos = 7 - (px & 7)
            bval = _rpeek(data + byte_idx)
            if (bval >> bit_pos) & 1:
                rx = px
                ry = py
                if flipx:
                    rx = pw - 1 - px
                if flipy:
                    ry = ph - 1 - py
                if rot == 0:
                    pixel(sx + rx, sy + ry)
                elif rot == 1:
                    pixel(sx + ph - 1 - ry, sy + rx)
                elif rot == 2:
                    pixel(sx + pw - 1 - rx, sy + ph - 1 - ry)
                elif rot == 3:
                    pixel(sx + ry, sy + pw - 1 - rx)
def sprite(x, y, pw, ph, data, w=1, h=1, rot=0):
    fpw = pw
    fph = ph
    fx = 0
    fy = 0
    if fpw < 0:
        fx = 1
        fpw = 0 - fpw
    if fph < 0:
        fy = 1
        fph = 0 - fph
    _sprite_px(x, y, fpw, fph, data, rot, fx, fy)
'''

# ---- getc_tap: multi-tap key reader ----
# Returns char code (ASCII 'A'..'Z', '0'..'9') via multi-tap.
# T9 style: press same key repeatedly to cycle through letters on that key.
# Timeout (via ticks): ~800ms inactivity commits current char. ticks() runs at
# 8000 ticks/s (Timer0 per libcw TICKS_PER_MS=8), so 800ms = 6400 ticks; a held
# key advances the cycle every 100ms (800 ticks).
# Returns committed char code, -32768 for AC (cancel), -2 for EXE (confirm)
# and -3 for DEL (backspace). EXE/DEL arriving while a character is still
# pending first commit that character; the control code is remembered in
# _gc_pend and returned by the NEXT call, so no typed letter is ever lost.
# Key mappings for cwii number keys (T9 layout):
#   K_1 -> '.' ',' '!' '?'
#   K_2 -> 'A' 'B' 'C'
#   K_3 -> 'D' 'E' 'F'
#   K_4 -> 'G' 'H' 'I'
#   K_5 -> 'J' 'K' 'L'
#   K_6 -> 'M' 'N' 'O'
#   K_7 -> 'P' 'Q' 'R' 'S'
#   K_8 -> 'T' 'U' 'V'
#   K_9 -> 'W' 'X' 'Y' 'Z'
#   K_0 -> ' '
PRELUDE['getc_tap'] = '''
_gc_pend = 0

def getc_tap():
    global _gc_pend
    if _gc_pend:
        c7 = _gc_pend
        _gc_pend = 0
        return c7
    last_k = -1
    tap_n = 0
    tap_t = 0
    while True:
        k6 = key()
        if k6 == K_AC:
            return -32768
        if k6 == K_EXE or k6 == K_DEL:
            if last_k != -1:
                _gc_pend = -2
                if k6 == K_DEL:
                    _gc_pend = -3
                return _tap_char(last_k, tap_n)
            if k6 == K_EXE:
                return -2
            return -3
        if k6 != -1 and k6 != last_k:
            if last_k != -1:
                return _tap_char(last_k, tap_n)
            last_k = k6
            tap_n = 0
            tap_t = ticks()
        elif k6 == last_k:
            if ticks() - tap_t > 800:
                tap_n += 1
                tap_t = ticks()
        elif k6 == -1 and last_k != -1:
            if ticks() - tap_t > 6400:
                c6 = _tap_char(last_k, tap_n)
                last_k = -1
                tap_n = 0
                return c6
def _tap_char(k, n):
    if k == K_1:
        return 46 + n % 4
    if k == K_2:
        return 65 + n % 3
    if k == K_3:
        return 68 + n % 3
    if k == K_4:
        return 71 + n % 3
    if k == K_5:
        return 74 + n % 3
    if k == K_6:
        return 77 + n % 3
    if k == K_7:
        return 80 + n % 4
    if k == K_8:
        return 84 + n % 3
    if k == K_9:
        return 87 + n % 4
    if k == K_0:
        return 32
    return 63
'''

# ---- input_tap: read a multi-tap string into buffer ----
# input_tap(buf, max_len, x, y): fill buf with null-terminated string,
# show current input at (x,y). EXE commits (returns length), DEL erases last
# char, AC cancels (returns -1, buf cleared). flip() only when the caller
# draws buffered (mode byte at 0xE800) - in direct mode flip would blank the
# screen (same rule as input_num). A release-gate at entry keeps the key
# that OPENED the screen (e.g. EXE) from confirming an empty string.
PRELUDE['input_tap'] = '''
def input_tap(bptr, max_len, x, y):
    pos6 = 0
    m6 = peek(0xE800)
    poke(bptr, 0)
    while key() != -1:
        pass
    while True:
        c6 = getc_tap()
        if c6 == -32768:
            return -1
        if c6 == -2:
            return pos6
        if c6 == -3:
            if pos6 > 0:
                pos6 -= 1
                poke(bptr + pos6, 0)
        elif pos6 < max_len - 1:
            poke(bptr + pos6, c6)
            pos6 += 1
            poke(bptr + pos6, 0)
        clear_rect(x, y, 120, 10)
        text(x, y, bptr)
        if m6:
            flip()
'''

# ---- input_pad: on-screen keyboard ----
# input_pad(buf, max_len, x, y): on-screen keyboard redrawn as a real key grid.
#   row 0:  a b c d e f g h i j k l m n      (14 keys)
#   row 1:  o p q r s t u v w x y z . ,
#   row 2:  0 1 2 3 4 5 6 7 8 9 ? ! - :      (dedicated digit row)
#   row 3:  [ Aa ] [    SPC    ] [ DEL ] [ OK ]
# ▲▼◄► move (rows wrap), EXE presses the highlighted key, DEL backspaces,
# ANS or the OK key confirms (returns length), AC cancels (returns -1).
# Aa toggles caps: the 26 letter keys redraw in the other case and the key
# label flips Aa/AA. SPC appends a space. The PHYSICAL digit keys (and the
# decimal key) type straight into the field, so numbers can be typed without
# walking the cursor. The selected key is shown INVERTED (invert_rect over the
# key interior - glyph included), the grid lines are shared key borders, so it
# looks like a real keypad. The pad is drawn ONCE and afterwards only the
# selection invert / the input line are touched (fast on hardware too).
# flip() only in buffered mode, like input_num/input_tap. A release-gate at
# entry keeps the key that OPENED the screen (e.g. EXE) from pressing a key.
# x/y place the input FIELD (y usually 12); the pad fills the screen below it.
PRELUDE['input_pad'] = '''
# Grid-line keyboard, 192x63, field at y=0..9, keyboard y=10..62
# 4 char rows (11px each) + 1 control row (9px) = 53px
# 10 cols (19px each), grid lines shared between keys
# row 0: a-j  row 1: k-t  row 2: u-z 0-3  row 3: 4-9 . , ? !
# control: [Aa=29][SPC=100][DEL=31][OK=29] (1px gaps, total=191)
_pad_cs = "abcdefghijklmnopqrstuvwxyz0123456789.,?!"
_pad_up = 0

def _pad_ch(r, c):
    global _pad_up
    ch = _rpeek(_pad_cs + r * 10 + c)
    if _pad_up and ch >= 97 and ch <= 122:
        ch = ch - 32
    return ch

def _pdig(k):
    if k == K_0:
        return 48
    elif k == K_1:
        return 49
    elif k == K_2:
        return 50
    elif k == K_3:
        return 51
    elif k == K_4:
        return 52
    elif k == K_5:
        return 53
    elif k == K_6:
        return 54
    elif k == K_7:
        return 55
    elif k == K_8:
        return 56
    elif k == K_9:
        return 57
    return 0

def _pad_draw_grid():
    clear_rect(0, 10, 192, 53)
    hline(0, 192, 10)
    hline(0, 192, 21)
    hline(0, 192, 32)
    hline(0, 192, 43)
    hline(0, 192, 54)
    hline(0, 192, 62)
    c = 0
    while c <= 10:
        vline(1 + c * 19, 10, 54)
        c += 1
    r = 0
    while r < 4:
        c = 0
        while c < 10:
            char(7 + c * 19, 11 + r * 11, _pad_ch(r, c))
            c += 1
        r += 1
    vline(1,   54, 63)
    vline(30,  54, 63)
    vline(131, 54, 63)
    vline(162, 54, 63)
    vline(191, 54, 63)
    if _pad_up:
        text(4,  55, "AA")
    else:
        text(4,  55, "Aa")
    text(55, 55, "SPACE")
    text(134, 55, "DEL")
    text(165, 55, "OK")

def _pad_sel(r, c):
    if r < 4:
        invert_rect(2 + c * 19, 11 + r * 11, 18, 10)
    else:
        if c == 0:
            invert_rect(2,   55, 28, 8)
        elif c == 1:
            invert_rect(31,  55, 100, 8)
        elif c == 2:
            invert_rect(132, 55, 29, 8)
        else:
            invert_rect(163, 55, 28, 8)

def _pad_redraw_letters():
    r = 0
    while r < 2:
        c = 0
        while c < 10:
            clear_rect(2 + c * 19, 11 + r * 11, 18, 10)
            char(7 + c * 19, 11 + r * 11, _pad_ch(r, c))
            c += 1
        r += 1
    clear_rect(2, 55, 28, 8)
    if _pad_up:
        text(4, 55, "AA")
    else:
        text(4, 55, "Aa")

def _pad_field(b, n, x, fw, m):
    clear_rect(x + 1, 1, fw - 2, 8)
    text(x + 2, 1, b)
    char(x + 2 + n * 6, 1, 95)
    if m:
        flip()

def input_pad(bptr, max_len, x, y):
    global _pad_up
    _pad_up = 0
    pad_r = 0
    pad_c = 0
    pos7 = 0
    m7 = peek(0xE800)
    fw7 = max_len * 6 + 8
    if fw7 > 190:
        fw7 = 190
    poke(bptr, 0)
    while key() != -1:
        pass
    clear()
    rect(x, 0, fw7, 10)
    _pad_draw_grid()
    _pad_field(bptr, 0, x, fw7, 0)
    _pad_sel(0, 0)
    if m7:
        flip()
    while True:
        k7 = wait_key()
        if k7 == K_AC:
            return -1
        if k7 == K_ANS:
            return pos7
        asc8 = _pdig(k7)
        if asc8 > 0:
            if pos7 < max_len - 1:
                poke(bptr + pos7, asc8)
                pos7 += 1
                poke(bptr + pos7, 0)
                _pad_field(bptr, pos7, x, fw7, m7)
        if k7 == K_DOT:
            if pos7 < max_len - 1:
                poke(bptr + pos7, 46)
                pos7 += 1
                poke(bptr + pos7, 0)
                _pad_field(bptr, pos7, x, fw7, m7)
        if k7 == K_DEL:
            if pos7 > 0:
                _pad_sel(pad_r, pad_c)
                pos7 -= 1
                poke(bptr + pos7, 0)
                _pad_field(bptr, pos7, x, fw7, m7)
                _pad_sel(pad_r, pad_c)
        if k7 == K_EXE:
            if pad_r < 4:
                if pos7 < max_len - 1:
                    poke(bptr + pos7, _pad_ch(pad_r, pad_c))
                    pos7 += 1
                    poke(bptr + pos7, 0)
                    _pad_field(bptr, pos7, x, fw7, m7)
            else:
                if pad_c == 0:
                    _pad_sel(pad_r, pad_c)
                    _pad_up = 1 - _pad_up
                    _pad_redraw_letters()
                    _pad_sel(pad_r, pad_c)
                    if m7:
                        flip()
                elif pad_c == 1:
                    if pos7 < max_len - 1:
                        poke(bptr + pos7, 32)
                        pos7 += 1
                        poke(bptr + pos7, 0)
                        _pad_field(bptr, pos7, x, fw7, m7)
                elif pad_c == 2:
                    if pos7 > 0:
                        pos7 -= 1
                        poke(bptr + pos7, 0)
                        _pad_field(bptr, pos7, x, fw7, m7)
                else:
                    return pos7
        if k7 == K_UP:
            _pad_sel(pad_r, pad_c)
            if pad_r == 0:
                pad_r = 4
                if pad_c >= 7:
                    pad_c = 3
                elif pad_c >= 3:
                    pad_c = 2
                elif pad_c >= 1:
                    pad_c = 1
                else:
                    pad_c = 0
            elif pad_r == 4:
                pad_r = 3
                if pad_c == 0:
                    pad_c = 0
                elif pad_c == 1:
                    pad_c = 4
                elif pad_c == 2:
                    pad_c = 7
                else:
                    pad_c = 9
            else:
                pad_r -= 1
            _pad_sel(pad_r, pad_c)
            if m7:
                flip()
        if k7 == K_DOWN:
            _pad_sel(pad_r, pad_c)
            if pad_r == 3:
                pad_r = 4
                if pad_c >= 7:
                    pad_c = 3
                elif pad_c >= 4:
                    pad_c = 2
                elif pad_c >= 1:
                    pad_c = 1
                else:
                    pad_c = 0
            elif pad_r == 4:
                pad_r = 0
                if pad_c == 0:
                    pad_c = 0
                elif pad_c == 1:
                    pad_c = 4
                elif pad_c == 2:
                    pad_c = 7
                else:
                    pad_c = 9
            else:
                pad_r += 1
            _pad_sel(pad_r, pad_c)
            if m7:
                flip()
        if k7 == K_LEFT:
            _pad_sel(pad_r, pad_c)
            if pad_r < 4:
                pad_c = (pad_c + 9) % 10
            else:
                pad_c = (pad_c + 3) % 4
            _pad_sel(pad_r, pad_c)
            if m7:
                flip()
        if k7 == K_RIGHT:
            _pad_sel(pad_r, pad_c)
            if pad_r < 4:
                pad_c = (pad_c + 1) % 10
            else:
                pad_c = (pad_c + 1) % 4
            _pad_sel(pad_r, pad_c)
            if m7:
                flip()
'''

PRELUDE['word'] = '''
def _rdw(a):
    return peek(a) + peek(a + 1) * 256

def _wrw(a, v):
    poke(a, v & 255)
    poke(a + 1, (v >> 8) & 255)

def peekw(a):
    return _rdw(a)

def pokew(a, v):
    _wrw(a, v)
'''   # WIZ-MOD: peekw/pokew - doc/ghi 16-bit tai dia chi RAM tuyet doi (port loop copy word tu firmware)

PRELUDE['alloc'] = '''
def alloc(n):
    if n < 1:
        return 0
    need = n
    if need & 1:
        need += 1
    need += 2
    p = _rdw(0xE818)
    hi = _rdw(0xE81A)
    while p < hi:
        h = _rdw(p)
        sz = h & 0x7FFF
        if h < 0 and sz >= need:
            if sz - need >= 4:
                _wrw(p, need)
                _wrw(p + need, (sz - need) | 0x8000)
            else:
                _wrw(p, sz)
            return p + 2
        p += sz
    return 0
'''

PRELUDE['free'] = '''
def _merge():
    q = _rdw(0xE818)
    hi = _rdw(0xE81A)
    while q < hi:
        h = _rdw(q)
        if h < 0:
            sz = h & 0x7FFF
            n2 = q + sz
            while n2 < hi:
                h2 = _rdw(n2)
                if h2 >= 0:
                    break
                sz += h2 & 0x7FFF
                n2 = q + sz
            _wrw(q, sz | 0x8000)
            q += sz
        else:
            q += h
    return 0

def free(p):
    if p == 0:
        return 0
    _wrw(p - 2, _rdw(p - 2) - 32768)
    _merge()
    return 0
'''

# ---- RAM file system ON the heap (nodes are ordinary heap blocks) ----
# f_save(name, buf, n) / f_load(name, buf, max) / f_exists(name) / f_remove(name).
# The list head is the word at 0xE81C; each node is an 18-byte heap block:
# [0..11] name (NUL padded) [12..13] next [14..15] data ptr [16..17] length.
# Data is a separate heap block, so removing a file gives the memory back to
# alloc(). Names are string literals (read with _rpeek, like text()) - on the
# cwapp target a RAM buffer as the name would be read in the wrong segment.
PRELUDE['file'] = '''
def _cpy(_dst, _src, n):
    for i in range(0, n):
        _dst[i] = peek(_src + i)
    return 0

def _feq(_nm, _node):
    k = 0
    while k < 12:
        c = _rpeek(_nm + k)
        if c != peek(_node + k):
            return 0
        if c == 0:
            return 1
        k += 1
    return 1

def _fnode(_nm):
    p = _rdw(0xE81C)
    while p != 0:
        if _feq(_nm, p):
            return p
        p = _rdw(p + 12)
    return 0

def _fsnew(_nm):
    _node = alloc(18)
    if _node == 0:
        return 0
    k = 0
    while k < 12:
        _node[k] = 0
        k += 1
    k = 0
    while k < 12:
        c = _rpeek(_nm + k)
        if c == 0:
            break
        _node[k] = c
        k += 1
    if k == 12:
        free(_node)
        return 0
    _wrw(_node + 12, _rdw(0xE81C))
    _wrw(0xE81C, _node)
    _wrw(_node + 14, 0)
    _wrw(_node + 16, 0)
    return _node

def f_save(_nm, _buf, n):
    if n < 0:
        return 0
    _node = _fnode(_nm)
    if _node == 0:
        _node = _fsnew(_nm)
        if _node == 0:
            return 0
    _old = _rdw(_node + 14)
    if _old != 0:
        free(_old)
    _wrw(_node + 14, 0)
    _wrw(_node + 16, 0)
    if n == 0:
        return 1
    _data = alloc(n)
    if _data == 0:
        return 0
    _cpy(_data, _buf, n)
    _wrw(_node + 14, _data)
    _wrw(_node + 16, n)
    return 1

def f_load(_nm, _buf, mx):
    _node = _fnode(_nm)
    if _node == 0:
        return -1
    n = _rdw(_node + 16)
    if n > mx:
        n = mx
    _data = _rdw(_node + 14)
    if _data != 0 and n > 0:
        _cpy(_buf, _data, n)
    return n

def f_exists(_nm):
    if _fnode(_nm) != 0:
        return 1
    return 0

def f_remove(_nm):
    _prev = 0
    p = _rdw(0xE81C)
    while p != 0:
        if _feq(_nm, p):
            _nxt = _rdw(p + 12)
            if _prev == 0:
                _wrw(0xE81C, _nxt)
            else:
                _wrw(_prev + 12, _nxt)
            d = _rdw(p + 14)
            if d != 0:
                free(d)
            free(p)
            return 1
        _prev = p
        p = _rdw(p + 12)
    return 0
'''

from font6x8 import FONT
from font_vn import VN_CODE
PRELUDE['font'] = 'rom8 _font = [' + ', '.join(str(v) for v in FONT) + ']\n'
PRELUDE['char'] = '''
def char(x, y, c):
    if c < 32 or c > 126:
        c = 63
    base = (c - 32) * 8
    for r in range(0, 8):
        bits = _font[base + r]
        for k in range(0, 6):
            pixel(x + k, y + r, (bits & 128) != 0)
            bits = bits + bits
'''
PRELUDE['text'] = '''
def text(x, y, s):
    c = _rpeek(s)
    while c != 0:
        char(x, y, c)
        x += 6
        s += 1
        c = _rpeek(s)
    return x
'''
PRELUDE['num'] = '''
def num(x, y, n):
    if n == -32768:
        return text(x, y, "-32768")
    if n < 0:
        char(x, y, 45)
        x += 6
        n = 0 - n
    d = 10000
    shown = 0
    while d > 0:
        q = n / d
        n = n - q * d
        if q > 0 or shown or d == 1:
            char(x, y, 48 + q)
            x += 6
            shown = 1
        d = d / 10
    return x
'''
PRELUDE['charz'] = '''
def charz(x, y, c, h, w):
    if c < 32 or c > 126:
        c = 63
    base = (c - 32) * 8
    sr = 0
    er = 0
    for r in range(0, h):
        bits = _font[base + sr]
        sc = 0
        ec = 0
        m = 128
        for k in range(0, w):
            pixel(x + k, y + r, (bits & m) != 0)
            ec += 6
            while ec >= w:
                ec -= w
                sc += 1
                m = m >> 1
        er += 8
        while er >= h:
            er -= h
            sr += 1
'''
PRELUDE['textz'] = '''
def textz(x, y, h, w, s):
    c = _rpeek(s)
    while c != 0:
        charz(x, y, c, h, w)
        x += w
        s += 1
        c = _rpeek(s)
    return x
'''
PRELUDE['numz'] = '''
def numz(x, y, h, w, n):
    if n == -32768:
        return textz(x, y, h, w, "-32768")
    if n < 0:
        charz(x, y, 45, h, w)
        x += w
        n = 0 - n
    d = 10000
    shown = 0
    while d > 0:
        q = n / d
        n = n - q * d
        if q > 0 or shown or d == 1:
            charz(x, y, 48 + q, h, w)
            x += w
            shown = 1
        d = d / 10
    return x
'''
# ---- Vietnamese: used INSTEAD of PRELUDE['char'] / ['charz'] when the program has a Vietnamese string
# (or `const VIET = 1`). Byte codes 128..255 and 1..6 are the 134 Vietnamese letters (see font_vn.py);
# each glyph is 13 rows = 4 rows of marks above the 8-row cell, the cell itself, 1 row below (dot).
# The rows outside the cell are ADD-ONLY (pixels are set, never cleared) so they cannot wipe the line above.
from font_vn import font_table, GLYPH_ROWS, OVER_ABOVE
PRELUDE_VN = {}
PRELUDE_VN['font_vn'] = 'rom8 _fontvn = [' + ', '.join(str(v) for v in font_table()) + ']\n'
PRELUDE_VN['char'] = '''
def _chvn(x, y, g):
    base = g * 13
    for r in range(0, 13):
        bits = _fontvn[base + r]
        inside = r > 3 and r < 12
        for k in range(0, 6):
            on = (bits & 128) != 0
            if on or inside:
                pixel(x + k, y + r - 4, on)
            bits = bits + bits

def char(x, y, c):
    if c >= 128:
        _chvn(x, y, c - 128)
        return 0
    if c > 0 and c < 7:
        _chvn(x, y, c + 127)
        return 0
    if c < 32 or c > 126:
        c = 63
    base = (c - 32) * 8
    for r in range(0, 8):
        bits = _font[base + r]
        for k in range(0, 6):
            pixel(x + k, y + r, (bits & 128) != 0)
            bits = bits + bits
'''
PRELUDE_VN['charz'] = '''
def _chvnz(x, y, g, h, w):
    base = g * 13
    off = (4 * h + 4) / 8
    dh = (13 * h + 7) / 8
    for dr in range(0, dh):
        sr = (dr * 8) / h
        bits = _fontvn[base + sr]
        inside = sr > 3 and sr < 12
        for k in range(0, w):
            on = (bits & (128 >> ((k * 6) / w))) != 0
            if on or inside:
                pixel(x + k, y + dr - off, on)

def charz(x, y, c, h, w):
    if c >= 128:
        _chvnz(x, y, c - 128, h, w)
        return 0
    if c > 0 and c < 7:
        _chvnz(x, y, c + 127, h, w)
        return 0
    if c < 32 or c > 126:
        c = 63
    base = (c - 32) * 8
    sr = 0
    er = 0
    for r in range(0, h):
        bits = _font[base + sr]
        sc = 0
        ec = 0
        m = 128
        for k in range(0, w):
            pixel(x + k, y + r, (bits & m) != 0)
            ec += 6
            while ec >= w:
                ec -= w
                sc += 1
                m = m >> 1
        er += 8
        while er >= h:
            er -= h
            sr += 1
'''

# sprite() defined in PRELUDE['sprite_rot']

PRELUDE['draw'] = '''
def _hexv(c):
    if c > 57:
        return (c | 32) - 87
    return c - 48

def draw(x, y, h, w, s):
    bw = (w + 7) >> 3
    for r in range(0, h):
        for k in range(0, w):
            i = (r * bw + (k >> 3)) * 2 + ((k & 4) >> 2)
            if _hexv(_rpeek(s + i)) & (8 >> (k & 3)):
                pixel(x + k, y + r)
'''


class WizError(Exception):
    def __init__(self, msg, line=0):
        super().__init__('line %d: %s' % (line, msg) if line else msg)


# ------------------------------------------------------------------ lexer
TOKEN_RE = re.compile(r'''
    (?P<num>0[xX][0-9a-fA-F]+|\d+)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<op><<=|>>=|==|!=|<=|>=|<<|>>|//|\+=|-=|\*=|/=|%=|&=|\|=|\^=|[-+*/%&|^~<>=():,\[\]])
  | (?P<ws>[ ]+)
''', re.X)


def strip_comment(raw):
    """cut at the first '#' that is not inside a string literal"""
    inq = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if inq:
            if c == '\\':
                i += 1
            elif c == '"':
                inq = False
        elif c == '"':
            inq = True
        elif c == '#':
            return raw[:i]
        i += 1
    return raw


ESC = {'n': 10, 't': 9, '0': 0, '\\': 92, '"': 34}


def decode_str(lit, ln):
    """string literal -> list of byte codes. ASCII 32..126 as is; Vietnamese letters become their one-byte code
    (font_vn.py); the source may use precomposed (NFC) or combining (NFD) Vietnamese."""
    lit = unicodedata.normalize('NFC', lit)
    out = []
    i = 1
    while i < len(lit) - 1:
        c = lit[i]
        if c == '\\':
            i += 1
            e = lit[i]
            if e not in ESC:
                raise WizError('unknown escape \\%s in string' % e, ln)
            out.append(ESC[e])
        elif c in VN_CODE:
            out.append(VN_CODE[c])
        else:
            if ord(c) > 126 or ord(c) < 32:
                raise WizError('only printable ASCII and Vietnamese letters are allowed in strings (got %r)' % c, ln)
            out.append(ord(c))
        i += 1
    return out


def has_vn(codes):
    """True if a decoded string holds Vietnamese codes (128..255 or 1..6)"""
    return any(b >= 128 or 1 <= b <= 6 for b in codes)


def lex(src):
    toks = []
    indents = [0]
    for ln, raw in enumerate(src.replace('\r', '').split('\n'), 1):
        line = strip_comment(raw).rstrip()
        # convert leading tabs to 4 spaces each so tab-indented files work
        expanded = []
        for ch in line:
            if ch == '\t':
                expanded.append('    ')
            else:
                expanded.append(ch)
        line = ''.join(expanded)
        if not line.strip():
            continue
        ind = len(line) - len(line.lstrip(' '))
        stripped = line.strip()
        # WIZ-MOD: dong nhan tuyet doi "NAME:" khong lam thay doi cap indent
        # (neu khong, lexer coi no la DEDENT va lam dut khoi len cua ham)
        # LUU Y: phai loai tru KEYWORD (vd "else:") neu khong se pha vo if/else
        m_lab = re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*:', stripped)
        is_label_line = m_lab is not None and m_lab.group(0)[:-1] not in KEYWORDS
        if is_label_line:
            ind = indents[-1]
        if ind > indents[-1]:
            indents.append(ind)
            toks.append(('INDENT', None, ln))
        while ind < indents[-1]:
            indents.pop()
            toks.append(('DEDENT', None, ln))
            if ind > indents[-1]:
                raise WizError('inconsistent indentation', ln)
        pos = ind if not is_label_line else (len(line) - len(stripped))
        while pos < len(line):
            m = TOKEN_RE.match(line, pos)
            if not m:
                raise WizError('unexpected character %r' % line[pos], ln)
            pos = m.end()
            k = m.lastgroup
            if k == 'ws':
                continue
            if k == 'num':
                toks.append(('num', int(m.group(), 0), ln))
            elif k == 'str':
                toks.append(('str', decode_str(m.group(), ln), ln))
            elif k == 'name':
                s = m.group()
                toks.append(('kw' if s in KEYWORDS else 'name', s, ln))
            else:
                toks.append(('op', m.group(), ln))
        toks.append(('NEWLINE', None, ln))
    while len(indents) > 1:
        indents.pop()
        toks.append(('DEDENT', None, 0))
    toks.append(('EOF', None, 0))
    return toks


# ----------------------------------------------------------------- parser
def wrap16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def fold(op, a, b):
    """compile-time evaluation with exactly the runtime's int16 semantics; None = do not fold"""
    if op == '+': return wrap16(a + b)
    if op == '-': return wrap16(a - b)
    if op == '*': return wrap16(a * b)
    if op == '&': return wrap16(a & b)
    if op == '|': return wrap16(a | b)
    if op == '^': return wrap16(a ^ b)
    if op == '<<' and 0 <= b <= 15: return wrap16(a << b)
    if op == '>>' and 0 <= b <= 15: return a >> b
    if op in ('/', '%'):
        if b == 0: return 0
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0): q = -q
        return wrap16(q if op == '/' else a - q * b)
    return None


class Parser:
    def __init__(self, toks, consts=None):
        self.t = toks
        self.i = 0
        self.consts = consts if consts is not None else {}
        self.overridden = set()
        self.builtin = set(self.consts)

    def peek(self):
        return self.t[self.i]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def is_op(self, s):
        t = self.peek()
        return t[0] == 'op' and t[1] == s

    def is_kw(self, s):
        t = self.peek()
        return t[0] == 'kw' and t[1] == s

    def expect_op(self, s):
        t = self.next()
        if t[0] != 'op' or t[1] != s:
            raise WizError('expected %r' % s, t[2])
        return t

    def expect_kind(self, k):
        t = self.next()
        if t[0] != k:
            raise WizError('expected %s' % k.lower(), t[2])
        return t

    def program(self):
        body = []
        while self.peek()[0] != 'EOF':
            body.append(self.stmt(top=True))
        return body

    def block(self):
        self.expect_op(':')
        if self.peek()[0] != 'NEWLINE':
            s = self.simple_stmt()
            self.expect_kind('NEWLINE')
            return [s]
        self.next()
        self.expect_kind('INDENT')
        out = []
        while self.peek()[0] != 'DEDENT':
            out.append(self.stmt())
        self.next()
        return out

    def stmt(self, top=False):
        t = self.peek()
        ln = t[2]
        if t[0] == 'kw':
            k = t[1]
            if k == 'def':
                if not top:
                    raise WizError('def only allowed at top level', ln)
                self.next()
                name = self.expect_kind('name')[1]
                self.expect_op('(')
                params = []
                defaults = []
                while not self.is_op(')'):
                    pn = self.expect_kind('name')
                    if pn[1] in self.consts:
                        raise WizError('%r is a constant, cannot be a parameter' % pn[1], pn[2])
                    params.append(pn[1])
                    if self.is_op('='):
                        self.next()
                        dv = self.expr()
                        if dv[0] != 'num':
                            raise WizError('default value must be a constant', ln)
                        defaults.append(dv[1])
                    elif defaults:
                        raise WizError('parameter without default after one with default', ln)
                    if self.is_op(','):
                        self.next()
                self.expect_op(')')
                return ('def', name, params, self.block(), ln, defaults)
            if k in ('rom', 'rom8'):
                if not top:
                    raise WizError('%s only allowed at top level' % k, ln)
                self.next()
                dn = self.expect_kind('name')
                self.expect_op('=')
                vals = self.data_list(k, ln)
                self.expect_kind('NEWLINE')
                return ('rom', dn[1], k, vals, ln)
            if k == 'const':
                if not top:
                    raise WizError('const only allowed at top level', ln)
                self.next()
                cn = self.expect_kind('name')
                self.expect_op('=')
                cv = self.expr()
                self.expect_kind('NEWLINE')
                if cv[0] != 'num':
                    raise WizError('const value must be a constant expression', ln)
                if cn[1] in self.consts and (cn[1] not in self.builtin or cn[1] in self.overridden):
                    raise WizError('constant %r already defined' % cn[1], ln)
                self.overridden.add(cn[1])
                self.consts[cn[1]] = cv[1]
                return ('pass', ln)
            if k == 'if':
                self.next()
                arms = []
                c = self.expr()
                arms.append((c, self.block()))
                els = []
                while self.is_kw('elif'):
                    self.next()
                    c = self.expr()
                    arms.append((c, self.block()))
                if self.is_kw('else'):
                    self.next()
                    els = self.block()
                return ('if', arms, els, ln)
            if k == 'while':
                self.next()
                c = self.expr()
                return ('while', c, self.block(), ln)
            if k == 'for':
                self.next()
                v = self.expect_kind('name')[1]
                if not self.is_kw('in'):
                    raise WizError("expected 'in'", ln)
                self.next()
                if not self.is_kw('range'):
                    raise WizError('only `for x in range(...)` is supported', ln)
                self.next()
                self.expect_op('(')
                a = [self.expr()]
                while self.is_op(','):
                    self.next()
                    a.append(self.expr())
                self.expect_op(')')
                if len(a) == 1:
                    start, stop, step = ('num', 0), a[0], 1
                elif len(a) == 2:
                    start, stop, step = a[0], a[1], 1
                elif len(a) == 3:
                    start, stop = a[0], a[1]
                    if a[2][0] != 'num':
                        raise WizError('range step must be a constant', ln)
                    step = a[2][1]
                    if step == 0:
                        raise WizError('range step cannot be 0', ln)
                else:
                    raise WizError('range takes 1-3 arguments', ln)
                return ('for', v, start, stop, step, self.block(), ln)
        # WIZ-MOD: nhan nguoi dung  NAME:
        if t[0] == 'name':
            n2 = self.t[self.i + 1]
            if n2[0] == 'op' and n2[1] == ':':
                self.next()
                self.next()
                self.expect_kind('NEWLINE')
                return ('ulabel', t[1], ln)
        s = self.simple_stmt()
        self.expect_kind('NEWLINE')
        return s

    def data_list(self, kind, ln):
        """[a, b, c] | [v] * N | "text"  ->  list of ints (all constants)"""
        t = self.peek()
        if t[0] == 'str':
            if kind != 'rom8':
                raise WizError('string data needs rom8', ln)
            self.next()
            return list(t[1]) + [0]
        self.expect_op('[')
        vals = []
        while not self.is_op(']'):
            e = self.expr()
            if e[0] != 'num':
                raise WizError('table entries must be constants', ln)
            vals.append(e[1])
            if self.is_op(','):
                self.next()
            elif not self.is_op(']'):
                raise WizError('expected , or ]', ln)
        self.next()
        if self.is_op('*'):
            self.next()
            n = self.expr()
            if n[0] != 'num' or len(vals) != 1:
                raise WizError('use [value] * COUNT with a constant COUNT', ln)
            vals = vals * n[1]
        if not vals:
            raise WizError('empty table', ln)
        if kind == 'rom8':
            for v in vals:
                if not 0 <= v <= 255:
                    raise WizError('rom8 entries must be 0..255, got %d' % v, ln)
        return vals

    def simple_stmt(self):
        t = self.peek()
        ln = t[2]
        if t[0] == 'kw':
            k = t[1]
            if k == 'return':
                self.next()
                e = None if self.peek()[0] == 'NEWLINE' else self.expr()
                return ('return', e, ln)
            if k in ('break', 'continue', 'pass'):
                self.next()
                return (k, ln)
            if k == 'global':
                self.next()
                names = [self.expect_kind('name')[1]]
                while self.is_op(','):
                    self.next()
                    names.append(self.expect_kind('name')[1])
                return ('global', names, ln)
            # WIZ-MOD: goto + asm
            if k == 'goto':
                self.next()
                nm = self.expect_kind('name')[1]
                return ('goto', nm, ln)
            if k == 'asm':
                self.next()
                parts = []
                while self.peek()[0] == 'str':
                    v = self.next()[1]
                    # decode_str tra ve LIST BYTE -> chuyen nguoc thanh text asm
                    if isinstance(v, list) and any(b > 126 or 0 < b < 7 for b in v):
                        raise WizError('asm strings must be plain ASCII', ln)
                    parts.append(bytes(v).decode('ascii') if isinstance(v, list) else v)
                if not parts:
                    raise WizError('asm expects a string literal', ln)
                return ('iasm', '\n'.join(parts), ln)
        if t[0] == 'name':
            n = self.t[self.i + 1]
            if n[0] == 'op' and n[1] == '=' and self.t[self.i + 2][0] == 'op' and self.t[self.i + 2][1] == '[':
                self.next(); self.next()
                return ('arr', t[1], self.data_list('rom', ln), ln)
            if n[0] == 'op' and n[1] == '[':
                self.next(); self.next()
                idx = self.expr()
                self.expect_op(']')
                op = self.next()
                if op[0] != 'op' or op[1] not in ('=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>='):
                    raise WizError('expected assignment after ]', ln)
                rhs = self.expr()
                if op[1] != '=':
                    if self.has_call(idx):
                        raise WizError('index with a function call cannot be used with %s' % op[1], ln)
                    rhs = ('bin', op[1][:-1], ('index', t[1], idx, ln), rhs)
                return ('aassign', t[1], idx, rhs, ln)
            if t[1] in self.consts and n[0] == 'op' and (n[1] == '=' or n[1].endswith('=') and n[1] not in ('==', '!=', '<=', '>=')):
                raise WizError('cannot assign to constant %r' % t[1], ln)
            if n[0] == 'op' and n[1] == '=':
                self.next(); self.next()
                return ('assign', t[1], self.expr(), ln)
            if n[0] == 'op' and n[1] in ('+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>='):
                self.next(); self.next()
                return ('assign', t[1], ('bin', n[1][:-1], ('var', t[1], ln), self.expr()), ln)
        e = self.expr()
        if e[0] != 'call':
            raise WizError('expression statement has no effect', ln)
        return ('expr', e, ln)

    @staticmethod
    def has_call(node):
        if isinstance(node, tuple):
            if node and node[0] == 'call':
                return True
            return any(Parser.has_call(x) for x in node)
        if isinstance(node, list):
            return any(Parser.has_call(x) for x in node)
        return False

    # --- expressions
    def expr(self):
        return self.or_e()

    def or_e(self):
        l = self.and_e()
        while self.is_kw('or'):
            self.next()
            l = ('or', l, self.and_e())
        return l

    def and_e(self):
        l = self.not_e()
        while self.is_kw('and'):
            self.next()
            l = ('and', l, self.not_e())
        return l

    def not_e(self):
        if self.is_kw('not'):
            self.next()
            return ('not', self.not_e())
        return self.cmp_e()

    def cmp_e(self):
        # WIZ-MOD: ho tro so sanh chuoi (a < b < c) - bien trung khong duoc goi ham
        l = self.bin_level(0)
        t = self.peek()
        if not (t[0] == 'op' and t[1] in ('==', '!=', '<', '>', '<=', '>=')):
            return l
        ln = t[2]
        chain = []
        while self.peek()[0] == 'op' and self.peek()[1] in ('==', '!=', '<', '>', '<=', '>='):
            op = self.next()[1]
            r = self.bin_level(0)
            chain.append((op, l, r))
            l = r
        for _, mid, _2 in chain[1:]:
            if Parser.has_call(mid):
                raise WizError('chained comparison: middle expression must not contain a function call', ln)
        out = None
        for op, a, b in reversed(chain):
            node = ('cmp', op, a, b)
            out = node if out is None else ('and', out, node)
        return out

    LEVELS = [('|',), ('^',), ('&',), ('<<', '>>'), ('+', '-'), ('*', '/', '%', '//')]

    def bin_level(self, lv):
        if lv == len(self.LEVELS):
            return self.unary()
        l = self.bin_level(lv + 1)
        while self.peek()[0] == 'op' and self.peek()[1] in self.LEVELS[lv]:
            op = self.next()[1]
            if op == '//':
                op = '/'
            r = self.bin_level(lv + 1)
            fv = fold(op, l[1], r[1]) if (l[0] == 'num' and r[0] == 'num') else None
            if fv is not None:
                l = ('num', fv)
            else:
                l = ('bin', op, l, r)
        return l

    def unary(self):
        t = self.peek()
        if t[0] == 'op' and t[1] in ('-', '+', '~'):
            self.next()
            e = self.unary()
            if t[1] == '+':
                return e
            if e[0] == 'num':
                return ('num', wrap16(-e[1] if t[1] == '-' else ~e[1]))
            return ('un', t[1], e)
        return self.primary()

    def primary(self):
        t = self.next()
        if t[0] == 'num':
            return ('num', wrap16(t[1]))
        if t[0] == 'kw' and t[1] in ('True', 'False'):
            return ('num', 1 if t[1] == 'True' else 0)
        if t[0] == 'str':
            return ('str', tuple(t[1]), t[2])
        if t[0] == 'name' and self.is_op('['):
            self.next()
            idx = self.expr()
            self.expect_op(']')
            return ('index', t[1], idx, t[2])
        if t[0] == 'name':
            if self.is_op('('):
                self.next()
                args = []
                while not self.is_op(')'):
                    args.append(self.expr())
                    if self.is_op(','):
                        self.next()
                    elif not self.is_op(')'):
                        raise WizError('expected , or )', t[2])
                self.next()
                return ('call', t[1], args, t[2])
            if t[1] in self.consts:
                return ('num', self.consts[t[1]])
            return ('var', t[1], t[2])
        if t[0] == 'op' and t[1] == '(':
            e = self.expr()
            self.expect_op(')')
            return e
        raise WizError('unexpected token %r' % (t[1],), t[2])


# ---------------------------------------------------------------- codegen
INV_JUMP = {'==': 'JNE', '!=': 'JEQ', '<': 'JGES', '>': 'JLES', '<=': 'JGTS', '>=': 'JLTS'}
TRUE_JUMP = {'==': 'JEQ', '!=': 'JNE', '<': 'JLTS', '>': 'JGTS', '<=': 'JLES', '>=': 'JGES'}


class Compiler:
    def __init__(self, target=None):
        from targets import get_target, DEFAULT_TARGET
        self.target = get_target(target or DEFAULT_TARGET)
        self.var_base = self.target.var_base
        self.var_limit = self.target.var_limit
        self.out = []
        self.nlabel = 0
        self.vars = {}
        self.next_addr = self.var_base
        self.funcs = {}
        self.globals = set()
        self.fn = None
        self.locals = set()
        self.declared_global = set()
        self.loops = []
        self.arrays = {}      # name -> (addr, size, init values)
        self.roms = {}        # name -> (label, kind, values)
        self.strings = {}     # tuple(bytes) -> label
        self.reach = {}
        self.notes = []

    # -- helpers
    def emit(self, s):
        self.out.append('    ' + s)

    def label(self, name):
        self.out.append(name + ':')

    def new_label(self):
        self.nlabel += 1
        return 'L%d' % self.nlabel

    def alloc(self, qname):
        if qname not in self.vars:
            if self.next_addr + 2 > self.var_limit:
                raise WizError('out of RAM for variables')
            self.vars[qname] = self.next_addr
            self.next_addr += 2
        return self.vars[qname]

    def var_addr(self, name, ln):
        if self.fn and name in self.locals and name not in self.declared_global:
            return self.alloc('%s.%s' % (self.fn, name))
        if name in self.globals:
            return self.alloc(name)
        raise WizError('undefined variable %r' % name, ln)

    # -- analysis
    @staticmethod
    def assigned_names(body, acc):
        for s in body:
            k = s[0]
            if k == 'assign':
                acc.add(s[1])
            elif k == 'for':
                acc.add(s[1])
                Compiler.assigned_names(s[5], acc)
            elif k == 'if':
                for _, b in s[1]:
                    Compiler.assigned_names(b, acc)
                Compiler.assigned_names(s[2], acc)
            elif k == 'while':
                Compiler.assigned_names(s[2], acc)

    @staticmethod
    def calls_in(node, acc):
        if isinstance(node, tuple):
            if node and node[0] == 'call':
                acc.add(node[1])
            for x in node:
                Compiler.calls_in(x, acc)
        elif isinstance(node, list):
            for x in node:
                Compiler.calls_in(x, acc)

    @staticmethod
    def refs_in(node, acc):
        """every name a tree mentions: calls, variables, indexed tables"""
        if isinstance(node, tuple):
            if len(node) >= 2 and node[0] in ('call', 'var', 'index') and isinstance(node[1], str):
                acc.add(node[1])
            for x in node:
                Compiler.refs_in(x, acc)
        elif isinstance(node, list):
            for x in node:
                Compiler.refs_in(x, acc)

    def add_prelude(self, prog, consts):
        """append the library pieces the program (transitively) calls and the user did not define"""
        user_defs = {x[1] for x in prog if x[0] in ('def', 'rom', 'arr')}
        snippets = {}
        provider = {}
        prelude = dict(PRELUDE)
        if getattr(self, 'use_vn', False):
            prelude.update(PRELUDE_VN)
        for sid, text in prelude.items():
            if self.target.rom_seg == 0:
                text = text.replace('_rpeek(', 'peek(')    # ROM strings/sprites live in segment 0: plain peek
            sp = Parser(lex(text), consts).program()
            snippets[sid] = sp
            for x in sp:
                if x[0] in ('def', 'rom', 'arr'):
                    provider[x[1]] = sid
        need = set()
        self.refs_in(prog, need)
        included = []
        done = set()
        while need:
            n = min(need)          # deterministic order (set.pop() varies with PYTHONHASHSEED)
            need.remove(n)
            if n in done:
                continue
            done.add(n)
            sid = provider.get(n)
            if sid is None or n in user_defs or sid in included:
                continue
            included.append(sid)
            for x in snippets[sid]:
                self.refs_in(x, need)
        out = list(prog)
        for sid in included:
            for x in snippets[sid]:
                if x[0] in ('def', 'rom', 'arr') and x[1] in user_defs:
                    continue
                out.append(x)
        return out

    def rewrite_print(self, node, data_names):
        """print(x, y, a, b, ...) -> num(text(x, y, a), y, b)...  A string literal or a rom8/array name
        prints as text, anything else prints as a number. Each piece returns the x where it ended."""
        if isinstance(node, list):
            return [self.rewrite_print(x, data_names) for x in node]
        if not isinstance(node, tuple):
            return node
        node = tuple(self.rewrite_print(x, data_names) for x in node)
        if len(node) == 4 and node[0] == 'call' and node[1] in ('text', 'char') and len(node[2]) == 5 \
                and node[1] not in self.user_defs:
            return ('call', node[1] + 'z', node[2], node[3])    # text(x, y, cao, dai, s) / char(x, y, c, cao, dai)
        if len(node) == 4 and node[0] == 'call' and node[1] == 'print':
            _, _, args, ln = node
            if len(args) < 3:
                raise WizError('print(x, y, value, ...) needs at least 3 arguments', ln)
            # print(x, y, cao, dai, value, ...): when cao and dai are both constants and a value follows,
            # they are the pixel height and width of each character cell (default 8 x 6)
            size = None
            if len(args) >= 5 and args[2][0] == 'num' and args[3][0] == 'num':
                if args[2][1] < 1 or args[3][1] < 1:
                    raise WizError('print(): character cao and dai must be at least 1', ln)
                size = [args[2], args[3]]
                args = args[:2] + args[4:]
            cur = args[0]
            for a in args[2:]:
                is_text = a[0] == 'str' or (a[0] == 'var' and a[1] in data_names)
                if size:
                    cur = ('call', 'textz' if is_text else 'numz', [cur, args[1]] + size + [a], ln)
                else:
                    cur = ('call', 'text' if is_text else 'num', [cur, args[1], a], ln)
            return cur
        return node

    def rewrite_draw(self, prog):
        """draw(x, y, cao, dai, hex) with a constant size and a constant hex string (a literal, or a global
        assigned once to a literal) becomes sprite(x, y, dai, cao, table) with the hex packed into a rom8 table.
        Anything else is left to the run-time draw() in the library (hex digits only, no spaces)."""
        if any(s[0] == 'def' and s[1] == 'draw' for s in prog):
            return prog                      # the program has its own draw()
        counts = {}

        def count(n):
            if isinstance(n, list):
                for x in n:
                    count(x)
            elif isinstance(n, tuple):
                if n and n[0] == 'assign' and len(n) > 2 and isinstance(n[1], str):
                    counts[n[1]] = counts.get(n[1], 0) + 1
                for x in n:
                    count(x)
        count(prog)
        strs = {s[1]: s[2][1] for s in prog if s[0] == 'assign' and s[2][0] == 'str' and counts.get(s[1]) == 1}
        data, newroms = {}, []

        def pack(lit, h, w, ln):
            txt = bytes(lit).decode('latin-1')
            digits = re.sub(r'[\s_]', '', txt)
            if re.search(r'[^0-9a-fA-F]', digits):
                raise WizError('draw(): the hex string may only contain 0-9, a-f (spaces and _ are ignored)', ln)
            if h <= 0 or w <= 0:
                raise WizError('draw(): cao and dai must be positive', ln)
            bw = (w + 7) >> 3
            need = h * bw * 2
            if len(digits) != need:
                raise WizError('draw(): a %d x %d picture needs %d hex digits (%d rows x %d digits per row) but the string has %d'
                               % (w, h, need, h, bw * 2, len(digits)), ln)
            vals = tuple(int(digits[i:i + 2], 16) for i in range(0, need, 2))
            if vals not in data:
                data[vals] = '_draw%d' % len(data)
                newroms.append(('rom', data[vals], 'rom8', list(vals), ln))
            return data[vals]

        def conv(n):
            if isinstance(n, list):
                return [conv(x) for x in n]
            if not isinstance(n, tuple):
                return n
            n = tuple(conv(x) for x in n)
            if len(n) == 4 and n[0] == 'call' and n[1] == 'draw':
                args, ln = n[2], n[3]
                if len(args) != 5:
                    raise WizError('draw(x, y, cao, dai, hex) takes 5 arguments', ln)
                x, y, h, w, s = args
                lit = s[1] if s[0] == 'str' else (strs.get(s[1]) if s[0] == 'var' else None)
                if lit is not None and h[0] == 'num' and w[0] == 'num':
                    return ('call', 'sprite', [x, y, w, h, ('var', pack(lit, h[1], w[1], ln), ln)], ln)
            return n
        prog = conv(prog)
        # a hex string that only draw() used does not need to stay in RAM/ROM as text
        used = set()

        def refs(n):
            if isinstance(n, list):
                for x in n:
                    refs(x)
            elif isinstance(n, tuple):
                if n and n[0] == 'var' and len(n) > 1 and isinstance(n[1], str):
                    used.add(n[1])
                for x in n:
                    refs(x)
        refs([s for s in prog if not (s[0] == 'assign' and s[1] in strs)])
        prog = [s for s in prog if not (s[0] == 'assign' and s[1] in strs and s[1] not in used)]
        return prog + newroms

    def compile(self, src):
        consts = dict(key_consts(self.target.name))
        toks = lex(src)
        # Vietnamese glyph tables (~1.7 KB) only when a string literal has Vietnamese letters (comments do not
        # count), or the program says `const VIET = 1` (needed only when it builds Vietnamese codes by number)
        self.use_vn = any(t[0] == 'str' and has_vn(t[1]) for t in toks)
        prog = Parser(toks, consts).program()
        if consts.get('VIET'):
            self.use_vn = True
        prog = self.rewrite_draw(prog)
        self.user_defs = {x[1] for x in prog if x[0] == 'def'}
        prog = self.rewrite_print(prog, {x[1] for x in prog if x[0] in ('rom', 'arr')})
        prog = self.add_prelude(prog, consts)
        self.uses_heap = any(x[0] == 'def' and x[1] in (
            'alloc', 'free', 'f_save', 'f_load', 'f_exists', 'f_remove') for x in prog)
        top = []
        for s in prog:
            if s[0] == 'def':
                if s[1] in self.funcs or s[1] in BUILTINS:
                    raise WizError('function %r already defined' % s[1], s[4])
                if len(set(s[2])) != len(s[2]):
                    raise WizError('duplicate parameter name', s[4])
                self.funcs[s[1]] = s
            else:
                top.append(s)
        decls = [x for x in top if x[0] in ('arr', 'rom')]
        top = [x for x in top if x[0] not in ('arr', 'rom')]
        for dcl in decls:
            self.declare(dcl)
        gl = set()
        self.assigned_names(top, gl)
        clash = gl & (set(self.arrays) | set(self.roms))
        if clash:
            raise WizError('%r is a table/array, cannot assign to the name itself' % sorted(clash)[0])
        self.globals = gl
        # recursion check
        graph = {}
        for n, d in self.funcs.items():
            c = set()
            self.calls_in(d[3], c)
            for cc in c:
                if cc not in self.funcs and cc not in BUILTINS:
                    raise WizError('call to unknown function %r' % cc, d[4])
            graph[n] = {x for x in c if x in self.funcs}
        # which functions can (transitively) call which -> decides where frames must be saved
        for n in graph:
            seen = set()
            todo = list(graph[n])
            while todo:
                m = todo.pop()
                if m in seen:
                    continue
                seen.add(m)
                todo.extend(graph[m])
            self.reach[n] = seen
        tc = set()
        self.calls_in(top, tc)
        for cc in tc:
            if cc not in self.funcs and cc not in BUILTINS:
                raise WizError('call to unknown function %r' % cc)
        for n in self.funcs:
            if n == 'main' and self.funcs[n][2]:
                raise WizError('main() takes no parameters', self.funcs[n][4])

        # entry
        self.label('__wiz_entry')
        self.emit('BL __rt_init')
        self.emit('BL __init')
        if 'main' in self.funcs:
            self.emit('BL f_main')
        self.label('__wiz_halt')
        self.emit('B __wiz_halt')
        # __init = top-level statements
        self.fn = None
        self.label('__init')
        self.emit('PUSH LR')
        self.init_arrays()
        self.block(top)
        self.emit('MOV ER0, #0')
        self.emit('POP PC')
        for name, d in self.funcs.items():
            self.func(d)
        self.expand_frames()
        self.emit_data()
        # heap: everything between the last variable and the runtime area at 0xE000.
        # alloc() and the RAM file system live here (cw ~3.5 KB for a typical
        # program, cwii up to ~20 KB). Emitted as EQUs so runtime.asm can
        # bootstrap them; pure-asm builds (kernel) define their own.
        self.out.append('__HEAP_LO EQU 0x%04X' % (self.next_addr & 0xFFFF))
        self.out.append('__HEAP_HI EQU 0x%04X' % self.var_limit)
        heap = self.var_limit - (self.next_addr & 0xFFFF)
        if heap < 256:
            self.notes.append('variables reach 0x%04X: only %d bytes left for the heap below 0xE000'
                              % (self.next_addr & 0xFFFF, heap))
        elif self.uses_heap:
            self.notes.append('heap: %d bytes free after the variables (alloc/file region, up to 0xE000)' % heap)
        return '\n'.join(self.out) + '\n'

    def init_arrays(self):
        for name, (addr, size, vals) in self.arrays.items():
            if len(set(vals)) == 1 and size > 6:
                lp = self.new_label()
                self.const(2, addr)
                self.const(4, size)
                self.const(0, vals[0])
                self.label(lp)
                self.emit('ST ER0, [ER2]')
                self.emit('ADD ER2, #2')
                self.emit('ADD ER4, #-1')
                self.emit('BNE ' + lp)
            else:
                for i, v in enumerate(vals):
                    self.const(0, v)
                    self.emit('ST ER0, 0x%04X' % (addr + 2 * i))

    def declare(self, d):
        if d[0] == 'arr':
            _, name, vals, ln = d
            if name in self.arrays or name in self.roms or name in self.funcs:
                raise WizError('%r already defined' % name, ln)
            if self.next_addr + 2 * len(vals) > self.var_limit:
                raise WizError('out of RAM for array %r' % name, ln)
            self.arrays[name] = (self.next_addr, len(vals), vals)
            self.next_addr += 2 * len(vals)
        else:
            _, name, kind, vals, ln = d
            if name in self.arrays or name in self.roms or name in self.funcs:
                raise WizError('%r already defined' % name, ln)
            self.roms[name] = ('__d_' + name, kind, vals)

    def str_label(self, bs):
        bs = tuple(bs)
        if bs not in self.strings:
            self.strings[bs] = '__s%d' % len(self.strings)
        return self.strings[bs]

    def expand_frames(self):
        out = []
        for line in self.out:
            t = line.strip()
            if t.startswith(';;SAVE ') or t.startswith(';;REST '):
                fn = t.split()[1]
                fv = sorted((a, v) for v, a in self.vars.items() if v.startswith(fn + '.'))
                if t.startswith(';;SAVE '):
                    for a, v in fv:
                        out.append('    L ER2, 0x%04X' % a)
                        out.append('    PUSH ER2')
                else:
                    for a, v in reversed(fv):
                        out.append('    POP ER2')
                        out.append('    ST ER2, 0x%04X' % a)
            else:
                out.append(line)
        self.out = out
        for fn in self.funcs:
            if fn in self.reach.get(fn, ()) or any(fn in self.reach[g] and g in self.reach[fn] for g in self.reach[fn]):
                n = len([1 for v in self.vars if v.startswith(fn + '.')])
                self.notes.append('recursive %s(): ~%d bytes of stack per call level, about %d levels max (stack is ~2000 bytes)' % (fn, 4 + 2 * n + 4, 2000 // (4 + 2 * n + 4)))

    def emit_data(self):
        total = 0
        for name, (label, kind, vals) in self.roms.items():
            if kind == 'rom':
                self.out.append(label + ':')
                for i in range(0, len(vals), 8):
                    self.out.append('    DW ' + ', '.join(str(v) for v in vals[i:i + 8]))
                total += 2 * len(vals)
        for name, (label, kind, vals) in self.roms.items():
            if kind == 'rom8':
                self.out.append(label + ':')
                for i in range(0, len(vals), 12):
                    self.out.append('    DB ' + ', '.join(str(v) for v in vals[i:i + 12]))
                total += len(vals)
        for bs, label in self.strings.items():
            self.out.append(label + ':')
            data = list(bs) + [0]
            for i in range(0, len(data), 12):
                self.out.append('    DB ' + ', '.join(str(v) for v in data[i:i + 12]))
            total += len(data)
        if total & 1:
            self.out.append('    DB 0')

    def func(self, d):
        _, name, params, body, ln = d[:5]
        self.fn = name
        names = set(params)
        self.assigned_names(body, names)
        clash = names & (set(self.arrays) | set(self.roms))
        if clash:
            raise WizError('%r is a table/array and cannot be used as a local variable' % sorted(clash)[0], ln)
        self.declared_global = set()
        for s in self.walk(body):
            if s[0] == 'global':
                self.declared_global |= set(s[1])
                for g in s[1]:
                    if g not in self.globals:
                        raise WizError('global %r is never assigned at top level' % g, s[2])
        self.locals = names
        for p in params:
            self.alloc('%s.%s' % (name, p))
        self.label('f_' + name)
        self.emit('PUSH LR')
        self.block(body)
        self.emit('MOV ER0, #0')
        self.label('f_%s__ret' % name)
        self.emit('POP PC')
        self.fn = None
        self.locals = set()
        self.declared_global = set()

    def walk(self, body):
        for s in body:
            yield s
            if s[0] == 'if':
                for _, b in s[1]:
                    yield from self.walk(b)
                yield from self.walk(s[2])
            elif s[0] == 'while':
                yield from self.walk(s[2])
            elif s[0] == 'for':
                yield from self.walk(s[5])

    # -- statements
    def block(self, body):
        for s in body:
            self.stmt(s)

    def stmt(self, s):
        k = s[0]
        if k == 'assign':
            self.ex(s[2])
            self.emit('ST ER0, 0x%04X' % self.var_addr(s[1], s[3]))
        elif k == 'expr':
            self.ex(s[1])
        elif k == 'aassign':
            _, name, idx, rhs, ln = s
            if name in self.arrays:
                addr, size, _ = self.arrays[name]
                self.ex(rhs)
                if idx[0] == 'num':
                    self.emit('ST ER0, 0x%04X' % ((addr + 2 * idx[1]) & 0xFFFF))
                else:
                    self.emit('PUSH ER0')
                    self.ex(idx)
                    self.emit('ADD ER0, ER0')
                    self.const(2, addr)
                    self.emit('ADD ER0, ER2')
                    self.emit('MOV ER2, ER0')
                    self.emit('POP ER0')
                    self.emit('ST ER0, [ER2]')
            elif name in self.vars or (self.fn and (self.fn + '.' + name) in self.vars):
                # pointer variable: p[i] = v -> _hpoke(p+i, v)
                qname = (self.fn + '.' + name) if (self.fn and (self.fn + '.' + name) in self.vars) else name
                addr = self.vars[qname]
                self.ex(rhs)              # ER0 = value
                self.emit('PUSH ER0')    # save value
                self.ex(idx)             # ER0 = index
                self.emit('L ER2, 0x%04X' % addr)  # ER2 = pointer value
                self.emit('ADD ER0, ER2')            # ER0 = ptr + i
                self.emit('POP ER2')                 # ER2 = value
                self.emit('BL __hpoke')              # write byte
            else:
                raise WizError('%r is not a RAM array or pointer variable (rom tables are read-only)' % name, ln)
        elif k == 'pass' or k == 'global':
            pass
        elif k == 'if':
            end = self.new_label()
            for cond, body in s[1]:
                nxt = self.new_label()
                self.branch(cond, nxt, False)
                self.block(body)
                self.emit('B ' + end)
                self.label(nxt)
            self.block(s[2])
            self.label(end)
        elif k == 'while':
            top, end = self.new_label(), self.new_label()
            self.label(top)
            self.branch(s[1], end, False)
            self.loops.append((end, top))
            self.block(s[2])
            self.loops.pop()
            self.emit('B ' + top)
            self.label(end)
        elif k == 'for':
            _, v, start, stop, step, body, ln = s
            addr = self.var_addr(v, ln)
            endv = self.alloc('%s.__end%d' % (self.fn or '', self.nlabel))
            top, cont, end = self.new_label(), self.new_label(), self.new_label()
            self.ex(start)
            self.emit('ST ER0, 0x%04X' % addr)
            self.ex(stop)
            self.emit('ST ER0, 0x%04X' % endv)
            self.label(top)
            self.emit('L ER0, 0x%04X' % addr)
            self.emit('L ER2, 0x%04X' % endv)
            self.emit('CMP R0, R2')
            self.emit('CMPC R1, R3')
            self.emit(('JGES ' if step > 0 else 'JLES ') + end)
            self.loops.append((end, cont))
            self.block(body)
            self.loops.pop()
            self.label(cont)
            self.emit('L ER0, 0x%04X' % addr)
            if -64 <= step <= 63:
                self.emit('ADD ER0, #%d' % step)
            else:
                self.const(2, step)
                self.emit('ADD ER0, ER2')
            self.emit('ST ER0, 0x%04X' % addr)
            self.emit('B ' + top)
            self.label(end)
        elif k == 'return':
            if self.fn is None:
                raise WizError('return outside function', s[2])
            if s[1] is None:
                self.emit('MOV ER0, #0')
            else:
                self.ex(s[1])
            self.emit('B f_%s__ret' % self.fn)
        elif k in ('break', 'continue'):
            if not self.loops:
                raise WizError('%s outside loop' % k, s[1])
            self.emit('B ' + (self.loops[-1][0] if k == 'break' else self.loops[-1][1]))
        # WIZ-MOD: nhan/goto nguoi dung + inline asm
        elif k == 'ulabel':
            self.label('_u_%s_%s' % (self.fn or 'top', s[1]))
        elif k == 'goto':
            self.emit('B _u_%s_%s' % (self.fn or 'top', s[1]))
        elif k == 'iasm':
            for al in s[1].split('\n'):
                al = al.strip()
                if al and not al.startswith('#'):
                    self.emit(al)
        else:
            raise WizError('internal: unknown statement %s' % k)

    # -- expressions -> ER0
    def const(self, reg, v):
        v = wrap16(v)
        if -64 <= v <= 63:
            self.emit('MOV ER%d, #%d' % (reg, v))
        else:
            self.emit('MOV R%d, #%d' % (reg, v & 0xFF))
            self.emit('MOV R%d, #%d' % (reg + 1, (v >> 8) & 0xFF))

    @staticmethod
    def is_leaf(e):
        return e[0] in ('num', 'var', 'str')

    def load_label(self, reg, label):
        self.emit('MOV R%d, #(%s & 255)' % (reg, label))
        self.emit('MOV R%d, #((%s >> 8) & 255)' % (reg + 1, label))

    def load(self, reg, e):
        if e[0] == 'num':
            self.const(reg, e[1])
        elif e[0] == 'str':
            self.load_label(reg, self.str_label(e[1]))
        elif e[1] in self.arrays:
            self.const(reg, self.arrays[e[1]][0])
        elif e[1] in self.roms:
            self.load_label(reg, self.roms[e[1]][0])
        else:
            self.emit('L ER%d, 0x%04X' % (reg, self.var_addr(e[1], e[2])))

    def operands(self, l, r):
        """leave l in ER0, r in ER2"""
        if self.is_leaf(r):
            self.ex(l)
            self.load(2, r)
        else:
            self.ex(l)
            self.emit('PUSH ER0')
            self.ex(r)
            self.emit('MOV ER2, ER0')
            self.emit('POP ER0')

    def ex(self, e):
        k = e[0]
        if k in ('num', 'var', 'str'):
            self.load(0, e)
        elif k == 'index':
            _, name, idx, ln = e
            if name in self.arrays:
                addr, size, _ = self.arrays[name]
                if idx[0] == 'num':
                    self.emit('L ER0, 0x%04X' % ((addr + 2 * idx[1]) & 0xFFFF))
                    return
                word, base = True, ('c', addr)
            elif name in self.roms:
                label, kind, _ = self.roms[name]
                word, base = (kind == 'rom'), ('l', label)
            elif name in self.vars or (self.fn and (self.fn + '.' + name) in self.vars):
                # pointer variable: p[i] -> byte at *(p+i) via _hpeek(p+i)
                qname = (self.fn + '.' + name) if (self.fn and (self.fn + '.' + name) in self.vars) else name
                addr = self.vars[qname]
                self.ex(idx)                       # ER0 = index
                self.emit('L ER2, 0x%04X' % addr) # ER2 = pointer value
                self.emit('ADD ER0, ER2')          # ER0 = ptr + i
                self.emit('BL __hpeek')            # ER0 = byte at that address
                return
            else:
                raise WizError('%r is not an array, table, or pointer variable' % name, ln)
            self.ex(idx)
            if word:
                self.emit('ADD ER0, ER0')
            if base[0] == 'c':
                self.const(2, base[1])
            else:
                self.load_label(2, base[1])
            self.emit('ADD ER0, ER2')
            self.emit('MOV ER2, ER0')
            if name in self.roms and self.target.rom_seg:
                self.emit('DSRI %d' % self.target.rom_seg)
            if word:
                self.emit('L ER0, [ER2]')
            else:
                self.emit('L R0, [ER2]')
                self.emit('MOV R1, #0')
        elif k == 'bin':
            op = e[1]
            self.operands(e[2], e[3])
            if op == '+':
                self.emit('ADD ER0, ER2')
            elif op == '-':
                self.emit('SUB R0, R2')
                self.emit('SUBC R1, R3')
            elif op in ('&', '|', '^'):
                m = {'&': 'AND', '|': 'OR', '^': 'XOR'}[op]
                self.emit('%s R0, R2' % m)
                self.emit('%s R1, R3' % m)
            elif op == '*':
                self.emit('BL __mul16')
            elif op == '/':
                self.emit('BL __div16')
            elif op == '%':
                self.emit('BL __div16')
                self.emit('MOV ER0, ER2')
            elif op == '<<':
                self.emit('BL __shl16')
            elif op == '>>':
                self.emit('BL __sra16')
            else:
                raise WizError('internal: operator %s' % op)
        elif k == 'un':
            self.ex(e[2])
            if e[1] == '-':
                self.emit('MOV ER2, ER0')
                self.emit('MOV ER0, #0')
                self.emit('SUB R0, R2')
                self.emit('SUBC R1, R3')
            else:
                self.emit('XOR R0, #255')
                self.emit('XOR R1, #255')
        elif k in ('cmp', 'and', 'or', 'not'):
            lf, le = self.new_label(), self.new_label()
            self.branch(e, lf, False)
            self.emit('MOV ER0, #1')
            self.emit('B ' + le)
            self.label(lf)
            self.emit('MOV ER0, #0')
            self.label(le)
        elif k == 'call':
            self.call(e)
        else:
            raise WizError('internal: expr %s' % k)

    def call(self, e):
        _, name, args, ln = e
        if name in BUILTINS:
            lo, hi = BUILTINS[name]
            if not lo <= len(args) <= hi:
                raise WizError('%s() takes %d-%d arguments' % (name, lo, hi), ln)
            for a in args:
                self.ex(a)
                self.emit('PUSH ER0')
            for i in reversed(range(len(args))):
                self.emit('POP ER%d' % (2 * i))
            if name == 'exit' and self.target.name != 'cwapp':
                raise WizError('exit() exists only for the cwapp target (a program patched into the firmware)', ln)
            if name == 'pixel':
                if len(args) == 2:
                    self.emit('MOV ER4, #1')
                self.emit('BL __pixel')
            elif name == 'getpixel':
                self.emit('BL __getpixel')
            elif name == 'copy_rect':
                self.emit('BL __copy_rect')
            elif name == 'invert_rect':
                self.emit('BL __invert_rect')
            elif name == 'clear_rect':
                self.emit('BL __clear_rect')
            elif name == '_hpeek':
                self.emit('BL __hpeek')
            elif name == '_hpoke':
                self.emit('BL __hpoke')
            elif name in ('ticks', 'delay_ms', 'getc', 'input_num',
                          'strlen', 'strcmp', 'strcpy', 'atoi', 'itoa'):
                self.emit('BL __' + name)
            else:
                self.emit('BL __' + name.lstrip('_'))
            return
        d = self.funcs.get(name)
        if d is None:
            raise WizError('unknown function %r' % name, ln)
        defaults = d[5]
        required = len(d[2]) - len(defaults)
        if not required <= len(args) <= len(d[2]):
            if defaults:
                raise WizError('%s() takes %d-%d arguments, got %d' % (name, required, len(d[2]), len(args)), ln)
            raise WizError('%s() takes %d arguments, got %d' % (name, len(d[2]), len(args)), ln)
        args = list(args) + [('num', v) for v in defaults[len(args) - required:]]
        save = self.fn is not None and (name == self.fn or self.fn in self.reach.get(name, ()))
        if save:
            self.emit(';;SAVE ' + self.fn)
        for a in args:
            self.ex(a)
            self.emit('PUSH ER0')
        for p in reversed(d[2]):
            self.emit('POP ER0')
            self.emit('ST ER0, 0x%04X' % self.alloc('%s.%s' % (name, p)))
        self.emit('BL f_' + name)
        if save:
            self.emit(';;REST ' + self.fn)

    def branch(self, e, label, jump_if):
        k = e[0]
        if k == 'cmp':
            self.operands(e[2], e[3])
            self.emit('CMP R0, R2')
            self.emit('CMPC R1, R3')
            self.emit('%s %s' % ((TRUE_JUMP if jump_if else INV_JUMP)[e[1]], label))
        elif k == 'not':
            self.branch(e[1], label, not jump_if)
        elif k == 'and':
            if not jump_if:
                self.branch(e[1], label, False)
                self.branch(e[2], label, False)
            else:
                skip = self.new_label()
                self.branch(e[1], skip, False)
                self.branch(e[2], label, True)
                self.label(skip)
        elif k == 'or':
            if jump_if:
                self.branch(e[1], label, True)
                self.branch(e[2], label, True)
            else:
                skip = self.new_label()
                self.branch(e[1], skip, True)
                self.branch(e[2], label, False)
                self.label(skip)
        elif k == 'num':
            if bool(e[1]) == jump_if:
                self.emit('B ' + label)
        else:
            self.ex(e)
            self.emit('OR R0, R1')
            self.emit(('JNE ' if jump_if else 'JEQ ') + label)


LAST_NOTES = []


def compile_to_asm(src, target=None):
    c = Compiler(target)
    table = key_consts(c.target.name)
    defined = set(re.findall(r'\bconst\s+(K_[A-Z0-9_]+)', src))
    for ln, line in enumerate(src.split('\n'), 1):
        for name in re.findall(r'\bK_[A-Z0-9_]+\b', re.sub(r'#.*', '', line)):
            if name not in table and name not in defined:
                raise WizError('%s is not a key on %s (keys of %s: %s)' % (
                    name, c.target.name, c.target.name,
                    ' '.join(sorted(k[2:] for k in table if k != 'K_NONE'))), ln)
    body = c.compile(src)
    notes = list(c.notes)
    LAST_NOTES[:] = notes
    return body, c.vars