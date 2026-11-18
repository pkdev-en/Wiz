

# Wiz

> [!NOTE]
> **Wiz** is a Python-like programming language that compiles directly into ROM binaries for Casio ClassWiz calculators (ML620906 / ML620909). All variables are **signed 16-bit integers** (−32768 to 32767).

---

## 1. Building & Running

```bash
# Compile a .wz file into a ROM .bin
python build.py prog.wz

# Specify a target
python build.py prog.wz --target cwii    # ClassWiz II (ML620909)
python build.py prog.wz --target cw      # ClassWiz    (ML620906)
python build.py prog.wz --target all     # Build both

# Output: prog.bin + prog.asm (assembly listing)
```

### Hardware Targets

| Target | Chip | RAM | Display |
|--------|------|-----|---------|
| `cwii` | ML620909 | 0x9000–0xEFFF (~24KB) | 192×64, 4 grayscale levels |
| `cw` | ML620906 | 0xD000–0xEFFF (~12KB) | 192×63, monochrome |
| `cwapp` | ML620906 | Same as `cw` | Patches into fx-580VN X firmware |

---

## 2. `.wz` File Structure

```python
# Comments use #
score = 0               # Global code runs BEFORE main()

def helper(x):
    return x * 2

def main():             # Main loop — optional
    clear()
    while True:
        k = key()
        if k == K_EXE:
            score += 1
```

> [!IMPORTANT]
> - Global code (outside `def`) runs **before** `main()` is called — use it to initialize variables.
> - `def main()` **does not accept parameters**.
> - Functions can only be declared at the **top level** (nested functions are not supported).

---

## 3. Multi-Target: `for <target>` Sections

Use this when a file needs different code for different calculators:

```python
# Shared code (runs on all targets)
score = 0

for cwii
# --- Compiled only when target = cwii ---
MAX_Y = 64

for cw
# --- Compiled only when target = cw ---
MAX_Y = 63

# ---- A separator line (3+ characters) switches back to shared code ----
def main():
    clear()
```

- `for all` — applies to every target.
- A line containing `---`, `===`, or `___` (3+ characters) acts as a separator. Code after it becomes **shared** again.

---

## 4. Imports

```python
import utils          # Finds utils.wz or utils in the same directory
from lib import extra # Equivalent syntax
```

- Automatic import guard: a file that has already been imported will **not be imported again**.
- Imported files also support `for cwii` sections.

---

## 5. Data Types & Limitations

| Type | Description |
|-----|-------|
| **Integer** | Signed 16-bit: −32768 to 32767 |
| **Hexadecimal** | `0xFF`, `0x1A2B` |
| **Boolean** | `True` = 1, `False` = 0 |
| **String** | Only used in `print()` and `text()` — printable ASCII only |
| **Not supported** | float, None, list (use arrays instead) |

> [!WARNING]
> Integer overflow does **NOT** raise an error. Values wrap around like in C: `32767 + 1 = -32768`.

---

## 6. Variables

### Global Variables

```python
score = 0        # Declared and assigned at top level → global variable
lives = 3
```

### Local Variables

```python
def foo():
    x = 10       # Automatically detected as a local variable in foo()
    return x
```

### Using Globals Inside Functions

```python
px = 0

def move():
    global px    # Required when REASSIGNING a global variable
    px += 2
```

> [!NOTE]
> If you only **read** a global variable inside a function without assigning to it, `global` is not required. It is only needed when **assigning** to it.

---

## 7. Constants (`const`)

```python
const W = 192
const H = 64
const S = 6       # Constants can be used in other expressions

const AREA = W * H   # Evaluated at compile time
```

- `const` can only be declared at the top level.
- Values must be **constant expressions** (no variables or function calls).
- Constants use no RAM — they are directly inlined into the generated code.

---

## 8. Operators

```python
# Arithmetic
a + b,  a - b,  a * b
a / b          # Integer division (truncated toward zero, like C)
a // b         # Also integer division (alias)
a % b          # Modulo

# Bitwise
a & b,  a | b,  a ^ b   # AND, OR, XOR
~a                        # Bitwise NOT
a << n,  a >> n           # Shift (0 ≤ n ≤ 15); >> is arithmetic (sign-preserving)

# Comparisons — return 0 or 1
a == b,  a != b
a < b,   a > b,  a <= b,  a >= b

# Logic — return 0 or 1 (short-circuit evaluation)
a and b
a or b
not a

# Compound assignment
x += 1;  x -= 1;  x *= 2;  x /= 3;  x %= 7
x &= 0xFF;  x |= 1;  x ^= mask;  x <<= 1;  x >>= 2
```

