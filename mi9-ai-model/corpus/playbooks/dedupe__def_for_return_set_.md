PLAYBOOK [dedupe] shape=def +for +return+set( (n=9 verified traces)
Strategy: solve any dedupe task of this shape the same way.
Example prompt: def dedupe(xs: list) -> list - remove duplicate items, keeping the FIRST occurrence and the original order. Example: dedupe([1,2,1,3]) == [1,2,3].

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final w
Example answer: ```python
def dedupe(xs: list) -> list:
    seen = set()
    result = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result
```

<answer>DONE</answer>
