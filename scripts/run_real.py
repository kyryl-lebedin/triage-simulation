#!/usr/bin/env python3
"""Runs the 111 experiment for real, on a sample of the control set's patients.

Every model call is `claude -p` on the subscription login (no API key), as in scripts/serve.py: no tools, no settings,
no project instructions, nothing saved. What is run is the setup as the platform shows it (data/triage-runs.js): the same
participant prompt, forms, chat prompts, judge instructions, closing messages and follow-up questions.

  one patient x one form     the patient fills the form in (or gives up)        -> the filled form is the record
  one patient x one chat     the chat agent and the patient take turns, each     -> the transcript is the record
                             its own model call; the agent sees only the chat,
                             the patient only its own fact sheet
  the judge                  reads the record alone and names a level 1 to 5
  one patient x one message  a patient the experts put at level 1 to 3 reads the message and chooses what to do
  follow-ups                 each question is its own call, after the action

    python3 scripts/run_real.py --n 60            run (resumes: finished runs are kept in data/control/real_runs.jsonl)
    python3 scripts/run_real.py --group           group the answers into short labels and write data/control/results_real.json
Then scripts/build_platform_runs.py puts the results on the page.
"""
import argparse, collections, concurrent.futures as cf, json, os, pathlib, random, re, shutil, subprocess, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data"
RUNS, OUT, USAGE = D / "control" / "real_runs.jsonl", D / "control" / "results_real.json", D / "control" / "real_usage.json"
CLAUDE = shutil.which("claude")
WORK = pathlib.Path.home() / ".cache" / "standin-runs"
MODEL = {"patient": "claude-haiku-5-5", "chat": "claude-haiku-5-5", "judge": "claude-sonnet-5-5", "group": "claude-sonnet-5-5"}
MAX_Q = 12          # the chat prompts say "at most 12 questions"; the loop stops there even if the agent does not
STOP_AT = 88        # stop starting new runs when the 5-hour limit is this full
lock = threading.Lock()
usage = collections.defaultdict(lambda: collections.Counter())
halt = threading.Event()


class Limit(Exception):
    pass


