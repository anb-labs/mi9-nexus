"""Task families: self-generating, executor-verified practice tasks.

Whitepaper Ch. 3.2 (Absolute Zero) + Ch. 6.4: tasks are generated with random
parameters; the answer lives in the checker, never in the prompt, so nothing
can be memorized from the training corpus. The reference solution is validated
through the sandbox at generation time; a family that cannot verify itself is
rejected. Difficulty 1..5 scales with the curriculum (zone of proximal
development, Ch. 4.3).
"""
import json
import random
import string
from fractions import Fraction

from . import answer as A

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

CODE_RULES = (
    "Write ONE Python function per the signature below. Standard library only, "
    "no input()/print(). Reply with a single ```python code block, then the "
    "final word <answer>DONE</answer>."
)


def mk_code(family, function, prompt_body, tests, difficulty, reference):
    return {
        "family": family, "domain": "code", "difficulty": difficulty,
        "prompt": prompt_body + "\n\n" + CODE_RULES,
        "kind": "code",
        "spec": {"kind": "tests", "function": function,
                 "tests": [{"args": list(a), "expected": e} for a, e in tests]},
        "reference": reference,
        "answer": "DONE",
    }


TOOL_RULES = (
    "Use the run_python tool to do the computation: emit exactly one tool call "
    "as <tool>{\"name\": \"run_python\", \"args\": {\"code\": \"print(...)\"}}</tool>. "
    "After the tool result appears, end with <answer>VALUE</answer>."
)


def mk_expr(family, expr, expected, prompt_body, difficulty, reference):
    """Spec the sandbox evaluates as a python expression in the module's
    namespace (sandbox.run_expr). Used for math-via-executor: the model emits
    a python block that defines the value, and the sandbox computes it."""
    return {
        "family": family, "domain": "math", "difficulty": difficulty,
        "prompt": prompt_body + "\n\n" + TOOL_RULES,
        "kind": "code",
        "spec": {"kind": "expr", "expr": expr, "expected": expected},
        "reference": reference,
        "answer": str(expected),
    }


def mk_text(family, prompt_body, expected, how, difficulty, reference, domain=None):
    if domain is None:
        domain = "logic" if how == "lower" else "math"
    return {
        "family": family, "domain": domain,
        "difficulty": difficulty,
        "prompt": prompt_body + "\n\nEnd with your final answer as <answer>...</answer>.",
        "kind": "text",
        "spec": {"kind": "text", "how": how, "answer": expected},
        "reference": reference,
        "answer": expected,
    }


# --------------------------------------------------------------------------
# CODE families
# --------------------------------------------------------------------------

def f_reverse_string(rng, d):
    s = "".join(rng.choice(string.ascii_lowercase) for _ in range(3 + d * 4))
    tests = [((s,), s[::-1]), (("ab",), "ba")]
    ref = "def reverse_string(s):\n    return s[::-1]"
    body = f"def reverse_string(s: str) -> str - return the characters of s in reverse order. Example: reverse_string('abcd') == 'dcba'."
    body = body.replace(" - ", " — ")
    return mk_code("reverse_string", "reverse_string", body, tests, d, ref)