> [!CAUTION]
> **Chained comparisons are not supported.** `a < b < c` causes a compile error. Write `a < b and b < c` instead.

---

## 9. Conditional Statements

```python
if x > 0:
    pixel(x, y)
elif x == 0:
    pixel(0, y)
else:
    pixel(-x, y)
```

- Inline one-liners are supported: `if cond: stmt` (single statement).
- Indentation must use **spaces**, not tabs.

---

## 10. Loops

### `for` — Only with `range()`

```python
for i in range(10):          # 0..9
    pixel(i, i)

for i in range(0, 64):       # 0..63
    pixel(i, 0)

for i in range(0, 100, 5):   # 0, 5, 10, ..., 95 (step must be constant)
    do_something(i)

for i in range(10, 0, -1):   # 10, 9, ..., 1 (countdown)
    pixel(i, i)
```

### `while`

```python
while True:
    k = key()
    if k == K_EXE:
        break

n = 10
while n > 0:
    n -= 1
```

### `break` and `continue`

```python
for i in range(100):
    if i == 50:
        break       # Exit the loop
    if i % 2 == 0:
        continue    # Skip this iteration
    pixel(i, 0)
```

---

## 11. Functions

```python
def square(n):
    return n * n

def add(a, b):
    return a + b

# Default parameters (values must be constants)
def draw_box(x, y, w=10, h=10, c=1):
    rect(x, y, w, h, c)

# Function calls
r = square(9)
draw_box(10, 10)
draw_box(10, 10, 20, 15)
draw_box(10, 10, 20, 15, 0)   # c=0 erases instead of drawing
```

### Recursion

```python
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
```

- The **compiler automatically detects** recursion and pushes/pops stack frames.
- Stack size is approximately 2000 bytes. Maximum recursion depth depends on the number of local variables.
- The compiler prints a note such as: `recursive fib(): ~12 bytes/level, ~166 levels max`.

---

## 12. Arrays

### RAM Arrays — Read and Write

```python
# Declare at the top level
buf = [0] * 16        # 16 elements, all initialized to 0
data = [1, 2, 3, 4]   # Initialize with specific values

# Access elements
buf[0] = 42
x = buf[i]            # Index can be a variable
buf[i] += 1
```

### ROM Table (16-bit, Read-Only)

```python
rom scores = [100, 200, 300, 500, 1000]
x = scores[i]         # Read-only; cannot be modified
```

### ROM8 Table (8-bit, Read-Only)

```python
rom8 tiles = [0x0F, 0xF0, 0xAA, 0x55]
rom8 msg = "Hello"    # String → ASCII byte array + null terminator
b = tiles[i]
```

> [!NOTE]
> `rom` and `rom8` are stored in ROM (flash) and do not consume RAM. `arr` is stored in RAM.

---

## 13. Pointers & Byte Access

```python
# peek/poke: access a byte at an absolute RAM address
v = peek(0xE800)      # Read 1 byte
poke(0xE801, 192)     # Write 1 byte

# _hpeek/_hpoke: access bytes in the heap (dynamic memory)
b = _hpeek(ptr)
_hpoke(ptr, value)

# _rpeek: read a byte from ROM (used with rom8 / string literals)
c = _rpeek(addr)
```

---

## 14. Display

### Pixels and Basic Drawing

```python
pixel(x, y)          # Draw a white pixel (c=1)
pixel(x, y, 0)       # Clear a pixel (c=0)
pixel(x, y, 1)       # Draw a pixel (c=1)
clear()              # Clear the entire screen
```

### Buffered Mode (Double Buffering)

```python
buffered(1)          # Enable double buffering
# ... draw to the back buffer ...
flip()               # Swap buffers → display on screen
buffered(0)          # Disable (draw directly)
```

> [!TIP]
> Always use `buffered(1)` + `flip()` in game loops to prevent flickering.

### Geometry (PRELUDE)

```python
# Lines
line(x0, y0, x1, y1)            # c=1, thick=1, dash=255
line(x0, y0, x1, y1, c, thick, dash)

# Rectangles
rect(x, y, w, h)                # Outline
fillrect(x, y, w, h)            # Filled
roundrect(x, y, w, h, r)        # Rounded corners

# Circles / Ellipses
circle(cx, cy, r)
disc(cx, cy, r)                  # Filled circle
ellipse(cx, cy, rx, ry)
fillellipse(cx, cy, rx, ry)

# Triangles
tri(x0, y0, x1, y1, x2, y2)
filltri(x0, y0, x1, y1, x2, y2)

# Horizontal / Vertical lines (clip-aware)
hline(x0, x1, y)
vline(x, y0, y1)

# Clip window — restrict the drawing area
clip(x, y, w, h)     # Set clip region
clip()               # Reset to full screen

# Copy / Invert / Clear regions
copy_rect(dx, dy, sx, sy, w, h)
invert_rect(x, y, w, h)
clear_rect(x, y, w, h)
```

