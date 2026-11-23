PLAYBOOK [count_occurrences] shape=def +return (n=8 verified traces)
Strategy: solve any count_occurrences task of this shape the same way.
Example prompt: def count_occurrences(s: str, c: str) -> int - return the number of times character c appears in string s.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answer>. /no_think
Example answer: ```python
def count_occurrences(s: str, c: str) -> int:
    return s.count(c)
```

<answer>DONE</answer>
