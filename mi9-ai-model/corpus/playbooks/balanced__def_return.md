PLAYBOOK [balanced] shape=def +return (n=6 verified traces)
Strategy: solve any balanced task of this shape the same way.
Example prompt: def balanced(s: str) -> bool - s contains only ( ) [ ] { }; return True exactly when every bracket closes correctly and in the right order. Example: balanced('([{}])') == True, balanced('([)]') == False.

Write ONE Python function per the signature below. Standard library only, no input()/print(). R
Example answer: def balanced(s: str) -> bool - s contains only ( ) [ ] { }; return True exactly when every bracket closes correctly and in the right order. Example: balanced('([{}])') == True, balanced('([)]') == False.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answer>. /no_think
