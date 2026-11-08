"""Vietnamese glyphs for Wiz (6 columns wide, same as font6x8).

Every Vietnamese letter that is not plain ASCII (67 lower + 67 upper case = 134) gets ONE byte code in a
Wiz string, so "Xin chào Việt Nam" is a normal string literal (UTF-8 source, NFC or NFD both fine):

    code 128..255  -> glyph 0..127          code 1..6  -> glyph 128..133        (see vn_code / vn_glyph_index)

A glyph is GLYPH_ROWS bytes, first byte = row TOP (= y - OVER_ABOVE), MSB = leftmost pixel:
    rows -OVER_ABOVE .. -1   marks above the 8-row cell (tone / hat / breve), drawn ADD-ONLY (never erase)
    rows 0 .. 7              the normal 6x8 cell, capital letters start at row 0, lower case at row 2
    row 8                    dot below (nang), add-only
So the cell origin y is where a plain ASCII letter would be drawn; Vietnamese marks poke up to OVER_ABOVE
pixels above it and one pixel below it.

python3 font_vn.py "Xin chào Việt Nam"   prints a preview.
"""
import sys
import unicodedata
from font6x8 import FONT

OVER_ABOVE = 4
OVER_BELOW = 1
GLYPH_ROWS = OVER_ABOVE + 8 + OVER_BELOW      # 13
W = 6

TONES = ['\u0300', '\u0301', '\u0309', '\u0303', '\u0323']     # huyen sac hoi nga nang
FORMS_LOWER = ['a', '\u0103', '\u00e2', 'e', '\u00ea', 'i', 'o', '\u00f4', '\u01a1', 'u', '\u01b0', 'y']


def _nfc(s):
    return unicodedata.normalize('NFC', s)


def _build_chars():
    lower = []
    for f in FORMS_LOWER:
        for t in [''] + TONES:
            ch = _nfc(f + t)
            if ord(ch) > 127:
                lower.append(ch)
    lower.append('\u0111')                       # d with stroke
    upper = [c.upper() for c in lower]
    return lower, upper


LOWER, UPPER = _build_chars()
VN_CHARS = LOWER + UPPER                      # glyph order
assert len(VN_CHARS) == 134 and len(set(VN_CHARS)) == 134


def vn_code(ch):
    """byte code of a Vietnamese letter, or None"""
    ch = _nfc(ch)
    if ch not in VN_CHARS:
        return None
    i = VN_CHARS.index(ch)
    return 128 + i if i < 128 else i - 127


def vn_glyph_index(code):
    if code >= 128:
        return code - 128
    if 1 <= code <= 6:
        return code + 127
    return None


VN_CODE = {ch: vn_code(ch) for ch in VN_CHARS}


# ------------------------------------------------------------------ drawing helpers
def _base(ch):
    c = ord(ch) - 32
    rows = []
    for b in FONT[c * 8:c * 8 + 8]:
        rows.append(''.join('X' if b & (128 >> k) else '.' for k in range(W)))
    return rows


def _blank():
    return [['.'] * W for _ in range(GLYPH_ROWS)]


def _put(cv, rows, top, dx=0):
    """paste a list of row strings with its first row at cell row `top` (may be negative)"""
    for j, row in enumerate(rows):
        r = top + j + OVER_ABOVE
        for k, c in enumerate(row):
            if c == 'X':
                cv[r][k + dx] = 'X'


MARK = {
    '\u0300': ['.X....',
               '..X...'],
    '\u0301': ['...X..',
               '..X...'],
    '\u0309': ['.XX...',
               '..X...'],
    '\u0303': ['.XX.X.',
               'X..X..'],
}
HAT = ['..X...',
       '.X.X..']
BREVE = ['X...X.',
         '.XXX..']

# single tone mark: gap rows between mark and letter top; combined: tone sits right above hat/breve
GAP_LOWER = 1
GAP_UPPER = 0


def _tall(upper):
    return upper


def _i_lower():
    return ['......', '......', '..X...', '..X...', '..X...', '..X...', '..X...', '......']


CAP = {   # hand drawn capitals that differ from ASCII
    '\u0110': ['.XXXX.', '.X..X.', '.X..X.', 'XXX.X.', '.X..X.', '.X..X.', '.XXXX.', '......'],
}


def glyph(ch):
    """GLYPH_ROWS rows of 6 chars for one Vietnamese letter"""
    upper = ch != ch.lower()
    low = ch.lower()
    d = unicodedata.normalize('NFD', low)
    base_letter = d[0]
    marks = d[1:]
    shape = None
    horn = False
    tone = None
    stroke = False
    for m in marks:
        if m == '\u0302':
            shape = HAT
        elif m == '\u0306':
            shape = BREVE
        elif m == '\u031b':
            horn = True
        elif m in TONES:
            tone = m
    if low == '\u0111':
        stroke = True
        base_letter = 'd'
    cv = _blank()
    if upper:
        rows = CAP['\u0110'] if stroke else _base(base_letter.upper())
        top = 0
    else:
        rows = _i_lower() if base_letter == 'i' else _base(base_letter)
        top = 2
    _put(cv, rows, 0)
    if stroke and not upper:
        for k in (2, 3, 4, 5):
            cv[1 + OVER_ABOVE][k] = 'X'
    if horn:
        cv[top + OVER_ABOVE][5] = 'X'
        cv[top + 1 + OVER_ABOVE][5] = 'X'
    gap = GAP_UPPER if upper else GAP_LOWER
    if shape is not None:
        shape_top = top - 2 - (GAP_UPPER if upper else GAP_LOWER)
        _put(cv, shape, shape_top)
        if tone in MARK:
            _put(cv, MARK[tone], shape_top - 2)
    elif tone in MARK:
        _put(cv, MARK[tone], top - 2 - gap)
    if tone == '\u0323':
        cv[8 + OVER_ABOVE][2] = 'X'
    return [''.join(r) for r in cv]


def glyph_bytes(ch):
    out = []
    for row in glyph(ch):
        v = 0
        for k, c in enumerate(row):
            if c == 'X':
                v |= 128 >> k
        out.append(v)
    return out


def font_table():
    t = []
    for ch in VN_CHARS:
        t.extend(glyph_bytes(ch))
    return t


# ------------------------------------------------------------------ preview
def render(text):
    """ASCII-art preview of a one-line string"""
    cols = []
    for ch in _nfc(text):
        if ch in VN_CODE:
            cols.append(glyph(ch))
        else:
            rows = _base(ch)
            g = ['......'] * OVER_ABOVE + rows + ['......'] * OVER_BELOW
            cols.append(g)
    out = []
    for r in range(GLYPH_ROWS):
        label = r - OVER_ABOVE
        out.append('%3d ' % label + ''.join(c[r].replace('.', ' ').replace('X', '#') for c in cols))
    return '\n'.join(out)


if __name__ == '__main__':
    print(render(' '.join(sys.argv[1:]) or 'Xin chào Việt Nam'))
