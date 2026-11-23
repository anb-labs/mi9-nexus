PLAYBOOK [max_subarray] shape=def +for +return (n=14 verified traces)
Strategy: solve any max_subarray task of this shape the same way.
Example prompt: def max_subarray(xs: list[int]) -> int - return the maximum possible sum of a contiguous, non-empty subarray (Kadane). At least one element must be used. Example: max_subarray([1,-2,3]) == 3.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a 
Example answer: ```python
def max_subarray(xs: list[int]) -> int:
    max_current = max_global = xs[0]
    for num in xs[1:]:
        max_current = max(num, max_current + num)
        max_global = max(max_global, max_current)
    return max_global
```

<answer>DONE</answer>
