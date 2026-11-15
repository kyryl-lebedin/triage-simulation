"""Generate MOCK results so the dashboard's Results tab has something to draw.

Nothing here comes from a model run. Outcomes are sampled from hand-set probabilities
that encode the hypotheses in triage_arms.json and messages.json. Replace with real
runs: write a file with the same shape into data/results/ and list it in index.json.
"""
import json, pathlib, random

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data"
load = lambda n: json.loads((D / n).read_text())
exp, vig, arms, prof, msgs = (load(n) for n in (
    "experiment.json", "vignettes.json", "triage_arms.json", "profiles.json", "messages.json"))

SEED, N = 7, 340
rng = random.Random(SEED)
SERVICE = {s["id"]: s for s in exp["services"]}
LEVEL_RANK = {l["id"]: l["rank"] for l in exp["levels"]}
BY_LEVEL = {}
for s in exp["services"]:
    BY_LEVEL.setdefault(LEVEL_RANK[s["level"]], []).append(s["id"])

ACT_NOW = set(next(c for c in exp["case_types"] if c["id"] == "act_now")["services"])
BANDS = {"16-29": (16, 29), "30-59": (30, 59), "60-79": (60, 79), "80+": (80, 92)}
ELICIT = {"F0": .62, "F1": .80, "F2": .68, "F3": .74, "C0": .76, "C1": .86, "C2": .89, "CALL": .93}
CLS = {a["id"]: a["class"] for a in arms["arms"]}

# Illustrative reason lines for the mock only. Real runs carry the participant's own words.
SAY = {
    ("proceed", "trust"): ["It's the NHS telling me, so I'll do it."],
    ("proceed", "perceived_severity"): ["That sounds like it matters. I'll go."],
    ("proceed", "access"): ["It's round the corner and they already have my answers."],
    ("proceed", "wait_time"): ["Ten minutes beats five hours in A&E."],
    ("escalate", "trust"): ["A website can't examine me. I'd rather a doctor looked at it."],
    ("escalate", "perceived_severity"): ["What if it's something worse? I'm not risking it."],
    ("escalate", "past_experience"): ["Last time I was told to wait and ended up in hospital anyway."],
    ("downgrade", "perceived_severity"): ["It's not that bad. I'll see how it is in the morning."],
    ("downgrade", "access"): ["I've got the kids and no car. I can't get there today."],
    ("downgrade", "wait_time"): ["I'm not sitting in a waiting room for hours over this."],
    ("second_opinion", "trust"): ["I'd ring 111 and speak to a person before I do anything."],
    ("second_opinion", "did_not_understand"): ["Too much text. I'm not sure what I should do first."],
    ("second_opinion", "perceived_severity"): ["I'll ask my sister, she's a nurse."],
    ("ignore", "perceived_severity"): ["It'll pass."],
    ("ignore", "access"): ["I can't take time off for this."],
    ("ignore", "did_not_understand"): ["I didn't really follow what it wanted me to do."],
}


def clamp(x): return max(0.02, min(0.98, x))


def service_at(rank, gold):
    rank = max(0, min(2, rank))
    opts = BY_LEVEL[rank]
    return gold if gold in opts and rng.random() < .85 else rng.choice(opts)


