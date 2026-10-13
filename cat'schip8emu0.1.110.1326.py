#!/usr/bin/env python3
"""
cat's chip 8 emulator 0.1.1
===========================
PR: 60 FPS CHIP-8 · mGBA GUI · CHIP-8 Audio Engine · Blue-hue · Black buttons
files = off ready (built-in ROMs in RAM + external .ch8/.rom loader)
"""

from __future__ import annotations

import argparse
import copy
import os
import pathlib
import pickle
import random
import sys
import time
import zlib
from typing import Dict, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────
# IDENTITY & BLUE-HUE / BLACK-BUTTON PALETTE
# ──────────────────────────────────────────────────────────────
WINDOW_TITLE = "cat's chip 8 emulator 0.1.1"
APP_VERSION = "0.1.1"
TARGET_FPS = 60.0
FRAME_PERIOD = 1.0 / TARGET_FPS

SCREEN_W = 64
SCREEN_H = 32
WIN_W, WIN_H = 600, 400   # fixed OS window size (centered)

# Blue-hue dark background & blue text palette
BG = "#1a1f2e"
BAR_BG = "#151a28"
PANEL_BG = "#181e2c"
VIEW_BG = "#0f1420"
INPUT_BG = "#121722"
STATUS_BG = "#007acc"
BORDER = "#2a3348"

FG = "#9bbcff"          # Primary blue text
FG_BRIGHT = "#d6e4ff"   # Highlight blue text
FG_DIM = "#6b86b5"      # Muted blue text
ACCENT = "#007acc"

BTN_BG = "#000000"      # Black buttons
BTN_FG = "#7eb6ff"      # Blue button text
BTN_HOVER = "#1a3a5c"   # Deep blue hover
BTN_ACTIVE = "#0d2238"

PIXEL_ON = "#7eb6ff"    # Phosphor blue-white pixel
PIXEL_OFF = "#0b101b"   # Deep navy CRT off pixel

FONTSET = (
    0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
    0x20, 0x60, 0x20, 0x20, 0x70,  # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
    0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
    0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
    0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
    0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
    0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
    0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
    0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
    0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
    0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
    0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
    0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
    0xF0, 0x80, 0xF0, 0x80, 0x80,  # F
)

# Standard CHIP-8 4x4 Hex Keypad layout -> PC Keyboard mapping
KEYPAD_LAYOUT = (
    (0x1, "1"), (0x2, "2"), (0x3, "3"), (0xC, "4"),
    (0x4, "q"), (0x5, "w"), (0x6, "e"), (0xD, "r"),
    (0x7, "a"), (0x8, "s"), (0x9, "d"), (0xE, "f"),
    (0xA, "z"), (0x0, "x"), (0xB, "c"), (0xF, "v"),
)
KEY_TO_CHIP8 = {k: code for code, k in KEYPAD_LAYOUT}
KEY_TO_CHIP8.update({
    "Up": 0x1, "Down": 0x4, "Left": 0x7, "Right": 0x9, "space": 0x5,
})


# ──────────────────────────────────────────────────────────────
# BUILT-IN IN-MEMORY CHIP-8 ROMS (FILES = OFF)
# ──────────────────────────────────────────────────────────────
def _words(*ops: int) -> bytes:
    out = bytearray()
    for op in ops:
        out.append((op >> 8) & 0xFF)
        out.append(op & 0xFF)
    return bytes(out)


