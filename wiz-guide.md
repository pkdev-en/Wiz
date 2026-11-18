# Wiz

> [!NOTE]
> **Wiz** là ngôn ngữ lập trình cú pháp giống Python, compile xuống ROM binary chạy thẳng trên máy tính Casio ClassWiz (ML620906 / ML620909). Mọi biến đều là **signed 16-bit integer** (−32768 đến 32767).

---

## 1. Cách Build & Chạy

```bash
# Compile file .wz thành ROM .bin
python build.py prog.wz

# Chỉ định target cụ thể
python build.py prog.wz --target cwii    # ClassWiz II (ML620909)
python build.py prog.wz --target cw      # ClassWiz    (ML620906)
python build.py prog.wz --target all     # Build cả hai

# Output: prog.bin + prog.asm (listing)
```

### Các Target Phần Cứng

| Target | Chip | RAM | Màn hình |
|--------|------|-----|----------|
| `cwii` | ML620909 | 0x9000–0xEFFF (~24KB) | 192×64, 4 mức xám |
| `cw` | ML620906 | 0xD000–0xEFFF (~12KB) | 192×63, đen trắng |
| `cwapp` | ML620906 | như `cw` | Patch vào firmware fx-580VN X |

---

## 2. Cấu Trúc File .wz

```python
# comment dùng dấu #
score = 0               # code toàn cục chạy TRƯỚC main()

def helper(x):
    return x * 2

def main():             # vòng lặp chính — tùy chọn
    clear()
    while True:
        k = key()
        if k == K_EXE:
            score += 1
```

> [!IMPORTANT]
> - Code toàn cục (ngoài `def`) chạy **trước** khi `main()` được gọi — dùng để khởi tạo biến.
> - `def main()` **không nhận tham số**.
> - `def` chỉ được khai báo ở **top-level** (không được lồng nhau).

---

## 3. Multi-Target: `for <target>` Sections

Khi một file cần code khác nhau cho từng máy:

```python
# code chung (chạy cho tất cả)
score = 0

for cwii
# --- chỉ compile khi target = cwii ---
MAX_Y = 64

for cw
# --- chỉ compile khi target = cw ---
MAX_Y = 63

# ---- dòng separator (3+ dấu gạch) trở về "chung" ----
def main():
    clear()
```

- `for all` — chạy cho mọi target
- Dòng `---` / `===` / `___` (3+ ký tự) = separator, code sau đó là **chung** lại

---

## 4. Import

```python
import utils          # tìm utils.wz hoặc utils cùng thư mục
from lib import extra # tương đương
```

- Guard tự động: file đã import sẽ **không import lại** lần 2
- File import cũng hỗ trợ `for cwii` sections

---

## 5. Kiểu Dữ Liệu & Giới Hạn

| Thứ | Mô tả |
|-----|-------|
| **Số nguyên** | Signed 16-bit: −32768 đến 32767 |
| **Hex** | `0xFF`, `0x1A2B` |
| **Boolean** | `True` = 1, `False` = 0 |
| **String** | Chỉ dùng trong `print()`, `text()` — chỉ ASCII in được |
| **Không có** | float, None, list (dùng array thay thế) |

> [!WARNING]
> Tràn số **KHÔNG báo lỗi** — tự wrap như C: `32767 + 1 = -32768`.

---

## 6. Biến

### Biến Toàn Cục (Global)

```python
score = 0        # khai báo + gán ở top-level → biến toàn cục
lives = 3
```

### Biến Cục Bộ (Local)

```python
def foo():
    x = 10       # local của foo — tự động phát hiện
    return x
```

### Dùng Global Bên Trong Hàm

```python
px = 0

def move():
    global px    # bắt buộc nếu muốn GÁN lại biến global
    px += 2
```

> [!NOTE]
> Nếu chỉ **đọc** biến global trong hàm mà không gán, không cần `global`. Chỉ cần khi **gán**.

---

## 7. Hằng Số (const)

```python
const W = 192
const H = 64
const S = 6       # hằng có thể dùng trong biểu thức khác

const AREA = W * H   # tính tại compile-time
```

- `const` chỉ khai báo ở top-level
- Giá trị phải là **biểu thức hằng** (không có biến, không có hàm)
- Không tốn RAM — inlined trực tiếp vào code

---

## 8. Toán Tử