def triage_run(v, p, arm, gr=None, top=2):
    """gr and top are passed when a case is scored on a scale of its own: the right level and the highest one
    (the control set uses the five KTAS levels). The result is then a level, not a service."""
    if gr is None:
        gold = v["gold_service"]; gr = LEVEL_RANK[SERVICE[gold]["level"]]
        place, need, drop = (lambda r: service_at(r, gold)), .6, (lambda g: g)
    else:   # a control case has one to three critical facts, so half of them is enough and a miss costs one level
        place, need, drop = (lambda r: max(0, min(top, r))), .5, (lambda g: 1)
    cls = CLS[arm]
    stoic, anxious = p["reporting_style"] == "stoic", p["reporting_style"] == "anxious"
    low_lit, lim_eng, low_dig = p["health_literacy"] == "low", p["english"] == "limited", p["digital_confidence"] == "low"
    run = {"arm": arm, "final_action": "submit", "disposition": None, "misses": []}

    if cls == "self":
        shift = 0
        r = rng.random()
        if gr > 0 and r < (.50 if stoic else .30 if not anxious else .12): shift = -1
        elif gr < top and r > (.92 if stoic else .80 if not anxious else .50): shift = 1
        run["disposition"] = place(gr + shift)
        return run

    p_abandon = .02 + (low_dig * {"form": .06, "chat": .09, "call": 0}[cls]) + (low_dig and arm == "F3") * .10 \
        + (lim_eng and arm == "F3") * .05
    if rng.random() < p_abandon:
        run["final_action"] = "abandon"
        run["abandon_destination"] = rng.choices(["go to A&E", "phone 111", "phone GP", "do nothing"], [3, 4, 1, 2])[0]
        return run

    probing = arm in ("C1", "C2", "CALL")
    pe = ELICIT[arm]
    pe -= stoic * (.05 if probing else .07 if arm == "F2" else .14)
    pe -= low_lit * (.03 if arm in ("F1", "CALL") else .05 if cls == "chat" else .13)
    pe -= lim_eng * (.05 if arm in ("F1", "C0", "C1", "C2", "CALL") else .11)
    pe = clamp(pe)

    positives = [f for f in v["facts"] if f["critical"] and f["value"] is not False]
    got = 0
    for f in positives:
        if rng.random() < pe: got += 1; continue
        if cls == "form":
            w = {"never_asked": 2 if arm != "F3" else 1, "misunderstood": 5 if arm != "F1" else 2,
                 "downplayed": (5 if stoic else 1) * (.5 if arm == "F2" else 1), "engine_missed": .6}
        else:
            w = {"never_asked": 4 if arm == "C0" else 2, "misunderstood": 1,
                 "downplayed": 5 if stoic else 1.5, "engine_missed": .8}
        run["misses"].append({"concept": f["concept"], "tag": rng.choices(list(w), list(w.values()))[0]})

    shift = 0
    if positives and gr > 0:
        frac = got / len(positives)
        shift = 0 if frac >= need else -1 if frac > 0 else -drop(gr)
    if shift == 0 and gr < top:
        p_over = (.26 if anxious else .07 if not stoic else .03) * \
                 {"F0": 1, "F1": .9, "F2": .55, "F3": 1.1, "C0": 1, "C1": 1.05, "C2": 1.35, "CALL": .7}[arm]
        if rng.random() < p_over: shift = 1
    if shift >= 0: run["misses"] = []
    run["disposition"] = place(gr + shift)
    return run


def moves_for(run, p, kind, r):
    """moves a participant makes along the way; a version only gets the moves of its own type"""
    arm = run["arm"]
    stoic, anxious = p["reporting_style"] == "stoic", p["reporting_style"] == "anxious"
    low_lit, lim_eng, low_dig = p["health_literacy"] == "low", p["english"] == "limited", p["digital_confidence"] == "low"
    moves = []
    if kind == "form":
        if r.random() < clamp(.16 + low_lit * (.10 if arm == "F1" else .26) + lim_eng * (.06 if arm == "F1" else .14) + anxious * .14): moves.append("not_sure")
        if r.random() < clamp(.05 + low_dig * .16 + (arm == "F3") * .06 + lim_eng * .05): moves.append("skip")
    elif kind == "agent_prompt":
        if r.random() < clamp((.08 + low_lit * .22 + lim_eng * .20) * (.6 if arm == "CALL" else 1)): moves.append("ask_clarification")
        if r.random() < clamp((.55 if stoic else .12 if anxious else .22) + low_lit * .05): moves.append("hedge")
    return moves


