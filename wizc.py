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

VAR_BASE = 0x9000
VAR_LIMIT = 0xE000
ROM_LIMIT = 0x9000
BUILTINS = {'pixel': (2, 3), 'clear': (0, 0), 'key': (0, 0), 'delay': (1, 1),
            'peek': (1, 1), 'poke': (2, 2), '_hspan': (4, 4),
            'key_down': (1, 1), 'key_hit': (1, 1), 'buffered': (1, 1), 'flip': (0, 0),
            '_rpeek': (1, 1), 'exit': (0, 0)}
KEYWORDS = {'def', 'if', 'elif', 'else', 'while', 'for', 'in', 'range', 'return', 'break',
            'continue', 'pass', 'global', 'and', 'or', 'not', 'True', 'False', 'const', 'rom', 'rom8'}

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
    'K_DOT': 0x0C, 'K_SCI': 0x0D, 'K_FORMAT': 0x0E, 'K_EXE': 0x0F,
}

# ClassWiz (cw, ML620906) has its OWN key layout - it is not the cwii layout. Scan codes below were
# measured on a real cw (code = KO*8 + KI). K_INTEGRAL = the integral key, next to X.
CW_KEY_CONSTS = {
    'K_NONE': -1,
    'K_SHIFT': 56, 'K_ALPHA': 48, 'K_UP': 40, 'K_DOWN': 33, 'K_LEFT': 41, 'K_RIGHT': 32,
    'K_MENU': 24, 'K_OPTN': 57, 'K_CALC': 49, 'K_INTEGRAL': 25, 'K_X': 17,
    'K_FRAC': 58, 'K_SQRT': 50, 'K_SQUARED': 42, 'K_POWER': 34, 'K_LOG': 26, 'K_LN': 18,
    'K_NEG': 59, 'K_DEG': 51, 'K_INV': 43, 'K_SIN': 35, 'K_COS': 27, 'K_TAN': 19,
    'K_STO': 60, 'K_ENG': 52, 'K_LPAREN': 44, 'K_RPAREN': 36, 'K_SD': 28, 'K_MPLUS': 20,
    'K_7': 61, 'K_8': 53, 'K_9': 45, 'K_DEL': 37, 'K_AC': 29,
    'K_4': 62, 'K_5': 54, 'K_6': 46, 'K_MUL': 38, 'K_DIV': 30,
    'K_1': 63, 'K_2': 55, 'K_3': 47, 'K_PLUS': 39, 'K_MINUS': 31,
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
    if y < 0 or y > 63:
        return 0
    if x0 < 0:
        x0 = 0
    if x1 > 192:
        x1 = 192
    if x0 >= x1:
        return 0
    _hspan(x0, x1, y, c != 0)
''',
    'vline': '''
def vline(x, y0, y1, c=1):
    if x < 0 or x > 191:
        return 0
    if y0 < 0:
        y0 = 0
    if y1 > 64:
        y1 = 64
    for y in range(y0, y1):
        pixel(x, y, c)
''',
    'rect': '''
def rect(x, y, w, h, c=1):
    hline(x, x + w, y, c)
    hline(x, x + w, y + h - 1, c)
    vline(x, y, y + h, c)
    vline(x + w - 1, y, y + h, c)
''',
    'fillrect': '''
def fillrect(x, y, w, h, c=1):
    for j in range(y, y + h):
        hline(x, x + w, j, c)
''',
    'line': '''
def line(x0, y0, x1, y1, c=1):
    dx = abs(x1 - x0)
    dy = 0 - abs(y1 - y0)
    sx = 1
    if x0 > x1:
        sx = -1
    sy = 1
    if y0 > y1:
        sy = -1
    err = dx + dy
    while True:
        pixel(x0, y0, c)
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
def circle(cx, cy, r, c=1):
    x = r
    y = 0
    err = 1 - r
    while x >= y:
        pixel(cx + x, cy + y, c)
        pixel(cx + y, cy + x, c)
        pixel(cx - y, cy + x, c)
        pixel(cx - x, cy + y, c)
        pixel(cx - x, cy - y, c)
        pixel(cx - y, cy - x, c)
        pixel(cx + y, cy - x, c)
        pixel(cx + x, cy - y, c)
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

from font6x8 import FONT
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
def charz(x, y, c, w, h):
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
def textz(x, y, w, h, s):
    c = _rpeek(s)
    while c != 0:
        charz(x, y, c, w, h)
        x += w
        s += 1
        c = _rpeek(s)
    return x
'''
PRELUDE['numz'] = '''
def numz(x, y, w, h, n):
    if n == -32768:
        return textz(x, y, w, h, \"-32768\")
    if n < 0:
        charz(x, y, 45, w, h)
        x += w
        n = 0 - n
    d = 10000
    shown = 0
    while d > 0:
        q = n / d
        n = n - q * d
        if q > 0 or shown or d == 1:
            charz(x, y, 48 + q, w, h)
            x += w
            shown = 1
        d = d / 10
    return x
'''
PRELUDE['sprite'] = '''
def sprite(x, y, w, h, d):
    bw = (w + 7) >> 3
    for r in range(0, h):
        for k in range(0, w):
            b = _rpeek(d + r * bw + (k >> 3))
            if b & (128 >> (k & 7)):
                pixel(x + k, y + r)
'''

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
        else:
            if ord(c) > 126 or ord(c) < 32:
                raise WizError('only printable ASCII is allowed in strings', ln)
            out.append(ord(c))
        i += 1
    return out


def lex(src):
    toks = []
    indents = [0]
    for ln, raw in enumerate(src.replace('\r', '').split('\n'), 1):
        line = strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if '\t' in line[:len(line) - len(line.lstrip())]:
            raise WizError('tabs are not allowed for indentation, use spaces', ln)
        ind = len(line) - len(line.lstrip(' '))
        if ind > indents[-1]:
            indents.append(ind)
            toks.append(('INDENT', None, ln))
        while ind < indents[-1]:
            indents.pop()
            toks.append(('DEDENT', None, ln))
            if ind > indents[-1]:
                raise WizError('inconsistent indentation', ln)
        pos = ind
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
        l = self.bin_level(0)
        t = self.peek()
        if t[0] == 'op' and t[1] in ('==', '!=', '<', '>', '<=', '>='):
            self.next()
            r = self.bin_level(0)
            n = self.peek()
            if n[0] == 'op' and n[1] in ('==', '!=', '<', '>', '<=', '>='):
                raise WizError('chained comparisons are not supported', n[2])
            return ('cmp', t[1], l, r)
        return l

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
        for sid, text in PRELUDE.items():
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
        """print(x, y, w, h, value, ...) -> num(text(x, y, a), y, b)...  A string literal or a rom8/array name
        prints as text, anything else prints as a number. Each piece returns the x where it ended."""
        if isinstance(node, list):
            return [self.rewrite_print(x, data_names) for x in node]
        if not isinstance(node, tuple):
            return node
        node = tuple(self.rewrite_print(x, data_names) for x in node)
        if len(node) == 4 and node[0] == 'call' and node[1] in ('text', 'char') and len(node[2]) == 5 \
                and node[1] not in self.user_defs:
            return ('call', node[1] + 'z', node[2], node[3])    # text(x, y, w, h, s) / char(x, y, c, w, h)
        if len(node) == 4 and node[0] == 'call' and node[1] == 'print':
            _, _, args, ln = node
            if len(args) < 3:
                raise WizError('print(x, y, value, ...) needs at least 3 arguments', ln)
            # print(x, y, w, h, value, ...): when w and h are both constants and a value follows,
            # they are the pixel width and height of each character cell (default 6 x 8)
            size = None
            if len(args) >= 5 and args[2][0] == 'num' and args[3][0] == 'num':
                if args[2][1] < 1 or args[3][1] < 1:
                    raise WizError('print(): character w and h must be at least 1', ln)
                # args[2]=w, args[3]=h; textz/numz/charz also expect (x, y, w, h, ...)
                size = [args[2], args[3]]   # [w, h]
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
        prog = Parser(lex(src), consts).program()
        prog = self.rewrite_draw(prog)
        self.user_defs = {x[1] for x in prog if x[0] == 'def'}
        prog = self.rewrite_print(prog, {x[1] for x in prog if x[0] in ('rom', 'arr')})
        prog = self.add_prelude(prog, consts)
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
            if name not in self.arrays:
                raise WizError('%r is not a RAM array (rom tables are read-only)' % name, ln)
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
            else:
                raise WizError('%r is not an array or table' % name, ln)
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
