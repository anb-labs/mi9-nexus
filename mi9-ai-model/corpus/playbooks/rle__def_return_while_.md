PLAYBOOK [rle] shape=def +return+while  (n=3 verified traces)
Strategy: solve any rle task of this shape the same way.
Example prompt: def rle(s: str) -> list - run-length encode: return a list of (character, run_length) tuples in order. Example: rle('aabb') == [('a', 2), ('b', 2)].

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final
Example answer: ```python
def rle(s: str) -> list:
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]: j += 1
        out.append((s[i], j - i)); i = j
    return out
```

<answer>DONE</answer>
