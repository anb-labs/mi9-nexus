PLAYBOOK [matmul2] shape=def +for +return (n=20 verified traces)
Strategy: solve any matmul2 task of this shape the same way.
Example prompt: def matmul2(A, B) -> list[list[int]] - A and B are 2x2 matrices given as nested lists; return their matrix product in the same format.

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>
Example answer: ```python
def matmul2(A, B) -> list[list[int]]:
    return [[sum(A[i][k] * B[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
```

<answer>DONE</answer>