def ask(role, system, prompt, schema=None, tries=3):
    """One model call. Returns parsed JSON (with a schema) or text."""
    cmd = [CLAUDE, "-p", prompt, "--model", MODEL[role], "--output-format", "json", "--tools", "", "--setting-sources", "",
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence", "--system-prompt", system]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    err = None
    for i in range(tries):
        if halt.is_set(): raise Limit("stopped")
        try:
            done = subprocess.run(cmd, cwd=WORK, env=env, capture_output=True, text=True, timeout=240)
            out = json.loads(done.stdout)
            if out.get("is_error"):
                msg = str(out.get("result") or out.get("subtype") or "error")
                if "limit" in msg.lower(): halt.set(); raise Limit(msg[:200])
                raise RuntimeError(msg[:200])
            u = out.get("usage") or {}
            with lock:
                c = usage[MODEL[role]]
                c["calls"] += 1; c["input"] += u.get("input_tokens", 0); c["cache_write"] += u.get("cache_creation_input_tokens", 0)
                c["cache_read"] += u.get("cache_read_input_tokens", 0); c["output"] += u.get("output_tokens", 0)
                c["cost_micro_usd"] += round((out.get("total_cost_usd") or 0) * 1e6)
            if schema:
                data = out.get("structured_output")
                if data is None: data = json.loads(out.get("result") or "null")
                if not isinstance(data, dict): raise RuntimeError("no structured output")
                return data
            return (out.get("result") or "").strip()
        except Limit:
            raise
        except Exception as e:   # a bad reply or a timeout: try again
            err = e; time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{role}: {err}")


def five_hour():
    try:
        r = subprocess.run([str(pathlib.Path.home() / ".local/bin/cs"), "--json-output", "--no-color"], input="{}", capture_output=True, text=True, timeout=20)
        return float(json.loads(r.stdout)["rate_limits"]["five_hour"]["used_percentage"])
    except Exception:
        return None


# ---------- the setup, read from what the platform shows ----------
def setup():
    t = (D / "triage-runs.js").read_text()
    raw = json.loads(t[t.index("const RAW = ") + 12:t.index(";\n  window.STANDIN_IMPORTS")])
    r = next(x for x in raw if x["id"] == "triage")
    return r


def persona(S, case, label, picks):
    """the participant prompt of the setup, filled in for one patient, plus their own first words and fact sheet"""
    def sub(m):
        k = m.group(1)
        if k == "name": return label.split(",")[0]
        if k == "age": return str(case["real"]["age"])
        v = next((x for x in S["vars"] if x["key"] == k), None)
        if not v: return m.group(0)
        o = v["opts"][picks[S["vars"].index(v)]]
        return o.get("say") or o["name"].lower()
    text = re.sub(r"\{([a-z0-9_]+)\}", sub, S["prompt"])
    d = case["derived"]
    who = "You are answering for yourself." if d["respondent"] == "self" else "You are with the patient and answer for them: they cannot answer for themselves."
    facts = "\n".join(f"- {f['lay']}" for f in d["facts"])
    return (f"{text}\n\n{who}\nYour first words, when asked what is wrong: \"{d['opening']}\"\n"
            f"Your private fact sheet. This is everything you know about the problem:\n{facts}\n\n"
            "You are taking part in a study. Stay in character throughout: answer only as this person would, in their own words.")


# ---------- one run ----------
F_ACTS = ["answer", "own_words", "not_sure", "skip", "give_up"]
C_ACTS = ["reply", "vague", "dont_know", "add_more", "stop"]
M_ACTS = ["go_now", "go_later", "ask_first", "do_nothing"]


def act_lines(S, ids):
    A = {a["id"]: a for a in S["actions"]}
    return "\n".join(f"- {i}: {A[i]['name']}. {A[i].get('desc', '')}" for i in ids)


def clean(t):
    t = t.strip()
    return t[1:-1].strip() if len(t) > 1 and t[0] in "\"\u201c" and t[-1] in "\"\u201d" else t


def follow(sys_p, context, question, about="it"):
    return clean(ask("patient", sys_p, f"{context}\n\nYou are now asked one question about {about}:\n{question}\n\nAnswer in one or two short sentences, in your own words. Reply with the answer only."))


# "What led to that?" is asked about an action. Of the things a patient did, it is asked about the most telling one.
TELLING = ["give_up", "stop", "skip", "not_sure", "vague", "dont_know", "own_words", "add_more", "answer", "reply"]


def why_triage(S, sys_p, ctx, moves):
    A = {a["id"]: a for a in S["actions"]}; m = next((x for x in TELLING if x in moves), None)
    q = next(q["text"] for q in S["questions"] if q["id"] == "why")
    if not m: return follow(sys_p, ctx, q), None
    return follow(sys_p, ctx, q, f"one thing you did while using it, which was: {A[m]['name']} ({A[m].get('desc', '').rstrip('.')})"), m


def why_message(S, sys_p, ctx):
    return follow(sys_p, ctx, next(q["text"] for q in S["questions"] if q["id"] == "why"), "that decision, not about your health problem")


def judge(S, record):
    lv = ask("judge", S["judge"]["text"], f"The record:\n\n{record}", {"type": "object", "properties": {"level": {"type": "integer", "enum": [1, 2, 3, 4, 5]}}, "required": ["level"], "additionalProperties": False})["level"]
    return int(lv)


def run_form(S, sys_p, v):
    text = v["vals"][v["field"]]["text"]
    got = ask("patient", sys_p,
              "You are at home and have opened this online form to find out how urgently you need to be seen. Go through it from the top, as you really would.\n\n"
              f"----- THE FORM -----\n{text}\n----- END OF THE FORM -----\n\n"
              "Give back the form as you leave it: each question you reached, followed by the answer you gave, in the form's own words for the options. "
              "Write (skipped) for a question you left empty. If you give up, end the record at the question where you stopped.\n\n"
              f"Also say which of these you did at least once:\n{act_lines(S, F_ACTS)}",
              {"type": "object", "properties": {"record": {"type": "string"}, "actions": {"type": "array", "items": {"type": "string", "enum": F_ACTS}}},
               "required": ["record", "actions"], "additionalProperties": False})
    moves = [a for a in F_ACTS if a in (got.get("actions") or [])]
    return got.get("record", "").strip(), moves, "give_up" in moves


def run_chat(S, sys_p, v):
    agent = v["vals"][v["field"]]["text"]
    turns, moves, quit_ = [], [], False
    show = lambda me, other: "\n".join(f"{me if w == 'a' else other}: {t}" for w, t in turns)
    for q in range(MAX_Q + 1):
        said = ask("chat", agent, ("The conversation so far:\n" + show("You", "Patient") + "\n\n" if turns else "The patient has just opened the chat.\n\n")
                   + "Write your next message to the patient, and nothing else." + (" You have asked all your questions: reply with exactly [END]." if q == MAX_Q else ""))
        if "[END]" in said or q == MAX_Q: break
        turns.append(("a", said))
        got = ask("patient", sys_p,
                  "You are at home, using an online chat to find out how urgently you need to be seen.\n\n"
                  + ("The chat so far:\n" + show("Assistant", "You") + "\n\n" if len(turns) > 1 else "") +
                  f"The assistant now says:\n{said}\n\nType your reply as you really would, then say which one of these it was:\n{act_lines(S, C_ACTS)}",
                  {"type": "object", "properties": {"say": {"type": "string"}, "action": {"type": "string", "enum": C_ACTS}}, "required": ["say", "action"], "additionalProperties": False})
        moves.append(got["action"])
        if got["action"] == "stop": quit_ = True; break
        turns.append(("p", got.get("say", "").strip()))
    record = "\n".join(f"{'Assistant' if w == 'a' else 'Patient'}: {t}" for w, t in turns)
    return record, sorted(set(moves), key=C_ACTS.index), quit_


def run_triage(S, case, sys_p, v):
    kind = v["field"]
    record, moves, quit_ = (run_form if kind == "form" else run_chat)(S, sys_p, v)
    level = None if quit_ else judge(S, record)
    what = "an online form" if kind == "form" else "an online chat"
    ctx = f"You have just used {what} to find out how urgently you need to be seen. This is what you entered:\n\n{record}\n\n" + ("You gave up before the end." if quit_ else "You got to the end.")
    qs = {q["id"]: q["text"] for q in S["questions"]}
    why, about = why_triage(S, sys_p, ctx, moves)
    unasked = None if quit_ else follow(sys_p, ctx, qs["unasked"])
    return {"record": record, "moves": moves, "final_action": "abandon" if quit_ else "submit", "level": level, "why": why, "why_about": about, "unasked": unasked}


def message_for(case, text):
    """the closing message, with its "You told us ..." line about this patient instead of the example patient"""
    d = case["derived"]
    line = f"You told us: “{d['opening']}” A problem like this needs a doctor to examine you today."
    out = re.sub(r"You told us[^\n]*", line, text)
    if not case["real"]["pain_score"]: out = out.replace("If the pain suddenly gets much worse", "If it suddenly gets much worse")
    return out


def run_message(S, case, sys_p, v):
    msg = message_for(case, v["vals"][v["field"]]["text"])
    got = ask("patient", sys_p,
              f"You have just finished an NHS 111 online check about how you feel. This message appears on your screen:\n\n---\n{msg}\n---\n\n"
              f"What do you do next? Choose one:\n{act_lines(S, M_ACTS)}\n\nAnswer as the person you are, not as the person you think you should be.",
              {"type": "object", "properties": {"action": {"type": "string", "enum": M_ACTS}}, "required": ["action"], "additionalProperties": False})
    a = got["action"]; A = {x["id"]: x for x in S["actions"]}
    ctx = f"You have just finished an NHS 111 online check about how you feel. This message appeared on your screen:\n\n---\n{msg}\n---\n\nWhat you decided to do: {A[a]['name']}. {A[a].get('desc', '')}"
    qs = {q["id"]: q["text"] for q in S["questions"]}
    return {"message": msg, "action": a, "why": why_message(S, sys_p, ctx), "when": follow(sys_p, ctx, qs["when"])}


# ---------- the sample ----------
def sample(cases, n, seed=29):
    """n patients with the same spread of expert levels as all of them"""
    R = random.Random(seed); by = collections.defaultdict(list)
    for c in cases: by[c["real"]["ktas_expert"]].append(c)
    want = {k: n * len(v) / len(cases) for k, v in by.items()}
    take = {k: int(w) for k, w in want.items()}
    for k in sorted(want, key=lambda k: want[k] - take[k], reverse=True)[:n - sum(take.values())]: take[k] += 1
    out = []
    for k in sorted(by): out += R.sample(by[k], take[k])
    return sorted(out, key=lambda c: c["id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60); ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--group", action="store_true"); ap.add_argument("--only", default=""); ap.add_argument("--rewhy", action="store_true")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    r = setup(); S = r["s"]
    cases = json.loads((D / "control" / "cases.json").read_text())["cases"]
    PEOPLE = {c["id"]: p for c, p in zip(cases, r["people"])}
    if USAGE.exists():
        for m, c in json.loads(USAGE.read_text()).items(): usage[m].update(c)
    done = {}
    if RUNS.exists():
        for line in RUNS.read_text().splitlines():
            x = json.loads(line); done[(x["patient_id"], x["version"])] = x
    if a.rewhy:
        # ask "What led to that?" again for the runs kept, now about a named action; everything else in a run is left as it was
        CASE = {c["id"]: c for c in cases}; A = {x["id"]: x for x in S["actions"]}
        def again(x):
            c = CASE[x["patient_id"]]; sys_p = persona(S, c, *PEOPLE[c["id"]])
            if x["type"] == "msg":
                ctx = f"You have just finished an NHS 111 online check about how you feel. This message appeared on your screen:\n\n---\n{x['message']}\n---\n\nWhat you decided to do: {A[x['action']]['name']}. {A[x['action']].get('desc', '')}"
                x["why"] = why_message(S, sys_p, ctx)
            else:
                quit_ = x["final_action"] == "abandon"; what = "an online form" if x["type"] == "form" else "an online chat"
                ctx = f"You have just used {what} to find out how urgently you need to be seen. This is what you entered:\n\n{x['record']}\n\n" + ("You gave up before the end." if quit_ else "You got to the end.")
                x["why"], x["why_about"] = why_triage(S, sys_p, ctx, x["moves"])
        todo = [x for x in done.values() if not x.get("rewhy")]
        with cf.ThreadPoolExecutor(a.workers) as pool:
            for x, fu in [(x, pool.submit(again, x)) for x in todo]:
                try: fu.result(); x["rewhy"] = True
                except Exception as e: print("  failed:", x["patient_id"], x["name"], str(e)[:100])
        RUNS.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in done.values()))
        USAGE.write_text(json.dumps(usage, indent=1)); print(sum(1 for x in done.values() if x.get("rewhy")), "of", len(done), "asked again")
        return report()
    if a.group:
        return group(S, cases, done)
    pts = sample(cases, a.n)
    todo = []
    for c in pts:
        for v in S["variants"]:
            if v["field"] == "real" or (a.only and v["field"] not in a.only.split(",")): continue
            if v["field"] == "msg" and c["real"]["ktas_expert"] > 3: continue   # the closing message is for patients told to go to emergency care
            if (c["id"], v["id"]) not in done: todo.append((c, v))
    random.Random(1).shuffle(todo)
    print(f"{len(pts)} patients, {len(done)} runs kept, {len(todo)} to do, 5-hour limit at {five_hour()}%", flush=True)
    t0 = time.time(); n_ok = n_bad = 0

    def one(job):
        c, v = job
        sys_p = persona(S, c, *PEOPLE[c["id"]])
        res = (run_message if v["field"] == "msg" else run_triage)(S, c, sys_p, v)
        return {"patient_id": c["id"], "version": v["id"], "name": v["name"], "type": v["field"], **res}

    with cf.ThreadPoolExecutor(a.workers) as pool, RUNS.open("a") as f:
        futs = {pool.submit(one, j): j for j in todo}
        for i, fu in enumerate(cf.as_completed(futs), 1):
            try:
                x = fu.result(); f.write(json.dumps(x, ensure_ascii=False) + "\n"); f.flush(); n_ok += 1
            except Limit:
                n_bad += 1
            except Exception as e:
                n_bad += 1; print("  failed:", futs[fu][0]["id"], futs[fu][1]["name"], str(e)[:120], flush=True)
            if i % 25 == 0 or i == len(todo):
                pc = five_hour(); calls = sum(c["calls"] for c in usage.values())
                print(f"  {i}/{len(todo)} runs, {n_bad} failed, {calls} calls, {time.time() - t0:.0f}s, 5-hour limit {pc}%", flush=True)
                with lock: USAGE.write_text(json.dumps(usage, indent=1))
                if pc is not None and pc >= STOP_AT and not halt.is_set():
                    print(f"  5-hour limit at {pc}%: stopping here. Run again later to carry on.", flush=True); halt.set()
    with lock: USAGE.write_text(json.dumps(usage, indent=1))
    report()


