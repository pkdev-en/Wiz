"""targets.py - hardware description of each supported calculator + `for <target>` source sections.

Facts below come from the files in nguyen_lieu (TRG memory maps, libcw.h IS_CWX branches, the Lapis
boot templates). Nothing here has been measured on a real ML620906 by me.

    cwii : ML620909, ROM 0x0000-0x8FFF, RAM 0x9000-0xEFFF, LCD = 2 bitplanes (4 grey levels), screen 192x64
    cw   : ML620906, ROM 0x0000-0xCFFF, RAM 0xD000-0xEFFF, LCD = 1 bitplane (black/white only), screen 192x63 (measured on a real screen: VRAM row 0 is not displayed,
           the visible rows are VRAM rows 1..63, so user y = 0..62 is drawn at VRAM row y+1)
           CPU core = nX-U16/100 (ML620906.TRG says FAMILY_ID=U16; the DCL only says nX-U8/100 as a Lexide
           workaround - its own comment: "U16 wont be recognized").
"""
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    name: str
    chip: str
    template: str        # boot template file (raw SFR addresses, assembles with u8asm)
    rom_limit: int       # first address that is NOT ROM
    ram_lo: int          # first RAM address
    var_base: int        # compiler variables/arrays start here
    var_limit: int       # ... and must stay below this (runtime RAM starts at 0xE000)
    planes: int          # LCD bitplanes (0xF037 plane select exists only when 2)
    rom_seg: int = 0     # data segment (DSR) of the program's ROM tables; 0 = normal, 3 = 'cwapp' (code lives in segment 3)
    rows: int = 64       # visible LCD rows (width is always 192): cwii 192x64, cw 192x63
    core: str = 'nX-U8/100'   # CPU core the assembler/simulator use (see u8asm.CORES). cw = ML620906 = nX-U16/100
    row_off: int = 0     # VRAM row of user y=0. cw: 1 (hardware row 0 is NOT shown; the 63 visible rows are VRAM rows 1..63)


TARGETS = {
    'cwii': Target('cwii', 'ML620909', 'template_ML620909.asm', 0x9000, 0x9000, 0x9000, 0xE000, 2),
    'cw': Target('cw', 'ML620906', 'template_ML620906.asm', 0xD000, 0xD000, 0xD000, 0xE000, 1, 0, 63, 'nX-U16/100', 1),
    # 'cwapp': a Wiz program that is patched INTO a fx-580VN X firmware ROM (free flash 0x30E40.., segment 3) - see patch_menu.py
    'cwapp': Target('cwapp', 'ML620906', 'template_cwapp.asm', 0xD000, 0xD000, 0xD000, 0xE000, 1, 3, 63, 'nX-U16/100', 1),
}
DEFAULT_TARGET = os.environ.get('WIZ_TARGET', 'cwii')


def get_target(t):
    if isinstance(t, Target):
        return t
    if t not in TARGETS:
        raise ValueError('unknown target %r (use %s)' % (t, ', '.join(TARGETS)))
    return TARGETS[t]


# ---------------------------------------------------------------- sections
_HEADER = re.compile(r'^for[ \t]+([A-Za-z0-9_]+(?:[ \t]*,[ \t]*[A-Za-z0-9_]+)*)[ \t]*(?:#.*)?$')
_SEP = re.compile(r'^[ \t]*[-\u2014\u2013\u2500\u2501\u2550=_]{3,}[ \t]*(?:#.*)?$')


class SectionError(Exception):
    pass


def _scan(src):
    """yield (line_no, raw_line, kind, names) where kind in header/sep/code"""
    for ln, raw in enumerate(src.replace('\r', '').split('\n'), 1):
        m = _HEADER.match(raw)
        if m:
            names = [x.strip() for x in m.group(1).split(',')]
            yield ln, raw, 'header', names
        elif _SEP.match(raw):
            yield ln, raw, 'sep', None
        else:
            yield ln, raw, 'code', None


def declared_targets(src):
    """targets named by `for ...` headers, in order of first appearance ('all' adds nothing)."""
    out = []
    for ln, raw, kind, names in _scan(src):
        if kind == 'header':
            for n in names:
                if n != 'all' and n not in TARGETS:
                    raise SectionError('line %d: unknown target %r (use %s, all)' % (ln, n, ', '.join(TARGETS)))
                if n != 'all' and n not in out:
                    out.append(n)
    return out


def select_sections(src, target):
    """Return `src` with every line that belongs to another target blanked out.
    Line numbers never change, so compiler errors still point at the right line.
    Text before the first header, and text after a separator line, is common to all targets."""
    tname = get_target(target).name
    declared = declared_targets(src)
    if declared and tname not in declared and not any(
            k == 'header' and 'all' in n for _, _, k, n in _scan(src)):
        raise SectionError("this file has no 'for %s' section (it has: %s)" % (tname, ', '.join(declared)))
    out = []
    active = True            # common code is active for every target
    for ln, raw, kind, names in _scan(src):
        if kind == 'header':
            active = ('all' in names) or (tname in names)
            out.append('')
        elif kind == 'sep':
            active = True
            out.append('')
        else:
            out.append(raw if active else '')
    return '\n'.join(out)
