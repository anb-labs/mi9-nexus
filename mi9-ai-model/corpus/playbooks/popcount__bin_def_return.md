PLAYBOOK [popcount] shape=bin(+def +return (n=11 verified traces)
Strategy: solve any popcount task of this shape the same way.
Example prompt: def popcount(n: int) -> int - return the number of 1-bits in the binary representation of n.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answer>. /no_think
Example answer: ```python
def popcount(n: int) -> int:
    return bin(n).count('1')
```

<answer>DONE</answer>