def report():
    tot = collections.Counter()
    for m, c in sorted(usage.items()):
        print(f"{m}: {c['calls']:,} calls, input {c['input'] + c['cache_write'] + c['cache_read']:,} tokens (of which cached {c['cache_read']:,}), output {c['output']:,} tokens, ${c['cost_micro_usd'] / 1e6:.2f} at list price")
        tot.update(c)
    print(f"TOTAL: {tot['calls']:,} calls, {tot['input'] + tot['cache_write'] + tot['cache_read']:,} input + {tot['output']:,} output tokens, ${tot['cost_micro_usd'] / 1e6:.2f} at list price (billed to the subscription, not paid per token)")


# ---------- short labels for the answers ----------
def label(question, about, answers):
    """one call: sort free-text answers into a few groups and name each in two or three words"""
    if not answers: return []
    out, known = [], []
    for at in range(0, len(answers), 150):
        part = answers[at:at + 150]
        got = ask("group", "You sort survey answers into groups. You are exact and brief.",
                  f"Patients were asked: “{question}” {about}\n\nSort their answers into at most 6 groups by what they say. Name each group in two or three plain words, "
                  "in sentence case, as the patient would put it (for example “Questions matched”, “Too many questions”). "
                  + (f"These groups already exist: {', '.join(known)}. Use these exact names. Add a new group only for an answer that fits none of them at all.\n\n" if known else "\n\n")
                  + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(part)) + f"\n\nGive the group name for each of the {len(part)} answers, in order.",
                  {"type": "object", "properties": {"groups": {"type": "array", "items": {"type": "string"}}}, "required": ["groups"], "additionalProperties": False})["groups"]
        got = (got + ["Other"] * len(part))[:len(part)]
        got = [g if not known or g in known or len(known) < 7 else "Other" for g in got]   # later parts keep to the names the first part made
        out += got; known = list(dict.fromkeys(known + got))[:7]
    return out


