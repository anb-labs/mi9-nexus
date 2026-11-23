PLAYBOOK [is_palindrome] shape=def +return (n=19 verified traces)
Strategy: solve any is_palindrome task of this shape the same way.
Example prompt: def is_palindrome(s: str) -> bool - return True exactly when s reads the same forwards and backwards. Example: is_palindrome('abba') == True.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <
Example answer: ```python
def is_palindrome(s: str) -> bool:
    return s == s[::-1]
```

<answer>DONE</answer>
