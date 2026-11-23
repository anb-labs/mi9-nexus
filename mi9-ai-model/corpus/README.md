# Grounded memory corpus (the 0.4% doctrine)

Drop any text/markdown/code files you want the assistant to know about here,
then run: python3 -m nexus.memory index

The assistant retrieves from this directory, cites files, and never claims
facts from outside it without the "model-judgment" label.
