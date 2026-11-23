PLAYBOOK [word_count] shape=def +dict(+for +return (n=18 verified traces)
Strategy: solve any word_count task of this shape the same way.
Example prompt: def word_count(words: list[str]) -> dict - return a dict mapping each word to how many times it occurs. Example: word_count(['a','a']) == {'a': 2}.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final 
Example answer: ```python
from collections import defaultdict

def word_count(words: list[str]) -> dict:
    count = defaultdict(int)
    for word in words:
        count[word] += 1
    return dict(count)
```

<answer>DONE</answer>
