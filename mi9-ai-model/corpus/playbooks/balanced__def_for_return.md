PLAYBOOK [balanced] shape=def +for +return (n=16 verified traces)
Strategy: solve any balanced task of this shape the same way.
Example prompt: def balanced(s: str) -> bool - s contains only ( ) [ ] { }; return True exactly when every bracket closes correctly and in the right order. Example: balanced('([{}])') == True, balanced('([)]') == False.

Write ONE Python function per the signature below. Standard library only, no input()/print(). R
Example answer: ```python
def balanced(s: str) -> bool:
    stack = []
    for char in s:
        if char in "([{" :
            stack.append(char)
        elif char in ")]}" :
            if not stack:
                return False
            top = stack.pop()
            if (top == '(' and char == ')') or (top == '[' and char == ']') or (top == '{' and char == '}'):
                continue
            else:
                return False
    return not stack
```

<answer>DONE</answer>
