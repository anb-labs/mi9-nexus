PLAYBOOK [second_largest] shape=def +return+set(+sorted( (n=8 verified traces)
Strategy: solve any second_largest task of this shape the same way.
Example prompt: def second_largest(xs: list[int]) -> int | None - return the second largest DISTINCT value, or None if there are fewer than two distinct values. Example: second_largest([1,3,3,2]) == 2.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single
Example answer: ```python
def second_largest(xs: list[int]) -> int | None:
    unique_values = sorted(set(xs))
    return unique_values[-2] if len(unique_values) >= 2 else None
```

<answer>DONE</answer>