def group(S, cases, done):
    CASE = {c["id"]: c for c in cases}; V = {v["id"]: v for v in S["variants"]}
    tri = [x for x in done.values() if x["type"] != "msg"]; msg = [x for x in done.values() if x["type"] == "msg"]
    for x in tri:
        gold = CASE[x["patient_id"]]["real"]["ktas_expert"]
        x["out"] = "quit" if x["final_action"] == "abandon" else "right" if x["level"] == gold else "low" if x["level"] > gold else "high"
    for x in msg: x["out"] = "proceed" if x["action"] == "go_now" else "notgo"
    # one set of labels per question and stage, shared by every version and outcome, so the same reason carries the same name everywhere
    used = "They had just used an online form or chat to find out how urgently they needed to be seen."
    jobs = [("why", S["questions"][0]["text"], used + " The question was about one thing they did while using it, such as ticking Not sure, skipping a question or giving up.", tri),
            ("unasked", next(q["text"] for q in S["questions"] if q["id"] == "unasked"), used, [x for x in tri if x.get("unasked")]),
            ("why", S["questions"][0]["text"], "They had just been told to go to emergency care, and the question was about what they decided to do: go now, or not.", msg),
            ("when", next(q["text"] for q in S["questions"] if q["id"] == "when"), "They had just been told to go to emergency care.", msg)]

    def do(j):
        k, q, about, rows = j
        for x, lab in zip(rows, label(q, about, [x[k] for x in rows])): x[k + "_short"] = lab.strip().rstrip(".")[:40] or "Other"
    with cf.ThreadPoolExecutor(8) as pool: list(pool.map(do, jobs))
    USAGE.write_text(json.dumps(usage, indent=1))
    ARM = {}   # the builder knows versions by their arm ids
    arms = json.loads((D / "triage_arms.json").read_text())["arms"]; marms = json.loads((D / "messages.json").read_text())["arms"]
    main_arms = [x["id"] for x in arms if x["id"] not in ("T0", "CALL")]
    for v, arm in zip([v for v in S["variants"] if v["field"] in ("form", "chat")], main_arms): ARM[v["id"]] = arm
    for v, arm in zip([v for v in S["variants"] if v["field"] == "msg"], [x["id"] for x in marms]): ARM[v["id"]] = arm
    tot = collections.Counter()
    for c in usage.values(): tot.update(c)
    out = {"label": "Real run. Patients, chat agent: " + MODEL["patient"] + ". Judge: " + MODEL["judge"] + ". Every row is a model's answer; nothing is sampled from assumed effects.",
           "models": MODEL, "patients": sorted({x["patient_id"] for x in done.values()}),
           "usage": {"by_model": usage, "calls": tot["calls"], "input_tokens": tot["input"] + tot["cache_write"] + tot["cache_read"], "output_tokens": tot["output"], "list_price_usd": round(tot["cost_micro_usd"] / 1e6, 2)},
           "triage_runs": [{"patient_id": x["patient_id"], "arm": ARM[x["version"]], "final_action": x["final_action"], "disposition": None if x["level"] is None else 5 - x["level"], "level": x["level"],
                            "moves": x["moves"], "why": x["why"], "why_short": x.get("why_short", "Other"), "unasked": x.get("unasked"), "unasked_short": x.get("unasked_short")} for x in sorted(tri, key=lambda x: (x["patient_id"], x["version"]))],
           "message_runs": [{"patient_id": x["patient_id"], "arm": ARM[x["version"]], "action": x["action"], "why": x["why"], "why_short": x.get("why_short", "Other"), "when": x["when"], "when_short": x.get("when_short", "Other")}
                            for x in sorted(msg, key=lambda x: (x["patient_id"], x["version"]))]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("wrote", OUT.relative_to(ROOT), len(out["triage_runs"]), "triage runs,", len(out["message_runs"]), "message runs,", len(out["patients"]), "patients")
    n = collections.defaultdict(collections.Counter)
    for x in tri + msg: n[x["name"]][x["out"]] += 1
    for name, c in n.items():
        t = sum(c.values()); print(f"  {name:26s} n={t:3d}  " + "  ".join(f"{k} {v * 100 // t}%" for k, v in sorted(c.items())))
    report()


if __name__ == "__main__":
    main()
