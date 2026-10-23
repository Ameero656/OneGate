# OneGate

A CPU with exactly one arithmetic instruction: `NAND`.

Most CPUs have dozens of instructions and a pile of hardware to run them. OneGate has exactly one: take two bits from memory, NAND them, write the result back. That’s the whole machine. Everything else, from NOT and XOR to a full 8-bit adder, is built in software out of that single operation, and a Python assembler does the stitching. It’s computing stripped to its bare minimum, and it shows that a working computer can come from one logic gate repeated enough times. If a normal ALU is a full toolbox, OneGate is one tool used over and over to build every other tool. Our philosophy is for the OneGate CPU to possess the smallest possible ALU and maintain conceptual universality (turning complete).

***I fear not the man who has practiced 10,000 kicks once, but I fear the man who has practiced one kick 10,000 times.***

## Feature goals
- A CPU with exactly one arithmetic instruction
- A Python assembler that builds programs for the OneGate CPU
- A custom assembly tokenizer/lexer

## Content goals
- Digital design files (.dig) for the CPU
- Verilog implementation source code
- Python OneGate assembly for programming and debugging

## Team

OneGate is built by a small team, and each role below owns one part of the repo. Roles marked `open` are waiting for someone. To take one, put your name after `Who:` in a pull request. One person can hold several roles, and a role can have several people. Roles tie to the [Roadmap](#roadmap) milestones, so tick items off there as you finish them.

**Hardware architect: design and research**
- Brainstorms, designs and researches the base Digital design. Makes the instruction-set calls (flag layout, how a jump is encoded) and adds the jump path to the control unit.
- Owns `Digital/*.dig` · Milestones 0 and 2 · Who: `Ameer Masoud`

**Researcher: dedicated research and compilation**
- Researches current and contemporary CPU implementations for modern methods and relevant implementations. Procures documents; presents them to other teams for context and decision making. 
- Owns `Documents/` · Who: `open`

**FPGA port: Digital to Vivado**
- Rebuilds the Digital design as Verilog and brings it up in Vivado: simulate it, synthesize it, and run it on a board if we have one. Keeps the Verilog synthesizable, for example by replacing the shared tri-state bus with a mux.
- Owns `verilog/` (planned) · Milestone 4 · Who: `open`

**Assembly proofreader**
- Checks that `asm.py` and `macros.py` do what they claim. Tests every macro against its truth table, builds the Python model that runs a program and returns RAM, and runs `add8` on all 65,536 inputs. Also checks that the generated `program.hex` and `program.lst` match the code.
- Owns tests for `asm.py` and `macros.py` · Milestone 1 · Who: `open`

**Language front end: tokenizer and parser**
- Builds the OneGate language, starting with the lexer/tokenizer and then the parser, so `var a:8 = 200` and `sum, carry = a + b` compile to assembly. Needs `add8` from Milestone 1 before `a + b` can work.
- Owns `onegate.py` (planned) · Milestone 3 · Who: `open`

**Assembler and macros**
- Writes the library the other roles build on: `add8`, shifts, subtract, compare, and later labels and jump macros.
- Owns `asm.py` and `macros.py` · Milestones 1 and 2 · Who: `open`

**Verification and CI**
- Makes sure the Python model, Digital and the Verilog all agree when they run the same `program.hex`, and runs those checks automatically on every pull request.
- Owns the cross-checks and CI setup · Milestone 4 · Who: `open`

**Project lead and docs**
- Keeps this README and the roadmap true, reviews pull requests and decides what is agreed.
- Owns `README.md` · All milestones · Who: `Ameer Masoud`

***Later, when we go toward a chip: a *silicon explorer* to look at open 180 nm flows and what the design would need for an ASIC.***

## How it works

```
RAM[dst] = NAND(RAM[a], RAM[b])
```

NAND is functionally complete, so the hardware stays minimal and everything else (NOT, AND, OR, XOR, adders) is built in software as sequences of that one instruction.

### Instruction format

Each ROM word is 25 bits: three 8-bit addresses plus `X` utility flags. Today `X = 1` (HALT).

| Bits  | Field  | Meaning                                  |
|-------|--------|------------------------------------------|
| 0-7   | `a`    | RAM address of the first operand         |
| 8-15  | `b`    | RAM address of the second operand        |
| 16-23 | `dst`  | RAM address the result is written to     |
| 24    | `HALT` | stop the machine                         |

More flags (jump, etc.) would go above bit 24. ***The number and meaning of flags have yet to be decided*** (see Milestone 2).

### Hardware

Built in [Digital](https://github.com/hneemann/Digital):

- `ALU.dig`: 1-bit ALU. Two input registers (A, B), a NAND gate and a tri-state driver onto the bus.
- `CU.dig`: control unit. An 8-bit program counter, a 256-word x 25-bit program ROM, and a 2-bit phase counter that steps every instruction through 4 clock phases: read `a`, read `b`, write `dst`, advance the program counter.
- `CPU.dig`: top level. Connects the ALU and control unit to a 256 x 1-bit dual-port RAM and a clock.

### Macros

Everything above NAND is a macro in `asm.py` (gates) or `macros.py` (adders). Instruction counts are measured from the assembler.

| Macro                      | Instructions | Built from                      |
|----------------------------|--------------|---------------------------------|
| `not_`                     | 1            | NAND                            |
| `and_`                     | 2            | NAND + NOT                      |
| `or_`                      | 3            | 2 NOT + NAND                    |
| `xor_`                     | 4            | 4 NAND                          |
| `mov`                      | 2            | 2 NOT                           |
| 1-bit half adder           | 6            | XOR + AND                       |
| 1-bit full adder           | 15           | 2 half adders + OR              |
| optimized 1-bit full adder | 9            | NAND intermediates shared by XOR and carry |
| 8-bit ripple-carry adder   | about 112    | planned (Milestone 1)           |

`xor_` accepts an optional `nand_dst` output to retain its `NAND(a, b)` intermediate for reuse by macros.

## Memory map

RAM is 256 x 1-bit cells (8-bit address).

| Address       | Use                                                       |
|---------------|-----------------------------------------------------------|
| `0x00`        | constant 0                                                |
| `0x01`        | constant 1 (made by the first instruction, `NAND(0,0)`)   |
| `0x02-0x0F`   | unused                                                    |
| `0x10-0x7F`   | variables (allocated & protected)                         |
| `0x80-0xFE`   | scratch space (allocated & unprotected)                   |
| `0xFF`        | unused                                                    |

- Both constants are write-protected (immutable)
- Variables are protected from scratch work overrides
- Multi-bit values are allocated as consecutive rows, LSB first
- Macros borrow scratch cells and release them when done. A result created without `dst=` stays allocated until you `release` it.
- Pass `name=` to `alloc()` to label a variable or scratch allocation in the generated RAM map.

## Layout

```
OneGatePython/
  __init__.py       Python package entry point
  asm.py            assembler, gate macros, scratch allocator, listing and hex output
  macros.py         half adder and full adder macros
  ram_tools.py      RAM simulation and visualization helpers
  onegate.py        (planned) OneGate language front end
  requirements.txt  Python dependencies
  program.lst       generated assembler listing
  program.hex       generated ROM image (ends with a HALT word)
  program_table.md  simulated RAM snapshot in a 16x16 bit grid
  memory_map.xlsx   colored spreadsheet RAM allocation map
Digital/
  ALU.dig           1-bit NAND ALU
  CU.dig            control unit, program counter, program ROM
  CPU.dig           top-level machine
Documents/
  ...
```

Python source and generated program outputs are kept together in `OneGatePython/`. The `.dig` hardware design files remain in `Digital/`. `program.lst`, `program.hex`, `program_table.md`, and `memory_map.xlsx` are generated; don't edit them by hand.

## Usage

Requires Python 3.10 or newer. Run from the repository root:

```
python -m pip install -r OneGatePython/requirements.txt
python -m OneGatePython.asm
```

Builds the demo program and writes `OneGatePython/program.hex`, `OneGatePython/program_table.md`, `OneGatePython/memory_map.xlsx`, and `OneGatePython/program.lst`. The Excel map uses a separate color per named allocation; labels are repeated for allocations split across rows. Open the workbook in a spreadsheet app to widen columns and inspect full names. RAM simulation and rendering live in `OneGatePython/ram_tools.py`; the `Asm` methods delegate to those helpers for convenience. The ROM in `Digital/CU.dig` loads `../OneGatePython/program.hex`.

Writing your own program:

```python
from OneGatePython.asm import Asm

asm = Asm()

s = asm.alloc(protected=True, name="sum")  # named, protected variable
input_bits = asm.alloc(8, protected=True, name="input")  # named 8-bit row, LSB first

x = asm.mov(asm.ONE, dst=None)  # uses unprotected scratch and assigns to temporary x
y = asm.mov(asm.ZERO, dst=None) # same as above but with y
asm.xor_(x, y, dst=s)

asm.release(x)                  # hand scratch cells back when you are done with them
asm.release(y)

asm.write_to_hex()              # ROM readable program instructions
asm.write_to_hex()              # ROM readable program instructions
```

## Roadmap

**Where we are:** the hardware runs straight-line NAND programs and the assembler builds them. There are no jumps yet, so a program can only be as long as the 256-word ROM. One 8-bit add takes about 112 instructions, so two of them fit in the 256-word ROM but a third won't. Control flow (Milestone 2) is what unlocks everything after it.

To keep this page honest, tick or untick an item in the same pull request that finishes or changes it.

### Milestone 0: make the repo safe to build on
- [x] `CU.dig` loads the program ROM from `../OneGatePython/program.hex` using a relative path

### Milestone 1: arithmetic library
- [x] NOT, AND, OR, XOR, MOV macros
- [x] Scratch and variable allocator with write-protected constants, plus listing and hex output
- [x] 1-bit half adder and full adder
- [ ] 8-bit ripple-carry adder `add8` that reads and writes allocated 8-bit variables and returns `(sum, carry)`, so the language example `sum, carry = a + b` works
- [x] A Python model (`Asm.simulate_ram`) that runs a program and returns the 256-cell RAM snapshot, so results can be compared with Digital before testing macros across all 65,536 inputs of `add8`
- [ ] Shifts, then subtract and compare

### Milestone 2: control flow
Open decisions, which also settle the "flags" question above:
- How is a jump encoded: a flag bit with the target in an existing 8-bit field (for example `dst`), or extra target bits?
- What does a conditional jump test: the value of a RAM cell (for example `RAM[a]`)? Jumping on the constant-1 cell would give an unconditional jump.

Work:
- [ ] Decide the flag layout and document it under "Instruction format"
- [ ] `CU.dig`: load the program counter on a jump (new control-ROM phase behaviour)
- [ ] `asm.py`: labels plus `jmp` and conditional-jump macros, with the ROM-size check updated
- [ ] Loop demo, for example repeated addition
- [ ] Stretch: store and run programs from RAM, not only ROM (the existing "dynamic programs in RAM" TODO)

### Milestone 3: OneGate language
A small language that compiles directly to this assembly:

```
var a:8 = 200
sum, carry = a + b
```

- [ ] Lexer/tokenizer in `onegate.py`
- [ ] Parser for variable declarations and arithmetic
- [ ] Code generation through `asm.py`, writing the same listing
- [ ] Loops and conditions

### Milestone 4: Verilog implementation
- [ ] Verilog version of the CPU
- [ ] Testbench that runs the same `program.hex` and checks the result against the Python model

### Ideas, not committed
- Display output. `Asm.disp` takes screen x/y arguments but is a placeholder with no hardware behind it yet.
