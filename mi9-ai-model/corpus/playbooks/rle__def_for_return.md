PLAYBOOK [rle] shape=def +for +return (n=10 verified traces)
Strategy: solve any rle task of this shape the same way.
Example prompt: def rle(s: str) -> list - run-length encode: return a list of (character, run_length) tuples in order. Example: rle('aabb') == [('a', 2), ('b', 2)].

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final
Example answer: ```python
def rle(s: str) -> list:
    if not s:
        return []
    result = []
    char = s[0]
    count = 1
    for i in range(1, len(s)):
        if s[i] == char:
            count += 1
        else:
            result.append((char, count))
            char = s[i]
            count = 1
    result.append((char, count))
    return result
```

<answer>DONE</answer>
