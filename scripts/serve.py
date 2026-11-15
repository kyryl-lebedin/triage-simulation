"""Serve the repo on http://localhost:8765 with caching switched off, plus what a real run needs.

    python3 scripts/serve.py

Static files work without anything else. The endpoints below are what "New scenario" uses to run synthetic
participants on a real model. Every model call is the `claude` command in print mode (`claude -p`), so it
uses the Claude subscription this machine is logged in to. No API key is read or needed.

    GET  /api/status        is `claude` reachable from here, and if not, why
    POST /api/participant   one participant reacting to one version, then the follow-up questions
    POST /api/estimate      a typical percentage split for one participant variable

STANDIN_FAKE=1 answers at random without calling a model, to test the page end to end for free.
"""
import concurrent.futures, functools, http.server, json, os, pathlib, random, shutil, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAKE = os.environ.get("STANDIN_FAKE") == "1"
CLAUDE = shutil.which("claude")
MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
# the calls run from their own empty folder, so no project instructions reach a participant
WORK = pathlib.Path.home() / ".cache" / "standin-runs"
SESSIONS = pathlib.Path.home() / ".claude" / "projects" / ("-" + str(WORK).strip("/").replace("/", "-").replace(".", "-"))


class Limit(Exception):
    pass


def status():
    if FAKE:
        return {"ready": True, "fake": True}
    if not CLAUDE:
        return {"ready": False, "why": "The claude command was not found. Install Claude Code and log in, then start the server again."}
    return {"ready": True, "fake": False}


def ask(cfg, prompt, schema=None, system=None, fork=None):
    """One `claude -p` call. A pure model call: no tools, no settings, no hooks, no MCP, no CLAUDE.md.
    `system` starts a new session; `fork` resumes an earlier session as a separate branch.
    Returns (parsed JSON or text, session id)."""
    if cfg.get("model") not in MODELS:
        raise ValueError(f"Unknown model: {cfg.get('model')}")
    cmd = [CLAUDE, "-p", prompt, "--model", cfg["model"], "--output-format", "json",
           "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands"]
    if cfg.get("effort") in EFFORTS:
        cmd += ["--effort", cfg["effort"]]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    if fork:
        cmd += ["--resume", fork, "--fork-session"]
    elif system:
        cmd += ["--system-prompt", system]
    # the subscription login is used: an API key in the environment would switch the call to API billing
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    WORK.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(cmd, cwd=WORK, env=env, capture_output=True, text=True, timeout=300)
    try:
        out = json.loads(done.stdout)
    except ValueError:
        raise RuntimeError((done.stderr or done.stdout or "claude returned nothing").strip()[:300])
    if out.get("is_error"):
        msg = str(out.get("result") or out.get("subtype") or "claude reported an error")
        raise (Limit if "limit" in msg.lower() else RuntimeError)(msg[:300])
    data = out.get("structured_output")
    if schema and data is None:
        data = json.loads(out.get("result") or "{}")
    return (data if schema else out.get("result", "")), out.get("session_id")


def forget(session_ids):
    """Delete the sessions a participant used, so runs do not pile up in the session list."""
    for sid in session_ids:
        f = SESSIONS / f"{sid}.jsonl"
        if sid and f.is_file() and f.parent.name.endswith("standin-runs"):
            f.unlink()


def participant(body):
    """Stage 1: the participant reacts. Stage 2: each follow-up resumes that chat as its own fork, in parallel."""
    qs = body.get("questions") or []
    if FAKE:
        ids = (((body.get("schema1") or {}).get("properties") or {}).get("actions") or {}).get("items", {}).get("enum", [])
        actions = [a for a in ids if random.random() < .35]
        answers = []
        for q in qs:
            for a in (actions if q.get("each") else [None]):
                tag = random.choice(["Test tag one", "Test tag two", "Test tag three"])
                answers.append({"question": q["id"], "action": a, "full": f"Test answer ({tag.lower()}), no model was called.", "short": tag})
        return {"actions": actions, "answers": answers}

    cfg, used = body["llm"], []
    try:
        first, sid = ask(cfg, body["first"], body.get("schema1"), system=body["system"])
        used.append(sid)
        actions = (first or {}).get("actions", []) if body.get("schema1") else []

        def branch(q):
            if q.get("each") and not actions:
                return []
            data, fid = ask(cfg, body["audit"] + "\n\n" + q["message"], q["schema"], fork=sid)
            used.append(fid)
            return (data or {}).get("answers", [])

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            answers = [a for part in pool.map(branch, qs) for a in part]
        return {"actions": actions, "answers": answers}
    finally:
        forget(used)


def estimate(body):
    options = [str(o) for o in body.get("options") or []]
    if FAKE:
        return {"pcts": [round(100 / len(options))] * len(options)}
    schema = {"type": "object", "additionalProperties": False, "required": ["pcts"],
              "properties": {"pcts": {"type": "array", "items": {"type": "integer"}}}}
    prompt = (f"An audience is being described for a study: {body.get('about', '')}\n\n"
              f"Estimate the typical split of this audience by \"{body.get('variable', '')}\" across these options, in this order:\n"
              + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(options))
              + f"\n\nGive one whole-number percentage per option, {len(options)} numbers that sum to 100.")
    data, sid = ask(body["llm"], prompt, schema, system="You estimate audience statistics. Answer with numbers only.")
    forget([sid])
    return {"pcts": (data or {}).get("pcts", [])}


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/status":
            return self.reply(200, status())
        super().do_GET()

    def do_POST(self):
        route = {"/api/participant": participant, "/api/estimate": estimate}.get(self.path.split("?")[0])
        if not route:
            return self.reply(404, {"error": "No such endpoint."})
        st = status()
        if not st["ready"]:
            return self.reply(503, {"error": st["why"]})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            return self.reply(200, route(body))
        except Limit as e:
            return self.reply(429, {"error": f"Usage limit: {e}"})
        except subprocess.TimeoutExpired:
            return self.reply(504, {"error": "claude took longer than five minutes on one call."})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):  # keep the terminal quiet for static files
        if "/api/" in str(args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print(f"http://localhost:8765  ({'test mode, no model is called' if FAKE else status().get('why') or 'real runs use claude -p on your subscription'})")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8765), functools.partial(Handler, directory=str(ROOT))).serve_forever()
