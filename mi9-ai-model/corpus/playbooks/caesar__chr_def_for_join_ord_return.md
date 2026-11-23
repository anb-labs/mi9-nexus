PLAYBOOK [caesar] shape=chr(+def +for +join+ord(+return (n=4 verified traces)
Strategy: solve any caesar task of this shape the same way.
Example prompt: def caesar(s: str, k: int) -> str - shift each lowercase letter forward by k positions, wrapping around z->a. Non-letters never appear. Example: caesar('abc', 1) == 'bcd'.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python cod
Example answer: ```python
def caesar(s: str, k: int) -> str:
    result = []
    for char in s:
        if char.islower():
            shifted = ord(char) + k
            if shifted > ord('z'):
                shifted = shifted - 26
            result.append(chr(shifted))
        else:
            result.append(char)
    return ''.join(result)
```

<answer>DONE</answer>
