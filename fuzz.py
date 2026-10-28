import random, sys
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import build_source
from u8sim import U8

def w16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v

def tdiv(a, b):
    if b == 0:
        return 0, 0
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q, a - q * b

class N:
    pass

def gen(depth, names, rng):
    if depth == 0 or rng.random() < 0.2:
        if rng.random() < 0.5:
            n = rng.choice(names)
            return ('v', n)
        return ('n', rng.choice([0, 1, 2, 3, 5, 7, 10, 100, 255, 256, 1000, 12345, 32767, -1, -2, -7, -100, -32768, -255]))
    r = rng.random()
    if r < 0.55:
        op = rng.choice(['+', '-', '*', '/', '%', '&', '|', '^'])
        return ('b', op, gen(depth - 1, names, rng), gen(depth - 1, names, rng))
    if r < 0.65:
        op = rng.choice(['<<', '>>'])
        return ('b', op, gen(depth - 1, names, rng), ('n', rng.randint(0, 15)))
    if r < 0.8:
        op = rng.choice(['==', '!=', '<', '>', '<=', '>='])
        return ('c', op, gen(depth - 1, names, rng), gen(depth - 1, names, rng))
    if r < 0.9:
        return (rng.choice(['and', 'or']), gen(depth - 1, names, rng), gen(depth - 1, names, rng))
    if r < 0.95:
        return ('not', gen(depth - 1, names, rng))
    return (rng.choice(['neg', 'inv']), gen(depth - 1, names, rng))

def src(e):
    k = e[0]
    if k == 'v': return e[1]
    if k == 'n': return '(%d)' % e[1]
    if k in ('b', 'c'): return '(%s %s %s)' % (src(e[2]), e[1], src(e[3]))
    if k in ('and', 'or'): return '(%s %s %s)' % (src(e[1]), k, src(e[2]))
    if k == 'not': return '(not %s)' % src(e[1])
    if k == 'neg': return '(-%s)' % src(e[1])
    if k == 'inv': return '(~%s)' % src(e[1])

def ev(e, env):
    k = e[0]
    if k == 'v': return env[e[1]]
    if k == 'n': return e[1]
    if k == 'b':
        a, b = ev(e[2], env), ev(e[3], env)
        op = e[1]
        if op == '+': return w16(a + b)
        if op == '-': return w16(a - b)
        if op == '*': return w16(a * b)
        if op == '/': return w16(tdiv(a, b)[0])
        if op == '%': return w16(tdiv(a, b)[1])
        if op == '&': return w16(a & b)
        if op == '|': return w16(a | b)
        if op == '^': return w16(a ^ b)
        if op == '<<': return w16(a << b)
        if op == '>>': return w16(a >> b)
    if k == 'c':
        a, b = ev(e[2], env), ev(e[3], env)
        return int({'==': a == b, '!=': a != b, '<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[e[1]])
    if k == 'and': return int(bool(ev(e[1], env)) and bool(ev(e[2], env)))
    if k == 'or': return int(bool(ev(e[1], env)) or bool(ev(e[2], env)))
    if k == 'not': return int(not ev(e[1], env))
    if k == 'neg': return w16(-ev(e[1], env))
    if k == 'inv': return w16(~ev(e[1], env))

rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
total = bad = 0
for prog in range(int(sys.argv[2]) if len(sys.argv) > 2 else 12):
    env = {n: rng.choice([0, 1, -1, 5, -5, 300, -300, 32767, -32768, 12345, -12345, 77]) for n in 'abcd'}
    lines = ['%s = %d' % (k, v) for k, v in env.items()]
    exprs = [gen(rng.randint(1, 4), list(env), rng) for _ in range(25)]
    for i, e in enumerate(exprs):
        lines.append('r%d = %s' % (i, src(e)))
    code = '\n'.join(lines) + '\n'
    rom, full, vars_, syms = build_source(code)
    m = U8(rom)
    res = m.run(5_000_000)
    assert 'B to self' in res, res
    for i, e in enumerate(exprs):
        a = vars_['r%d' % i]
        got = w16(m.mem[a] | (m.mem[a + 1] << 8))
        exp = ev(e, env)
        total += 1
        if got != exp:
            bad += 1
            if bad <= 6:
                print('MISMATCH', src(e), 'env', env, 'got', got, 'exp', exp)
print('expressions', total, 'mismatches', bad)
