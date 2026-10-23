from asm import Asm
from macros import *

assembly = Asm()

var_a = Asm.ZERO
var_b = Asm.ONE
var_c = Asm.ZERO #carry
var_s = assembly.alloc(1, protected=True, name="var_s")
example_alloc8b = assembly.alloc(8, protected=True, name="example")
example2_alloc8b = assembly.alloc(8, protected=True, name="nxt_row_example")
full_adder_1b(assembly, var_a, var_b, var_c, dst=var_s)

assembly.write_to_hex()

print(f'Var_a:{var_a:08x}')
print(f'Var_b:{var_b:08x}')
print(f'Var_c:{var_c:08x}')
print(f'Var_s:{var_s:08x}')
assembly.terminal_print(0, 256)
assembly.write_memory_map_xlsx()