PLAYBOOK [flatten] shape=def +for +return (n=15 verified traces)
Strategy: solve any flatten task of this shape the same way.
Example prompt: def flatten(xs) -> list - xs is a list possibly containing nested lists at any depth; return a single flat list in left-to-right order. Example: flatten([1,[2,[3]]]) == [1, 2, 3].

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```py
Example answer: ```python
def flatten(xs):
    result = []
    def recurse(lst):
        for item in lst:
            if isinstance(item, list):
                recurse(item)
            else:
                result.append(item)
    recurse(xs)
    return result
```

<answer>DONE</answer>