def build_builtin_roms() -> Dict[str, bytes]:
    """Assemble playable CHIP-8 programs directly in memory."""
    # 1. Cat's Pong (1P Paddle vs Wall/Court · Keys: 1/Q/Up = Up, 4/A/Down = Down)
    pong = _words(
        0x6002,  # 0x200: V0 = 2 (paddle X)
        0x610C,  # 0x202: V1 = 12 (paddle Y)
        0x6220,  # 0x204: V2 = 32 (ball X)
        0x6310,  # 0x206: V3 = 16 (ball Y)
        0x6401,  # 0x208: V4 = 1 (ball dX)
        0x6501,  # 0x20A: V5 = 1 (ball dY)
        0x6600,  # 0x20C: V6 = 0 (score)
        # Main loop (0x20E):
        0x00E0,  # 0x20E: CLS
        0xA260,  # 0x210: I = paddle sprite (0x260)
        0xD016,  # 0x212: DRW V0, V1, 6
        0xA266,  # 0x214: I = ball sprite (0x266)
        0xD232,  # 0x216: DRW V2, V3, 2
        0xF629,  # 0x218: I = font(V6)
        0x671E,  # 0x21A: V7 = 30
        0x6801,  # 0x21C: V8 = 1
        0xD785,  # 0x21E: DRW V7, V8, 5 (draw score)
        # Input check:
        0x6901,  # 0x220: V9 = key 1
        0xE99E,  # 0x222: SKP V9
        0x1228,  # 0x224: JMP 0x228
        0x71FE,  # 0x226: V1 -= 2
        0x6904,  # 0x228: V9 = key 4
        0xE99E,  # 0x22A: SKP V9
        0x1230,  # 0x22C: JMP 0x230
        0x7102,  # 0x22E: V1 += 2
        0x691F,  # 0x230: V9 = 31
        0x8192,  # 0x232: V1 &= 31
        # Move ball:
        0x8244,  # 0x234: V2 += V4
        0x8354,  # 0x236: V3 += V5
        # Bounce Y (0 or 30):
        0x3300,  # 0x238: SE V3, 0
        0x1240,  # 0x23A: JMP 0x240
        0x6501,  # 0x23C: V5 = 1
        0x1246,  # 0x23E: JMP 0x246
        0x331E,  # 0x240: SE V3, 30
        0x1246,  # 0x242: JMP 0x246
        0x65FF,  # 0x244: V5 = -1
        # Bounce right wall (X == 62):
        0x323E,  # 0x246: SE V2, 62
        0x124E,  # 0x248: JMP 0x24E
        0x64FF,  # 0x24A: V4 = -1
        0x120E,  # 0x24C: JMP 0x20E
        # Check left side (X == 4):
        0x3204,  # 0x24E: SE V2, 4
        0x120E,  # 0x250: JMP 0x20E
        0x6401,  # 0x252: V4 = 1
        0x7601,  # 0x254: V6 += 1 (score++)
        0x690F,  # 0x256: V9 = 0x0F
        0x8692,  # 0x258: V6 &= 0x0F
        0x6902,  # 0x25A: V9 = 2 (beep)
        0xF918,  # 0x25C: ST = V9
        0x120E,  # 0x25E: JMP 0x20E
        # Sprites at 0x260:
        0x8080, 0x8080, 0x8080,  # 0x260: 6-px tall paddle
        0xC0C0,                  # 0x266: 2x2 ball
    )

    # 2. 10PRINT Maze Generator
    maze = _words(
        0x00E0,  # 0x200: CLS
        0x6000,  # 0x202: V0 = 0 (X)
        0x6100,  # 0x204: V1 = 0 (Y)
        0xA222,  # 0x206: I = 0x222 (slash1)
        0xC201,  # 0x208: V2 = rnd & 1
        0x3201,  # 0x20A: SE V2, 1
        0xA226,  # 0x20C: I = 0x226 (slash2)
        0xD014,  # 0x20E: DRW V0, V1, 4
        0x7004,  # 0x210: V0 += 4
        0x3040,  # 0x212: SE V0, 64
        0x1206,  # 0x214: JMP 0x206
        0x6000,  # 0x216: V0 = 0
        0x7104,  # 0x218: V1 += 4
        0x3120,  # 0x21A: SE V1, 32
        0x1206,  # 0x21C: JMP 0x206
        0x1200,  # 0x21E: JMP 0x200 (restart)
        0x0000,  # 0x220: pad
        0x8040, 0x2010,  # 0x222: backslash
        0x1020, 0x4080,  # 0x226: slash
    )

    # 3. Target Blaster (Move crosshair with W/A/S/D or 2/4/6/8, Fire with 5/Space)
    blaster = _words(
        0x601E,  # 0x200: V0 = 30 (cursor X)
        0x610E,  # 0x202: V1 = 14 (cursor Y)
        0xC237,  # 0x204: V2 = target X
        0xC31B,  # 0x206: V3 = target Y
        0x00E0,  # 0x208: CLS
        0xA240,  # 0x20A: I = target sprite
        0xD233,  # 0x20C: DRW V2, V3, 3
        0xA243,  # 0x20E: I = crosshair sprite
        0xD013,  # 0x210: DRW V0, V1, 3
        0x6405,  # 0x212: V4 = key 5 (Space / W)
        0xE49E,  # 0x214: SKP V4
        0x1220,  # 0x216: JMP 0x220
        0x6503,  # 0x218: V5 = 3
        0xF518,  # 0x21A: ST = 3
        0xC237,  # 0x21C: new target X
        0xC31B,  # 0x21E: new target Y
        0x6407,  # 0x220: key 7 (A/Left)
        0xE49E,  # 0x222: SKP V4
        0x7002,  # 0x224: V0 += 2
        0x70FF,  # 0x226: V0 -= 1
        0x6409,  # 0x228: key 9 (D/Right)
        0xE49E,  # 0x22A: SKP V4
        0x70FE,  # 0x22C: V0 -= 2
        0x7001,  # 0x22E: V0 += 1
        0x6401,  # 0x230: key 1 (Up)
        0xE49E,  # 0x232: SKP V4
        0x7102,  # 0x234: V1 += 2
        0x71FF,  # 0x236: V1 -= 1
        0x6404,  # 0x238: key 4 (Down)
        0xE49E,  # 0x23A: SKP V4
        0x71FE,  # 0x23C: V1 -= 2
        0x7101,  # 0x23E: V1 += 1
        0x1208,  # 0x240 -> wait, keep sprite at 0x242
    )
    # Fix blaster jump & sprites cleanly:
    blaster = _words(
        0x601E, 0x610E, 0xC237, 0xC31B,
        0x00E0, 0xA234, 0xD233, 0xA238, 0xD013,
        0x6405, 0xE49E, 0x121E, 0x6503, 0xF518, 0xC237, 0xC31B,
        0x6407, 0xE4A1, 0x70FF,
        0x6409, 0xE4A1, 0x7001,
        0x6401, 0xE4A1, 0x71FF,
        0x6404, 0xE4A1, 0x7101,
        0x1208,
        0xE0A0, 0xE000,  # 0x234: target box
        0x40E0, 0x4000,  # 0x238: crosshair
    )

    return {
        "Cat's Pong": pong,
        "10PRINT Maze": maze,
        "Target Blaster": blaster,
    }


BUILTIN_ROMS = build_builtin_roms()