### Text & Numbers

```python
# Default font: 6×8 pixels, printable ASCII
char(x, y, 65)           # Draw one character (ASCII code)
text(x, y, "Hello!")     # Draw a string literal
text(x, y, ptr)          # Draw a string from a ROM/RAM address
num(x, y, value)         # Draw a number (signed 16-bit)

# print() — built-in function (uses the calculator's system font)
print(x, y, w, h, "text")

# Scalable fonts
charz(x, y, ch, h, w)   # Draw one character with height h and width w pixels
textz(x, y, h, w, s)    # Draw a scaled string
numz(x, y, h, w, n)     # Draw a scaled number
```

### Sprites (Bitmaps)

```python
rom8 ship_data = [0x18, 0x3C, 0x7E, 0xFF, ...]   # Row-major bitmap data, MSB first

# sprite(x, y, pw, ph, data, w=1, h=1, rot=0)
# pw, ph = pixel dimensions; rot: 0=normal, 1=90CW, 2=180, 3=270CW
sprite(10, 20, 8, 8, ship_data)
sprite(10, 20, 8, 8, ship_data, 1, 1, 2)   # Rotate 180°

# pw < 0 = horizontal flip; ph < 0 = vertical flip
sprite(10, 20, -8, 8, ship_data)           # Horizontal flip
```

### Drawing from Hex Strings

```python
# draw(x, y, h, w, hex_string)
# Each nybble = 4 pixels, MSB first
rom8 icon = "3C7EFFFFFF7E3C"
draw(x, y, 8, 8, icon)
```

---

## 15. Input (Keyboard)

### Built-in Function

```python
k = key()            # Scan code of the currently held key; -1 = no key
```

### Key Constants — ClassWiz II (`cwii`)

```python
K_UP, K_DOWN, K_LEFT, K_RIGHT, K_OK
K_HOME, K_BACK, K_SETTINGS, K_SHIFT
K_EXE, K_DEL, K_AC
K_PLUS, K_MINUS, K_MUL, K_DIV
K_0 .. K_9, K_DOT
K_SIN, K_COS, K_TAN, K_SQRT, K_POWER
K_LPAREN, K_RPAREN
K_FUNC, K_VAR, K_CATALOG, K_TOOLS
K_PGUP, K_PGDOWN
K_ANS, K_NEG
K_NONE    # = -1
```

### Key Constants — ClassWiz (`cw`)

```python
K_UP, K_DOWN, K_LEFT, K_RIGHT
K_MENU, K_SHIFT, K_ALPHA, K_OPTN, K_CALC
K_EXE, K_DEL, K_AC
K_PLUS, K_MINUS, K_MUL, K_DIV
K_0 .. K_9, K_DOT
K_SIN, K_COS, K_TAN, K_LOG, K_LN, K_SQRT
K_FRAC, K_SQUARED, K_POWER, K_INV
K_NEG, K_ANS, K_STO, K_ENG
```

### Advanced Input Functions (PRELUDE)

```python
# Edge detection — returns 1 only once when a key is pressed
key_down(k)     # 1 if key k is currently held
key_hit(k)      # 1 if key k was just pressed (edge)

# Wait for a key
k = wait_key()       # Block until any key is pressed
k = waitkey(ms)      # Wait up to ms milliseconds; -1 on timeout

# Numeric input from the keyboard
n = input_num(x, y)             # Enter a number, displayed at (x,y)
n = input_num(x, y, default)    # With a default value
# EXE = confirm, AC = cancel (returns -32768), DEL = delete last digit, (-) = toggle sign

# String input — multi-tap (T9 style)
buf = [0] * 32
n = input_tap(buf, 32, x, y)    # Enter text into buf, displayed at (x,y)

# String input — on-screen keyboard
n = input_pad(buf, 32, x, y)    # Grid keyboard, more convenient
```

---

## 16. Time & Timer

