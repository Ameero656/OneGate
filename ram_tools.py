"""RAM simulation and visualization helpers, kept separate from instruction emission."""

from __future__ import annotations

import colorsys
from collections.abc import Mapping, Sequence, Set
from html import escape

Instruction = tuple[int, int, int]
Allocation = tuple[int, str | None, bool]


def simulate_ram(program: Sequence[Instruction], ram_size: int = 256) -> list[int]:
    """Run NAND instructions from zeroed RAM and return the resulting snapshot."""
    ram = [0] * ram_size
    for address, (a, b, dst) in enumerate(program):
        if any(not 0 <= cell < ram_size for cell in (a, b, dst)):
            raise ValueError(
                f"instruction {address} contains an address outside RAM: "
                f"a={a}, b={b}, dst={dst}"
            )
        ram[dst] = 1 - (ram[a] & ram[b])
    return ram


def render_ram_table(ram: Sequence[int], start: int = 0, end: int = 256) -> str | None:
    """Format simulated RAM as a markdown 16-column grid for [start, end)."""
    if not 0 <= start <= end <= len(ram):
        raise ValueError(f"RAM range must be within 0..{len(ram)}, got {start}..{end}")
    if start == end:
        return None

    first_row = start & ~0x0F
    last_row = (end - 1) & ~0x0F
    header = ["Addr", *[f"0x{offset:02X}" for offset in range(16)]]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for base in range(first_row, last_row + 1, 16):
        row = [f"0x{base:02X}", *(str(bit) for bit in ram[base:base + 16])]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_ram_table(ram: Sequence[int], path: str, start: int = 0, end: int = 256) -> None:
    """Write the markdown RAM table if the requested range is non-empty."""
    table = render_ram_table(ram, start, end)
    if table is not None:
        with open(path, "w") as file:
            file.write(table + "\n")


def _span(base: int, size: int) -> str:
    return f"0x{base:02X}" if size == 1 else f"0x{base:02X}..0x{base + size - 1:02X}"


def _allocation_color(index: int) -> str:
    hue = (index * 0.618033988749895) % 1
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.3, 0.98)
    red, green, blue = (round(channel * 245) for channel in (red, green, blue))
    return f"#{red:02X}{green:02X}{blue:02X}"


def write_memory_map(
    path: str,
    program: Sequence[Instruction],
    allocations: Mapping[int, Allocation],
    free_variables: Set[int],
    free_scratch: Set[int],
    protected_range: tuple[int, int],
    scratch_range: tuple[int, int],
    zero: int,
    one: int,
    ram_size: int = 256,
) -> None:
    """Write a color-coded RAM map using allocator metadata and simulated values."""
    allocation_cells: dict[int, tuple[str | None, int, bool, str]] = {}
    ordered_allocations = sorted(allocations.items())
    allocation_colors = {
        base: _allocation_color(index)
        for index, (base, _) in enumerate(ordered_allocations)
    }
    for base, (size, name, protected) in ordered_allocations:
        color = allocation_colors[base] if name is not None else "#C9DAF8"
        for bit_index in range(size):
            allocation_cells[base + bit_index] = (name, bit_index, protected, color)

    lines = [
        "# RAM Allocation Map",
        "",
        "Named allocations have unique background colors; hover over a cell for its bit name "
        "and address. Blue cells are allocated but unnamed, white cells are free, and gray "
        "cells are reserved or unused. Cell values are from `simulate_ram()`.",
        "",
        "| Name | Address range | Type | Color |",
        "| --- | --- | --- | --- |",
    ]
    for base, (size, name, protected) in ordered_allocations:
        if name is not None:
            kind = "Variable" if protected else "Scratch"
            color = allocation_colors[base]
            lines.append(
                f"| <code>{escape(name)}</code> | `{_span(base, size)}` | "
                f"{kind} | `{color}` |"
            )
    if not any(name is not None for _, (_, name, _) in ordered_allocations):
        lines.append("| No named allocations | - | Add `name=` to `alloc()` | - |")

    lines.extend([
        "",
        '<table border="1" cellpadding="4" cellspacing="0">',
        "<thead><tr><th>Addr</th>",
        *[f"<th>0x{offset:02X}</th>" for offset in range(16)],
        "</tr></thead>",
        "<tbody>",
    ])
    ram = simulate_ram(program, ram_size)
    for base in range(0, ram_size, 16):
        cells = [f"<th>0x{base:02X}</th>"]
        for address in range(base, min(base + 16, ram_size)):
            allocation = allocation_cells.get(address)
            if address == zero:
                color, title = "#EEEEEE", "constant zero"
            elif address == one:
                color, title = "#D9EAD3", "constant one"
            elif allocation is not None:
                name, bit_index, protected, color = allocation
                kind = "variable" if protected else "scratch"
                title = f"{name}[{bit_index}]" if name is not None else f"allocated {kind}"
            elif address in free_variables:
                color, title = "#FFFFFF", "free variable"
            elif address in free_scratch:
                color, title = "#FFFFFF", "free scratch"
            elif protected_range[0] <= address <= protected_range[1]:
                color, title = "#C9DAF8", "allocated variable"
            elif scratch_range[0] <= address <= scratch_range[1]:
                color, title = "#C9DAF8", "allocated scratch"
            else:
                color, title = "#F3F3F3", "unused"
            cells.append(
                f'<td bgcolor="{color}" style="color: #000000;" '
                f'title="{escape(title, quote=True)} '
                f'@ 0x{address:02X}">{ram[address]}</td>'
            )
        lines.append("<tr>" + "".join(cells) + "</tr>")
    lines.extend(["</tbody>", "</table>", ""])

    with open(path, "w") as file:
        file.write("\n".join(lines))