def message_run(v, p, arm):
    gold = v["gold_service"]; act_now = gold in ACT_NOW
    stoic, anxious = p["reporting_style"] == "stoic", p["reporting_style"] == "anxious"
    low_trust, hard, lim_eng = p["nhs_trust"] == "low", p["access"] == "hard", p["english"] == "limited"
    has = lambda c: c in next(a for a in msgs["arms"] if a["id"] == arm)["components"]
    if act_now:
        w = {"escalate": 0, "downgrade": .10, "second_opinion": .06, "ignore": .04}
        if stoic: w["downgrade"] *= 2.4 * (.45 if has("consequence") else 1) * (.5 if has("authority") else 1)
        if hard: w["downgrade"] *= 1.8 * (.45 if has("facilitation") else 1); w["ignore"] *= 1.5 * (.6 if has("facilitation") else 1)
        if low_trust: w["second_opinion"] *= 1.8 * (.5 if has("reason") else 1)
        if has("reason"): w["downgrade"] *= .75
        if has("consequence"): w["ignore"] *= .6
    else:
        w = {"escalate": .11, "downgrade": .04 if gold != "self_care" else 0, "second_opinion": .08, "ignore": .03 if gold != "self_care" else 0}
        if low_trust: w["escalate"] *= 1.9 * (.45 if has("reason") else 1); w["second_opinion"] *= 1.6 * (.6 if has("reason") else 1)
        if anxious: w["escalate"] *= 1.7 * (.5 if has("safety_net") else 1) * (1.2 if has("consequence") and not has("safety_net") else 1)
        if hard and gold == "gp": w["downgrade"] *= 2.2 * (.4 if has("facilitation") else 1)
        if has("facilitation"): w["escalate"] *= .8
        if has("consequence"): w["escalate"] *= .8
        if has("authority"): w["second_opinion"] *= .8
    if lim_eng and len(next(a for a in msgs["arms"] if a["id"] == arm)["components"]) > 3:
        w["second_opinion"] = w["second_opinion"] * 1.6 + .03
    w["proceed"] = max(.05, 1 - sum(w.values()))
    action = rng.choices(list(w), list(w.values()))[0]

    if action == "proceed":
        rc = {"trust": 4, "perceived_severity": 3, "access": 2 if has("facilitation") else .5, "wait_time": 2 if has("consequence") else .3}
    elif action == "escalate":
        rc = {"trust": 4 if low_trust else 1, "perceived_severity": 5 if anxious else 2, "past_experience": 1.5}
    elif action == "downgrade":
        rc = {"perceived_severity": 5 if stoic else 2, "access": 5 if hard else 1, "wait_time": 1.5}
    elif action == "second_opinion":
        rc = {"trust": 4 if low_trust else 1.5, "did_not_understand": 4 if lim_eng else .8, "perceived_severity": 1}
    else:
        rc = {"perceived_severity": 3, "access": 3 if hard else 1, "did_not_understand": 2 if lim_eng else .5}
    when = "Not at all" if action == "ignore" else rng.choices(
        ["Right now", "Later today", "In the next few days"], [6, 3, 1] if act_now and action == "proceed" else [2, 4, 3])[0]
    code = rng.choices(list(rc), list(rc.values()))[0]
    return {"arm": arm, "action": action, "reason_code": code,
            "reason_text": rng.choice(SAY.get((action, code), [""])), "when_act": when,
            "perceived_urgency": max(1, min(5, round(rng.gauss(4.3 if act_now else 2.2, .8) + anxious * .6 - stoic * .6)))}


# more than one wording per reason, so the grouping of answers has something to group
SAY2 = {
    ("proceed", "trust"): ["It's the NHS telling me, so I'll do it.", "They know better than I do. I'll go."],
    ("proceed", "perceived_severity"): ["That sounds like it matters. I'll go.", "Reading that, I don't want to leave it."],
    ("proceed", "access"): ["It's round the corner and they already have my answers.", "They've sorted it for me, so there's no excuse."],
    ("proceed", "wait_time"): ["Ten minutes beats five hours in A&E.", "If it's quicker this way, fine."],
    ("escalate", "trust"): ["A website can't examine me. I'd rather a doctor looked at it.", "I want someone to actually look at it."],
    ("escalate", "perceived_severity"): ["What if it's something worse? I'm not risking it.", "It could be serious. I'd rather be told it's nothing at A&E."],
    ("escalate", "past_experience"): ["Last time I was told to wait and ended up in hospital anyway.", "I've been sent away before and it wasn't nothing."],
    ("downgrade", "perceived_severity"): ["It's not that bad. I'll see how it is in the morning.", "It's eased a bit. I'll give it a day."],
    ("downgrade", "access"): ["I've got the kids and no car. I can't get there today.", "There's no bus at this time and nobody to mind the children."],
    ("downgrade", "wait_time"): ["I'm not sitting in a waiting room for hours over this.", "I can't lose half a day waiting."],
    ("second_opinion", "trust"): ["I'd ring 111 and speak to a person before I do anything.", "I'd want a person to tell me that, not a screen."],
    ("second_opinion", "did_not_understand"): ["Too much text. I'm not sure what I should do first.", "Too many words. Which part is for me?"],
    ("second_opinion", "perceived_severity"): ["I'll ask my sister, she's a nurse.", "I'd check with my daughter before going anywhere."],
    ("ignore", "perceived_severity"): ["It'll pass.", "It always settles on its own."],
    ("ignore", "access"): ["I can't take time off for this.", "I've got a shift. It will have to wait."],
    ("ignore", "did_not_understand"): ["I didn't really follow what it wanted me to do.", "I did not understand the message."],
}
COMP = {a["id"]: a["components"] for a in msgs["arms"]}