```python
delay(ms)            # Delay for ms milliseconds (max ~1000)
delay_ms(ms)         # Delay for ms milliseconds (automatically split into 256ms chunks)

t = ticks()          # Read timer counter (8000 ticks/second)
dt = elapsed(t)      # = ticks() - t (elapsed time)

# Example: fixed 60 FPS game loop
t = ticks()
while True:
    update()
    draw()
    while elapsed(t) < 133:   # 133 ticks ≈ 16.6ms ≈ 60 FPS
        pass
    t = ticks()
```

---

## 17. RTC (Real-Time Clock)

```python
# Read time (BCD decoded)
h = hour()       # 0..23
m = minute()     # 0..59
s = second()     # 0..59
d = day()        # 1..31
mo = month()     # 1..12
y = year()       # 2026..

# Stable read (avoids tearing when seconds change)
rtc_read()       # Snapshot into _rtc[0..6]
# _rtc = [hour, minute, second, day, weekday, month, year]

# Enable / disable / reset
rtc_enable()
rtc_disable()
rtc_reset()

# Set time
set_time(h, m, s)
set_date(y, mo, d)
set_hours(h);  set_minutes(m);  set_seconds(s)
set_day(d);    set_month(mo);   set_year(y)

# Check whether the RTC is running
if rtc_alive():
    draw_time(4, 4)

# Draw directly on the screen
draw_time(x, y)    # HH:MM:SS
draw_date(x, y)    # DD/MM/YY
```

---

## 18. Dynamic Memory (Heap)

```python
# alloc(n): allocate n bytes in the heap, returns the address (0 = failure)
p = alloc(64)
if p == 0:
    # Out of RAM
    pass

# free(p): release allocated memory
free(p)

# Read/write 16-bit words in the heap
v = _rdw(p)         # Read word at address p
_wrw(p, value)      # Write word
```

---

## 19. File System (RAM)

```python
buf = [0] * 32

# Save / Load / Check / Delete
ok = f_save("score", buf, 10)   # Save 10 bytes
n  = f_load("score", buf, 32)   # Load; returns byte count (-1 if not found)
ex = f_exists("score")          # 1 if it exists
f_remove("score")               # Delete file

# File names: maximum 11 characters; must be string literals
```

> [!CAUTION]
> The file system resides in heap RAM.

---

## 20. Strings

```python
# Get string length
n = strlen(ptr)

# Compare (0 = equal)
r = strcmp(a, b)

# Copy
strcpy(dst, src)

# Conversion
n = atoi(ptr)               # String → number
itoa(buf, n, 10)            # Number → string, base 10
itoa(buf, n, 16)            # Number → hexadecimal string

# Read individual characters from a ROM string
c = _rpeek(ptr)             # Read byte at ROM address
c = getc()                  # = wait_key() (read one character)

# Multi-tap (T9)
c = getc_tap()              # Returns ASCII code; -32768=AC, -2=EXE, -3=DEL
```

---

## 21. Math Library (PRELUDE)

```python
# Always available (automatically compiled when used)
n = abs(x)
n = min(a, b)
n = max(a, b)
n = clamp(v, lo, hi)
n = sign(x)         # -1, 0, or 1

# Random numbers
srand(seed)          # Set seed
n = rand(max)        # Random number from 0..max-1
```

---

## 22. Escape Characters in Strings

```python
text(x, y, "Hello\nWorld")   # \n = newline (10)
text(x, y, "Tab\there")      # \t = tab (9)
text(x, y, "End\0")          # \0 = null (0)
text(x, y, "Back\\slash")    # \\ = backslash
text(x, y, "Say \"hi\"")     # \" = quote
```

---

## 23. Tips & Gotchas

### Things to Remember

```python
# Use buffering for games
def main():
    buffered(1)
    while True:
        clear()
        # ... draw ...
        flip()
        delay(16)          # ~60 FPS

# Use constants instead of magic numbers
const SCREEN_W = 192
const SCREEN_H = 64

# Call srand() before rand()
srand(3)                   # Fixed seed → reproducible results
srand(ticks())             # Time-based seed
```

### Common Mistakes

```python
# WRONG: Tab indentation
def foo():
    x = 1           # Error: tabs are not supported

# CORRECT: Spaces
def foo():
    x = 1

# WRONG: Chained comparison
if 0 < x < 10:     # Compile error

# CORRECT:
if x > 0 and x < 10:

# WRONG: Nested functions
def outer():
    def inner():   # Error: functions must be declared at the top level
        pass

# WRONG: Assigning to a global without declaring it
px = 0
def move():
    px += 1        # Error: requires global px

# CORRECT:
def move():
    global px
    px += 1

# WRONG: String longer than a 16-bit address
# (Not an actual issue, but remember that everything is int16)
```