# ──────────────────────────────────────────────────────────────
# CHIP-8 VIRTUAL MACHINE ARCHITECTURE
# ──────────────────────────────────────────────────────────────
class Chip8CPU:
    """Clean-room CHIP-8 interpreter (4K RAM, 35 opcodes, 60Hz timers)."""

    MEM_SIZE = 4096
    START_ADDR = 0x200
    FONT_ADDR = 0x050

    def __init__(self) -> None:
        self.ram = bytearray(self.MEM_SIZE)
        self.v = bytearray(16)
        self.i = 0
        self.pc = self.START_ADDR
        self.stack: List[int] = [0] * 16
        self.sp = 0
        self.delay_timer = 0
        self.sound_timer = 0
        self.vram = bytearray(SCREEN_W * SCREEN_H)
        self.keys = bytearray(16)
        self.wait_key_reg: Optional[int] = None
        self.draw_flag = True
        self.cycles = 0
        self.rom_data = b""
        self.reset()

    def reset(self) -> None:
        self.ram[:] = b"\x00" * self.MEM_SIZE
        self.ram[self.FONT_ADDR:self.FONT_ADDR + len(FONTSET)] = bytes(FONTSET)
        if self.rom_data:
            end = min(self.MEM_SIZE, self.START_ADDR + len(self.rom_data))
            self.ram[self.START_ADDR:end] = self.rom_data[:end - self.START_ADDR]
        self.v[:] = b"\x00" * 16
        self.i = 0
        self.pc = self.START_ADDR
        self.stack = [0] * 16
        self.sp = 0
        self.delay_timer = 0
        self.sound_timer = 0
        self.vram[:] = b"\x00" * (SCREEN_W * SCREEN_H)
        self.keys[:] = b"\x00" * 16
        self.wait_key_reg = None
        self.draw_flag = True
        self.cycles = 0

    def load_rom_bytes(self, data: bytes) -> None:
        self.rom_data = bytes(data[:self.MEM_SIZE - self.START_ADDR])
        self.reset()

    def tick_timers(self) -> bool:
        """Advance 60 Hz hardware timers. Returns True if sound buzzer is active."""
        if self.delay_timer > 0:
            self.delay_timer -= 1
        beep = self.sound_timer > 0
        if self.sound_timer > 0:
            self.sound_timer -= 1
        return beep

    def step(self) -> int:
        """Fetch, decode, and execute one 16-bit big-endian CHIP-8 instruction."""
        if self.wait_key_reg is not None:
            for k in range(16):
                if self.keys[k]:
                    self.v[self.wait_key_reg] = k
                    self.wait_key_reg = None
                    break
            if self.wait_key_reg is not None:
                return 0

        pc = self.pc & 0xFFF
        op = (self.ram[pc] << 8) | self.ram[(pc + 1) & 0xFFF]
        self.pc = (pc + 2) & 0xFFF
        self.cycles += 1

        top = op & 0xF000
        x = (op >> 8) & 0x0F
        y = (op >> 4) & 0x0F
        n = op & 0x000F
        nn = op & 0x00FF
        nnn = op & 0x0FFF
        v = self.v

        if op == 0x00E0:  # CLS
            self.vram[:] = b"\x00" * (SCREEN_W * SCREEN_H)
            self.draw_flag = True
        elif op == 0x00EE:  # RET
            self.sp = (self.sp - 1) & 0x0F
            self.pc = self.stack[self.sp]
        elif top == 0x0000:  # SYS NNN (ignored on modern interpreters)
            pass
        elif top == 0x1000:  # JP NNN
            self.pc = nnn
        elif top == 0x2000:  # CALL NNN
            self.stack[self.sp] = self.pc
            self.sp = (self.sp + 1) & 0x0F
            self.pc = nnn
        elif top == 0x3000:  # SE Vx, NN
            if v[x] == nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0x4000:  # SNE Vx, NN
            if v[x] != nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0x5000:  # SE Vx, Vy
            if v[x] == v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0x6000:  # LD Vx, NN
            v[x] = nn
        elif top == 0x7000:  # ADD Vx, NN
            v[x] = (v[x] + nn) & 0xFF
        elif top == 0x8000:
            if n == 0x0:
                v[x] = v[y]
            elif n == 0x1:
                v[x] |= v[y]
                v[0xF] = 0
            elif n == 0x2:
                v[x] &= v[y]
                v[0xF] = 0
            elif n == 0x3:
                v[x] ^= v[y]
                v[0xF] = 0
            elif n == 0x4:
                total = v[x] + v[y]
                v[x] = total & 0xFF
                v[0xF] = 1 if total > 0xFF else 0
            elif n == 0x5:
                borrow = 1 if v[x] >= v[y] else 0
                v[x] = (v[x] - v[y]) & 0xFF
                v[0xF] = borrow
            elif n == 0x6:
                lsb = v[x] & 1
                v[x] = v[x] >> 1
                v[0xF] = lsb
            elif n == 0x7:
                borrow = 1 if v[y] >= v[x] else 0
                v[x] = (v[y] - v[x]) & 0xFF
                v[0xF] = borrow
            elif n == 0xE:
                msb = (v[x] >> 7) & 1
                v[x] = (v[x] << 1) & 0xFF
                v[0xF] = msb
        elif top == 0x9000:  # SNE Vx, Vy
            if v[x] != v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0xA000:  # LD I, NNN
            self.i = nnn
        elif top == 0xB000:  # JP V0, NNN
            self.pc = (nnn + v[0]) & 0xFFF
        elif top == 0xC000:  # RND Vx, NN
            v[x] = random.randint(0, 255) & nn
        elif top == 0xD000:  # DRW Vx, Vy, N
            sx = v[x] % SCREEN_W
            sy = v[y] % SCREEN_H
            v[0xF] = 0
            vram = self.vram
            for row in range(n):
                py = sy + row
                if py >= SCREEN_H:
                    break
                sprite_byte = self.ram[(self.i + row) & 0xFFF]
                if not sprite_byte:
                    continue
                for col in range(8):
                    px = sx + col
                    if px >= SCREEN_W:
                        break
                    if sprite_byte & (0x80 >> col):
                        idx = py * SCREEN_W + px
                        if vram[idx]:
                            v[0xF] = 1
                        vram[idx] ^= 1
            self.draw_flag = True
        elif top == 0xE000:
            key_idx = v[x] & 0x0F
            if nn == 0x9E:  # SKP Vx
                if self.keys[key_idx]:
                    self.pc = (self.pc + 2) & 0xFFF
            elif nn == 0xA1:  # SKNP Vx
                if not self.keys[key_idx]:
                    self.pc = (self.pc + 2) & 0xFFF
        elif top == 0xF000:
            if nn == 0x07:
                v[x] = self.delay_timer
            elif nn == 0x0A:
                self.wait_key_reg = x
            elif nn == 0x15:
                self.delay_timer = v[x]
            elif nn == 0x18:
                self.sound_timer = v[x]
            elif nn == 0x1E:
                self.i = (self.i + v[x]) & 0xFFF
            elif nn == 0x29:
                self.i = (self.FONT_ADDR + (v[x] & 0x0F) * 5) & 0xFFF
            elif nn == 0x33:
                val = v[x]
                self.ram[self.i & 0xFFF] = val // 100
                self.ram[(self.i + 1) & 0xFFF] = (val // 10) % 10
                self.ram[(self.i + 2) & 0xFFF] = val % 10
            elif nn == 0x55:
                for r in range(x + 1):
                    self.ram[(self.i + r) & 0xFFF] = v[r]
            elif nn == 0x65:
                for r in range(x + 1):
                    v[r] = self.ram[(self.i + r) & 0xFFF]
        return op

    @staticmethod
    def disassemble_op(op: int) -> str:
        top = op & 0xF000
        x = (op >> 8) & 0x0F
        y = (op >> 4) & 0x0F
        n = op & 0x000F
        nn = op & 0x00FF
        nnn = op & 0x0FFF
        if op == 0x00E0:
            return "CLS"
        if op == 0x00EE:
            return "RET"
        if top == 0x1000:
            return f"JP   ${nnn:03X}"
        if top == 0x2000:
            return f"CALL ${nnn:03X}"
        if top == 0x3000:
            return f"SE   V{x:X}, #${nn:02X}"
        if top == 0x4000:
            return f"SNE  V{x:X}, #${nn:02X}"
        if top == 0x5000:
            return f"SE   V{x:X}, V{y:X}"
        if top == 0x6000:
            return f"LD   V{x:X}, #${nn:02X}"
        if top == 0x7000:
            return f"ADD  V{x:X}, #${nn:02X}"
        if top == 0x8000:
            alu = {
                0: "LD  ", 1: "OR  ", 2: "AND ", 3: "XOR ",
                4: "ADD ", 5: "SUB ", 6: "SHR ", 7: "SUBN", 0xE: "SHL ",
            }.get(n, "ALU?")
            return f"{alu} V{x:X}, V{y:X}"
        if top == 0x9000:
            return f"SNE  V{x:X}, V{y:X}"
        if top == 0xA000:
            return f"LD   I,  #${nnn:03X}"
        if top == 0xB000:
            return f"JP   V0, ${nnn:03X}"
        if top == 0xC000:
            return f"RND  V{x:X}, #${nn:02X}"
        if top == 0xD000:
            return f"DRW  V{x:X}, V{y:X}, {n}"
        if top == 0xE000:
            return f"{'SKP ' if nn == 0x9E else 'SKNP'} V{x:X}"
        if top == 0xF000:
            fmap = {
                0x07: f"LD   V{x:X}, DT",
                0x0A: f"LD   V{x:X}, K",
                0x15: f"LD   DT, V{x:X}",
                0x18: f"LD   ST, V{x:X}",
                0x1E: f"ADD  I,  V{x:X}",
                0x29: f"LD   F,  V{x:X}",
                0x33: f"LD   B,  V{x:X}",
                0x55: f"LD   [I], V{x:X}",
                0x65: f"LD   V{x:X}, [I]",
            }
            return fmap.get(nn, f"DATA ${op:04X}")
        return f"SYS  ${nnn:03X}"

    def save_state(self) -> bytes:
        state = {
            "ram": bytes(self.ram),
            "v": bytes(self.v),
            "i": self.i,
            "pc": self.pc,
            "stack": list(self.stack),
            "sp": self.sp,
            "dt": self.delay_timer,
            "st": self.sound_timer,
            "vram": bytes(self.vram),
            "cycles": self.cycles,
        }
        return zlib.compress(pickle.dumps(state, protocol=4))

    def load_state(self, blob: bytes) -> None:
        st = pickle.loads(zlib.decompress(blob))
        self.ram[:] = st["ram"]
        self.v[:] = st["v"]
        self.i = st["i"]
        self.pc = st["pc"]
        self.stack = list(st["stack"])
        self.sp = st["sp"]
        self.delay_timer = st["dt"]
        self.sound_timer = st["st"]
        self.vram[:] = st["vram"]
        self.cycles = st["cycles"]
        self.draw_flag = True


# ──────────────────────────────────────────────────────────────
# CHIP-8 AUDIO ENGINE (60 Hz sound timer · square-wave buzzer)
# ──────────────────────────────────────────────────────────────
class Chip8AudioEngine:
    """
    CHIP-8 audio engine driven by the sound timer (ST).

    While ST > 0 the buzzer runs as a continuous ~440 Hz square wave
    (classic COSMAC VIP / CHIP-8 feel). Stops the moment ST hits 0.

    Backends (first that works wins):
      1. pygame / pygame-ce mixer (preferred)
      2. stdlib tone thread (macOS/Windows/Linux soft beep pulse)
      3. silent (engine still tracks state for UI)
    """

    SAMPLE_RATE = 22050
    FREQ_HZ = 440.0
    DUTY = 0.5
    LOOP_SEC = 0.25

    def __init__(self) -> None:
        self.enabled = False
        self.backend = "none"
        self.volume = 0.40
        self._playing = False
        self._sound = None
        self._channel = None
        self._pygame = None
        self._pulse_thread = None
        self._pulse_stop = None
        self._init_backend()

    def _init_backend(self) -> None:
        # Prefer CoreAudio on macOS when SDL is free to choose
        if sys.platform == "darwin":
            os.environ.setdefault("SDL_AUDIODRIVER", "coreaudio")
        elif sys.platform.startswith("win"):
            os.environ.setdefault("SDL_AUDIODRIVER", "directsound")

        # ── 1) pygame square-wave loop ──
        try:
            import pygame

            self._pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(self.SAMPLE_RATE, -16, 1, 256)
                pygame.mixer.init(self.SAMPLE_RATE, -16, 1, 256)
            if not pygame.mixer.get_init():
                raise RuntimeError("mixer not initialized")
            pygame.mixer.set_num_channels(max(8, pygame.mixer.get_num_channels()))
            self._sound = self._build_square_sound()
            self._channel = pygame.mixer.Channel(1)
            self.enabled = True
            self.backend = "pygame"
            return
        except Exception:
            self._pygame = None
            self._sound = None
            self._channel = None

        # ── 2) stdlib pulse thread (no extra packages) ──
        self.enabled = True
        self.backend = "pulse"
        import threading

        self._pulse_stop = threading.Event()

    def _build_square_sound(self):
        import array

        pygame = self._pygame
        n = max(1, int(self.SAMPLE_RATE * self.LOOP_SEC))
        period = max(1, int(round(self.SAMPLE_RATE / self.FREQ_HZ)))
        high = max(1, int(period * self.DUTY))
        amp = max(1, int(32767 * self.volume))
        buf = array.array("h", ((amp if (i % period) < high else -amp) for i in range(n)))
        return pygame.mixer.Sound(buffer=buf)

    def set_volume(self, vol: float) -> None:
        self.volume = max(0.0, min(1.0, float(vol)))
        if self.backend == "pygame" and self._pygame is not None:
            was = self._playing
            self.stop()
            try:
                self._sound = self._build_square_sound()
            except Exception:
                return
            if was:
                self._start_pygame()

    def _start_pygame(self) -> None:
        if self._sound is None:
            return
        try:
            if self._channel is not None:
                self._channel.set_volume(self.volume)
                self._channel.play(self._sound, loops=-1)
            else:
                self._sound.set_volume(self.volume)
                self._sound.play(loops=-1)
            self._playing = True
        except Exception:
            self._playing = False

    def _start_pulse(self) -> None:
        import threading

        if self._pulse_stop is None:
            self._pulse_stop = threading.Event()
        if self._pulse_thread and self._pulse_thread.is_alive():
            self._playing = True
            return
        self._pulse_stop.clear()

        def worker() -> None:
            # Soft tick every ~80 ms while ST is active (CHIP-8 buzzer proxy)
            while self._pulse_stop is not None and not self._pulse_stop.is_set():
                try:
                    if sys.platform == "darwin":
                        # System beep — no files, no pygame required
                        import subprocess

                        subprocess.Popen(
                            ["osascript", "-e", "beep"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    elif sys.platform.startswith("win"):
                        import winsound

                        winsound.Beep(int(self.FREQ_HZ), 60)
                    else:
                        # Linux console bell
                        sys.stdout.write("\a")
                        sys.stdout.flush()
                except Exception:
                    pass
                if self._pulse_stop.wait(0.08):
                    break

        self._pulse_thread = threading.Thread(target=worker, name="chip8-audio", daemon=True)
        self._pulse_thread.start()
        self._playing = True

    def stop(self) -> None:
        if self.backend == "pygame":
            try:
                if self._channel is not None:
                    self._channel.stop()
                elif self._sound is not None:
                    self._sound.stop()
            except Exception:
                pass
        elif self.backend == "pulse":
            if self._pulse_stop is not None:
                self._pulse_stop.set()
            self._pulse_thread = None
        self._playing = False

    def update(self, active: bool, muted: bool = False, bell_cb=None) -> None:
        """Drive the buzzer from the 60 Hz sound timer (call once per frame)."""
        if not self.enabled or muted or self.volume <= 0.001:
            self.stop()
            return
        if active:
            if self.backend == "pygame":
                if not self._playing:
                    self._start_pygame()
            elif self.backend == "pulse":
                if not self._playing:
                    self._start_pulse()
            elif bell_cb is not None:
                try:
                    bell_cb()
                except Exception:
                    pass
                self._playing = True
        else:
            self.stop()

    def shutdown(self) -> None:
        self.stop()
        self.enabled = False
        if self.backend == "pygame" and self._pygame is not None:
            try:
                # Leave mixer up for the process; just release our channel
                if self._channel is not None:
                    self._channel.stop()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────
# mGBA-STYLE GUI · BLUE-HUE CHROME & BLACK BUTTONS
# ──────────────────────────────────────────────────────────────
class MgbaChip8GUI:
    def __init__(self, root: tk.Tk, rom_path: Optional[str] = None) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cpu = Chip8CPU()
        self.audio = Chip8AudioEngine()
        self.rom_name = "Cat's Pong"
        self.paused = False
        # CHIP-8 classic speed @ 60 FPS ≈ 12 cycles/frame (~720 Hz)
        self.cycles_per_frame = 12
        # Scale that fits 64×32 inside 600×400 with toolbar/status (~7–8×)
        self.scale = tk.IntVar(value=7)
        self.show_debugger = tk.BooleanVar(value=False)
        self.muted = tk.BooleanVar(value=False)
        self.volume = tk.DoubleVar(value=0.35)
        self.state_slot = tk.IntVar(value=1)
        self.state_slots: Dict[int, bytes] = {}

        self._fps_val = 60.0
        self._frame_counter = 0
        self._fps_timer = time.perf_counter()
        self._next_frame = time.perf_counter()

        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._build_statusbar()
        self._bind_keys()
        self._center_window()

        if rom_path:
            self.load_rom_file(rom_path)
        else:
            self.load_builtin("Cat's Pong")

        self.root.after(1, self._tick)

    def _center_window(self) -> None:
        """Fixed 600×400 window, centered on the OS desktop."""
        self.root.update_idletasks()
        self.root.resizable(False, False)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - WIN_W) // 2)
        y = max(0, (sh - WIN_H) // 2)
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")
        self.root.minsize(WIN_W, WIN_H)
        self.root.maxsize(WIN_W, WIN_H)

    def _black_btn(
        self, parent: tk.Widget, text: str, cmd, width: Optional[int] = None, pad: Tuple[int, int] = (10, 4)
    ) -> tk.Button:
        """Create a black button (#000000) with blue text (#7eb6ff)."""
        kw = dict(
            text=text, command=cmd, bg=BTN_BG, fg=BTN_FG,
            activebackground=BTN_ACTIVE, activeforeground=FG_BRIGHT,
            bd=1, relief="flat", padx=pad[0], pady=pad[1],
            font=("Segoe UI" if sys.platform.startswith("win") else "Helvetica", 10, "bold"),
            cursor="hand2", highlightthickness=1, highlightbackground=BORDER,
        )
        if width is not None:
            kw["width"] = width
        b = tk.Button(parent, **kw)
        b.bind("<Enter>", lambda _e: b.configure(bg=BTN_HOVER))
        b.bind("<Leave>", lambda _e: b.configure(bg=BTN_BG))
        return b

    # ── mGBA Menu Bar ─────────────────────────────────────────
    def _build_menu(self) -> None:
        m = tk.Menu(self.root, bg=PANEL_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG_BRIGHT)

        file_m = tk.Menu(m, tearoff=0, bg=PANEL_BG, fg=FG)
        file_m.add_command(label="Load ROM...", accelerator="Ctrl+O", command=self.open_rom_dialog)
        builtin_m = tk.Menu(file_m, tearoff=0, bg=PANEL_BG, fg=FG)
        for name in BUILTIN_ROMS:
            builtin_m.add_command(label=name, command=lambda n=name: self.load_builtin(n))
        file_m.add_cascade(label="Load Built-in ROM", menu=builtin_m)
        file_m.add_separator()
        file_m.add_command(label="Quick Save State (F5)", command=self.quick_save)
        file_m.add_command(label="Quick Load State (F7)", command=self.quick_load)
        file_m.add_separator()
        file_m.add_command(label="Reset", accelerator="Ctrl+R", command=self.reset_rom)
        file_m.add_separator()
        file_m.add_command(label="Exit", accelerator="Ctrl+Q", command=self.root.destroy)
        m.add_cascade(label="File", menu=file_m)

        emu_m = tk.Menu(m, tearoff=0, bg=PANEL_BG, fg=FG)
        emu_m.add_command(label="Pause / Resume", accelerator="Space", command=self.toggle_pause)
        emu_m.add_command(label="Frame Advance", accelerator="N", command=self.step_instruction)
        emu_m.add_separator()
        for label, cpf in (
            ("CHIP-8 Classic (12 cyc/f @ 60 FPS)", 12),
            ("CHIP-8 Fast (16 cyc/f @ 60 FPS)", 16),
            ("CHIP-8 Turbo (24 cyc/f @ 60 FPS)", 24),
            ("CHIP-8 Slow (8 cyc/f @ 60 FPS)", 8),
            ("CHIP-8 Max (32 cyc/f @ 60 FPS)", 32),
        ):
            emu_m.add_command(label=label, command=lambda c=cpf: self.set_cpf(c))
        m.add_cascade(label="Emulation", menu=emu_m)

        av_m = tk.Menu(m, tearoff=0, bg=PANEL_BG, fg=FG)
        for sc in (5, 6, 7, 8):
            av_m.add_radiobutton(
                label=f"Video Scale {sc}x ({64*sc}x{32*sc})",
                variable=self.scale, value=sc, command=self.apply_scale,
            )
        av_m.add_separator()
        av_m.add_checkbutton(
            label="Mute CHIP-8 Buzzer",
            variable=self.muted,
            command=self._on_mute_toggle,
        )
        vol_m = tk.Menu(av_m, tearoff=0, bg=PANEL_BG, fg=FG)
        for pct in (10, 25, 35, 50, 75, 100):
            vol_m.add_command(
                label=f"Volume {pct}%",
                command=lambda p=pct: self._set_volume(p / 100.0),
            )
        av_m.add_cascade(label="Audio Volume", menu=vol_m)
        av_m.add_command(label="Test Buzzer (0.25s)", command=self._test_buzzer)
        m.add_cascade(label="Audio/Video", menu=av_m)

        tools_m = tk.Menu(m, tearoff=0, bg=PANEL_BG, fg=FG)
        tools_m.add_checkbutton(
            label="Toggle mGBA Debugger & Keypad Dock",
            variable=self.show_debugger, command=self.toggle_debugger_dock,
        )
        m.add_cascade(label="Tools", menu=tools_m)

        help_m = tk.Menu(m, tearoff=0, bg=PANEL_BG, fg=FG)
        help_m.add_command(label="About", command=self.show_about)
        m.add_cascade(label="Help", menu=help_m)

        self.root.config(menu=m)

    # ── mGBA Quick Toolbar ────────────────────────────────────
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=BAR_BG, pady=6, padx=8)
        bar.pack(fill=tk.X)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        self._black_btn(bar, "📂 Load ROM", self.open_rom_dialog).pack(side=tk.LEFT, padx=3)
        for name in BUILTIN_ROMS:
            self._black_btn(bar, f"▶ {name}", lambda n=name: self.load_builtin(n)).pack(side=tk.LEFT, padx=3)

        self.pause_btn = self._black_btn(bar, "⏸ Pause", self.toggle_pause)
        self.pause_btn.pack(side=tk.LEFT, padx=3)
        self._black_btn(bar, "⏭ Step", self.step_instruction).pack(side=tk.LEFT, padx=3)
        self._black_btn(bar, "↻ Reset", self.reset_rom).pack(side=tk.LEFT, padx=3)
        self._black_btn(bar, "💾 Save", self.quick_save).pack(side=tk.LEFT, padx=3)
        self._black_btn(bar, "📥 Load", self.quick_load).pack(side=tk.LEFT, padx=3)

        tk.Label(
            bar, text="mGBA GUI · CHIP-8 Audio · 60 FPS", bg=BAR_BG, fg=FG_BRIGHT,
            font=("Helvetica", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=6)

    # ── Main Viewport & mGBA Dock ─────────────────────────────
    def _build_main_area(self) -> None:
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill=tk.BOTH, expand=True)

        # Centered CHIP-8 viewport inside fixed 600×400 window
        screen_wrap = tk.Frame(self.body, bg=BORDER, padx=2, pady=2)
        screen_wrap.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        sc = self.scale.get()
        self.canvas = tk.Canvas(
            screen_wrap, width=SCREEN_W * sc, height=SCREEN_H * sc,
            bg=PIXEL_OFF, highlightthickness=0,
        )
        self.canvas.pack()
        self._init_canvas_pixels()

        # mGBA Inspector dock (optional — off by default at 600×400)
        self.dock = tk.Frame(self.body, bg=PANEL_BG, width=280, padx=8, pady=6,
                             highlightthickness=1, highlightbackground=BORDER)
        # packed only when Tools → debugger is enabled

        tk.Label(
            self.dock, text="mGBA CPU & REGISTER INSPECTOR", bg=PANEL_BG, fg=FG_BRIGHT,
            font=("Helvetica", 9, "bold"), anchor="w",
        ).pack(fill=tk.X)

        self.reg_text = tk.Text(
            self.dock, width=32, height=7, bg=INPUT_BG, fg=FG,
            font=("Consolas", 9), bd=0, padx=6, pady=4, state=tk.DISABLED,
        )
        self.reg_text.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            self.dock, text="DISASSEMBLER", bg=PANEL_BG, fg=FG_BRIGHT,
            font=("Helvetica", 9, "bold"), anchor="w",
        ).pack(fill=tk.X)

        self.dis_text = tk.Text(
            self.dock, width=32, height=6, bg=INPUT_BG, fg=FG,
            font=("Consolas", 9), bd=0, padx=6, pady=4, state=tk.DISABLED,
        )
        self.dis_text.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            self.dock, text="HEX KEYPAD", bg=PANEL_BG, fg=FG_BRIGHT,
            font=("Helvetica", 9, "bold"), anchor="w",
        ).pack(fill=tk.X, pady=(0, 2))

        pad_grid = tk.Frame(self.dock, bg=PANEL_BG)
        pad_grid.pack()
        self.key_btns: Dict[int, tk.Button] = {}
        for idx, (code, key_char) in enumerate(KEYPAD_LAYOUT):
            r, c = divmod(idx, 4)
            b = self._black_btn(
                pad_grid, f"{code:X} ({key_char.upper()})",
                cmd=lambda: None, width=5, pad=(2, 2),
            )
            b.bind("<ButtonPress-1>", lambda _e, k=code: self._set_key(k, 1))
            b.bind("<ButtonRelease-1>", lambda _e, k=code: self._set_key(k, 0))
            b.grid(row=r, column=c, padx=1, pady=1)
            self.key_btns[code] = b

        if self.show_debugger.get():
            self.dock.place(relx=1.0, rely=0.5, anchor=tk.E, x=-4)

    def _init_canvas_pixels(self) -> None:
        self.canvas.delete("all")
        sc = self.scale.get()
        self.rects: List[int] = []
        for y in range(SCREEN_H):
            for x in range(SCREEN_W):
                rid = self.canvas.create_rectangle(
                    x * sc, y * sc, (x + 1) * sc, (y + 1) * sc,
                    fill=PIXEL_OFF, outline="#111826", width=1,
                )
                self.rects.append(rid)

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self.root, bg=STATUS_BG, height=24)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self.status_left = tk.Label(
            bar, text=f"  {WINDOW_TITLE}  ·  Ready", bg=STATUS_BG, fg=FG_BRIGHT,
            font=("Helvetica", 9, "bold"),
        )
        self.status_left.pack(side=tk.LEFT)

        self.status_right = tk.Label(
            bar, text="60.0 FPS  |  PC: $200  |  I: $000  ", bg=STATUS_BG, fg=FG_BRIGHT,
            font=("Consolas", 9, "bold"),
        )
        self.status_right.pack(side=tk.RIGHT)

    # ── Input & Controls ──────────────────────────────────────
    def _bind_keys(self) -> None:
        self.root.bind("<KeyPress>", self._on_key_down)
        self.root.bind("<KeyRelease>", self._on_key_up)
        self.root.bind("<Control-o>", lambda _e: self.open_rom_dialog())
        self.root.bind("<Control-r>", lambda _e: self.reset_rom())
        self.root.bind("<Control-q>", lambda _e: self.root.destroy())
        self.root.bind("<F5>", lambda _e: self.quick_save())
        self.root.bind("<F7>", lambda _e: self.quick_load())

    def _set_key(self, code: int, state: int) -> None:
        self.cpu.keys[code & 0x0F] = state
        btn = self.key_btns.get(code)
        if btn:
            btn.configure(bg=STATUS_BG if state else BTN_BG)

    def _on_key_down(self, event) -> None:
        sym = event.keysym
        if sym == "space" and event.state & 0x4:
            self.toggle_pause()
            return
        if sym.lower() == "n" and self.paused:
            self.step_instruction()
            return
        code = KEY_TO_CHIP8.get(sym) or KEY_TO_CHIP8.get(sym.lower())
        if code is not None:
            self._set_key(code, 1)

    def _on_key_up(self, event) -> None:
        sym = event.keysym
        code = KEY_TO_CHIP8.get(sym) or KEY_TO_CHIP8.get(sym.lower())
        if code is not None:
            self._set_key(code, 0)

    # ── Actions ───────────────────────────────────────────────
    def load_builtin(self, name: str) -> None:
        data = BUILTIN_ROMS[name]
        self.rom_name = name
        self.cpu.load_rom_bytes(data)
        self.paused = False
        self.pause_btn.configure(text="⏸ Pause")
        self._render_screen(force=True)
        self._update_inspector()

    def open_rom_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Load CHIP-8 ROM",
            filetypes=(("CHIP-8 ROMs", ("*.ch8", "*.rom", "*.c8")), ("All files", "*.*")),
        )
        if path:
            self.load_rom_file(path)

    def load_rom_file(self, path: str) -> None:
        p = pathlib.Path(path)
        try:
            data = p.read_bytes()
        except OSError as exc:
            messagebox.showerror(WINDOW_TITLE, f"Could not load ROM:\n{exc}")
            return
        self.rom_name = p.name
        self.cpu.load_rom_bytes(data)
        self.paused = False
        self.pause_btn.configure(text="⏸ Pause")
        self._render_screen(force=True)
        self._update_inspector()

    def reset_rom(self) -> None:
        self.cpu.reset()
        self._render_screen(force=True)
        self._update_inspector()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_btn.configure(text="▶ Resume" if self.paused else "⏸ Pause")
        if self.paused:
            self.audio.stop()
        self._update_inspector()

    def step_instruction(self) -> None:
        self.paused = True
        self.pause_btn.configure(text="▶ Resume")
        self.cpu.step()
        beep = self.cpu.tick_timers()
        self.audio.update(beep, muted=True)  # silent while stepping
        self._render_screen(force=True)
        self._update_inspector()

    def set_cpf(self, cpf: int) -> None:
        self.cycles_per_frame = cpf
        self.status_left.configure(
            text=f"  {WINDOW_TITLE}  ·  CHIP-8 speed {cpf} cyc/frame @ 60 FPS"
        )

    def _on_mute_toggle(self) -> None:
        if self.muted.get():
            self.audio.stop()

    def _set_volume(self, vol: float) -> None:
        self.volume.set(vol)
        self.audio.set_volume(vol)
        self.status_left.configure(text=f"  {WINDOW_TITLE}  ·  Audio volume {int(vol*100)}%")

    def _test_buzzer(self) -> None:
        if self.muted.get():
            self.status_left.configure(text=f"  {WINDOW_TITLE}  ·  Unmute to test buzzer")
            return
        self.audio.set_volume(self.volume.get())
        self.audio.update(True, muted=False, bell_cb=self.root.bell)
        self.root.after(250, lambda: self.audio.stop())

    def _on_close(self) -> None:
        self.audio.shutdown()
        self.root.destroy()

    def apply_scale(self) -> None:
        # Clamp so 64×32 display fits inside 600×400 chrome
        max_fit = max(1, min((WIN_W - 40) // SCREEN_W, (WIN_H - 100) // SCREEN_H))
        sc = max(1, min(int(self.scale.get()), max_fit))
        self.scale.set(sc)
        self.canvas.configure(width=SCREEN_W * sc, height=SCREEN_H * sc)
        self._init_canvas_pixels()
        self._render_screen(force=True)
        self._center_window()

    def toggle_debugger_dock(self) -> None:
        if self.show_debugger.get():
            self.dock.place(relx=1.0, rely=0.5, anchor=tk.E, x=-4)
        else:
            self.dock.place_forget()
        self._center_window()

    def quick_save(self) -> None:
        slot = self.state_slot.get()
        self.state_slots[slot] = self.cpu.save_state()
        self.status_left.configure(text=f"  {WINDOW_TITLE}  ·  Saved State #{slot}")

    def quick_load(self) -> None:
        slot = self.state_slot.get()
        blob = self.state_slots.get(slot)
        if not blob:
            self.status_left.configure(text=f"  {WINDOW_TITLE}  ·  Slot #{slot} Empty")
            return
        self.cpu.load_state(blob)
        self._render_screen(force=True)
        self._update_inspector()
        self.status_left.configure(text=f"  {WINDOW_TITLE}  ·  Loaded State #{slot}")

    def show_about(self) -> None:
        messagebox.showinfo(
            f"About {WINDOW_TITLE}",
            f"{WINDOW_TITLE}\n\n"
            "mGBA-styled CHIP-8 Virtual Machine\n"
            "60.0 FPS display + delay/sound timers\n"
            f"CHIP-8 Audio Engine ({self.audio.backend}) · 440 Hz square buzzer\n"
            "Classic speed: 12 cycles/frame @ 60 FPS\n"
            "Blue-Hue Theme · Black Control Buttons\n"
            "35 Standard CHIP-8 Opcodes + Built-in ROMs",
        )

    # ── 60 FPS Main Loop & Rendering ──────────────────────────
    def _render_screen(self, force: bool = False) -> None:
        if not (self.cpu.draw_flag or force):
            return
        self.cpu.draw_flag = False
        vram = self.cpu.vram
        itemconfig = self.canvas.itemconfigure
        for idx, rid in enumerate(self.rects):
            itemconfig(rid, fill=PIXEL_ON if vram[idx] else PIXEL_OFF)

    def _update_inspector(self) -> None:
        if not self.show_debugger.get():
            return
        c = self.cpu
        regs = []
        for row in range(4):
             base = row * 4
             regs.append("  ".join(f"V{base+k:X}:${c.v[base+k]:02X}" for k in range(4)))
        regs.append(f"PC:${c.pc:03X}  I:${c.i:03X}  SP:{c.sp:X}  DT:{c.delay_timer:02X}  ST:{c.sound_timer:02X}")
        regs.append(f"Cycles: {c.cycles}   ROM: {self.rom_name}   Audio: {self.audio.backend}")

        self.reg_text.configure(state=tk.NORMAL)
        self.reg_text.delete("1.0", tk.END)
        self.reg_text.insert("1.0", "\n".join(regs))
        self.reg_text.configure(state=tk.DISABLED)

        dis_lines = []
        addr = max(0x200, (c.pc - 4) & 0xFFF)
        for _ in range(7):
            op = (c.ram[addr] << 8) | c.ram[(addr + 1) & 0xFFF]
            prefix = "▶ " if addr == c.pc else "  "
            dis_lines.append(f"{prefix}${addr:03X}: {op:04X}  {c.disassemble_op(op)}")
            addr = (addr + 2) & 0xFFF

        self.dis_text.configure(state=tk.NORMAL)
        self.dis_text.delete("1.0", tk.END)
        self.dis_text.insert("1.0", "\n".join(dis_lines))
        self.dis_text.configure(state=tk.DISABLED)

    def _tick(self) -> None:
        now = time.perf_counter()
        if not self.paused:
            for _ in range(self.cycles_per_frame):
                self.cpu.step()
            beep = self.cpu.tick_timers()
            self.audio.update(
                beep,
                muted=self.muted.get(),
                bell_cb=self.root.bell,
            )
            self._render_screen()
            if self._frame_counter % 3 == 0:
                self._update_inspector()
        else:
            self.audio.stop()

        self._frame_counter += 1
        elapsed = now - self._fps_timer
        if elapsed >= 0.5:
            self._fps_val = self._frame_counter / elapsed
            self._frame_counter = 0
            self._fps_timer = now
            state_str = "PAUSED" if self.paused else "RUNNING"
            buzz = "BUZZ" if (not self.paused and self.cpu.sound_timer > 0 and not self.muted.get()) else "—"
            self.status_left.configure(
                text=f"  {WINDOW_TITLE}  ·  {self.rom_name} ({state_str})"
            )
            self.status_right.configure(
                text=(
                    f"{self._fps_val:4.1f} FPS  |  CHIP-8 {self.cycles_per_frame}c/f  |  "
                    f"AUD:{self.audio.backend}/{buzz}  |  "
                    f"PC:${self.cpu.pc:03X}  I:${self.cpu.i:03X}  "
                )
            )

        self._next_frame += FRAME_PERIOD
        delay_ms = max(1, int((self._next_frame - time.perf_counter()) * 1000.0))
        if delay_ms > 20:
            self._next_frame = time.perf_counter()
            delay_ms = 16
        self.root.after(delay_ms, self._tick)


# ──────────────────────────────────────────────────────────────
# HEADLESS SELF-TEST
# ──────────────────────────────────────────────────────────────
def self_test() -> int:
    vm = Chip8CPU()
    # Test CLS, LD, ADD, DRW, BCD, and memory store/load
    test_rom = _words(
        0x00E0,  # CLS
        0x600A,  # V0 = 10
        0x6114,  # V1 = 20
        0x8014,  # V0 += V1 (30)
        0xA300,  # I = 0x300
        0xF033,  # BCD(V0) -> [0x300..0x302] = 0, 3, 0
        0xF029,  # I = font(0)
        0x6204,  # V2 = 4
        0x6304,  # V3 = 4
        0xD235,  # DRW V2, V3, 5
        0x6805,  # V8 = 5
        0xF818,  # ST = V8 (sound timer)
    )
    vm.load_rom_bytes(test_rom)
    for _ in range(12):
        vm.step()
    assert vm.v[0] == 30, f"Expected V0=30, got {vm.v[0]}"
    assert (vm.ram[0x300], vm.ram[0x301], vm.ram[0x302]) == (0, 3, 0)
    assert any(vm.vram), "Expected sprite pixels in VRAM"
    assert vm.sound_timer == 5, f"Expected ST=5, got {vm.sound_timer}"
    beep = vm.tick_timers()
    assert beep and vm.sound_timer == 4
    audio = Chip8AudioEngine()
    audio.update(True, muted=False)
    audio.update(False, muted=False)
    assert audio.backend in ("pygame", "pulse", "none", "bell"), audio.backend
    audio.shutdown()
    blob = vm.save_state()
    vm.reset()
    vm.load_state(blob)
    assert vm.v[0] == 30
    print(
        f"{WINDOW_TITLE}: self-test passed "
        f"(opcodes, VRAM, BCD, ST, audio={audio.backend}, save states OK)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument("rom", nargs="?", help="Optional .ch8/.rom file to open")
    parser.add_argument("--self-test", action="store_true", help="Run headless core verification")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if tk is None:
        sys.exit("Tkinter is required for the mGBA GUI.")
    root = tk.Tk()
    MgbaChip8GUI(root, args.rom)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