```python
# Số học
a + b,  a - b,  a * b
a / b          # chia nguyên (truncate về 0, như C)
a // b         # cũng là chia nguyên (alias)
a % b          # modulo

# Bitwise
a & b,  a | b,  a ^ b   # AND, OR, XOR
~a                        # NOT bitwise
a << n,  a >> n           # shift (0 ≤ n ≤ 15); >> là arithmetic (giữ dấu)

# So sánh — trả về 0 hoặc 1
a == b,  a != b
a < b,   a > b,  a <= b,  a >= b

# Logic — trả về 0 hoặc 1 (short-circuit)
a and b
a or b
not a

# Gán kết hợp
x += 1;  x -= 1;  x *= 2;  x /= 3;  x %= 7
x &= 0xFF;  x |= 1;  x ^= mask;  x <<= 1;  x >>= 2
```

> [!CAUTION]
> **Không có** `a < b < c` — chained comparison gây lỗi compile. Phải viết `a < b and b < c`.

---

## 9. Điều Kiện

```python
if x > 0:
    pixel(x, y)
elif x == 0:
    pixel(0, y)
else:
    pixel(-x, y)
```

- Inline one-liner: `if cond: stmt` (một dòng)
- Indentation dùng **spaces** (không dùng tab)

---

## 10. Vòng Lặp

### `for` — chỉ với `range()`

```python
for i in range(10):          # 0..9
    pixel(i, i)

for i in range(0, 64):       # 0..63
    pixel(i, 0)

for i in range(0, 100, 5):   # 0, 5, 10, ..., 95 (step phải là hằng)
    do_something(i)

for i in range(10, 0, -1):   # 10, 9, ..., 1 (đếm ngược)
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

### `break` và `continue`

```python
for i in range(100):
    if i == 50:
        break       # thoát vòng lặp
    if i % 2 == 0:
        continue    # bỏ qua iteration này
    pixel(i, 0)
```

---

## 11. Hàm (Functions)

```python
def square(n):
    return n * n

def add(a, b):
    return a + b

# Tham số mặc định (giá trị phải là hằng)
def draw_box(x, y, w=10, h=10, c=1):
    rect(x, y, w, h, c)

# Gọi hàm
r = square(9)
draw_box(10, 10)
draw_box(10, 10, 20, 15)
draw_box(10, 10, 20, 15, 0)   # c=0 xóa thay vì vẽ
```

### Đệ Quy

```python
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
```

- **Compiler tự phát hiện** đệ quy và tự động push/pop frame lên stack
- Stack ~2000 bytes → depth phụ thuộc số local vars
- Compiler in note: `recursive fib(): ~12 bytes/level, ~166 levels max`

---

## 12. Mảng (Arrays)

### Mảng RAM — đọc/ghi được

```python
# Khai báo ở top-level
buf = [0] * 16        # 16 phần tử, tất cả = 0
data = [1, 2, 3, 4]   # khởi tạo với giá trị cụ thể

# Truy cập
buf[0] = 42
x = buf[i]            # index có thể là biến
buf[i] += 1
```

### ROM Table (16-bit, read-only)

```python
rom scores = [100, 200, 300, 500, 1000]
x = scores[i]         # chỉ đọc, không ghi được
```

### ROM8 Table (8-bit, read-only)

```python
rom8 tiles = [0x0F, 0xF0, 0xAA, 0x55]
rom8 msg = "Hello"    # string → mảng byte ASCII + null terminator
b = tiles[i]
```

> [!NOTE]
> `rom`/`rom8` lưu trong ROM (flash), không tốn RAM. `arr` lưu trong RAM.

---

## 13. Con Trỏ & Byte Access

```python
# peek/poke: truy cập byte tại địa chỉ RAM tuyệt đối
v = peek(0xE800)      # đọc 1 byte
poke(0xE801, 192)     # ghi 1 byte

# _hpeek/_hpoke: truy cập byte trong heap (dynamic memory)
b = _hpeek(ptr)
_hpoke(ptr, value)

# _rpeek: đọc byte từ ROM (dùng với rom8 / string literal)
c = _rpeek(addr)
```

---

## 14. Hiển Thị (Display)

### Pixel và Vẽ Cơ Bản

```python
pixel(x, y)          # vẽ pixel trắng (c=1)
pixel(x, y, 0)       # xóa pixel (c=0)
pixel(x, y, 1)       # vẽ pixel (c=1)
clear()              # xóa toàn màn hình
```

### Chế Độ Buffered (Double Buffering)

```python
buffered(1)          # bật double buffering
# ... vẽ vào back buffer ...
flip()               # đổi buffer → hiển thị lên màn hình
buffered(0)          # tắt (vẽ trực tiếp)
```

> [!TIP]
> Luôn dùng `buffered(1)` + `flip()` trong game loop để tránh nhấp nháy.

### Hình Học (PRELUDE)

```python
# Đường thẳng
line(x0, y0, x1, y1)            # c=1, thick=1, dash=255
line(x0, y0, x1, y1, c, thick, dash)

