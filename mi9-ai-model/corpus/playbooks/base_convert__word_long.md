PLAYBOOK [base_convert] shape=word:long (n=5 verified traces)
Strategy: solve any base_convert task of this shape the same way.
Example prompt: Convert the decimal number 201 to base 4. Give the digits as a plain string (use a-f for 10-15). Example: 26 in base 16 is 1a.

End with your final answer as <answer>...</answer>. /no_think
Example answer: ```python
def decimal_to_base4(n):
    if n == 0:
        return "0"
    digits = []
    while n > 0:
        digits.append(str(n % 4))
        n = n // 4
    digits.reverse()
    # Convert to lowercase for a-f
    return ''.join([d if d < 'a' else d.lower() for d in digits])

# Convert 201 to base 4
result = decimal_to_base4(201)
print(result)
```

<answer>3021</answer>
