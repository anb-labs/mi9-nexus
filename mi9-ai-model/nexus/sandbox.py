"""Verifier stack: sandboxed Python executor.

Whitepaper Ch. 3.10 / 4.2: "precision is a service, not a learned skill". The
executor runs candidate code with:
  - no network (unshare -rn user namespace, kernel.unprivileged_userns_clone=1)
  - CPU time limit (RLIMIT_CPU)
  - memory limit (RLIMIT_AS)
  - single-use tmpdir workspace, nothing shared with the host

All growth-loop rewards and online code checks go through run_code(); nothing
is ever trusted on the model's word alone.
"""
import json
import os
import resource
import shutil
import subprocess
import tempfile

from . import config

HARNESS = r'''
import json, sys, io, traceback
sys.setrecursionlimit(20000)
spec = json.load(open("spec.json"))          # {"kind": "tests", ...}
try:
    exec(compile(open("cand.py").read(), "cand.py", "exec"), {"__name__": "cand"})
    ns = {}
    exec(compile(open("cand.py").read(), "cand.py", "exec"), ns)
except Exception:
    print(json.dumps({"ok": False, "error": "import: " + traceback.format_exc(limit=3)[-400:]}))
    raise SystemExit
failures = []
tests = spec["tests"]
for i, t in enumerate(tests):
    try:
        args = t["args"]
        kwargs = t.get("kwargs", {})
        got = ns[spec["function"]](*args, **kwargs)
        exp = t["expected"]
        import json as _json
        ok = _json.dumps(got, sort_keys=True, default=str) == _json.dumps(exp, sort_keys=True, default=str)
        if not ok:
            failures.append({"i": i, "got": repr(got)[:200], "expected": repr(exp)[:200]})
    except Exception:
        failures.append({"i": i, "error": traceback.format_exc(limit=2)[-300:]})
res = {"ok": not failures, "failures": failures[:3], "ntests": len(tests)}
print(json.dumps(res))
'''


