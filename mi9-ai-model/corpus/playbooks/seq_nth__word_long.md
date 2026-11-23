PLAYBOOK [seq_nth] shape=word:long (n=2 verified traces)
Strategy: solve any seq_nth task of this shape the same way.
Example prompt: The sequence starts 11, 14, 17, 20, 23, 26. Each term: add 3 to get the next term. Find term number 7 (a_7, with a_1 = 11).

End with your final answer as <answer>...</answer>. /no_think
Example answer: To find the 7th term ($a_7$) of the sequence where each term is obtained by adding 3 to the previous term and starting with $a_1 = 11$, we use the arithmetic sequence formula:

$$
a_n = a_1 + (n - 1) \cdot d
$$

Where:
- $a_1 = 11$
- $d = 3$
- $n = 7$

Substitute the values:

$$
a_7 = 11 + (7 - 1) \cdot 3 = 11 + 18 = 29
$$

Thus, the correct answer is:

<answer>29</answer>
