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
  OneGatePython/program.hex   ROM image for Digital, ends with a HALT word
  OneGatePython/program_table.md   simulated 256-cell RAM snapshot
  OneGatePython/memory_map.xlsx  spreadsheet RAM allocation map with colored cells
  OneGatePython/program.lst   every call you made (alloc, mov, ...) with the
                              instructions it expands into, plus ROM address
                              and word

Operands are captured before the result is written, so dst may be the same
cell as a or b.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Concatenate, ParamSpec, cast

if __package__:
    from .macros import full_adder_1b
    from .ram_tools import (
        render_ram_table,
        simulate_ram as run_ram,
        write_memory_map_xlsx as write_ram_memory_map_xlsx,
        write_ram_table,
    )
else:
    from macros import full_adder_1b
    from ram_tools import (
        render_ram_table,
        simulate_ram as run_ram,
        write_memory_map_xlsx as write_ram_memory_map_xlsx,
        write_ram_table,
    )

OUTPUT_DIR = Path(__file__).resolve().parent

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
    PROTECTED_LO, PROTECTED_HI = 0x10, 0x7F #allocated space for protected values (vars)
    SCRATCH_CALL_LO, SCRATCH_CALL_HI = 0x80, 0x9F # allocated space for call scratch work
    SCRATCH_FUNC_LO, SCRATCH_FUNC_HI = 0xA0, 0xBF # allocated space for func scratch work
    
    
    HALT = 0b000
    HALT_WORD = (0, 0, 0, HALT)
    NAND = 0b001
    NAND_RET = 0b010
    CALL = 0b011
    ARGS = 0b100



    PC_BITS = 8 # used for hex writing checks (instructions do not exceed ROM capacity)

    def __init__(self) -> None:
        self.prog: list[tuple[int, int, int, int]] = []
        self.bodies: list[tuple[int, int, int, int]] = []
        self._rows: list[Row] = []
        self._depth: int = 0
        self._protected: set[int] = set(range(self.PROTECTED_LO, self.PROTECTED_HI + 1))  # free variable cells
        self._free_call: set[int] = set(range(self.SCRATCH_CALL_LO, self.SCRATCH_CALL_HI + 1))  # free scratch cells
        self._free_func: set[int] = set(range(self.SCRATCH_FUNC_LO, self.SCRATCH_FUNC_HI + 1))
        self._scratch: tuple[int, int] = (self.SCRATCH_CALL_LO, self.SCRATCH_CALL_HI)
        self._free: set[int] = self._free_call
        self._blocks: dict[int, int] = {}   # base -> length, for every live row longer than one cell
        self._allocations: dict[int, tuple[int, str | None, bool]] = {}
        self.peak: int = 0
        self._ready: bool = False                        # constants are writable only for the next line
        self.nand_(self.ZERO, self.ZERO, dst=self.ONE)   # RAM[1] = NAND(0,0) = 1
        self._ready = True

    # listing

    @contextmanager
    def _scope(self, text: str) -> Iterator[None]:
        """List one operation; everything emitted inside it is indented underneath."""
        row: Row = [self._depth, text, len(self.prog), None, self.prog]
        self._rows.append(row)
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            row[3] = len(row[4])

    def _note(self, text: str) -> None:
        """List an operation that emits no instructions (alloc, temp, release)."""
        self._rows.append([self._depth, text, None, None, None])

    def write_listing(self, path: str | Path = OUTPUT_DIR / "program.lst") -> None:
        def line(addr: str, word: str, text: str, depth: int = 0) -> str:
            return f"{addr:<8}{word:<9}{'    ' * depth}{text}\n"

        with open(path, "w") as f:
            f.write(line("addr", "word", "operation"))
            for depth, text, start, end, words in self._rows:                
                if start is None or end is None or end == start:
                    addr = word = ""
                elif end - start == 1:
                    addr = f"{start:03d}"
                    word = f"{self._word(*words[start]):07x}"
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
        self.peak = max(self.peak, self._scratch[1] - self._scratch[0] + 1 - len(self._free))
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

    def alloc(self, size: int = 1, *, protected: bool = False, name: str | None = None) -> int:
        """Reserve `size` consecutive cells and return the base address; bit n is at base + n.

        Variables (protected=True) are never freed. Scratch goes back with release().
        An optional name appears in the generated RAM allocation map.
        """
        if isinstance(size, bool):      
            raise TypeError("alloc(True) was the old protected flag: write alloc(protected=True)")
        if name is not None:
            if not name.strip():
                raise ValueError("allocation name cannot be empty")
            if any(allocation_name == name for _, allocation_name, _ in self._allocations.values()):
                raise ValueError(f"an active allocation is already named {name!r}")
        base = self._take(size, protected=protected)
        self._allocations[base] = (size, name, protected)
        tag = f"[{size}]" if size > 1 else ""
        label = f" {name!r}" if name is not None else ""
        self._note(f"alloc {'var' if protected else 'scratch'}{label}{tag} -> {self._span(base, size)}")
        return base

    def release(self, cell: int) -> None:
        """Return a scratch cell to the pool, or a whole scratch row given its base address.

        Variables and constants are ignored. A cell from the middle of a row raises ValueError.
        """
        if not self._scratch[0] <= cell <= self._scratch[1]:
            return
        base, size = self._row_of(cell)
        if base != cell:
            raise ValueError(f"0x{cell:02X} is inside the row {self._span(base, size)}; "
                             f"release it by its base address 0x{base:02X}")
        if cell in self._free:
            return
        self._give(cell, size)
        self._allocations.pop(cell, None)
        self._note(f"release {self._span(cell, size)}")


    def call(self, body: int, *args: int) -> None:
        """Emit CALL. args are base addresses of up to 4 rows (8-aligned, below 0x80)."""
        if len(args) > 4:
            raise ValueError("CALL carries 4 rows; more needs an ARGS word first")
        rows = []
        for addr in args:
            if addr & 7 or not 0 <= addr < 0x80:
                raise ValueError(f"0x{addr:02X} can't be a row argument: multiple of 8, below 0x80")
            rows.append(addr >> 3)
        rows += [0] * (4 - len(rows))
        a = rows[0] | rows[1] << 4          # slot 0 low nibble, slot 1 high
        b = rows[2] | rows[3] << 4
        with self._scope(f"call body {body} " + ", ".join(f"0x{x:02X}" for x in args)):
            self.prog.append((a, b, body, self.CALL))   #

    def _layout(self):
        main_size = len(self.prog) + 1
        if any(op == self.CALL for *_, op in self.bodies):
            raise RuntimeError("a body contains a CALL; bodies are leaf-only")
        words = [(a, b, main_size + loc, op) if op == self.CALL else (a, b, loc, op)
                for a, b, loc, op in self.prog]
        words.append(self.HALT_WORD)
        words += self.bodies
        if len(words) > 1 << self.PC_BITS:
            raise RuntimeError(f"{len(words)} words won't fit")
        return words
    
    def place_body(self, instructions: list[tuple[int, int, int, int]]):
        if not instructions:
            raise ValueError("a body needs at least one instruction")
        *rest, (a, b, d, _) = instructions
        start = len(self.bodies)                      # offset within the bodies list
        self.bodies.extend(rest)
        self.bodies.append((a, b, d, self.NAND_RET))  # last word also returns
        return start


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

    @contextmanager
    def body(self):
        main, self.prog = self.prog, []
        saved = (self._free, self._scratch)
        self._free, self._scratch = self._free_func, (self.SCRATCH_FUNC_LO, self.SCRATCH_FUNC_HI)
        try:
            yield self.prog
        finally:
            self.prog = main
            self._free, self._scratch = saved

    # instructions

    @gate
    def nand_(self, a: int, b: int, *, dst: int | None = None) -> None:
        assert dst is not None          # gate always supplies it
        self.prog.append((a, b, dst, self.NAND))

    @gate
    def not_(self, a: int, *, dst: int | None = None) -> None:
        self.nand_(a, a, dst=dst)

    @gate
    def mov(self, a: int, *, dst: int | None = None, cleanup: bool = False) -> None:
        """Copy a into dst (a is left alone). cleanup=True makes it a move: a is released afterwards."""
        if cleanup and a != dst and self._scratch[0] <= a <= self._scratch[1]:
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
    def xor_(
        self,
        a: int,
        b: int,
        *,
        dst: int | None = None,
        nand_dst: int | None = None,
    ) -> None:
        """Compute XOR, optionally storing its NAND(a, b) intermediate in nand_dst."""
        if nand_dst is not None:
            if nand_dst in (a, b, dst):
                raise ValueError("nand_dst must not alias either input or the XOR destination")
            self.nand_(a, b, dst=nand_dst)
            with self.temp() as u, self.temp() as v:
                self.nand_(a, nand_dst, dst=u)
                self.nand_(b, nand_dst, dst=v)
                self.nand_(u, v, dst=dst)
            return

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
    def _word(a: int, b: int, d: int, op: int | None = None) -> int:
        return a | b << 8 | d << 16 | (Asm.NAND if op is None else op) << 24


    # def simulate_ram(self) -> list[int]:
    #     """Run the program with the RAM simulation helper and return its snapshot."""
    #     return run_ram(self.prog, 1 << self.PC_BITS)

    # def terminal_print(self, start: int = 0, end: int = 256) -> None:
    #     """Print and save the simulated RAM rows covering the address range [start, end)."""
    #     ram = self.simulate_ram()
    #     table = render_ram_table(ram, start, end)
    #     if table is None:
    #         print("No RAM addresses in range.")
    #         return

    #     print(table)
    #     write_ram_table(ram, OUTPUT_DIR / "program_table.md", start, end)

    # def write_memory_map_xlsx(
    #     self, path: str | Path = OUTPUT_DIR / "memory_map.xlsx"
    # ) -> None:
    #     pass

    def write_to_hex(self) -> None:
        words = [self._word(*ins) for ins in self._layout()]
        
        with open(OUTPUT_DIR / "program.hex", "w") as f:
            f.write("v2.0 raw\n")
            for w in words:
                f.write(f"{w:07x}\n")

        self.write_listing()






if __name__ == "__main__":
    assembly = Asm()
    
    var_a = assembly.alloc(8, protected=True, name="var_a")
    for i in range(8): assembly.mov(Asm.ZERO, dst=var_a + i)

    var_b = assembly.alloc(8, protected=True, name="var_b")

    not_8_body = None
    with assembly.body() as words:
        for i in range(8): assembly.nand_(var_a + i, var_a + i, dst=var_b + i)
        not_8_body = assembly.place_body(words)


    print(f'Var_a:{var_a:08x}')
    print(f'Var_c:{var_b:08x}')
    assembly.call(not_8_body, var_a)

    assembly.write_to_hex()

    # assembly.terminal_print(0, 256)
    # assembly.write_memory_map_xlsx()
