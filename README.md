# OneGate

A CPU with exactly one arithmetic instruction: `NAND`.

Most CPUs have dozens of instructions and a pile of hardware to run them. OneGate has exactly one: take two bits from memory, NAND them, write the result back. That’s the whole machine. Everything else, from NOT and XOR to a full 8-bit adder, is built in software out of that single operation, and a Python assembler does the stitching. It’s computing stripped to its bare minimum, and it shows that a working computer can come from one logic gate repeated enough times. If a normal ALU is a full toolbox, OneGate is one tool used over and over to build every other tool. Our philosophy is for the OneGate CPU to possess the smallest possible ALU and maintain conceptual universality (turning complete).

***I fear not the man who has practiced 10,000 kicks once, but I fear the man who has practiced one kick 10,000 times.***

## Feature goals
- A CPU with exactly one arithmetic instruction
- A Python assembler that builds programs for the OneGate CPU
- A custom assembly tokenizer/lexer
- An interactive terminal (REPL): type one line at a time and see the result straight away, like a calculator

## Content goals
- Digital design files (.dig) for the CPU
- Verilog implementation source code
- Python OneGate assembly for programming and debugging

## Team

OneGate is built by a small team, and each role below owns one part of the repo. Roles marked `open` are waiting for someone. To take one, put your name after `Who:` in a pull request. One person can hold several roles, and a role can have several people. Roles tie to the [Roadmap](#roadmap) milestones, so tick items off there as you finish them.

**Hardware architect: design and research**
- Brainstorms, designs and researches the base Digital design. Makes the instruction-set calls (flag layout, how a jump is encoded) and adds the jump path to the control unit.
- Owns `Digital/*.dig` · Milestones 0 and 2 · Who: `Ameer Masoud & Isaac Blommel`

**Researcher: dedicated research and compilation**
- Researches current and contemporary CPU implementations for modern methods and relevant implementations. Procures documents; presents them to other teams for context and decision making. 
- Owns `Documents/` · Who: `Isaac Blommel`

**FPGA port: Digital to Vivado**
- Rebuilds the Digital design as Verilog and brings it up in Vivado: simulate it, synthesize it, and run it on a board if we have one. Keeps the Verilog synthesizable, for example by replacing the shared tri-state bus with a mux.
- Owns `verilog/` (planned) · Milestone 4 · Who: `open`

**Assembly proofreader**
- Checks that `asm.py` and `macros.py` do what they claim. Tests every macro against its truth table, builds the Python model that runs a program and returns RAM, and runs `add8` on all 65,536 inputs. Also checks that the generated `program.hex` and `program.lst` match the code.
- Owns tests for `asm.py` and `macros.py` · Milestone 1 · Who: `open`

**Language front end: tokenizer and parser**
- Builds the OneGate language, starting with the lexer/tokenizer and then the parser, so `var a:8 = 200` and `sum, carry = a + b` compile to assembly. Needs `add8` from Milestone 1 before `a + b` can work.
- Owns `onegate.py` (planned) · Milestone 3 · Who: `open`

**Interactive terminal: REPL**
- Builds the live prompt. A line is typed, assembled into NAND instructions, run on the Python model against RAM that persists between lines, and the result is printed along with what it cost. It starts as a prompt over the `Asm` API and later takes OneGate language lines. Also extends the model so a line runs only its own new instructions, instead of replaying the whole program from zeroed RAM as `simulate_ram` does today.
- Owns `repl.py` (planned) · Milestone 5 · Who: `open`

**Assembler and macros**
- Writes the library the other roles build on: `add8`, shifts, subtract, compare, and later labels and jump macros.
- Owns `asm.py` and `macros.py` · Milestones 1 and 2 · Who: `open`

**Verification and CI**
- Makes sure the Python model, Digital and the Verilog all agree when they run the same `program.hex`, and runs those checks automatically on every pull request. Before tapeout this includes simulating the synthesized gate-level design.
- Owns the cross-checks and CI setup · Milestone 4 · Who: `open`

**Tapeout and physical design**
- Takes the Verilog through synthesis, place and route, and signoff in the club's 180 nm flow, and works with the club on area, pin and deadline limits. Everything that touches the foundry kit lives outside this public repo, and the person must be covered by the NDA first.
- Owns the physical-design flow (outside this repo) · Milestone 6 · Who: `Isaac Blommel`

**Project lead and docs**
- Keeps this README and the roadmap true, reviews pull requests and decides what is agreed.
- Owns `README.md` · All milestones · Who: `Ameer Masoud`

***Silicon: OneGate is a Stone Arch Silicon project, planned for a 180 nm tapeout where each subteam's design shares one chip. The foundry kit is under NDA and stays out of this repo (see [Tapeout](#tapeout-planned)).***

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

### Interactive terminal (planned)

A live prompt in the spirit of the Python shell: type one line, get the answer. Nothing here is built yet (Milestone 5). It comes in two stages:

1. **Assembler prompt.** A Python prompt with `Asm` and the Python model already loaded. Each call assembles into NAND instructions, runs on the model, and shows the value it produced. This needs nothing beyond the model from Milestone 1.
2. **OneGate prompt.** The same loop fed with OneGate language lines, once Milestone 3 exists. Target behavior:

```
>>> var a:8 = 200
>>> var b:8 = 100
>>> sum, carry = a + b
sum = 44, carry = 1
```

How it is meant to work:

- **It runs on the Python model, not on the hardware.** The ROM is fixed when the CPU starts, so the real machine can't take new lines on the fly. A prompt on the hardware needs program memory that can be written while the CPU waits, plus a host link to send instructions. That is the loadable program memory planned under [Tapeout](#tapeout-planned). The programs do not need to run from the data RAM.
- **RAM persists between lines.** Variables live in `0x10-0x7F` (112 cells, so fourteen 8-bit variables) and scratch in `0x80-0xFE` (127 cells). Temporaries are released after every line, and running out of variables, scratch cells or ROM is reported as a plain error.
- **Every line shows its cost** in NAND instructions (4 clock cycles each) and how much of the 256-word ROM the session has used, so you can see when a session would no longer fit on the real machine.
- **Meta-commands start with `:`** and build on the existing helpers: `:ram` (`render_ram_table`), `:listing` (`write_listing`), `:save` (`write_to_hex`, so a session becomes a `program.hex` for Digital) and `:reset`.

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
  repl.py           (planned) interactive terminal
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
```

Interactive terminal (planned, Milestone 5), launched the same way:

```
python -m OneGatePython.repl
```

## Tapeout (planned)

OneGate is a Stone Arch Silicon project. The club plans a 180 nm tapeout in which each subteam's design shares one chip, so OneGate has to fit an area and pin budget that is still to be confirmed with the club. Silicon can't be patched after fabrication, which changes a few things for the design:

- **Program memory must be loadable.** A ROM fixed at fabrication runs one program forever. The first chip needs program memory that can be written after fabrication, and a stop state (the end-of-program `HALT` or a resumable `AWAIT`) that leaves RAM untouched so the next chunk of instructions can follow. This is also what lets the interactive terminal run on the real chip.
- **Few pins, so a serial interface.** Load instruction words, read the 256 RAM cells, and report halt status over a small serial link, plus clock and reset. `Digital/CPU.dig` has only a clock, a button and an LED today.
- **Defined power-up.** The assembler assumes RAM cell `0x00` is 0 at start. On silicon that needs a reset, or the two constant cells wired outside the RAM.
- **No tri-state bus inside the chip.** The RTL uses a mux (see the FPGA port role).
- **Gate-level checks.** The same `program.hex` must give the same RAM in the Python model, Digital, the RTL simulation and the synthesized gate-level simulation.
- **The foundry kit is under NDA.** Don't commit the process kit, cell libraries, layouts, or any script or report derived from them. RTL, testbenches, Python and docs stay public. Anyone working with the kit must be covered by the NDA first.

These are decisions still to make, not settled design. The loadable-program interface also depends on the flag layout from Milestone 2.

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
- [ ] Compile one statement at a time and keep variable names and allocations between calls, so the interactive terminal (Milestone 5) can reuse it
- [ ] Loops and conditions

### Milestone 4: Verilog implementation
- [ ] Verilog version of the CPU
- [ ] Testbench that runs the same `program.hex` and checks the result against the Python model

### Milestone 5: interactive terminal
A live prompt where you type one line at a time, like the Python shell (see [Interactive terminal](#interactive-terminal-planned)). Stage 1 needs only the Python model from Milestone 1, so it does not have to wait for Milestones 2 to 4.

Stage 1: assembler prompt
- [ ] Python model with RAM that persists between lines: run only the new instructions of each line (`simulate_ram` always starts from zeroed RAM and replays the whole program)
- [ ] `repl.py`: a prompt with `Asm` and the model preloaded that prints the value each call produced
- [ ] Release temporaries after every line, and report running out of variables, scratch cells or ROM as a plain error
- [ ] Cost readout per line: NAND instructions, clock cycles (4 per instruction) and ROM words used out of 256
- [ ] Meta-commands `:ram`, `:listing`, `:save` and `:reset`

Stage 2: OneGate prompt
- [ ] Accept OneGate language lines (`var a:8 = 200`, `sum, carry = a + b`) once Milestone 3 can compile one statement at a time
- [ ] Continuation prompt for multi-line blocks once loops and conditions exist (Milestones 2 and 3)

### Milestone 6: tapeout readiness
See [Tapeout](#tapeout-planned). The first four items need no foundry access.
- [ ] Confirm with the club: tapeout deadline, area and pin budget, NDA coverage, and what may be public
- [ ] Decide the loadable-program interface (writable program memory, serial load and read-back, halt/await behavior) and document it under "Instruction format"
- [ ] Define reset and power-up behavior, including the constant cells `0x00` and `0x01`
- [ ] RTL without a tri-state bus that passes the Milestone 4 testbench
- [ ] Gate-level simulation of the synthesized design matches the Python model on the same `program.hex`
- [ ] Physical design and signoff in the club's 180 nm flow, kept outside this repo
- [ ] Submit to the club's shared-chip tapeout

### Ideas, not committed
- Display output. `Asm.disp` takes screen x/y arguments but is a placeholder with no hardware behind it yet.
- A prompt on the real machine: once Milestone 6 gives the CPU loadable program memory, the interactive terminal can send instructions to an FPGA board or the chip over its serial link instead of using the Python model.
- A try-it-in-your-browser version of the interactive terminal. The Python model could run in the browser through Pyodide, published on GitHub Pages.
