PLAYBOOK [sum_ints] shape=def +return (n=12 verified traces)
Strategy: solve any sum_ints task of this shape the same way.
Example prompt: def sum_ints(xs: list[int]) -> int - return the sum of all integers in the list xs.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answer>. /no_think
Example answer: ```python
def sum_ints(xs: list[int]) -> int:
    return sum(xs)
```

<answer>DONE</answer>
