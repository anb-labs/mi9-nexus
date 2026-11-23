PLAYBOOK [reverse_string] shape=def +return+reverse (n=16 verified traces)
Strategy: solve any reverse_string task of this shape the same way.
Example prompt: def reverse_string(s: str) -> str — return the characters of s in reverse order. Example: reverse_string('abcd') == 'dcba'.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answe
Example answer: ```python
def reverse_string(s: str) -> str:
    return s[::-1]
```

<answer>DONE</answer>