### Integer Arithmetic

```python
# / always performs integer division (truncated toward zero)
7 / 2  = 3
-7 / 2 = -3    # (not -4)
7 % 2  = 1
-7 % 2 = -1    # Sign follows the numerator
```

---

## 24. Example: Dot Collection Game

```python
# Control a square and collect dots to increase your score
const TOP = 8
const W = 192
const H = 64
const S = 6          # Square side length
const D = 4          # Dot side length

px = 90
py = 36
cx = 0
cy = 0
score = 0

def new_dot():
    global cx, cy
    cx = 4 + rand(W - 8 - D)
    cy = TOP + 4 + rand(H - TOP - 8 - D)

def touching():
    if px + S <= cx or cx + D <= px:
        return 0
    if py + S <= cy or cy + D <= py:
        return 0
    return 1

def main():
    global px, py, score
    srand(3)
    new_dot()
    buffered(1)
    while True:
        if key_down(K_LEFT):
            px = max(px - 2, 1)
        if key_down(K_RIGHT):
            px = min(px + 2, W - S - 1)
        if key_down(K_UP):
            py = max(py - 2, TOP + 1)
        if key_down(K_DOWN):
            py = min(py + 2, H - S - 1)
        if touching():
            score += 1
            new_dot()
        clear()
        rect(0, TOP, W, H - TOP)
        fillrect(px, py, S, S)
        rect(cx, cy, D, D)
        print(4, TOP + 3, "Score ", score)
        flip()
        delay(4)
```

---

## 25. Summary

### Built-in Functions

| Function | Description |
|-----|-------|
| `pixel(x, y, c=1)` | Draw/clear a pixel |
| `getpixel(x, y)` | Read pixel value |
| `clear()` | Clear the screen |
| `flip()` | Swap buffers (buffered mode) |
| `buffered(1\|0)` | Enable/disable double buffering |
| `key()` | Read the currently held key |
| `key_down(k)` | 1 if the key is held |
| `key_hit(k)` | 1 if the key was just pressed |
| `delay(ms)` | Delay |
| `delay_ms(ms)` | Delay (chunked) |
| `ticks()` | Read timer (8000/s) |
| `peek(addr)` | Read RAM byte |
| `poke(addr, v)` | Write RAM byte |
| `_rpeek(addr)` | Read ROM byte |
| `_hpeek(addr)` | Read heap byte |
| `_hpoke(addr, v)` | Write heap byte |
| `_hspan(x0, x1, y, c)` | Draw horizontal span (low-level) |
| `print(x, y, w, h, str)` | Print text using system font |
| `copy_rect(...)` | Copy screen region |
| `invert_rect(x,y,w,h)` | Invert region colors |
| `clear_rect(x,y,w,h)` | Clear region |
| `exit()` | Exit the program |

### PRELUDE

| Category | Functions |
|------|-----|
| **Math** | `abs`, `min`, `max`, `clamp`, `sign` |
| **Random** | `rand(n)`, `srand(s)` |
| **Lines** | `line`, `hline`, `vline` |
| **Rectangles** | `rect`, `fillrect`, `roundrect` |
| **Circles** | `circle`, `disc`, `ellipse`, `fillellipse` |
| **Triangles** | `tri`, `filltri` |
| **Clipping** | `clip(x,y,w,h)` |
| **Text** | `char`, `text`, `num`, `charz`, `textz`, `numz` |
| **Sprites** | `sprite(x,y,pw,ph,data,...)` |
| **Bitmaps** | `draw(x,y,h,w,hexstr)` |
| **Keyboard** | `wait_key`, `waitkey(ms)` |
| **Numeric input** | `input_num(x,y,default=0)` |
| **String input** | `input_tap`, `input_pad`, `getc_tap` |
| **Strings** | `strlen`, `strcmp`, `strcpy`, `atoi`, `itoa`, `getc` |
| **Heap** | `alloc(n)`, `free(p)` |
| **Files** | `f_save`, `f_load`, `f_exists`, `f_remove` |
| **RTC** | `hour`, `minute`, `second`, `day`, `month`, `year` |
| **RTC setup** | `rtc_read`, `rtc_alive`, `rtc_enable`, `set_time`, `set_date` |
| **RTC display** | `draw_time(x,y)`, `draw_date(x,y)` |
| **Timer** | `elapsed(t)` |

---

<sub>Documentation proudly sponsored by Claude to make this file more dynamic (((((:</sub>

