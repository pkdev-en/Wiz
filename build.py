"""build.py - one command: Wiz source -> ROM .bin (+ .asm listing).

usage: python3 build.py prog.wz [out.bin] [--target cwii|cw|all]

"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from u8asm import Assembler, to_bin, AsmError
from wizc import compile_to_asm, WizError
from targets import TARGETS, DEFAULT_TARGET, get_target, declared_targets, select_sections, SectionError
import wizimport


def make_boot(target):
    t = open(os.path.join(HERE, target.template), encoding='utf8', errors='replace').read()
    t = t.replace('\r', '').replace('\t', ' ')
    keep = []
    for line in t.split('\n'):
        if re.match(r'^\s*(type\s*\(|model\b|romwindow\b|extrn\b|public\b)', line, re.I):
            continue
        if re.match(r'^\s*b\s+_main\s*$', line, re.I):
            line = '    B __wiz_entry'
        keep.append(line)
    return '\n'.join(keep) + '\n'


def runtime_for(target):
    """runtime.asm with the lines tagged for the other LCD type removed."""
    drop = ';@1p' if target.planes == 2 else ';@2p'
    out = ['_ROWS EQU %d' % target.rows]      # visible LCD rows: pixel() ignores y >= _ROWS
    for line in open(os.path.join(HERE, 'runtime.asm')).read().split('\n'):
        if line.rstrip().endswith(drop):
            continue
        if line.rstrip().endswith(';@seg') and not target.rom_seg:
            continue
        if line.rstrip().endswith(';@off'):          # VRAM row offset (cw: user y=0 is VRAM row 1)
            if not target.row_off:
                continue
            line = line.replace('#32 ;@off', '#%d ;@off' % (32 * target.row_off))
        out.append(line)
    return '\n'.join(out)


def build_source(src, target=None, path=None):
    """path = the file the source came from, so `import` can find files next to it"""
    tg = get_target(target or DEFAULT_TARGET)
    try:
        src = select_sections(src, tg)
    except SectionError as e:
        raise WizError(str(e))
    src = wizimport.expand_imports(src, tg, path, WizError)
    body, variables = compile_to_asm(src, tg)
    full = make_boot(tg) + body + runtime_for(tg)
    asm = Assembler(tg.core)
    img = asm.assemble(full)
    rom = to_bin(img)
    return rom, full, variables, asm.syms


def main():
    ap = argparse.ArgumentParser(description='Wiz compiler', usage='build.py prog.wz [out.bin] [--target cwii|cw|all]')
    ap.add_argument('prog')
    ap.add_argument('out', nargs='?')
    ap.add_argument('--target', default=None)
    a = ap.parse_args()
    text = open(a.prog).read()
    try:
        declared = declared_targets(text)
    except SectionError as e:
        print('error:', e)
        sys.exit(2)
    if a.target in (None, 'all'):
        targets = declared or ([DEFAULT_TARGET] if a.target is None else [t for t in TARGETS if t != 'cwapp'])
    else:
        if a.target not in TARGETS:
            print('error: unknown target %r (use %s, all)' % (a.target, ', '.join(TARGETS)))
            sys.exit(2)
        targets = [a.target]
    base = os.path.splitext(a.out or a.prog)[0]
    # one declared machine (e.g. cwii.wz with `for cwii`) -> plain prog.bin, no repeated machine name
    legacy_name = (a.target is None and targets == (declared or ['cwii']) and len(targets) == 1)
    failed = False
    for name in targets:
        tg = TARGETS[name]
        out = a.out if (a.out and len(targets) == 1) else (base + '.bin' if legacy_name else '%s.%s.bin' % (base, name))
        try:
            rom, full, variables, syms = build_source(text, tg, a.prog)
        except (WizError, AsmError) as e:
            m = re.search(r'line (\d+)', str(e))
            where = wizimport.describe_line(int(m.group(1))) if m else None
            msg = str(e)
            if where and not msg.startswith(where[0]):
                msg = re.sub(r'line \d+', '%s line %d' % (where[0], where[1]), msg, 1)
            print('error [%s]:' % name, msg)
            if where and not str(e).startswith(where[0]):
                print('  %4d | %s' % (where[1], where[2]))
            failed = True
            continue
        from wizc import LAST_NOTES
        for note in LAST_NOTES:
            print('note [%s]:' % name, note)
        open(out, 'wb').write(rom)
        open(os.path.splitext(out)[0] + '.asm', 'w').write(full)
        print('%s [%s %s, core %s]: %d bytes ROM, %d variables -> %s' % (a.prog, name, tg.chip, tg.core, len(rom), len(variables), out))
    if failed:
        sys.exit(2)


if __name__ == '__main__':
    main()
