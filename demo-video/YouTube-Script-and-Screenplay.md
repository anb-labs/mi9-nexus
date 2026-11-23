# Mi9-Nexus — Demo Video Script

**Length:** ~3.5 minutes
**Tone:** humble, plain-spoken. No hype. Just "here's a thing I made and how."
**Format:** screen recording + voiceover in post.

---

## BEFORE YOU RECORD

Get three things running (from `~/Mi9`):

```sh
# 1. model
cd ~/Mi9/mi9-ai-model && nexus/serve

# 2. tools
cd ~/Mi9/mi9-ai-model && .venv/bin/python -m nexus.toolserver

# 3. web UI  -> open http://localhost:3000
cd ~/Mi9/nexus-web && node server.js
```

Do one warm-up chat first so the model is loaded. Bump your browser font size so the chat is readable at 1080p. Turn on Do Not Disturb.

---

## THE SCRIPT

### Intro (0:00–0:20)

**SCREEN:** The Mi9·Nexus chat screen, open and idle.

**VO:**
> I made a small AI that runs on my laptop — no GPU, no internet needed. It's about 1.8 gigabytes. I want to show you what it does and how I built it.

---

### What it is (0:20–1:15)

**SCREEN:** Same chat window.

**VO:**
> Under the hood it's a 1.7-billion-parameter open model. But the model on its own isn't the interesting part. What I added is a set of tools it can use. When you ask it something, it can run code in a sandbox, search the web, and read documents — and then it answers based on what those tools actually returned, not just a guess.

**SCREEN — Demo 1.** Type slowly, then let the whole agent loop play on screen:
> `What is 17 times 23? Verify with code.`

The model shows a `run_python` tool card, runs it, returns `391`.

**VO:**
> So I ask it for seventeen times twenty-three, and instead of answering from memory, it writes code, runs it, and gives me the result the sandbox actually produced.

**SCREEN — Demo 2.** New chat. Type:
> `What is the latest stable Python version right now?`

It runs `web_search` and answers with a citation.

**VO:**
> It can search the live web too, and it shows where the answer came from.

**SCREEN:** Back to the full window.

**VO:**
> That's basically it. A small model, plus tools, plus it checks its own work.

---

### How I built it (1:15–2:35)

**SCREEN:** Cut to a terminal in `~/Mi9/mi9-ai-model`. Show the layout:
```sh
ls
```

Then show the training data:
```sh
wc -l data/replay.jsonl
```

**VO:**
> I built it on top of the idea that reasoning and knowledge are separate things. The model's job is to think; its knowledge can live on disk and be looked up; and anything that needs to be *correct* gets checked by actually running it. If that's true, you don't need a giant model — just a decent reasoner and good tools around it.

**SCREEN:** Show a couple of past eval reports (from `reports/`) so viewers see real numbers:
```sh
ls reports/
```

**VO:**
> Most of the work was getting the harness right, not the model. Honestly, I broke things a lot along the way. At one point my code ability dropped from 73% to 22% just because I trained it on the wrong format. And I was quietly hurting the model by compressing it too much — switching to a slightly bigger file took it from 70% to 86% on my tests.

**SCREEN:** If you have it, show the two reports side by side — the healthy one and the collapsed one — for about 3 seconds. Then move on.

**VO:**
> The thing I keep coming back to: the model itself is close to its limit for its size. The gains came from the harness around it — letting it try a few answers and keep the one that checks out, and giving it real tools. That took it from about 58% to 83% on code and text tasks.

---

### What I want to do next (2:35–3:15)

**SCREEN:** Open `roadmap.md` in your editor. Leave it visible.

**VO:**
> What I actually want to do next is keep making models smaller, not bigger — but more useful. A small model that can think, use tools, and remember things is often more practical than a giant one. That's the direction I want to take this.

**SCREEN:** If you have it, a 2-second cutaway of the app on your phone running a tool call. (Optional — skip if it's a hassle.)

---

### Outro (3:15–3:30)

**SCREEN:** Back to the chat screen, calm.

**VO:**
> That's Mi9-Nexus. It's a work in progress, but it runs on a five-year-old laptop, and I think the approach is worth sharing. Code's in the description if you want to look. Thanks for watching.

**SCREEN:** End card with repo link. Fade.

---

## DEMO PROMPTS (copy-paste)

| Prompt | Shows |
|---|---|
| `What is 17 times 23? Verify with code.` | sandbox runs Python → 391 |
| `What is the latest stable Python version right now?` | web search + citation |

---

## TIPS

- Record voiceover first, then record the screen while listening to it — much easier than narrating live.
- Cut any pause longer than ~1 second where nothing is happening.
- Burn in captions (most people watch muted).
- Keep the two failure stats brief — they're there for honesty, not to dwell on.

---

## TITLES / THUMBNAIL

- Title: "I made a 1.8 GB AI that runs on my laptop"
- Thumbnail: laptop or the app on a phone + text "1.8 GB · No GPU"
- Description: one line — what it is, code link, whitepaper link.