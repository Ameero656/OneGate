"""
asm.py - back end for the OneGate machine.

The machine has ONE ALU instruction:   RAM[dst] = NAND(RAM[a], RAM[b])
onegate.py calls this module for everything below the syntax:
named variables, macros (not/and/or/xor/mov/add/shifts), padding, program.hex
output, a listing, and a Python model of the machine so a program can be
checked before it ever reaches Digital.

RAM map:
  0x00        constant 0 (never written)
  0x01        constant 1 (written by the first instruction, never again)
  0x10-0x7F   variables
  0x80-0xFE   scratch for macros

Rows: alloc(8) reserves 8 consecutive cells and returns the base address; bit n
lives at base + n (LSB first). Cells are handed out lowest address first.
release(base) frees a whole scratch row, and freeing one cell from the middle
of a row raises ValueError.

Writing to 0x00 or 0x01 raises ValueError. mov(a, dst=d) copies and leaves a
alone; mov(a, dst=d, cleanup=True) is a move: it also releases a if a is a
scratch cell (variables and constants are never released by cleanup).

Output files:
  Digital/program.hex   ROM image for Digital, ends with a HALT word
  program.lst   every call you made (alloc, mov, ...) with the instructions it
                expands into indented underneath, plus ROM address and word

Operands are captured before the result is written, so dst may be the same
cell as a or b.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, Concatenate, ParamSpec, cast

from macros import *

P = ParamSpec("P")

# One listing row: [depth, text, first_addr, end_addr]. The addresses are None
# for operations that emit no instructions (alloc, temp, release).
Row = list[Any]


def gate(emit: Callable[Concatenate[Asm, P], None]) -> Callable[Concatenate[Asm, P], int]:
    """Make dst an optional keyword (a fresh scratch cell if omitted) and list the call.

    Refuses to write the constant cells, and passes any extra keyword options
    (mov's cleanup, say) through to the macro.

    Typing: the decorated method is declared with its public signature (dst
    keyword-only and optional), so that is what an editor shows on hover. The
    wrapper resolves dst before calling the body and returns the destination
    cell, which is why the hover says -> int although the method itself is
    declared -> None.
    """
    name = getattr(emit, "__name__", "op").rstrip("_")
    run = cast("Callable[..., None]", emit)

    @wraps(emit)
    def wrapper(self: Asm, *operands: int, dst: int | None = None, **opts: Any) -> int:
        new = dst is None
        out = self._take() if dst is None else dst
        args = ", ".join(f"0x{x:02X}" for x in operands)
        text = f"{name} {args} -> 0x{out:02X}" + (" (new)" if new else "")
        if self._ready and out in self.CONSTANTS:
            raise ValueError(f"{text}: 0x{out:02X} is a constant cell and can't be written")
        with self._scope(text):
            run(self, *operands, dst=out, **opts)
        return out

    return cast("Callable[Concatenate[Asm, P], int]", wrapper)


class Asm:
    ZERO, ONE = 0x00, 0x01
    CONSTANTS = (ZERO, ONE)
    SCRATCH_LO, SCRATCH_HI = 0x80, 0xFE # allocated space for scratch work
    PROTECTED_LO, PROTECTED_HI = 0x10, 0x7F #allocated space for protected values (vars)
    HALT = 1 << 24 # bit24 flags the end of program; pauses tri-state cycle & program counter

    PC_BITS = 8 # used for hex writing checks (instructions do not exceed ROM capacity)

    def __init__(self) -> None:
        self.prog: list[tuple[int, int, int]] = []
        self._rows: list[Row] = []
        self._depth: int = 0
        self._protected: set[int] = set(range(self.PROTECTED_LO, self.PROTECTED_HI + 1))  # free variable cells
        self._free: set[int] = set(range(self.SCRATCH_LO, self.SCRATCH_HI + 1))           # free scratch cells
        self._blocks: dict[int, int] = {}   # base -> length, for every live row longer than one cell
        self.peak: int = 0
        self._ready: bool = False                        # constants are writable only for the next line
        self.nand_(self.ZERO, self.ZERO, dst=self.ONE)   # RAM[1] = NAND(0,0) = 1
        self._ready = True

    # listing

    @contextmanager
    def _scope(self, text: str) -> Iterator[None]:
        """List one operation; everything emitted inside it is indented underneath."""
        row: Row = [self._depth, text, len(self.prog), None]
        self._rows.append(row)
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            row[3] = len(self.prog)

    def _note(self, text: str) -> None:
        """List an operation that emits no instructions (alloc, temp, release)."""
        self._rows.append([self._depth, text, None, None])

    def write_listing(self, path: str = "program.lst") -> None:
        def line(addr: str, word: str, text: str, depth: int = 0) -> str:
            return f"{addr:<8}{word:<9}{'    ' * depth}{text}\n"

        with open(path, "w") as f:
            f.write(line("addr", "word", "operation"))
            for depth, text, start, end in self._rows:
                if start is None or end is None or end == start:
                    addr = word = ""
                elif end - start == 1:
                    addr = f"{start:03d}"
                    word = f"{self._word(*self.prog[start]):07x}"
                else:
                    addr, word = f"{start:03d}-{end - 1:03d}", ""
                f.write(line(addr, word, text, depth))
            f.write(line(f"{len(self.prog):03d}", f"{self.HALT:07x}", "HALT"))

    # memory

    @staticmethod
    def _span(base: int, size: int = 1) -> str:
        """'0x80' for one cell, '0x80..0x87' for a row."""
        return f"0x{base:02X}" if size == 1 else f"0x{base:02X}..0x{base + size - 1:02X}"

    @staticmethod
    def _first_run(pool: set[int], size: int) -> int | None:
        """Lowest address that starts `size` consecutive cells, all in pool; None if there is no such run."""
        start = run = 0
        prev = -2
        for cell in sorted(pool):
            if cell == prev + 1:
                run += 1
            else:
                start, run = cell, 1
            if run == size:
                return start
            prev = cell
        return None

    def _take(self, size: int = 1, *, protected: bool = False) -> int:
        if size < 1:
            raise ValueError(f"size must be at least 1, got {size}")
        pool = self._protected if protected else self._free
        base = self._first_run(pool, size)
        if base is None:
            kind = "variables" if protected else "scratch"
            if len(pool) < size:
                raise RuntimeError(f"out of {kind}")
            raise RuntimeError(f"no run of {size} consecutive {kind} cells ({len(pool)} free, but fragmented)")
        pool.difference_update(range(base, base + size))
        if size > 1:
            self._blocks[base] = size
        self.peak = max(self.peak, self.SCRATCH_HI - self.SCRATCH_LO + 1 - len(self._free))
        return base

    def _give(self, base: int, size: int = 1) -> None:
        """Put scratch cells back in the pool. Safe to repeat."""
        self._free.update(range(base, base + size))
        self._blocks.pop(base, None)

    def _row_of(self, cell: int) -> tuple[int, int]:
        """(base, size) of the multi-cell row containing cell, or (cell, 1) for a single cell."""
        for base, size in self._blocks.items():
            if base <= cell < base + size:
                return base, size
        return cell, 1

    def alloc(self, size: int = 1, *, protected: bool = False) -> int:
        """Reserve `size` consecutive cells and return the base address; bit n is at base + n.

        Variables (protected=True) are never freed. Scratch goes back with release().
        """
        if isinstance(size, bool):      # alloc(True) used to mean protected=True
            raise TypeError("alloc(True) was the old protected flag: write alloc(protected=True)")
        base = self._take(size, protected=protected)
        tag = f"[{size}]" if size > 1 else ""
        self._note(f"alloc {'var' if protected else 'scratch'}{tag} -> {self._span(base, size)}")
        return base

    def release(self, cell: int) -> None:
        """Return a scratch cell to the pool, or a whole scratch row given its base address.

        Variables and constants are ignored. A cell from the middle of a row raises ValueError.
        """
        if not self.SCRATCH_LO <= cell <= self.SCRATCH_HI:
            return
        base, size = self._row_of(cell)
        if base != cell:
            raise ValueError(f"0x{cell:02X} is inside the row {self._span(base, size)}; "
                             f"release it by its base address 0x{base:02X}")
        if cell in self._free:
            return
        self._give(cell, size)
        self._note(f"release {self._span(cell, size)}")

    @contextmanager
    def temp(self, size: int = 1) -> Iterator[int]:
        """Borrow `size` consecutive scratch cells for the length of the with-block."""
        t = self._take(size)
        tag = f"[{size}]" if size > 1 else ""
        self._note(f"temp{tag} -> {self._span(t, size)}")
        try:
            yield t
        finally:
            self._give(t, size)

    # instructions

    @gate
    def nand_(self, a: int, b: int, *, dst: int | None = None) -> None:
        assert dst is not None          # gate always supplies it
        self.prog.append((a, b, dst))

    @gate
    def not_(self, a: int, *, dst: int | None = None) -> None:
        self.nand_(a, a, dst=dst)

    @gate
    def mov(self, a: int, *, dst: int | None = None, cleanup: bool = False) -> None:
        """Copy a into dst (a is left alone). cleanup=True makes it a move: a is released afterwards."""
        if cleanup and a != dst and self.SCRATCH_LO <= a <= self.SCRATCH_HI:
            base, size = self._row_of(a)
            if size > 1:             
                raise ValueError(f"cleanup would free the whole row {self._span(base, size)}; "
                                 "release the row with release(base) once all of it is done")
        with self.temp() as t:
            self.not_(a, dst=t); self.not_(t, dst=dst)
        if cleanup and a != dst:        # moving a cell onto itself must not free the result
            self.release(a)             # no-op unless a is a scratch cell


    @gate
    def and_(self, a: int, b: int, *, dst: int | None = None) -> None:
        with self.temp() as t:
            self.nand_(a, b, dst=t); self.not_(t, dst=dst)

    @gate
    def or_(self, a: int, b: int, *, dst: int | None = None) -> None:
        with self.temp() as x, self.temp() as y:
            self.not_(a, dst=x); self.not_(b, dst=y); self.nand_(x, y, dst=dst)

    @gate
    def xor_(self, a: int, b: int, *, dst: int | None = None) -> None:
        with self.temp() as t, self.temp() as u, self.temp() as v:
            self.nand_(a, b, dst=t)
            self.nand_(a, t, dst=u)
            self.nand_(b, t, dst=v)
            self.nand_(u, v, dst=dst)


    
    
    @gate
    def disp(self, *args: int, scrn_x: int | None = None, scrn_y: int | None = None, dst: int | None = None) -> None:
        pass

    # output

    @staticmethod
    def _word(a: int, b: int, d: int) -> int:
        return a | b << 8 | d << 16

    def terminal_print(self) -> None:
        ram = [0] * 256
        for a, b, d in self.prog:
            ram[d] = 1 - (ram[a] & ram[b])
        print(ram[:8])

    def write_to_hex(self) -> None:
        words = [self._word(*ins) for ins in self.prog] + [self.HALT]
        if len(words) > 1 << self.PC_BITS:
            raise RuntimeError(f"{len(words)} words (including HALT) won't fit in a {1 << self.PC_BITS}-word ROM")

        with open("Digital/program.hex", "w") as f:
            f.write("v2.0 raw\n")
            for w in words:
                f.write(f"{w:07x}\n")

        self.write_listing()






if __name__ == "__main__":
    assembly = Asm()
    
    var_a = Asm.ZERO
    var_b = Asm.ONE
    var_c = Asm.ZERO #carry
    var_s = assembly.alloc(1, protected=True)
    full_adder_1b(assembly, var_a, var_b, var_c, dst=var_s)

    assembly.write_to_hex()

    print(f'Var_a:{var_a:08x}')
    print(f'Var_b:{var_b:08x}')
    print(f'Var_c:{var_c:08x}')
    print(f'Var_s:{var_s:08x}')