def _limit(mbps_mb):
    def apply():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (config.SANDBOX_CPU_SECONDS,
                                                  config.SANDBOX_CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_AS, (mbps_mb << 20, mbps_mb << 20))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def run_code(candidate_source, spec, timeout=None):
    """Run candidate code against a spec.

    spec kinds:
      {"kind": "tests", "function": name, "tests": [{"args": [...], "expected": ...}, ...]}
    Returns {"ok": bool, ...diagnostics...}.
    """
    if spec.get("kind") != "tests":
        raise ValueError("unsupported spec kind")
    timeout = timeout or (config.SANDBOX_CPU_SECONDS + 5)
    tmp = tempfile.mkdtemp(prefix="nexus_sbx_")
    try:
        (tmp + "/cand.py",)
        with open(tmp + "/cand.py", "w") as f:
            f.write(candidate_source)
        with open(tmp + "/spec.json", "w") as f:
            json.dump(spec, f)
        with open(tmp + "/harness.py", "w") as f:
            f.write(HARNESS)
        cmd = ["python3", "-I", "harness.py"]
        if config.SANDBOX_NET is False and shutil.which("unshare"):
            cmd = ["unshare", "-rn"] + cmd
        p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout,
                           preexec_fn=_limit(config.SANDBOX_MEM_MB))
        if p.returncode != 0:
            return {"ok": False, "error": ("timeout/killed" if p.returncode < 0
                                           else p.stderr.strip()[-300:] or f"rc={p.returncode}")}
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            return {"ok": False, "error": "unparseable harness output: " + p.stdout[-200:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_expr_tests(code, function, tests):
    """Convenience wrapper: tests as [(args, expected), ...]."""
    return run_code(code, {"kind": "tests", "function": function,
                           "tests": [{"args": list(a), "expected": e} for a, e in tests]})


_SCRIPT_HARNESS = r'''
import json, sys, io, traceback
buf = io.StringIO()
sys.stdout = buf
err = None
try:
    exec(compile(open("cand.py").read(), "cand.py", "exec"), {"__name__": "__main__"})
except Exception:
    err = traceback.format_exc(limit=3)[-500:]
sys.stdout = sys.__stdout__
print(json.dumps({"ok": err is None, "error": err, "stdout": buf.getvalue()[:2000]}))
'''


def run_script(candidate_source, timeout=None, files=None, expected_stdout=None):
    """Run a standalone script in the sandbox and capture its stdout.

    This is the agent's calculator: `run_python` tool calls land here, and the
    printed output goes back to the model so it can use the result. Without
    this the tool is a black hole -- ok=True but no answer comes back.

    `files`: {filename: content} written into the sandbox tmpdir before the
    script runs (for file-ops tasks). `expected_stdout`: if given, the
    verdict compares the captured stdout to it.
    """
    if timeout is None:
        timeout = config.SANDBOX_CPU_SECONDS + 5
    tmp = tempfile.mkdtemp(prefix="nexus_sbx_")
    try:
        with open(tmp + "/cand.py", "w") as f:
            f.write(candidate_source)
        for name, content in (files or {}).items():
            with open(tmp + "/" + name, "w") as f:
                f.write(content)
        with open(tmp + "/harness.py", "w") as f:
            f.write(_SCRIPT_HARNESS)
        cmd = ["python3", "-I", "harness.py"]
        if config.SANDBOX_NET is False and shutil.which("unshare"):
            cmd = ["unshare", "-rn"] + cmd
        p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout,
                           preexec_fn=_limit(config.SANDBOX_MEM_MB))
        if p.returncode != 0:
            return {"ok": False, "error": ("timeout/killed" if p.returncode < 0
                                            else p.stderr.strip()[-300:] or f"rc={p.returncode}")}
        try:
            r = json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            return {"ok": False, "error": "unparseable: " + p.stdout[-200:]}
        if expected_stdout is not None and r.get("ok"):
            r["ok"] = r.get("stdout", "").strip() == expected_stdout.strip()
            if not r["ok"]:
                r["error"] = f"stdout mismatch: got {r.get('stdout','')[:120]!r}"
        return r
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_script_dir(candidate_source, workdir, timeout=None):
    """Run a script in a PERSISTENT per-chat directory.

    Same isolation as run_script (netns, rlimits), but the workdir is reused
    across calls and NOT deleted, so files written in one turn are visible in
    the next turn of the SAME chat — while different chats get different dirs
    (isolation between conversations).
    """
    if timeout is None:
        timeout = config.SANDBOX_CPU_SECONDS + 5
    os.makedirs(workdir, exist_ok=True)
    with open(workdir + "/cand.py", "w") as f:
        f.write(candidate_source)
    with open(workdir + "/harness.py", "w") as f:
        f.write(_SCRIPT_HARNESS)
    cmd = ["python3", "-I", "harness.py"]
    if config.SANDBOX_NET is False and shutil.which("unshare"):
        cmd = ["unshare", "-rn"] + cmd
    try:
        p = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout,
                           preexec_fn=_limit(config.SANDBOX_MEM_MB))
        if p.returncode != 0:
            return {"ok": False, "error": ("timeout/killed" if p.returncode < 0
                                            else p.stderr.strip()[-300:] or f"rc={p.returncode}")}
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            return {"ok": False, "error": "unparseable: " + p.stdout[-200:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}


_EXPR_HARNESS = r'''
import json, sys, io, traceback
spec = json.load(open("spec.json"))          # {"kind": "expr", "expr": "...", "expected": ...}
try:
    exec(compile(open("cand.py").read(), "cand.py", "exec"), {"__name__": "cand"})
    ns = {}
    exec(compile(open("cand.py").read(), "cand.py", "exec"), ns)
except Exception:
    print(json.dumps({"ok": False, "error": "import: " + traceback.format_exc(limit=3)[-400:]}))
    raise SystemExit
expr = spec["expr"]
try:
    got = eval(expr, {"__builtins__": {}}, ns)
except Exception:
    print(json.dumps({"ok": False, "error": "eval: " + traceback.format_exc(limit=2)[-300:]}))
    raise SystemExit
import json as _json
ok = _json.dumps(got, sort_keys=True, default=str) == _json.dumps(spec["expected"], sort_keys=True, default=str)
print(json.dumps({"ok": ok, "got": repr(got)[:200], "expected": repr(spec["expected"])[:200]}))
'''


def run_expr(candidate_source, expr, expected, timeout=None):
    """Run a candidate module, then evaluate `expr` in its namespace and
    compare to `expected`. Used for the math-via-executor family: the model
    emits a python block; the sandbox computes and checks -- teaching the
    model to route arithmetic to the executor rather than doing it in weights."""
    if timeout is None:
        timeout = config.SANDBOX_CPU_SECONDS + 5
    tmp = tempfile.mkdtemp(prefix="nexus_sbx_")
    try:
        with open(tmp + "/cand.py", "w") as f:
            f.write(candidate_source)
        with open(tmp + "/spec.json", "w") as f:
            json.dump({"kind": "expr", "expr": expr, "expected": expected}, f)
        with open(tmp + "/harness.py", "w") as f:
            f.write(_EXPR_HARNESS)
        cmd = ["python3", "-I", "harness.py"]
        if config.SANDBOX_NET is False and shutil.which("unshare"):
            cmd = ["unshare", "-rn"] + cmd
        p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout,
                           preexec_fn=_limit(config.SANDBOX_MEM_MB))
        if p.returncode != 0:
            return {"ok": False, "error": ("timeout/killed" if p.returncode < 0
                                            else p.stderr.strip()[-300:] or f"rc={p.returncode}")}
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            return {"ok": False, "error": "unparseable: " + p.stdout[-200:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
