PLAYBOOK [popcount] shape=def +return+while  (n=6 verified traces)
Strategy: solve any popcount task of this shape the same way.
Example prompt: def popcount(n: int) -> int - return the number of 1-bits in the binary representation of n.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answer>. /no_think
Example answer: ```python
def popcount(n: int) -> int:
    count = 0
    while n:
        count += n & 1
        n >>= 1
    return count
```

<answer>DONE</answer>
