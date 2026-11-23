PLAYBOOK [dataframe] shape=def +return (n=1 verified traces)
Strategy: solve any dataframe task of this shape the same way.
Example prompt: def group_by_city(rows) -> dict:
    # rows is a list of dicts like [{'name': 'p1', 'age': 22, 'city': 'BOS'}, {'name': 'p2', 'age': 35, 'city': 'SF'}]...
    # return a dict mapping each city to the list of names there, in order of first appearance.
    # Example: group_by_city([{'name': 'p1', 'age
Example answer: def group_by_city(rows) -> dict:
    # rows is a list of dicts like [{'name': 'p1', 'age': 22, 'city': 'BOS'}, {'name': 'p2', 'age': 35, 'city': 'SF'}]...
    # return a dict mapping each city to the list of names there, in order of first appearance.
    # Example: group_by_city([{'name': 'p1', 'age': 22, 'city': 'BOS'}]) == {'BOS': ['p1']}

Write ONE Python function per the signature below. Standard library only, no input()/print(). Reply with a single ```python code block, then the final word <answer>DONE</answer>. /no_think
