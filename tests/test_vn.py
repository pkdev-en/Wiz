"""Vietnamese text regression tests (run: python3 tests/test_vn.py). No simulator needed.

1. the Wiz library code that draws Vietnamese (PRELUDE_VN char/charz) is run as plain Python over a fake
   framebuffer and checked against font_vn.py: every one of the 134 glyphs, ASCII unchanged, add-only marks,
   sized text = exact pixel doubling.
2. compile-level: lexer/NFC/NFD, detection (comments do not pull the tables in), error messages, all targets
   assemble.
"""
import os, re, sys, unicodedata
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import wizc
from wizc import PRELUDE, PRELUDE_VN, WizError, decode_str
from build import build_source
import font_vn
from font6x8 import FONT

FAILS = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if (extra and not cond) else ''))
    if not cond:
        FAILS.append(name)


# ------------------------------------------------------------ 1. library code as Python
def to_py(wiz):
    wiz = re.sub(r'^rom8 ', '', wiz, flags=re.M)
    return wiz.replace('/', '//')            # these snippets only use integer division


class Lib:
    def __init__(self, vn=True):
        self.px = {}
        ns = {'pixel': self.pixel, '_rpeek': lambda a: 0}
        parts = [PRELUDE['font']]
        if vn:
            parts += [PRELUDE_VN['font_vn'], PRELUDE_VN['char'], PRELUDE_VN['charz']]
        else:
            parts += [PRELUDE['char'], PRELUDE['charz']]
        for p in parts:
            exec(to_py(p), ns)
        self.char, self.charz = ns['char'], ns['charz']

    def pixel(self, x, y, c=1):
        if c:
            self.px[(x, y)] = 1
        else:
            self.px.pop((x, y), None)


def lit(L):
    return {k for k in L.px}


vn = Lib(True)
old = Lib(False)

# every glyph: blank screen -> exactly the font_vn bitmap, origin y at row OVER_ABOVE
bad = []
for ch in font_vn.VN_CHARS:
    L = Lib(True)
    L.char(20, 20, font_vn.VN_CODE[ch])
    want = {(20 + k, 20 + r - font_vn.OVER_ABOVE) for r, row in enumerate(font_vn.glyph(ch)) for k, c in enumerate(row) if c == 'X'}
    if lit(L) != want:
        bad.append(ch)
check('all 134 Vietnamese glyphs draw exactly the font_vn bitmap', not bad, ''.join(bad))
check('134 distinct one-byte codes', len({font_vn.VN_CODE[c] for c in font_vn.VN_CHARS}) == 134 and
      all(1 <= v <= 6 or 128 <= v <= 255 for v in font_vn.VN_CODE.values()))
check('no code collides with ASCII, \\t \\n or \\0', all(v not in (0, 9, 10) and not 32 <= v <= 126 for v in font_vn.VN_CODE.values()))

# the marks outside the 8-row cell never erase; the cell itself does
L = Lib(True)
for r in range(-6, 12):
    for k in range(-1, 8):
        L.px[(20 + k, 20 + r)] = 1
L.char(20, 20, font_vn.VN_CODE['\u1ea4'])      # capital A, circumflex, acute
above = all(L.px.get((20 + k, 20 + r)) for r in range(-4, 0) for k in range(6) if not font_vn.glyph('\u1ea4')[r + 4][k] == 'X')
cell = all(((20 + k, 20 + r) in L.px) == (font_vn.glyph('\u1ea4')[r + 4][k] == 'X') for r in range(0, 8) for k in range(6))
check('marks above the cell are add-only (do not erase what is there)', above)
check('the 6x8 cell is cleared and redrawn', cell)

# ASCII (and bad codes) unchanged by the Vietnamese build
diff = []
for c in list(range(0, 128)) + [200]:
    if c >= 128 or 1 <= c <= 6:
        continue
    a, b = Lib(True), Lib(False)
    a.char(5, 5, c)
    b.char(5, 5, c)
    if lit(a) != lit(b):
        diff.append(c)
check('ASCII / invalid codes draw the same as without Vietnamese', not diff, diff)
for c in (7, 20, 31, 127):
    a, b = Lib(True), Lib(True)
    a.char(0, 0, c)
    b.char(0, 0, 63)
    check('code %d still draws "?"' % c, lit(a) == lit(b))

