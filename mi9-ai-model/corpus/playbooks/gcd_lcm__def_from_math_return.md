PLAYBOOK [gcd_lcm] shape=def +from math+return (n=17 verified traces)
Strategy: solve any gcd_lcm task of this shape the same way.
Example prompt: def gcd_lcm(a: int, b: int) -> tuple[int, int] - return (greatest common divisor, least common multiple) as a tuple. Example: gcd_lcm(4, 6) == (2, 12).

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the fi
Example answer: ```python
def gcd_lcm(a: int, b: int) -> tuple[int, int]:
    from math import gcd
    return (gcd(a, b), a * b // gcd(a, b))
```

<answer>DONE</answer>
