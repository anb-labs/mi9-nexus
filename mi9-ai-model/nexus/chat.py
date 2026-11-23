"""Interactive runtime: reasoning core + tool belt + verifier + grounded memory.

The model contributes judgment and decomposition; the executor contributes
precision; retrieval contributes facts (Ch. 4.2). Every answer is labeled by
evidence class - executor-verified, retrieval-grounded, or model judgment -
per Ch. 6.3 (no silent opinion laundering).
"""
import argparse
import json
import re
import sys

from . import client, memory, sandbox, config, tasks
from .agentic import parse_tool_call

SYSTEM = """You are NEXUS-Micro, a local reasoning assistant on a small laptop.

You have these tools, used by emitting ONE tool call as the last thing in your reply:

<tool>{"name": "retrieve", "args": {"query": "..."}}</tool>
<tool>{"name": "run_python", "args": {"code": "print(2+2)"}}</tool>
<tool>{"name": "web_search", "args": {"query": "..."}}</tool>
<tool>{"name": "web_fetch", "args": {"url": "..."}}</tool>
<tool>{"name": "office_read", "args": {"path": "..."}}</tool>

Tool rules:
- retrieve: search your local corpus for facts AND for proven solution strategies
  (playbooks). Use it for any factual claim, name, date, API, number about the
  world, AND for any task you've seen before -- retrieve the playbook for its
  family and follow it. Cite the file names you used.
- run_python: sandboxed Python (NO network, no file access outside /tmp).
  Use it for ALL arithmetic and any logic you can express as code. Never do
  arithmetic in your head.
- web_search: search the live web for up-to-date or world knowledge.
- web_fetch: read a page's text (use after web_search).
- office_read: read a local Office document (docx/pptx/xlsx) by path.

After tool results appear, continue. When you are done, give the final answer
wrapped in <answer>...</answer>, then a final line labeling it:
EVIDENCE: executor-verified | retrieval-grounded | model-judgment
"""


def tool_run(name, args):
    if name == "retrieve":
        hits = memory.query(args.get("query", ""), k=5)
        return {"hits": [{"path": h["path"], "text": h["text"][:600]} for h in hits]}
    if name == "run_python":
        r = sandbox.run_script(args.get("code", ""))
        out = {"ok": r.get("ok", False), "error": r.get("error"),
               "stdout": r.get("stdout", "")}
        return out
    if name == "web_search":
        from . import web
        return {"hits": web.search(args.get("query", ""), limit=5)}
    if name == "web_fetch":
        from . import web
        return {"text": web.fetch(args.get("url", ""), max_chars=3000)}
    if name == "office_read":
        from . import office
        return {"text": office.extract(args.get("path", ""), max_chars=3000)}
    return {"error": f"unknown tool {name}"}


def playbook_hint(question):
    """If the question looks like a known task family, surface its playbook
    from the memory index (schema retrieval -- Ch. 4.3 chunking)."""
    try:
        fams = [f for f in tasks.FAMILIES if f.replace("_", " ") in question.lower()
                or f in question.lower()]
        if not fams:
            return ""
        hits = memory.query(f"PLAYBOOK {fams[0]}", k=1)
        if hits and "PLAYBOOK" in hits[0]["text"]:
            return ("\nRelevant playbook from memory (follow its strategy):\n"
                    + hits[0]["text"][:800])
    except Exception:
        pass
    return ""


TOOL_RE = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.S)


def chat_once(question, history=(), max_rounds=4):
    hint = playbook_hint(question)
    q = question + hint
    msgs = [{"role": "system", "content": SYSTEM}] + list(history) + \
           [{"role": "user", "content": q}]
    tools_used = []
    for _ in range(max_rounds):
        raw = client.chat(msgs, temperature=0.7, max_tokens=1500)
        text = client.strip_thinking(raw["text"])
        m = TOOL_RE.search(text)
        if not m:
            return text, tools_used
        call = parse_tool_call(text)
        if call is None:
            return text, tools_used
        result = tool_run(call.get("name"), call.get("args", {}))
        tools_used.append(call.get("name"))
        msgs = msgs + [{"role": "assistant", "content": text},
                       {"role": "user", "content":
                        f"TOOL RESULT ({call.get('name')}):\n{json.dumps(result, ensure_ascii=False)[:2000]}\n"
                        "Continue."}]
    return text, tools_used


def chat_best_of(question, k=3, history=()):
    """Test-time compute for serving: sample k ReAct trajectories and return the
    first with a non-empty, executor-verified answer, else the majority non-empty
    answer (Snell 2024; Large Language Monkeys 2024)."""
    import collections
    results = []
    for _ in range(max(1, k)):
        text, tools = chat_once(question, history)
        results.append((text, tools))
        answer = text.split("EVIDENCE:")[0].strip()
        if tools and answer and "executor-verified" in text.lower():
            return text, tools, 1  # a verified, non-empty trajectory wins
    answers = [t.split("EVIDENCE:")[0].strip() for t, _ in results
               if t.split("EVIDENCE:")[0].strip()]
    top = collections.Counter(answers).most_common(1)[0][0] if answers else ""
    return top, results[0][1], len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", nargs="*", help="one-shot question")
    ap.add_argument("--best-of", type=int, default=3,
                    help="test-time compute: sample k trajectories, keep the verified answer")
    args = ap.parse_args()
    if not client.health():
        raise SystemExit("llama-server is not up (nexus serve start)")
    if args.ask:
        if args.best_of > 1:
            text, tools, n = chat_best_of(" ".join(args.ask), k=args.best_of)
            print(text)
            print(f"\n[best-of-{n} | tools: {', '.join(tools) if tools else 'none'}]")
        else:
            text, tools = chat_once(" ".join(args.ask))
            print(text)
            if tools:
                print(f"\n[tools: {', '.join(tools)}]")
        return
    history = []
    print("NEXUS-Micro interactive (empty line to quit)")
    while True:
        try:
            q = input("\nyou> ").strip()
        except EOFError:
            break
        if not q:
            break
        text, tools = chat_once(q, history)
        history = (history + [{"role": "user", "content": q},
                              {"role": "assistant", "content": text}])[-8:]
        print("\nnexus> " + text)


if __name__ == "__main__":
    main()
