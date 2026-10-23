# OneGate

A CPU with exactly one instruction, plus the Python assembler that builds programs for it.

```
RAM[dst] = NAND(RAM[a], RAM[b])
```

NAND is functionally complete, so the hardware stays minimal and everything else (NOT, AND, OR, XOR, adders) is built in software as sequences of that one instruction.

## How it works

- **Instruction:** 25 bits, three 8-bit addresses (`a`, `b`, `dst`) plus a halt flag. No opcode, no decoder
- **Hardware:** built in [Digital](https://github.com/hneemann/Digital): a 1-bit NAND ALU, a program counter, a small control unit, and RAM
- **Macros:** NOT is 1 instruction, AND is 2, OR is 3, XOR is 4. Half adder, full adder and 8-bit ripple-carry adder are built from those

## Memory map

| Address     | Use                                              |
|-------------|--------------------------------------------------|
| `0x00`      | constant 0                                       |
| `0x01`      | constant 1 (made by the first instruction, `NAND(0,0)`) |
| `0x10-0x7F` | variables                                        |
| `0x80-0xFE` | scratch space for macros                         |

Both constants are write-protected. Multi-bit values are allocated as consecutive rows, LSB first. Macros borrow scratch cells and release them when done.

## Layout

```
asm.py        assembler, macros, scratch allocator, listing and hex output
onegate.py    OneGate language front end (in progress)
ALU.dig       1-bit NAND ALU
CU.dig        control unit, program counter, program ROM
CPU.dig       top-level machine
program.hex   generated ROM image (ends with a HALT word)
program.lst   generated listing: each call with the instructions it expands into
```

## Usage

```
python asm.py
```

Builds the demo program (an 8-bit add) and writes `program.hex` and `program.lst`. Open `CPU.dig` in Digital and point the ROM in `CU.dig` at `program.hex`.

```python
from asm import Asm

asm = Asm()
x = asm.alloc(protected=True)     # a variable
y = asm.alloc(protected=True)
asm.mov(asm.ONE, dst=x)
asm.mov(asm.ZERO, dst=y)
s = asm.xor_(x, y)                # no dst: result goes to a fresh scratch cell
asm.write_to_hex()
```

## Roadmap

A small OneGate language that compiles directly to this assembly:

```
var a:8 = 200
sum, carry = a + b
```

## Status

The datapath and assembler are in place; the language front end is to be implemented next.