# Hình chữ nhật
rect(x, y, w, h)                # viền
fillrect(x, y, w, h)            # tô đặc
roundrect(x, y, w, h, r)        # bo góc

# Tròn / Bầu dục
circle(cx, cy, r)
disc(cx, cy, r)                  # tô đặc
ellipse(cx, cy, rx, ry)
fillellipse(cx, cy, rx, ry)

# Tam giác
tri(x0, y0, x1, y1, x2, y2)
filltri(x0, y0, x1, y1, x2, y2)

# Đường ngang / dọc (clip-aware)
hline(x0, x1, y)
vline(x, y0, y1)

# Clip window — giới hạn vùng vẽ
clip(x, y, w, h)     # đặt clip region
clip()               # reset về full screen

# Copy / Invert / Clear vùng
copy_rect(dx, dy, sx, sy, w, h)
invert_rect(x, y, w, h)
clear_rect(x, y, w, h)
```

### Text & Số

```python
# Font mặc định 6×8 pixels, ASCII printable
char(x, y, 65)           # vẽ 1 ký tự (ASCII code)
text(x, y, "Hello!")     # vẽ chuỗi string literal
text(x, y, ptr)          # vẽ chuỗi từ địa chỉ ROM/RAM
num(x, y, value)         # vẽ số (signed 16-bit)

# print() — hàm built-in (dùng font hệ thống máy tính)
print(x, y, w, h, "text")

# Font có thể scale
charz(x, y, ch, h, w)   # 1 ký tự với height h, width w pixels
textz(x, y, h, w, s)    # chuỗi scale
numz(x, y, h, w, n)     # số scale
```

### Sprite (Bitmap)

```python
rom8 ship_data = [0x18, 0x3C, 0x7E, 0xFF, ...]   # dữ liệu bitmap row-major, MSB first

# sprite(x, y, pw, ph, data, w=1, h=1, rot=0)
# pw, ph = kích thước pixel; rot: 0=normal, 1=90CW, 2=180, 3=270CW
sprite(10, 20, 8, 8, ship_data)
sprite(10, 20, 8, 8, ship_data, 1, 1, 2)   # lật 180°

# pw < 0 = flip ngang; ph < 0 = flip dọc
sprite(10, 20, -8, 8, ship_data)           # flip ngang
```

### Vẽ Từ Hex String

```python
# draw(x, y, h, w, hex_string)
# hex_string: mỗi nybble = 4 pixels, MSB first
rom8 icon = "3C7EFFFFFF7E3C"
draw(x, y, 8, 8, icon)
```

---

## 15. Input (Phím Bấm)

### Hàm Built-in

```python
k = key()            # scan code của phím đang giữ; -1 = không có phím
```

### Hằng Phím — ClassWiz II (`cwii`)

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

### Hằng Phím — ClassWiz (`cw`)

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

### Hàm Input Nâng Cao (PRELUDE)

```python
# Phát hiện cạnh (edge) — chỉ trả về 1 lần khi nhấn xuống
key_down(k)     # 1 nếu phím k đang được giữ
key_hit(k)      # 1 nếu phím k vừa được nhấn (edge)

# Chờ phím
k = wait_key()       # block cho đến khi có phím (bất kỳ phím)
k = waitkey(ms)      # chờ tối đa ms milliseconds; -1 nếu timeout

# Nhập số từ bàn phím
n = input_num(x, y)             # nhập số, hiển thị tại (x,y)
n = input_num(x, y, default)    # với giá trị mặc định
# EXE = xác nhận, AC = hủy (trả về -32768), DEL = xóa số cuối, (-) = đổi dấu

# Nhập chuỗi — multi-tap (T9 style)
buf = [0] * 32
n = input_tap(buf, 32, x, y)    # nhập vào buf, hiện tại (x,y)