def reason_line(run, r):
    """a fuller wording for a message run's reason, or None to keep the one it has"""
    key, c = (run["action"], run["reason_code"]), COMP[run["arm"]]
    lines = SAY2.get(key)
    # a reason can only cite what the message actually contained
    if key == ("second_opinion", "did_not_understand") and len(c) <= 3: lines = ["I'm not sure what it wants me to do. I'd ask someone.", "I do not understand some of the words. I would ask."]
    if key == ("proceed", "access") and "facilitation" not in c: lines = ["It's easy enough for me to get there.", "That's close to me anyway."]
    if key == ("proceed", "wait_time") and "consequence" not in c: lines = ["It'll be quicker than sitting in A&E.", "I don't fancy a night in A&E."]
    return r.choice(lines) if lines else None


def main():
    triage, message, patients = [], [], {}
    draw = lambda axis: rng.choices([l["id"] for l in axis["levels"]], [l.get("pct", 1) for l in axis["levels"]])[0]
    levels = sorted({SERVICE[v["gold_service"]]["level"] for v in vig["vignettes"]})
    for i in range(N):
        p = {a["id"]: draw(a) for a in prof["axes"]}
        lo, hi = BANDS[p["age_band"]]
        ok = [v for v in vig["vignettes"] if v["eligible"]["sex"] in ("any", p["sex"])
              and v["eligible"]["age_max"] >= lo and v["eligible"]["age_min"] <= hi]
        lvl = rng.choice([l for l in levels if any(SERVICE[v["gold_service"]]["level"] == l for v in ok)])  # balanced case mix
        v = rng.choice([v for v in ok if SERVICE[v["gold_service"]]["level"] == lvl])
        age = rng.randint(max(lo, v["eligible"]["age_min"]), min(hi, v["eligible"]["age_max"]))
        pid = f"p{i:03d}"
        patients[pid] = {"vignette_id": v["id"], "age": age, "profile": p}
        for a in arms["arms"]:
            triage.append({"patient_id": pid, **triage_run(v, p, a["id"])})
        for a in msgs["arms"]:
            message.append({"patient_id": pid, **message_run(v, p, a["id"])})

    # ---- second pass, on its own random stream so the outcomes above stay exactly as they were ----
    r2 = random.Random(SEED + 3)  # +1 happened to give hedging a spurious gap between versions
    KIND = {a["id"]: a["type"] for a in arms["arms"]}

    for run in triage:
        run["moves"] = moves_for(run, patients[run["patient_id"]]["profile"], KIND[run["arm"]], r2)

    for run in message:
        line = reason_line(run, r2)
        if line: run["reason_text"] = line

    out = {"mock": True, "label": "MOCK — sampled from assumed effect sizes, no model was run",
           "seed": SEED, "participants": N, "case_mix": "balanced across urgency levels",
           "patients": patients, "triage_runs": triage, "message_runs": message}
    (D / "results").mkdir(exist_ok=True)
    (D / "results" / "MOCK_results.json").write_text(json.dumps(out, separators=(",", ":")))
    idx_path = D / "results" / "index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"files": []}
    if not any(f["file"] == "MOCK_results.json" for f in idx["files"]):
        idx["files"].append({"file": "MOCK_results.json", "label": "MOCK (schema demo)"})
    idx_path.write_text(json.dumps(idx, indent=2) + "\n")
    print(f"wrote {len(patients)} patients, {len(triage)} triage runs, {len(message)} message runs")


if __name__ == "__main__":
    main()
