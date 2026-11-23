PLAYBOOK [fraction_ops] shape=word:long (n=2 verified traces)
Strategy: solve any fraction_ops task of this shape the same way.
Example prompt: Compute 10/8 - 3/4. Give the result as a fully reduced fraction p/q (e.g. 3/4). If it is an integer, answer n/1.

End with your final answer as <answer>...</answer>. /no_think
Example answer: To compute $ \frac{10}{8} - \frac{3}{4} $, we first find a common denominator. The least common denominator of 8 and 4 is 8. We convert $ \frac{3}{4} $ to have a denominator of 8, which gives $ \frac{6}{8} $. Now we subtract:

$$
\frac{10}{8} - \frac{6}{8} = \frac{4}{8}
$$

We simplify $ \frac{4}{8} $ by dividing both the numerator and the denominator by their greatest common divisor, which is 4:

$$
\frac{4}{8} = \frac{1}{2}
$$

Thus, the result is $ \frac{1}{2} $.

<answer>1/2</answer>
