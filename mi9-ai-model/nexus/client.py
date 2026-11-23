"""Thin OpenAI-compatible client for llama-server (llama.cpp)."""
import json
import urllib.request
import urllib.error

from . import config


def chat(messages, model=None, temperature=0.7, max_tokens=1024, stop=None,
         timeout=600, extra_body=None, think=False):
    body = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if not think:
        # disable the thinking channel properly (Qwen3 template) instead of
        # relying on the /no_think soft switch
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if model:
        body["model"] = model
    if stop:
        body["stop"] = stop
    if extra_body:
        body.update(extra_body)
    req = urllib.request.Request(
        config.SERVER_URL + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        # server rejected the request (e.g., context overflow) — return the
        # error as text so the collector can trim and continue instead of
        # dying mid-cycle
        return {"text": f"[server error {e.code}]", "reasoning": "", "tokens": 0}
    except Exception as e:
        # connection dropped (server restart), timeout, reset — the collector
        # must survive these; one bad request must not kill a whole cycle
        return {"text": f"[connection error: {type(e).__name__}]",
                "reasoning": "", "tokens": 0}
    msg = out["choices"][0]["message"]
    text = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    if not text.strip() and reasoning.strip():
        # some template states deliver the whole answer via the reasoning
        # channel; use it rather than losing the response
        text = reasoning
    usage = out.get("usage", {})
    return {"text": text, "reasoning": reasoning,
            "tokens": usage.get("completion_tokens", 0)}


def health(timeout=5):
    try:
        with urllib.request.urlopen(config.SERVER_URL + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def strip_thinking(text):
    """Remove <think>...</think> blocks (Qwen3 thinking mode) from content text."""
    if "<think>" not in text:
        return text
    out, seen_open = [], False
    for part in text.split("<think>"):
        if not seen_open:
            out.append(part)
            seen_open = True
        else:
            head, sep, tail = part.partition("</think>")
            if sep:
                out.append(tail)
            seen_open = False
    return "".join(out)
