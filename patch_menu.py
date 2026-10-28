#!/usr/bin/env python3
"""patch_menu.py - put a Wiz program into the menu of a Casio fx-580VN X (ML620906, 256 KB) ROM.

    python3 patch_menu.py rom.bin app.wz out.bin [--slot 2] [--mode E0] [--force]

What it does (all addresses were read from bro.bin with a disassembler; NOT yet run on the real firmware):
  1. builds app.wz for the 'cwapp' target: code + data at 3:0E40 (ROM offset 30E40h, free flash, all 0xFF)
  2. writes the program there; its first bytes are a trampoline (see template_cwapp.asm)
  3. overwrites firmware 2:5E1E  "CMP R8,03 / BEQ 2:5E88"  (set_mode, 2:5D82)  with  "B 3:0E40"
  4. sets the mode id of menu slot N (menu table at 0x7FF8, 6 bytes per entry: icon ptr, mode id, data ptr)
     to the mode the trampoline answers to (default 0E0h). The slot keeps its icon and name.
Selecting that slot then runs the program; exit() in the program restarts the firmware (reset handler 0:A1CE).
"""
import argparse
import sys

from build import build_source
from u8asm import AsmError
from wizc import WizError

SZ = 262144
MB = 0x7FF8              # menu table
NB = 0x5516              # name pointer table
NS = 12
HOOK = 0x25E1E           # inside set_mode
HOOK_OLD = bytes([0x03, 0x78, 0x33, 0xC9])      # CMP R8,03 ; BEQ $25E88
HOOK_NEW = bytes([0x00, 0xF3, 0x40, 0x0E])      # B 3:0E40
BASE = 0x30E40
CH = '123456789ABC'


def u16(r, o):
    return r[o] | r[o + 1] << 8


def cstr(r, a):
    s = ''
    while r[a] and len(s) < 40:
        s += chr(r[a])
        a += 1
    return s


def check_menu(r):
    for k in range(NS):
        o = MB + 6 * k
        ip, dp = u16(r, o), u16(r, o + 4)
        if not (0x100 <= ip <= SZ - 138) or r[o + 3] or r[dp] != 2 or r[dp + 2] or r[dp + 3]:
            return 'menu entry %s does not look right' % CH[k]
        s = cstr(r, u16(r, NB + 2 * (r[dp + 1] - 2)))
        if len(s) < 3 or not all(32 <= ord(c) < 127 for c in s):
            return 'menu entry %s: cannot read its name' % CH[k]
    return ''


def slot_name(r, k):
    o = MB + 6 * k
    return cstr(r, u16(r, NB + 2 * (r[u16(r, o + 4) + 1] - 2)))


def main():
    ap = argparse.ArgumentParser(description='patch a Wiz program into the fx-580VN X menu')
    ap.add_argument('rom')
    ap.add_argument('app')
    ap.add_argument('out')
    ap.add_argument('--slot', type=int, default=2, help='menu slot 1..12 (default 2)')
    ap.add_argument('--mode', default='E0', help='mode id (hex) the trampoline answers to (default E0)')
    ap.add_argument('--force', action='store_true', help='write even if the target area is not all 0xFF')
    a = ap.parse_args()

    rom = bytearray(open(a.rom, 'rb').read())
    if len(rom) != SZ:
        sys.exit('error: ROM is %d bytes, an fx-580VN X dump is %d' % (len(rom), SZ))
    bad = check_menu(rom)
    if bad:
        sys.exit('error: this does not look like the ROM these addresses were read from: ' + bad)
    if bytes(rom[HOOK:HOOK + 4]) != HOOK_OLD:
        sys.exit('error: set_mode at %05X is %s, expected %s (different firmware?)' % (HOOK, bytes(rom[HOOK:HOOK + 4]).hex(' '), HOOK_OLD.hex(' ')))
    if not 1 <= a.slot <= NS:
        sys.exit('error: --slot must be 1..%d' % NS)
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
    if BASE + len(code) > SZ:
        sys.exit('error: program is %d bytes, only %d fit' % (len(code), SZ - BASE))
    if not a.force and any(b != 0xFF for b in rom[BASE:BASE + len(code)]):
        sys.exit('error: %05X.. is not free flash (not all FF); use --force to overwrite anyway' % BASE)

    changes = []
    rom[BASE:BASE + len(code)] = code
    changes.append((BASE, 'program (%d bytes)' % len(code)))
    rom[HOOK:HOOK + 4] = HOOK_NEW
    changes.append((HOOK, 'hook  %s -> %s' % (HOOK_OLD.hex(' '), HOOK_NEW.hex(' '))))
    o = MB + 6 * (a.slot - 1) + 2
    old = bytes(rom[o:o + 2])
    rom[o:o + 2] = bytes([mode, 0x00])
    changes.append((o, 'menu slot %s (%s) mode id %s -> %02X 00' % (CH[a.slot - 1], slot_name(rom, a.slot - 1), old.hex(' '), mode)))
    open(a.out, 'wb').write(rom)

    print('wrote %s' % a.out)
    for addr, what in changes:
        print('  %05X  %s' % (addr, what))
    print('program entry  %X:%04X   exit -> 0:A1CE (firmware reset)' % (syms['_APP'] >> 16, syms['_APP'] & 0xFFFF))
    print('slot %s keeps its icon and name; selecting it runs the program.' % CH[a.slot - 1])
    print('NOT tested on the real firmware: try it in an emulator first.')


if __name__ == '__main__':
    main()