# sized text
bad = []
for ch in font_vn.VN_CHARS:
    a, b = Lib(True), Lib(True)
    code = font_vn.VN_CODE[ch]
    a.char(40, 30, code)
    b.charz(40, 30, code, 16, 12)
    want = {(40 + 2 * (x - 40) + i, 30 + 2 * (y - 30) + j) for (x, y) in lit(a) for i in (0, 1) for j in (0, 1)}
    if lit(b) != want:
        bad.append(ch)
check('charz 16x12 = exact 2x of the 8x6 Vietnamese glyph (all 134)', not bad, ''.join(bad))
bad = []
for ch in font_vn.VN_CHARS:
    a, b = Lib(True), Lib(True)
    a.char(40, 30, font_vn.VN_CODE[ch])
    b.charz(40, 30, font_vn.VN_CODE[ch], 8, 6)
    if lit(a) != lit(b):
        bad.append(ch)
check('charz 8x6 = char for Vietnamese', not bad, ''.join(bad))
ok = True
for h, w in ((11, 7), (5, 4), (24, 18), (9, 3), (1, 1)):
    L = Lib(True)
    L.charz(50, 40, font_vn.VN_CODE['\u1ec6'], h, w)
    xs = [p[0] for p in L.px]
    ys = [p[1] for p in L.px]
    if not L.px or min(xs) < 50 or max(xs) >= 50 + w or min(ys) < 40 - (h + 1) // 2 - 2 * h // 8 - 1 or max(ys) > 40 + h + h // 8 + 1:
        ok = False
check('charz odd sizes stay inside the scaled cell', ok)
a, b = Lib(True), Lib(False)
for c in range(32, 127):
    a.charz(0, 0, c, 13, 9)
    b.charz(0, 0, c, 13, 9)
check('charz ASCII unchanged by the Vietnamese build', lit(a) == lit(b))

# ------------------------------------------------------------ 2. compile level
WORD = 'Xin ch\u00e0o Vi\u1ec7t Nam'
check('decode: Vietnamese letters become 1 byte each', len(decode_str('"%s"' % WORD, 1)) == len(WORD))
check('decode: NFC and NFD give the same bytes',
      decode_str('"%s"' % WORD, 1) == decode_str('"%s"' % unicodedata.normalize('NFD', WORD), 1))
check('decode: ASCII is untouched', decode_str('"Hi 42\\n"', 1) == [72, 105, 32, 52, 50, 10])
for bad_s in ('"\u00f1"', '"\u2192"', '"\u00b0"'):
    try:
        decode_str(bad_s, 7)
        check('decode rejects non-Vietnamese %r' % bad_s, False)
    except WizError as e:
        check('decode rejects non-Vietnamese %r' % bad_s, 'line 7' in str(e) and 'Vietnamese' in str(e), e)

SRC_VN = 'def main():\n    clear()\n    text(4, 6, "%s")\n    print(4, 20, "%s", 12)\n    print(4, 36, 16, 12, "\u0110i\u1ec3m")\n    while True:\n        key()\n' % (WORD, WORD)
SRC_PLAIN = 'def main():\n    clear()\n    text(4, 6, "Xin chao")\n    while True:\n        key()\n'
SRC_COMMENT = '# Ti\u1ebfng Vi\u1ec7t trong ch\u00fa th\u00edch kh\u00f4ng \u0111\u01b0\u1ee3c t\u00ednh\n' + SRC_PLAIN + '    # \u0111\u00e2y c\u0169ng l\u00e0 ch\u00fa th\u00edch\n'
for t in ('cwii', 'cw', 'cwapp'):
    try:
        rom, full, variables, syms = build_source(SRC_VN, t)
        check('Vietnamese program assembles for %s' % t, '__d__fontvn' in full or '_fontvn' in full)
    except Exception as e:
        check('Vietnamese program assembles for %s' % t, False, e)
    p = build_source(SRC_PLAIN, t)[1]
    c = build_source(SRC_COMMENT, t)[1]
    check('plain program has no Vietnamese tables on %s' % t, '_fontvn' not in p)
    check('Vietnamese in comments only does not pull the tables in (%s)' % t, '_fontvn' not in c and c.replace('\n', '') != '' and p.split('f_main')[1:] == c.split('f_main')[1:])
check('const VIET = 1 forces the tables',
      '_fontvn' in build_source('const VIET = 1\n' + SRC_PLAIN, 'cwii')[1])
try:
    build_source('def main():\n    asm "NOP \u0111"\n', 'cwii')
    check('asm strings must be ASCII', False)
except WizError as e:
    check('asm strings must be ASCII', 'ASCII' in str(e), e)

print('\n%d failure(s)' % len(FAILS))
sys.exit(1 if FAILS else 0)