# Nhập chuỗi — bàn phím on-screen
n = input_pad(buf, 32, x, y)    # grid keyboard, tiện lợi hơn
```

---

## 16. Thời Gian & Timer

```python
delay(ms)            # trì hoãn ms milliseconds (max ~1000)
delay_ms(ms)         # trì hoãn ms milliseconds (chia chunk 256ms tự động)

t = ticks()          # đọc timer counter (8000 ticks/giây)
dt = elapsed(t)      # = ticks() - t (thời gian đã trôi qua)

# Ví dụ game loop cố định 60fps
t = ticks()
while True:
    update()
    draw()
    while elapsed(t) < 133:   # 133 ticks ≈ 16.6ms ≈ 60fps
        pass
    t = ticks()
```

---

## 17. RTC (Đồng Hồ Thực)

```python
# Đọc thời gian (BCD decoded)
h = hour()       # 0..23
m = minute()     # 0..59
s = second()     # 0..59
d = day()        # 1..31
mo = month()     # 1..12
y = year()       # 2026..

# Đọc stable (không bị tear khi giây đổi)
rtc_read()       # snapshot vào _rtc[0..6]
# _rtc = [hour, minute, second, day, weekday, month, year]

# Bật/tắt/reset
rtc_enable()
rtc_disable()
rtc_reset()

# Ghi thời gian
set_time(h, m, s)
set_date(y, mo, d)
set_hours(h);  set_minutes(m);  set_seconds(s)
set_day(d);    set_month(mo);   set_year(y)

# Kiểm tra RTC đang chạy
if rtc_alive():
    draw_time(4, 4)

# Vẽ trực tiếp lên màn
draw_time(x, y)    # HH:MM:SS
draw_date(x, y)    # DD/MM/YY
```

---

## 18. Bộ Nhớ Động (Heap)

```python
# alloc(n): cấp phát n bytes trong heap, trả về địa chỉ (0 = thất bại)
p = alloc(64)
if p == 0:
    # hết RAM
    pass

# free(p): giải phóng
free(p)

# Đọc/ghi word 16-bit vào heap
v = _rdw(p)         # đọc word tại địa chỉ p
_wrw(p, value)      # ghi word
```

---

## 19. File System (RAM)

```python
buf = [0] * 32

# Lưu / Tải / Kiểm tra / Xóa
ok = f_save("score", buf, 10)   # lưu 10 bytes
n  = f_load("score", buf, 32)   # tải, trả về số bytes (-1 nếu không tồn tại)
ex = f_exists("score")          # 1 nếu tồn tại
f_remove("score")               # xóa file

# Tên file: tối đa 11 ký tự, phải là string literal
```

> [!CAUTION]
> File system sống trong heap RAM

---

## 20. String & Chuỗi

```python
# Đo độ dài
n = strlen(ptr)

# So sánh (0 = bằng nhau)
r = strcmp(a, b)

# Copy
strcpy(dst, src)

# Chuyển đổi
n = atoi(ptr)               # string → số
itoa(buf, n, 10)            # số → string base 10
itoa(buf, n, 16)            # số → string hex

# Đọc từng ký tự từ ROM string
c = _rpeek(ptr)             # đọc byte tại ROM address
c = getc()                  # = wait_key() (đọc 1 ký tự)

# Multi-tap (T9)
c = getc_tap()              # trả về ASCII code; -32768=AC, -2=EXE, -3=DEL
```

---

## 21. Math Library (PRELUDE)

```python
# Luôn available (dùng là tự compile vào)
n = abs(x)
n = min(a, b)
n = max(a, b)
n = clamp(v, lo, hi)
n = sign(x)         # -1, 0, hoặc 1

# Random
srand(seed)          # đặt seed
n = rand(max)        # số ngẫu nhiên 0..max-1
```

---

## 22. Escape Characters Trong String

```python
text(x, y, "Hello\nWorld")   # \n = newline (10)
text(x, y, "Tab\there")      # \t = tab (9)
text(x, y, "End\0")          # \0 = null (0)
text(x, y, "Back\\slash")    # \\ = backslash
text(x, y, "Say \"hi\"")     # \" = quote
```

---

## 23. Tips & Gotchas

### Các Điều Nên Nhớ

```python
# Dùng buffered cho game
def main():
    buffered(1)
    while True:
        clear()
        # ... vẽ ...
        flip()
        delay(16)          # ~60fps

# Hằng thay vì magic number
const SCREEN_W = 192
const SCREEN_H = 64

