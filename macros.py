from asm import Asm

def half_adder_1b(assembly: Asm, a: int, b: int, dst: int | None = None) -> tuple[int, int]:

    s = assembly.xor_(a, b, dst=dst)
    cout = assembly.and_(a, b, dst=None)

    return s, cout

def full_adder_1b(assembly: Asm, a: int, b: int, c: int, dst: int | None = None) -> tuple[int, int]:
    s1, cout1 = half_adder_1b(assembly, a, b)
    s, cout2 = half_adder_1b(assembly, s1, c, dst=dst)
    assembly.release(s1)
    cout = assembly.or_(cout1, cout2, dst=cout1)
    assembly.release(cout2)
    return s, cout