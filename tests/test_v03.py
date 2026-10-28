"""Wiz 0.3 tests: arrays, rom tables, strings, text/num, sprite, recursion, peek/poke, errors."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from build import build_source
from u8sim import U8
from wizc import WizError
from targets import get_target, DEFAULT_TARGET
TG = get_target(DEFAULT_TARGET)
PK = TG.var_base + 0xF00      # a spare RAM address on this target (0x9F00 on cwii, 0xDF00 on cw)
from font6x8 import FONT

FAILS = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if (extra and not cond) else ''))
    if not cond:
        FAILS.append(name)

def s16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v

def run(src, steps=6_000_000):
    src = src.replace('@PK', hex(PK))
    rom, full, variables, syms = build_source(src)
    m = U8(rom, [])
    why = m.run(steps)
    return m, variables, why, rom

def var(m, variables, name):
    a = variables[name]
    return s16(m.mem[a] | (m.mem[a + 1] << 8))

def lit(m):
    return {(x, y) for y in range(64) for x in range(192) if m.pixel(x, y)}

def text_ref(x, y, s):
    out = set()
    for i, ch in enumerate(s):
        base = (ord(ch) - 32) * 8
        for r in range(8):
            for k in range(6):
                if FONT[base + r] & (0x80 >> k):
                    out.add((x + i * 6 + k, y + r))
    return {(a, b) for a, b in out if 0 <= a < 192 and 0 <= b < 64}

# ------------------------------------------------------------------ arrays
m, v, why, _ = run('''
a = [10, 20, 30, 40]
z = [0] * 20
big = [7] * 30
total = 0
i = 0
t1 = 0
t2 = 0
t3 = 0
t4 = 0
def main():
    global total, t1, t2, t3, t4
    for i in range(0, 4):
        total += a[i]
    a[1] = 99
    a[2] += 5
    a[3] -= 1
    z[19] = 1234
    z[0] = a[1] + a[2]
    t1 = a[a[0] - 9]
    t2 = z[19] + big[29] + big[0]
    t3 = a[2]
    k = 3
    z[k + 2] = k * 100
    t4 = z[5]
''')
check('array init, read, write, +=, nested index',
      (var(m,v,'total'), var(m,v,'t1'), var(m,v,'t2'), var(m,v,'t3'), var(m,v,'t4')) == (100, 99, 1234 + 14, 35, 300),
      [var(m,v,n) for n in ('total','t1','t2','t3','t4')])
base = TG.var_base
check('array memory layout words', m.mem[base] | (m.mem[base+1] << 8) == 10 and
      (m.mem[base+2] | (m.mem[base+3] << 8)) == 99, (m.mem[base], m.mem[base+2]))

# ------------------------------------------------------------------ rom tables
m, v, why, rom = run('''
rom w = [100, -5, 30000, 7]
rom8 b = [1, 2, 255, 128]
rom8 msg = "Hi!"
r0 = w[0]
r1 = w[1]
r2 = w[2]
b0 = b[0]
b2 = b[2]
b3 = b[3]
c0 = msg[0]
c2 = msg[2]
c3 = msg[3]
p = peek(msg + 1)
def f(i):
    return w[i] + b[i]
r5 = f(3)
def main():
    pass
''')
got = [var(m,v,n) for n in ('r0','r1','r2','b0','b2','b3','c0','c2','c3','p','r5')]
check('rom/rom8 tables, strings, peek on ROM', got == [100, -5, 30000, 1, 255, 128, 72, 33, 0, 105, 7 + 128], got)

# ------------------------------------------------------------------ text / num rendering
m, v, why, _ = run('''
def main():
    text(3, 5, "Hello, World! 0123456789")
    text(100, 40, "A~z")
    text(-4, 60, "clip")
''')
exp = text_ref(3, 5, "Hello, World! 0123456789") | text_ref(100, 40, "A~z") | text_ref(-4, 60, "clip")
check('text() matches font reference (incl. clipping)', lit(m) == exp, (len(lit(m)), len(exp), sorted(lit(m) ^ exp)[:6], why))

cases = [0, 7, 10, 99, 100, 12345, -5, -32768, 32767, -1000, 1, -1]
prog = 'def main():\n'
for i, n in enumerate(cases):
    prog += '    num(%d, %d, %d)\n' % (4 + (i % 2) * 90, 2 + (i // 2) * 10, n)
m, v, why, _ = run(prog, steps=30_000_000)
exp = set()
for i, n in enumerate(cases):
    exp |= text_ref(4 + (i % 2) * 90, 2 + (i // 2) * 10, str(n))
check('num() renders signed decimals incl. -32768 / 32767 / 0', lit(m) == exp, (sorted(lit(m) ^ exp)[:6], why))

# text return value = end x
m, v, why, _ = run('''
e = text(10, 10, "abcd")
f = num(10, 30, -123)
def main():
    pass
''')
check('text/num return end x', (var(m,v,'e'), var(m,v,'f')) == (34, 34), (var(m,v,'e'), var(m,v,'f')))

# ------------------------------------------------------------------ sprite
m, v, why, _ = run('''
rom8 arrow = [0x18, 0x3C, 0x7E, 0xFF, 0x18, 0x18, 0x18, 0x18,   0xAA, 0x55]
def main():
    sprite(20, 10, 8, 8, arrow)
    sprite(60, 30, 10, 1, arrow + 8)
''')
exp = set()
data = [0x18, 0x3C, 0x7E, 0xFF, 0x18, 0x18, 0x18, 0x18]
for r in range(8):
    for k in range(8):
        if data[r] & (0x80 >> k): exp.add((20 + k, 10 + r))
for k in range(10):
    byte = [0xAA, 0x55][k >> 3]
    if byte & (0x80 >> (k & 7)): exp.add((60 + k, 30))
check('sprite() 8x8 and 10-wide rows', lit(m) == exp, (sorted(lit(m) ^ exp)[:6]))

# ------------------------------------------------------------------ recursion
def fib(n): return n if n < 2 else fib(n - 1) + fib(n - 2)
def ack(m_, n_):
    if m_ == 0: return n_ + 1
    if n_ == 0: return ack(m_ - 1, 1)
    return ack(m_ - 1, ack(m_, n_ - 1))
m, v, why, _ = run('''
def fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
def gcd(a, b):
    if b == 0:
        return a
    return gcd(b, a % b)
def is_even(n):
    if n == 0:
        return 1
    return is_odd(n - 1)
def is_odd(n):
    if n == 0:
        return 0
    return is_even(n - 1)
def ack(m, n):
    if m == 0:
        return n + 1
    if n == 0:
        return ack(m - 1, 1)
    return ack(m - 1, ack(m, n - 1))
def sumto(n):
    s = 0
    for i in range(0, 1):
        if n > 0:
            s = n + sumto(n - 1)
    return s
def depth(n):
    k = n * 2
    if n == 0:
        return 0
    r = depth(n - 1)
    return r + k - n * 2 + 1
r_fact = fact(7)
r_fib = fib(12)
r_gcd = gcd(1071, 462)
r_even = is_even(11) * 10 + is_odd(11)
r_ack = ack(2, 3)
r_sum = sumto(60)
r_depth = depth(150)
def main():
    pass
''', steps=60_000_000)
got = [var(m,v,n) for n in ('r_fact','r_fib','r_gcd','r_even','r_ack','r_sum','r_depth')]
check('recursion: fact, fib, gcd, mutual even/odd, ackermann, loops-in-recursion, depth 150',
      got == [5040, 144, 21, 1, 9, 1830, 150], got)
# the framebuffer/runtime state area must be untouched by stack use
check('stack stayed clear of runtime RAM (0xE000..0xE80F untouched)',
      all(m.mem[a] == 0 for a in range(0xE000, 0xE810)), [hex(a) for a in range(0xE000, 0xE810) if m.mem[a]][:4])

# ------------------------------------------------------------------ peek / poke
m, v, why, _ = run('''
poke(@PK, 77)
poke(@PK + 1, 300)
a = peek(@PK)
b = peek(@PK + 1)
c = peek(@PK) + peek(@PK + 1) * 256
def main():
    pass
''')
check('poke/peek roundtrip (low byte only)', (var(m,v,'a'), var(m,v,'b'), var(m,v,'c')) == (77, 44, 77 + 44 * 256),
      (var(m,v,'a'), var(m,v,'b'), var(m,v,'c')))

# ------------------------------------------------------------------ error cases
def errs(src):
    try:
        build_source(src)
    except Exception as e:
        return type(e).__name__ + ': ' + str(e)
    return None

e1 = errs('rom t = [1,2]\ndef main():\n    t[0] = 5\n')
check('error: write to rom table', e1 and 'read-only' in e1, e1)
e2 = errs('a = [1,2]\na = 5\ndef main():\n    pass\n')
check('error: assign to array name', e2 and 'array' in e2, e2)
e3 = errs('def main():\n    x[0] = 1\n')
check('error: unknown array', e3 and 'not a RAM array' in e3, e3)
e4 = errs('rom8 t = [1, 300]\ndef main():\n    pass\n')
check('error: rom8 entry out of range', e4 and '0..255' in e4, e4)
e5 = errs('def main():\n    text(0, 0, "caf\\xe9")\n')
check('error: bad escape/nonascii string', e5 is not None, e5)
e6 = errs('a = [0] * 4\ndef f():\n    return 1\ndef main():\n    a[f()] += 1\n')
check('error: call inside index of compound assignment', e6 and 'function call' in e6, e6)
e7 = errs('def main():\n    x = "hi" "there"\n')
check('error: junk after string', e7 is not None, e7)

print('\n%d failure(s)' % len(FAILS))
sys.exit(1 if FAILS else 0)