# rand() cần gọi srand() trước
srand(3)                   # seed cố định → reproducible
srand(ticks())             # seed ngẫu nhiên theo thời gian
```

### Các lỗi hay gặp

```python
# SAI: tab indentation
def foo():
	x = 1           # lỗi: dùng tab

# ĐÚNG: spaces
def foo():
    x = 1

# SAI: chained comparison
if 0 < x < 10:     # lỗi compile

# ĐÚNG:
if x > 0 and x < 10:

# SAI: def lồng nhau
def outer():
    def inner():   # lỗi: def chỉ ở top-level
        pass

# SAI: không khai báo global trước khi gán
px = 0
def move():
    px += 1        # lỗi: cần global px

# ĐÚNG:
def move():
    global px
    px += 1

# SAI: string dài hơn 16-bit address
# (không có vấn đề gì, nhưng nhớ là mọi thứ là int16)
```

### Toán Học Nguyên

```python
# / luôn là chia nguyên (truncate về 0)
7 / 2  = 3
-7 / 2 = -3    # (không phải -4)
7 % 2  = 1
-7 % 2 = -1    # dấu theo tử số
```

---

## 24. Vd: Game bắt chấm

```python
# Điều khiển ô vuông, ăn chấm để tăng điểm
const TOP = 8
const W = 192
const H = 64
const S = 6          # cạnh ô vuông
const D = 4          # cạnh chấm

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

## 25. Tóm tắt 

### Built-in

| Hàm | Mô tả |
|-----|-------|
| `pixel(x, y, c=1)` | Vẽ/xóa pixel |
| `getpixel(x, y)` | Đọc giá trị pixel |
| `clear()` | Xóa màn hình |
| `flip()` | Swap buffer (buffered mode) |
| `buffered(1\|0)` | Bật/tắt double buffering |
| `key()` | Đọc phím hiện tại |
| `key_down(k)` | 1 nếu phím đang giữ |
| `key_hit(k)` | 1 nếu vừa nhấn phím |
| `delay(ms)` | Trì hoãn |
| `delay_ms(ms)` | Trì hoãn (chunked) |
| `ticks()` | Đọc timer (8000/s) |
| `peek(addr)` | Đọc byte RAM |
| `poke(addr, v)` | Ghi byte RAM |
| `_rpeek(addr)` | Đọc byte ROM |
| `_hpeek(addr)` | Đọc byte heap |
| `_hpoke(addr, v)` | Ghi byte heap |
| `_hspan(x0, x1, y, c)` | Vẽ span ngang (low-level) |
| `print(x, y, w, h, str)` | In text với font hệ thống |
| `copy_rect(...)` | Copy vùng màn hình |
| `invert_rect(x,y,w,h)` | Đảo màu vùng |
| `clear_rect(x,y,w,h)` | Xóa vùng |
| `exit()` | Thoát chương trình |

### PRELUDE

| Nhóm | Hàm |
|------|-----|
| **Math** | `abs`, `min`, `max`, `clamp`, `sign` |
| **Random** | `rand(n)`, `srand(s)` |
| **Vẽ đường** | `line`, `hline`, `vline` |
| **Hình hộp** | `rect`, `fillrect`, `roundrect` |
| **Tròn** | `circle`, `disc`, `ellipse`, `fillellipse` |
| **Tam giác** | `tri`, `filltri` |
| **Clip** | `clip(x,y,w,h)` |
| **Text** | `char`, `text`, `num`, `charz`, `textz`, `numz` |
| **Sprite** | `sprite(x,y,pw,ph,data,...)` |
| **Bitmap** | `draw(x,y,h,w,hexstr)` |
| **Phím** | `wait_key`, `waitkey(ms)` |
| **Nhập số** | `input_num(x,y,default=0)` |
| **Nhập chuỗi** | `input_tap`, `input_pad`, `getc_tap` |
| **String** | `strlen`, `strcmp`, `strcpy`, `atoi`, `itoa`, `getc` |
| **Heap** | `alloc(n)`, `free(p)` |
| **File** | `f_save`, `f_load`, `f_exists`, `f_remove` |
| **RTC** | `hour`, `minute`, `second`, `day`, `month`, `year` |
| **RTC setup** | `rtc_read`, `rtc_alive`, `rtc_enable`, `set_time`, `set_date` |
| **Hiển thị RTC** | `draw_time(x,y)`, `draw_date(x,y)` |
| **Timer** | `elapsed(t)` |


---


<sub> claude han hanh tai tro khien cho file sinh dong hon (((((:<sub>