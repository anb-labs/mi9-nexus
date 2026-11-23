PLAYBOOK [dataframe] shape=def +for +return (n=2 verified traces)
Strategy: solve any dataframe task of this shape the same way.
Example prompt: def total_age(rows) -> int:
    # rows is a list of dicts like [{'name': 'p1', 'age': 19, 'city': 'CHI'}, {'name': 'p2', 'age': 21, 'city': 'BOS'}]...
    # return the sum of the 'age' column.
    # Example: total_age([{'name': 'p1', 'age': 19, 'city': 'CHI'}]) == 19

Write ONE Python function per t
Example answer: ```python
def total_age(rows):
    return sum(row['age'] for row in rows)
```

<answer>DONE</answer>
