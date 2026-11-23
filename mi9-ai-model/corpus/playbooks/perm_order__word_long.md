PLAYBOOK [perm_order] shape=word:long (n=2 verified traces)
Strategy: solve any perm_order task of this shape the same way.
Example prompt: 5 people (P1, P2, P3, P4, P5) stand in a line, one per position. Clues:
- P2 stands immediately after P4.
- P5 is NOT adjacent to P2.
- Exactly one person stands between P1 and P5.
- P1 is somewhere after P5.
The clues allow exactly one arrangement. Who is at position 5 (1-indexed)? Answer with just
Example answer: ```python
# Define possible positions for each person
positions = ['P1', 'P2', 'P3', 'P4', 'P5']

# Generate all permutations
from itertools import permutations

# Check the clues
valid_permutations = []

for perm in permutations(positions):
    # Clue 1: P2 stands immediately after P4
    if perm.index('P4') + 1 == perm.index('P2'):
        # Clue 2: P5 is NOT adjacent to P2
        if not (perm.index('P5') in [perm.index('P2') - 1, perm.index('P2') + 1]):
            # Clue 3: Exactly one person stands between P1 and P5
            if abs(perm.index('P1') - perm.index('P5')) == 2:
          
