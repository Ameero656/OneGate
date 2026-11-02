    def var_to_args(var: int):
            return [int(bit) for bit in bin(var)[2:].zfill(8)][3:6]

        print