def f_is_palindrome(rng, d):
    n = 3 + d * 5
    half = "".join(rng.choice(string.ascii_lowercase) for _ in range(n // 2))
    mid = rng.choice(string.ascii_lowercase) if n % 2 else ""
    if rng.random() < 0.5:
        s = half + mid + half[::-1]
        want = True
    else:
        s = half + mid + "".join(rng.choice(string.ascii_lowercase) for _ in range(n // 2))
        s = s if s != s[::-1] else s[:-1] + ("x" if s[-1] != "x" else "y")
        want = s == s[::-1]
    tests = [((s,), want), (("abba",), True), (("abc",), False)]
    ref = "def is_palindrome(s: str) -> bool:\n    return s == s[::-1]"
    body = ("def is_palindrome(s: str) -> bool — return True exactly when s reads the same "
            "forwards and backwards. Example: is_palindrome('abba') == True.")
    body = body.replace(" — ", " - ")
    return mk_code("is_palindrome", "is_palindrome", body, tests, d, ref)


def f_sum_ints(rng, d):
    n = 3 + d * 4
    xs = [rng.randint(-50, 99) for _ in range(n)]
    tests = [((xs,), sum(xs)), (([1, 2, 3],), 6)]
    ref = "def sum_ints(xs):\n    return sum(xs)"
    body = "def sum_ints(xs: list[int]) -> int - return the sum of all integers in the list xs."
    return mk_code("sum_ints", "sum_ints", body, tests, d, ref)


def f_count_occurrences(rng, d):
    n = 4 + d * 5
    s = "".join(rng.choice(string.ascii_lowercase) for _ in range(n))
    c = rng.choice(string.ascii_lowercase)
    ref = "def count_occurrences(s: str, c: str) -> int:\n    return s.count(c)"
    body = "def count_occurrences(s: str, c: str) -> int - return the number of times character c appears in string s."
    return mk_code("count_occurrences", "count_occurrences", body,
                   [((s, c), s.count(c)), (("aaa", "a"), 3), (("abc", "z"), 0)], d, ref)


def f_dedupe(rng, d):
    n = 4 + d * 4
    xs = [rng.randint(0, 9 + d) for _ in range(n)]
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    tests = [((xs,), out), (([1, 1, 2],), [1, 2])]
    ref = ("def dedupe(xs):\n"
           "    out, seen = [], set()\n"
           "    for x in xs:\n"
           "        if x not in seen:\n"
           "            seen.add(x); out.append(x)\n"
           "    return out")
    body = ("def dedupe(xs: list) -> list - remove duplicate items, keeping the FIRST "
            "occurrence and the original order. Example: dedupe([1,2,1,3]) == [1,2,3].")
    return mk_code("dedupe", "dedupe", body, tests, d, ref)


def f_second_largest(rng, d):
    n = max(3, 2 + d)
    xs = rng.sample(range(0, 200), n)
    want = sorted(set(xs))[-2] if len(set(xs)) >= 2 else None
    tests = [((xs,), want), (([5, 5],), None), (([3, 9, 9, 4],), 4)]
    ref = ("def second_largest(xs):\n"
           "    u = sorted(set(xs))\n"
           "    return u[-2] if len(u) >= 2 else None")
    body = ("def second_largest(xs: list[int]) -> int | None - return the second largest "
            "DISTINCT value, or None if there are fewer than two distinct values. "
            "Example: second_largest([1,3,3,2]) == 2.")
    return mk_code("second_largest", "second_largest", body, tests, d, ref)


def f_max_subarray(rng, d):
    n = 3 + d * 3
    xs = [rng.randint(-9, 9) for _ in range(n)]
    best, cur = xs[0], xs[0]
    for x in xs[1:]:
        cur = max(x, cur + x)
        best = max(best, cur)
    tests = [((xs,), best), (([-1, -2],), -1), (([1, -1, 3],), 3)]
    ref = ("def max_subarray(xs):\n"
           "    best = cur = xs[0]\n"
           "    for x in xs[1:]:\n"
           "        cur = max(x, cur + x); best = max(best, cur)\n"
           "    return best")
    body = ("def max_subarray(xs: list[int]) -> int - return the maximum possible sum of a "
            "contiguous, non-empty subarray (Kadane). At least one element must be used. "
            "Example: max_subarray([1,-2,3]) == 3.")
    return mk_code("max_subarray", "max_subarray", body, tests, d, ref)


def f_gcd_lcm(rng, d):
    a, b = rng.randint(2, 10 * d + 5), rng.randint(2, 10 * d + 5)
    g = 1
    for i in range(1, min(a, b) + 1):
        if a % i == 0 and b % i == 0:
            g = i
    l = a * b // g
    tests = [((a, b), (g, l)), ((4, 6), (2, 12))]
    ref = ("def gcd_lcm(a: int, b: int) -> tuple:\n"
           "    import math\n"
           "    g = math.gcd(a, b)\n"
           "    return (g, a * b // g)")
    body = ("def gcd_lcm(a: int, b: int) -> tuple[int, int] - return (greatest common "
            "divisor, least common multiple) as a tuple. Example: gcd_lcm(4, 6) == (2, 12).")
    return mk_code("gcd_lcm", "gcd_lcm", body, tests, d, ref)


def f_popcount(rng, d):
    n = rng.randint(1, 2 ** (4 + d * 4) - 1)
    w = bin(n).count("1")
    tests = [((n,), w), ((7,), 3), ((8,), 1)]
    ref = "def popcount(n: int) -> int:\n    return bin(n).count('1')"
    body = "def popcount(n: int) -> int - return the number of 1-bits in the binary representation of n."
    return mk_code("popcount", "popcount", body, tests, d, ref)


def f_matmul2(rng, d):
    def m():
        return [[rng.randint(-9, 9) for _ in range(2)] for _ in range(2)]
    A_, B_ = m(), m()
    C = [[sum(A_[i][k] * B_[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    tests = [((A_, B_), C), (([[1, 0], [0, 1]], [[2, 3], [4, 5]]), [[2, 3], [4, 5]])]
    ref = ("def matmul2(A, B):\n"
           "    return [[sum(A[i][k] * B[k][j] for k in range(2)) for j in range(2)] for i in range(2)]")
    body = ("def matmul2(A, B) -> list[list[int]] - A and B are 2x2 matrices given as nested "
            "lists; return their matrix product in the same format.")
    return mk_code("matmul2", "matmul2", body, tests, d, ref)


def f_balanced(rng, d):
    n = 2 + d * 2
    chars = []
    for _ in range(n):
        chars.append(rng.choice("([{])}"))
    s = "".join(chars)
    pairs = {")": "(", "]": "[", "}": "{"}
    stack, ok = [], True
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        else:
            if not stack or stack.pop() != pairs[ch]:
                ok = False
                break
    want = ok and not stack
    tests = [((s,), want), (("()",), True), (("([)]",), False)]
    ref = ("def balanced(s: str) -> bool:\n"
           "    pairs = {')': '(', ']': '[', '}': '{'}\n"
           "    st = []\n"
           "    for ch in s:\n"
           "        if ch in '([{': st.append(ch)\n"
           "        elif not st or st.pop() != pairs[ch]: return False\n"
           "    return not st")
    body = ("def balanced(s: str) -> bool - s contains only ( ) [ ] { }; return True exactly "
            "when every bracket closes correctly and in the right order. "
            "Example: balanced('([{}])') == True, balanced('([)]') == False.")
    return mk_code("balanced", "balanced", body, tests, d, ref)


def f_rle(rng, d):
    n = 3 + d * 3
    out, parts = [], []
    prev = ""
    while sum(len(x) for x in parts) < n:
        ch = rng.choice([c for c in string.ascii_lowercase if c != prev])
        k = rng.randint(1, 4)
        parts.append(ch * k)
        out.append((ch, k))
        prev = ch
    s = "".join(parts)
    tests = [((s,), out), (("aabb",), [("a", 2), ("b", 2)])]
    ref = ("def rle(s: str) -> list:\n"
           "    out, i = [], 0\n"
           "    while i < len(s):\n"
           "        j = i\n"
           "        while j < len(s) and s[j] == s[i]: j += 1\n"
           "        out.append((s[i], j - i)); i = j\n"
           "    return out")
    body = ("def rle(s: str) -> list - run-length encode: return a list of (character, "
            "run_length) tuples in order. Example: rle('aabb') == [('a', 2), ('b', 2)].")
    return mk_code("rle", "rle", body, tests, d, ref)


def f_caesar(rng, d):
    n = 4 + d * 4
    s = "".join(rng.choice(string.ascii_lowercase) for _ in range(n))
    k = rng.randint(1, 25)
    enc = "".join(chr((ord(c) - 97 + k) % 26 + 97) for c in s)
    tests = [((s, k), enc), (("abc", 1), "bcd")]
    ref = ("def caesar(s: str, k: int) -> str:\n"
           "    return ''.join(chr((ord(c) - 97 + k) % 26 + 97) for c in s)")
    body = ("def caesar(s: str, k: int) -> str - shift each lowercase letter forward by k "
            "positions, wrapping around z->a. Non-letters never appear. "
            "Example: caesar('abc', 1) == 'bcd'.")
    return mk_code("caesar", "caesar", body, tests, d, ref)


def f_flatten(rng, d):
    def nest(depth):
        xs = []
        for _ in range(rng.randint(1, 3) if depth else 3 + d):
            if depth < d - 1 and rng.random() < 0.5:
                xs.append(nest(depth + 1))
            else:
                xs.append(rng.randint(0, 99))
        return xs
    x = nest(0)
    flat = []
    def fl(v):
        for i in v:
            if isinstance(i, list):
                fl(i)
            else:
                flat.append(i)
    fl(x)
    tests = [((x,), flat), (([1, [2, [3]]],), [1, 2, 3])]
    ref = ("def flatten(xs):\n"
           "    out = []\n"
           "    def fl(v):\n"
           "        for i in v:\n"
           "            if isinstance(i, list): fl(i)\n"
           "            else: out.append(i)\n"
           "    fl(xs)\n"
           "    return out")
    body = ("def flatten(xs) -> list - xs is a list possibly containing nested lists at any "
            "depth; return a single flat list in left-to-right order. "
            "Example: flatten([1,[2,[3]]]) == [1, 2, 3].")
    return mk_code("flatten", "flatten", body, tests, d, ref)


def f_word_count(rng, d):
    vocab = ["cat", "dog", "sun", "run", "red", "sky", "box", "key"]
    words = [rng.choice(vocab) for _ in range(3 + d * 3)]
    want = {}
    for w in words:
        want[w] = want.get(w, 0) + 1
    tests = [((words,), want), ((["a", "a"],), {"a": 2})]
    ref = ("def word_count(words):\n"
           "    out = {}\n"
           "    for w in words: out[w] = out.get(w, 0) + 1\n"
           "    return out")
    body = ("def word_count(words: list[str]) -> dict - return a dict mapping each word to "
            "how many times it occurs. Example: word_count(['a','a']) == {'a': 2}.")
    return mk_code("word_count", "word_count", body, tests, d, ref)


# --------------------------------------------------------------------------
# MATH families
# --------------------------------------------------------------------------

def f_arith_chain(rng, d):
    n_terms = 2 + d
    ops = ["+", "-", "*"] + (["//"] if d >= 3 else [])
    val = rng.randint(2, 9 + d * 9)
    expr = str(val)
    for _ in range(n_terms - 1):
        op = rng.choice(ops)
        if op == "//":
            b = rng.randint(2, 6)
        else:
            b = rng.randint(2, 9 + d * 6)
        if op == "+":
            val += b
        elif op == "-":
            val -= b
        elif op == "*":
            val *= b
        else:
            val //= b
        expr = f"({expr} {op} {b})"
    body = (f"Compute this expression step by step, respecting standard precedence. "
            f"Expression: {expr}")
    return mk_text("arith_chain", body, str(val), "int", d, expr + " = " + str(val))


def f_fraction_ops(rng, d):
    ops = ["+", "-", "*"] + (["/"] if d >= 3 else [])
    op = rng.choice(ops)
    a, b = rng.randint(1, 4 + d * 3), rng.randint(2, 4 + d * 3)
    c, e = rng.randint(1, 4 + d * 3), rng.randint(2, 4 + d * 3)
    fa, fb = Fraction(a, b), Fraction(c, e)
    val = {"+": fa + fb, "-": fa - fb, "*": fa * fb, "/": fa / fb}[op]
    want = f"{val.numerator}/{val.denominator}"
    body = (f"Compute {a}/{b} {op} {c}/{e}. Give the result as a fully reduced fraction "
            f"p/q (e.g. 3/4). If it is an integer, answer n/1.")
    return mk_text("fraction_ops", body, want, "frac", d,
                   f"{fa} {op} {fb} = {val}")


def f_modular_pow(rng, d):
    a = rng.randint(2, 9 + d * 4)
    k = rng.randint(2, 3 + d * 3)
    m = rng.randint(5, 10 + d * 20)
    val = pow(a, k, m)
    body = (f"Compute {a}^{k} mod {m}. Show the repeated-squaring or modular reduction "
            f"steps, then give the remainder.")
    return mk_text("modular_pow", body, str(val), "int", d, f"pow({a},{k},{m})={val}")


def f_linear_solve(rng, d):
    if rng.random() < 0.6:
        x = rng.randint(1, 9 + d * 3)
        a = rng.randint(1, 4 + d * 2)
        b = rng.randint(-9, 9 + d * 3)
        c = a * x + b
        want = str(x)
        body = (f"Solve for x: {a}x + ({b}) = {c}. Give x as an integer.")
    else:
        x = Fraction(rng.randint(1, 4 + d * 2), rng.randint(2, 4 + d))
        a = rng.randint(2, 3 + d * 2)
        b = rng.randint(-9, 9)
        c = a * x + b
        want = f"{x.numerator}/{x.denominator}"
        cc = f"{c}" if c.denominator != 1 else f"{c.numerator}"
        body = (f"Solve for x: {a}x + ({b}) = {cc}. If x is fractional, answer as a reduced "
                f"fraction p/q. Reduce fully.")
    return mk_text("linear_solve", body, want, "frac", d, f"x = {want}")


def f_base_convert(rng, d):
    b = rng.choice([2, 4, 8, 16] if d >= 3 else [2, 4])
    n = rng.randint(3, 50 + d * 250)
    digs = "0123456789abcdef"
    v, out = n, ""
    while v:
        out = digs[v % b] + out
        v //= b
    out = out or "0"
    body = (f"Convert the decimal number {n} to base {b}. Give the digits as a plain string "
            f"(use a-f for 10-15). Example: 26 in base 16 is 1a.")
    return mk_text("base_convert", body, out, "lower", d, f"{n} base{b} = {out}",
                   domain="math")


def f_seq_nth(rng, d):
    kind = rng.choice(["arith", "geom"] if d >= 2 else ["arith"])
    a0 = rng.randint(-5, 12)
    if kind == "arith":
        r = rng.randint(2, 4 + d)
        seq = [a0 + r * i for i in range(6)]
        rule = f"add {r} to get the next term"
    else:
        r = rng.randint(2, 2 + d // 2)
        seq = [a0 * r ** i for i in range(6)]
        rule = f"multiply by {r} to get the next term"
    n = 6 + rng.randint(0, d)
    val = seq[0] if n == 1 else (seq[-1] + r if kind == "arith" else seq[-1] * r)
    body = (f"The sequence starts {', '.join(map(str, seq))}. Each term: {rule}. "
            f"Find term number {n} (a_{n}, with a_1 = {seq[0]}).")
    return mk_text("seq_nth", body, str(val), "int", d, f"rule={kind} r={r} a_{n}={val}")


# --------------------------------------------------------------------------
# LOGIC families
# --------------------------------------------------------------------------

def f_perm_order(rng, d):
    n = 3 + min(d, 4)
    people = [f"P{i}" for i in range(1, n + 1)]
    order = people[:]
    rng.shuffle(order)
    pos = {p: i + 1 for i, p in enumerate(order)}

    # start from a fully determining chain of "immediately after" clues,
    # then repeatedly weaken/remove while a unique solution survives
    clues = [{"t": "adj", "a": order[i], "b": order[i + 1]} for i in range(n - 1)]

    def consistent(seq):
        p = {q: i + 1 for i, q in enumerate(seq)}
        for c in clues:
            pa, pb = p[c["a"]], p[c["b"]]
            if c["t"] == "adj" and pb != pa + 1:
                return False
            if c["t"] == "after" and pb <= pa:
                return False
            if c["t"] == "notadj" and abs(pb - pa) == 1:
                return False
            if c["t"] == "between" and abs(pb - pa) != 2:
                return False
        return True

    import itertools
    def unique():
        return sum(1 for o in itertools.permutations(people) if consistent(list(o))) == 1

    for _ in range(n * 8):
        idx = rng.randrange(len(clues))
        cand = clues[:idx] + clues[idx + 1:]
        a, b = rng.sample(people, 2)
        pa, pb = pos[a], pos[b]
        kind = rng.choice(["after", "notadj", "between"])
        extra = None
        if kind == "after" and pb > pa + 1:
            extra = {"t": "after", "a": a, "b": b}
        elif kind == "notadj" and abs(pb - pa) > 1:
            extra = {"t": "notadj", "a": a, "b": b}
        elif kind == "between" and abs(pb - pa) == 2:
            extra = {"t": "between", "a": a, "b": b}
        if extra:
            cand = cand + [extra]
        clues_old = clues
        clues = cand
        if not unique():
            clues = clues_old

    text = []
    for c in clues:
        if c["t"] == "adj":
            text.append(f"{c['b']} stands immediately after {c['a']}.")
        elif c["t"] == "after":
            text.append(f"{c['b']} is somewhere after {c['a']}.")
        elif c["t"] == "notadj":
            text.append(f"{c['b']} is NOT adjacent to {c['a']}.")
        else:
            text.append(f"Exactly one person stands between {c['a']} and {c['b']}.")
    k = rng.randint(1, n)
    want = order[k - 1]
    body = (f"{n} people ({', '.join(people)}) stand in a line, one per position. Clues:\n" +
            "\n".join("- " + t for t in text) +
            f"\nThe clues allow exactly one arrangement. Who is at position {k} (1-indexed)? "
            f"Answer with just the name.")
    return mk_text("perm_order", body, want, "lower", d, "line: " + " < ".join(order))


def _bool_tree(rng, names, depth):
    if depth == 0 or rng.random() < 0.35:
        v = rng.choice(names)
        return ("lit", v, rng.random() < 0.25)
    op = rng.choice(["and", "or", "xor"])
    return (op, _bool_tree(rng, names, depth - 1), _bool_tree(rng, names, depth - 1))


def _bool_ev(node, vals):
    if node[0] == "lit":
        _, v, neg = node
        x = vals[v]
        return (not x) if neg else x
    _, l, r = node
    a, b = _bool_ev(l, vals), _bool_ev(r, vals)
    if node[0] == "and":
        return a and b
    if node[0] == "or":
        return a or b
    return a != b


def _bool_render(node):
    if node[0] == "lit":
        _, v, neg = node
        return v if not neg else f"NOT {v}"
    _, l, r = node
    op = {"and": "AND", "or": "OR", "xor": "XOR"}[node[0]]
    return f"({_bool_render(l)} {op} {_bool_render(r)})"


def f_bool_expr(rng, d):
    nvars = 3 if d < 3 else 4
    names = [chr(ord("A") + i) for i in range(nvars)]
    vals = {v: rng.random() < 0.5 for v in names}
    e = _bool_tree(rng, names, 1 + d // 2)
    want = _bool_ev(e, vals)
    assign = ", ".join(f"{v} = {'True' if vals[v] else 'False'}" for v in names)
    body = (f"Given: {assign}. Evaluate this boolean expression "
            f"(NOT binds to the single letter after it, XOR is exclusive-or):\n"
            f"{_bool_render(e)}\nAnswer True or False.")
    return mk_text("bool_expr", body, str(want), "lower", d,
                   f"{assign}; {e} = {want}")


def f_truth_table(rng, d):
    nvars = 3 if d < 4 else 4
    names = [chr(ord("A") + i) for i in range(nvars)]
    e = _bool_tree(rng, names, 1 + d // 2)
    count = 0
    for bits in range(2 ** nvars):
        vals = {names[i]: bool(bits >> i & 1) for i in range(nvars)}
        if _bool_ev(e, vals):
            count += 1
    body = (f"How many of the 2^{nvars} possible True/False assignments make this "
            f"boolean expression True? (NOT binds to the letter after it, XOR is "
            f"exclusive-or.)\n{_bool_render(e)}\nGive the count as a number.")
    return mk_text("truth_table", body, str(count), "int", d,
                   f"{e} -> {count}")


def f_math_exec(rng, d):
    """Math routed through the executor: the model must write a python block
    whose evaluation computes the answer. This is how a 1.7B becomes numerate
    -- it learns to reach for the tool rather than doing arithmetic in weights
    (whitepaper Ch. 4.2: precision is a service, not a learned skill)."""
    ops = rng.choice([["+", "-"], ["*", "//"], ["+", "*", "-"]])
    n = 2 + min(d, 4)
    val = rng.randint(2, 9 + d * 9)
    expr = str(val)
    for _ in range(n):
        op = rng.choice(ops)
        b = rng.randint(2, 9 + d * 6) if op != "//" else rng.randint(2, 6)
        if op == "+":
            val += b
        elif op == "-":
            val -= b
        elif op == "*":
            val *= b
        else:
            val //= b
        expr = f"({expr} {op} {b})"
    ref = (f"<tool>{{\"name\": \"run_python\", \"args\": {{\"code\": \"print({expr})\"}}}}</tool>\n"
           f"<answer>{val}</answer>")
    body = (f"Compute: {expr}. Use the run_python tool to do the arithmetic, "
            f"then report the result as <answer>{val}</answer>.")
    return mk_expr("math_exec", f"result", val, body, d, ref)


def f_dataframe(rng, d):
    """pandas-style data wrangling: the model writes a function that filters /
    groups / aggregates a table, and the sandbox verifies the result. This is
    the "data analyst" skill -- teachable, verifiable, and very common in real
    agent workflows."""
    n = 4 + d * 4
    names = [f"p{i}" for i in range(1, n + 1)]
    ages = [rng.randint(18, 70) for _ in range(n)]
    cities = [rng.choice(["NYC", "LA", "SF", "BOS", "CHI"]) for _ in range(n)]
    rows = [{"name": nm, "age": ag, "city": ct}
            for nm, ag, ct in zip(names, ages, cities)]
    kind = rng.choice(["filter", "group", "sum"])
    if kind == "filter":
        threshold = rng.randint(25, 60)
        want = [r["name"] for r in rows if r["age"] >= threshold]
        body = (f"def filter_by_age(rows, threshold={threshold}) -> list[str]:\n"
                f"    # rows is a list of dicts like {rows[:2]}...\n"
                f"    # return the names of people aged at least {threshold}, in order.\n"
                f"    # Example: filter_by_age([{rows[0]}], {threshold}) == {want[:2]}")
        ref = (f"def filter_by_age(rows, threshold):\n"
               f"    return [r['name'] for r in rows if r['age'] >= threshold]")
        tests = [((rows, threshold), want), (([{"name": "a", "age": 30, "city": "NYC"}], 25), ["a"])]
    elif kind == "group":
        want = {}
        for r in rows:
            want.setdefault(r["city"], []).append(r["name"])
        body = (f"def group_by_city(rows) -> dict:\n"
                f"    # rows is a list of dicts like {rows[:2]}...\n"
                f"    # return a dict mapping each city to the list of names there, "
                f"in order of first appearance.\n"
                f"    # Example: group_by_city([{rows[0]}]) == {{'{rows[0]['city']}': ['{rows[0]['name']}']}}")
        ref = (f"def group_by_city(rows):\n"
               f"    out = {{}}\n"
               f"    for r in rows: out.setdefault(r['city'], []).append(r['name'])\n"
               f"    return out")
        tests = [((rows,), want), (([{"name": "a", "age": 30, "city": "NYC"}],), {"NYC": ["a"]})]
    else:
        col = rng.choice(["age"])
        want = sum(r[col] for r in rows)
        body = (f"def total_{col}(rows) -> int:\n"
                f"    # rows is a list of dicts like {rows[:2]}...\n"
                f"    # return the sum of the '{col}' column.\n"
                f"    # Example: total_{col}([{rows[0]}]) == {rows[0][col]}")
        ref = (f"def total_{col}(rows):\n"
               f"    return sum(r['{col}'] for r in rows)")
        tests = [((rows,), want), (([{"name": "a", "age": 30, "city": "NYC"}],), 30)]
    return mk_code("dataframe", f"total_{col}" if kind == "sum" else
                   ("filter_by_age" if kind == "filter" else "group_by_city"),
                   body, tests, d, ref)


def f_file_ops(rng, d):
    """File-system ops: read a file in the sandbox, transform it, print the
    result. Teaches real file I/O (the CLI-assistant skill)."""
    n_lines = 4 + d * 3
    lines = []
    ips = []
    for _ in range(n_lines):
        ip = f"10.0.{rng.randint(0,255)}.{rng.randint(1,254)}"
        ips.append(ip)
        status = rng.choice([200, 200, 200, 404, 500])
        lines.append(f'{ip} - - [12/Nov/2026:10:{rng.randint(10,59)}:00] "{rng.choice(["GET", "POST"])} /path HTTP/1.1" {status}')
    content = "\n".join(lines) + "\n"
    kind = rng.choice(["unique_ips", "count_500s"])
    if kind == "unique_ips":
        want = "\n".join(sorted(set(ips)))
        body = (f"File input.txt contains {n_lines} log lines like:\n"
                f"{lines[0]}\n\nWrite a python script that reads input.txt and prints "
                f"the unique client IPs, one per line, sorted.")
        ref = (f"ips = sorted(set(line.split()[0] for line in open('input.txt')))\n"
               f"print('\\n'.join(ips))")
    else:
        want = str(sum(1 for l in lines if l.endswith(" 500")))
        body = (f"File input.txt contains {n_lines} log lines like:\n"
                f"{lines[0]}\n\nWrite a python script that reads input.txt and prints "
                f"the number of lines with status 500.")
        ref = (f"print(sum(1 for line in open('input.txt') if line.strip().endswith(' 500')))")
    return {
        "family": "file_ops", "domain": "code", "difficulty": d,
        "prompt": body + "\n\nReply with a single ```python code block, then <answer>DONE</answer>.",
        "kind": "script",
        "spec": {"kind": "script", "files": {"input.txt": content},
                  "expected_stdout": want},
        "reference": ref,
        "answer": want,
    }


# key terms per family for the retrieval-qa verifier (the playbook's core
# strategy word -- the answer must contain it to prove the playbook was used)
PLAYBOOK_KEYS = {
    "balanced": "stack",
    "dedupe": "first",
    "reverse_string": "reverse",
    "is_palindrome": "same",
    "sum_ints": "sum",
    "count_occurrences": "count",
    "second_largest": "distinct",
    "max_subarray": "contiguous",
    "gcd_lcm": "gcd",
    "popcount": "1-bit",
    "matmul2": "matrix",
    "rle": "run",
    "caesar": "shift",
    "flatten": "flat",
    "word_count": "count",
    "arith_chain": "precedence",
    "fraction_ops": "fraction",
    "modular_pow": "mod",
    "linear_solve": "solve",
    "base_convert": "base",
    "seq_nth": "term",
    "perm_order": "arrangement",
    "bool_expr": "boolean",
    "truth_table": "assignments",
    "closure": "transitive",
    "math_exec": "python",
    "dataframe": "rows",
    "file_ops": "input.txt",
}


def f_retrieval_qa(rng, d):
    """Retrieval-augmented Q&A: ask about a playbook; the model must emit a
    retrieve call, read the playbook, and answer with its key term. Teaches
    'look it up before answering' -- the grounded-memory skill."""
    fam = rng.choice(list(PLAYBOOK_KEYS.keys()))
    key = PLAYBOOK_KEYS[fam]
    body = (f"According to the local playbooks, what is the core strategy for "
            f"solving {fam} tasks? Use the retrieve tool to look it up, then "
            f"answer in one sentence. Your answer must contain the word "
            f"'{key}'.")
    return mk_text("retrieval_qa", body, key, "contains", d,
                   f"playbook[{fam}] key={key}", domain="logic")


def f_closure(rng, d):
    n = 4 + min(d, 3)
    names = [f"N{i}" for i in range(1, n + 1)]
    pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    rng.shuffle(pairs)
    edges = []
    reach = [[False] * n for _ in range(n)]
    def add(i, j):
        edges.append((names[i], names[j]))
        reach[i][j] = True
        for a in range(n):
            for b in range(n):
                if reach[a][i] and reach[j][b]:
                    reach[a][b] = True
    for i, j in pairs:
        if not reach[i][j] and not reach[j][i] and len(edges) < 2 + d:
            add(i, j)
    if len(edges) < 2:
        return None
    i, j = rng.randrange(n), rng.randrange(n)
    while i == j:
        j = (j + 1) % n
    want = "yes" if reach[i][j] else ("no" if reach[j][i] else "unknown")
    facts = "; ".join(f"{a} > {b}" for a, b in edges)
    body = (f"Facts: {facts}. 'Greater-than' is transitive (if A > B and B > C then A > C) "
            f"and nothing else is true beyond what follows from the facts. Is {names[i]} > {names[j]}? "
            f"Answer yes, no, or unknown (unknown = not determined by the facts).")
    return mk_text("closure", body, want, "lower", d, f"facts={edges} q={i},{j} -> {want}")


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

FAMILIES = {
    # code
    "reverse_string": f_reverse_string,
    "is_palindrome": f_is_palindrome,
    "sum_ints": f_sum_ints,
    "count_occurrences": f_count_occurrences,
    "dedupe": f_dedupe,
    "second_largest": f_second_largest,
    "max_subarray": f_max_subarray,
    "gcd_lcm": f_gcd_lcm,
    "popcount": f_popcount,
    "matmul2": f_matmul2,
    "balanced": f_balanced,
    "rle": f_rle,
    "caesar": f_caesar,
    "flatten": f_flatten,
    "word_count": f_word_count,
    # math
    "arith_chain": f_arith_chain,
    "fraction_ops": f_fraction_ops,
    "modular_pow": f_modular_pow,
    "linear_solve": f_linear_solve,
    "base_convert": f_base_convert,
    "seq_nth": f_seq_nth,
    # new: tool-augmented workflows
    "math_exec": f_math_exec,
    "dataframe": f_dataframe,
    "file_ops": f_file_ops,
    "retrieval_qa": f_retrieval_qa,
    # logic
    "perm_order": f_perm_order,
    "bool_expr": f_bool_expr,
    "truth_table": f_truth_table,
    "closure": f_closure,
}

CODE_FAMILIES = [n for n, f in FAMILIES.items()
                 if f.__name__.startswith("f_") and "mk_code" in f.__code__.co_names]
TEXT_FAMILIES = [n for n in FAMILIES if n not in CODE_FAMILIES]


def generate(family, difficulty, seed=None):
    """Generate one task; returns None if the family rejects this draw."""
    rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
    for attempt in range(8):
        t = FAMILIES[family](rng, difficulty)
        if t is not None:
            t["id"] = f"{family}~d{difficulty}~{rng.randrange(1 << 30):08x}"
            return t
    return None
