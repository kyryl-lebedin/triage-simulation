"""Turn the triage experiment into runs for the platform prototype (index.html): triage, advice message, and the control set.

Reads data/*.json, data/versions/*.txt and data/results/MOCK_results.json.
Writes data/triage-runs.js, which index.html loads before its own script:

    window.STANDIN_IMPORTS = [{ id, status, date, s, responses() }]

`s` is a scenario in the platform's own shape (fields, variants, vars, prompt, actions, questions).
`responses()` returns one row per participant per version, in the shape the platform's stage 2
returns: { variant, participant, persona, profile, actions, answers: [{ question, action, full, short }] }.

The results are MOCK (see make_mock_results.py). The short tags and some quotes below are written
here for the mock; a real run carries the participant's own words.
"""
import hashlib, json, pathlib, random

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data"
load = lambda n: json.loads((D / n).read_text())
exp, vig, arms, prof, msgs = (load(n) for n in (
    "experiment.json", "vignettes.json", "triage_arms.json", "profiles.json", "messages.json"))
res = load("results/MOCK_results.json")

R = random.Random(11)  # only picks between wordings of the same reason
SERVICE = {s["id"]: s for s in exp["services"]}
LEVEL = {l["id"]: l for l in exp["levels"]}
rank = lambda sid: LEVEL[SERVICE[sid]["level"]]["rank"]
VIG = {v["id"]: v for v in vig["vignettes"]}
LABEL = vig["concept_labels"]
ACT_NOW = set(next(c for c in exp["case_types"] if c["id"] == "act_now")["services"])
P = res["patients"]

SHORT = {"E1": "Heart attack", "E2": "Stroke / TIA", "E3": "Child with sepsis", "E4": "Ectopic pregnancy",
         "E5": "Blood clot in lung", "U1": "Kidney infection", "U2": "Cellulitis, diabetic", "U3": "Hand cut",
         "G1": "3-week cough, smoker", "G2": "Rectal bleeding", "P1": "Urine infection", "P2": "Sore throat",
         "P3": "Insect bite", "S1": "Common cold", "S2": "Back pain", "D1": "Dental abscess", "H1": "Mental health crisis"}
SVC = {"ambulance": "999 ambulance", "ae": "A&E", "utc": "Urgent treatment centre", "urgent_gp": "Urgent GP today",
       "callback": "111 call-back", "mental_health": "Mental health line", "dental": "Urgent dentist",
       "gp": "GP appointment", "pharmacy": "Pharmacy", "self_care": "Self-care"}
BANDS = {"16-29": (16, 29), "30-59": (30, 59), "60-79": (60, 79), "80+": (80, 120)}
LETTERS = "ABCDEFGHIJKLMNOPQRST"
KTAS_NAME = {1: "Resuscitation", 2: "Emergent", 3: "Urgent", 4: "Less urgent", 5: "Non-urgent"}
NAMES = ["Alex", "Sam", "Robin", "Jordan", "Noor", "Kai", "Ari", "Remy", "Sasha", "Jules", "Devon", "Quinn",
         "Morgan", "Ashley", "Kiran", "Lee", "Chris", "Pat", "Shan", "Toni", "Jo", "Nicky", "Dani", "Frankie"]
h = lambda s: int(hashlib.md5(s.encode()).hexdigest(), 16)
pct = lambda n, d: int(n * 100 / d + .5) if d else 0


def shares(weights, total=100, floor=1):
    """whole numbers in proportion to the weights, summing to total, none below floor"""
    t = sum(weights) or 1
    raw = [w / t * total for w in weights]
    out = [max(floor, int(x)) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - int(raw[i]), reverse=True)
    i = 0
    while sum(out) < total: out[order[i % len(out)]] += 1; i += 1
    while sum(out) > total:
        j = max(range(len(out)), key=lambda k: out[k]); out[j] -= 1
    return out


# ---------- participants ----------
axis = lambda i: next(a for a in prof["axes"] if a["id"] == i)
AXIS_VAR = {"sex": ("sex", "sex", "Sex"), "age_band": ("age", "age", "Age"),
            "reporting_style": ("style", "reporting_style", "Reporting style"),
            "health_literacy": ("literacy", "health_literacy", "Health literacy"),
            "english": ("english", "english", "English"),
            "digital_confidence": ("digital", "digital_confidence", "Digital confidence"),
            "nhs_trust": ("trust", "nhs_trust", "Trust in NHS advice"), "access": ("access", "access", "Access to care")}


def axis_var(aid):
    a = axis(aid); vid, key, name = AXIS_VAR[aid]
    levels = a["levels"]
    design = [l.get("pct") for l in levels]
    pcts = design if all(x is not None for x in design) else shares([1] * len(levels))
    v = {"id": vid, "key": key, "name": name, "_axis": aid, "_levels": [l["id"] for l in levels],
         "opts": [{"name": l["label"], "pct": p, **({"say": l["say"]} if l.get("say") else {})} for l, p in zip(levels, pcts)]}
    if aid == "sex":
        v["opts"][0]["say"], v["opts"][1]["say"] = "woman", "man"
    if a.get("source"):
        v["ai"] = True
        v["ref"] = {"pcts": pcts, "src": f'{a["source"]["label"]}; {a["source"]["note"]}'.rstrip("."), "url": a["source"]["url"]}
    else:
        v["note"] = "Set by design, not taken from data: equal groups, so each one is large enough to compare."
    return v


def case_var():
    vs = vig["vignettes"]
    n = [sum(1 for p in P.values() if p["vignette_id"] == v["id"]) for v in vs]
    by_level = {}
    for v in vs: by_level.setdefault(SERVICE[v["gold_service"]]["level"], []).append(v["id"])
    real = exp["case_mix"]["real"]
    per = {l: dict(zip(ids, shares([1] * len(ids), real[l]))) for l, ids in by_level.items()}  # each level keeps its real total
    ref = [per[SERVICE[v["gold_service"]]["level"]][v["id"]] for v in vs]
    bands = list(BANDS)
    opts = []
    for v, k in zip(vs, shares(n)):
        who = "You are answering for your young son, not for yourself. " if v["respondent"] == "parent" else ""
        facts = " ".join(f'[{LABEL.get(f["concept"], f["concept"])}] {f["lay"]}' for f in v["facts"])
        say = (f'{who}Your first words would be: "{v["opening"]}" What you think is going on: {v["belief"]} '
               f'Your private fact sheet, one fact per topic, which you reveal only when asked about that topic in words you understand: {facts}')
        o = {"name": SHORT[v["id"]], "pct": k, "say": say}
        need, e = {}, v["eligible"]
        if e["sex"] != "any": need["sex"] = [0 if e["sex"] == "female" else 1]
        ok = [i for i, b in enumerate(bands) if BANDS[b][0] <= e["age_max"] and BANDS[b][1] >= e["age_min"]]
        if len(ok) < len(bands): need["age"] = ok
        if need: o["needs"] = need
        opts.append(o)
    return {"id": "case", "key": "situation", "name": "Condition", "_levels": [v["id"] for v in vs], "opts": opts,
            "note": "Hidden from the participant: they are given the fact sheet, never the name of the condition. Each condition has one right service. The split shown is the one that was run: balanced across emergency, non-emergency and self-care. A condition is only given to people it can apply to; hover an option to see who.",
            "ref": {"pcts": ref, "src": f'{exp["case_mix"]["source"]["label"]}: emergency {real["emergency"]}%, non-emergency {real["non_emergency"]}%, self-care {real["self_care"]}% of real 111 outcomes, shared evenly between the conditions at each level',
                    "url": exp["case_mix"]["source"]["url"]}}


def people_for(vars_):
    """persona line and option index per variable, for every mock patient"""
    out, order = [], sorted(P)
    for pid in order:
        p = P[pid]; pr = p["profile"]; v = VIG[p["vignette_id"]]
        idx = []
        for var in vars_:
            key = p["vignette_id"] if var["id"] == "case" else pr[var["_axis"]]
            idx.append(var["_levels"].index(key))
        traits = [SHORT[v["id"]] if v["respondent"] == "self" else "parent, " + SHORT[v["id"]].lower()]
        ids = {var["id"] for var in vars_}
        if pr["reporting_style"] == "stoic": traits.append("plays things down")
        if pr["reporting_style"] == "anxious": traits.append("fears the worst")
        if pr["health_literacy"] == "low": traits.append("low health literacy")
        if pr["english"] == "limited": traits.append("limited English")
        if "digital" in ids and pr["digital_confidence"] == "low": traits.append("low digital confidence")
        if "trust" in ids and pr["nhs_trust"] == "low": traits.append("low trust")
        if "access" in ids and pr["access"] == "hard": traits.append("hard access")
        name = f'{NAMES[h(pid) % len(NAMES)]} {"ABCDEFGHJKLMNPRSTW"[h("s" + pid) % 18]}.'
        out.append([", ".join([name, str(p["age"]), pr["sex"], *traits]), idx])
    return order, out


class Table:
    """rows of responses, with repeated strings stored once"""
    def __init__(self, order, acts, qs):
        self.pid = {p: i for i, p in enumerate(order)}; self.acts = acts; self.qs = qs
        self.strings, self.at, self.rows = [], {}, []
    def s(self, t):
        if t not in self.at: self.at[t] = len(self.strings); self.strings.append(t)
        return self.at[t]
    def add(self, v, pid, actions, answers):
        self.rows.append([v, self.pid[pid], [self.acts.index(a) for a in actions],
                          [[self.qs.index(q), self.acts.index(a) if a else -1, self.s(full), self.s(short)] for q, a, full, short in answers]])


def pick(options):
    """options: [(weight, [wordings], [quotes])] -> (short, full)"""
    o = R.choices(options, [x[0] for x in options])[0]
    return R.choice(o[1]), R.choice(o[2])


def typical(rows):
    """one row carrying the most common reason among these rows"""
    if not rows: return None
    n = {}
    for x in rows: n[x[3]] = n.get(x[3], 0) + 1
    top = max(n, key=n.get)
    return next(x for x in rows if x[3] == top)


def clean(v):
    return {k: x for k, x in v.items() if not k.startswith("_")}


# ---------- run 1: triage channel ----------
T_ARMS = arms["arms"]
T_NAME = {"T0": "No tool", "F0": "Form: baseline", "F1": "Form: plain words", "F2": "Form: anchored",
          "F3": "Form: describe it", "C0": "Chat: neutral", "C1": "Chat: probing", "C2": "Chat: reassuring",
          "CALL": "111 call"}
T_ROLE = {"T0": "Baseline, and the check that participants do not know their diagnosis. ", "CALL": "Benchmark the substitutes are measured against. "}
T_ACTS = [
    {"id": "right", "name": "Sent to the right service", "on": True, "icon": "yes"},
    {"id": "low", "name": "Sent too low", "on": True, "bad": True, "icon": "down"},
    {"id": "high", "name": "Sent too high", "on": True, "bad": True, "icon": "up"},
    {"id": "quit", "name": "Gave up part-way", "on": True, "bad": True, "icon": "away", "fields": ["form", "chat", "call"]},
    {"id": "notsure", "name": "Ticked “Not sure”", "on": True, "bad": True, "icon": "help", "fields": ["form"]},
    {"id": "skip", "name": "Skipped a question", "on": True, "bad": True, "icon": "skip", "fields": ["form"]},
    {"id": "clarify", "name": "Asked what a question meant", "on": True, "bad": True, "icon": "comment", "fields": ["chat", "call"]},
    {"id": "hedge", "name": "Gave a vague answer", "on": True, "bad": True, "icon": "wave", "fields": ["chat", "call"]},
]
# these are types of treatment (split: True): each version is exactly one of them
# viz: the researcher's own HTML file that draws a version of this type on the Treatments page
T_FIELDS = [{"id": "form", "name": "Form", "type": "file", "viz": {"name": "form.html", "src": "viz/form.html"}},
            {"id": "chat", "name": "Chat prompt", "type": "file", "viz": {"name": "chat-agent.html", "src": "viz/chat-agent.html"}},
            {"id": "call", "name": "Call script", "type": "file"}, {"id": "ask", "name": "Direct question", "type": "file"}]
field_of = lambda a: "call" if a["id"] == "CALL" else {"question": "ask", "form": "form", "agent_prompt": "chat"}[a["type"]]
T_DESC = {'right': 'The judge names a service at the right urgency level.', 'low': 'The judge names a service below the right level. The safety risk.', 'high': 'The judge names a service above the right level. Adds demand.', 'quit': 'Stops before the end and does something else.', 'notsure': 'Answers “Not sure” to at least one question.', 'skip': 'Leaves at least one question unanswered.', 'clarify': 'Asks the agent what a question means.', 'hedge': 'Says “a bit”, “sort of” or “probably” at least once.'}
for _a in T_ACTS:
    _a["desc"] = T_DESC[_a["id"]]
    if _a["id"] in ("right", "low", "high"): _a["scored"] = True  # set by the judge, never offered to the participant
T_QS = [{"id": "why", "text": "What led to that?", "each": True},
        {"id": "where", "text": "Where did it send you?", "each": False},
        {"id": "unasked", "text": "Was there anything it never asked about?", "each": False}]
MOVE = {"not_sure": "notsure", "skip": "skip", "ask_clarification": "clarify", "hedge": "hedge"}
DEST = {"go to A&E": ("Gave up, went to A&E", "go to A&E"), "phone 111": ("Gave up, phoned 111", "phone 111"),
        "phone GP": ("Gave up, phoned GP", "ring my GP"), "do nothing": ("Gave up, did nothing", "leave it")}


def t_outcome(run, v):
    if run["final_action"] == "abandon": return "quit"
    d = rank(run["disposition"]) - rank(v["gold_service"])
    return "right" if d == 0 else "low" if d < 0 else "high"


def t_why(run, v, pr, out):
    arm, kind = run["arm"], next(a["type"] for a in T_ARMS if a["id"] == run["arm"])
    stoic, anxious = pr["reporting_style"] == "stoic", pr["reporting_style"] == "anxious"
    low_lit, lim_eng, low_dig = pr["health_literacy"] == "low", pr["english"] == "limited", pr["digital_confidence"] == "low"
    if out == "right":
        if kind == "question":
            minor = rank(v["gold_service"]) == 0
            return pick([(4, ["Looked minor", "It looked minor"], ["It's the kind of thing you just get on with."]) if minor else
                         (4, ["Felt serious enough", "It felt serious enough"], ["It didn't feel like something to sit on."]),
                         (3, ["Common sense"], ["That's just where you go for this."]),
                         (2, ["Guessed"], ["Honestly I wasn't sure. I picked what seemed about right."])])
        if kind == "form":
            o = [(4, ["Questions matched", "The questions matched"], ["It asked about exactly what I had."]),
                 (2, ["Clear choices"], ["The answers were easy to pick from."])]
            if arm == "F1": o.append((6 if low_lit or lim_eng else 3, ["Plain words", "Words were plain"], ["It used the words I'd use myself."]))
            if arm == "F2": o.append((5, ["Options fit me"], ["I could say what it stops me doing, instead of guessing mild or severe."]))
            if arm == "F3": o.append((5, ["Could describe it"], ["The box let me put it in my own words."]))
            return pick(o)
        o = [(4, ["Said it my way"], ["I could just describe it."]), (2, ["Simple questions"], ["One short question at a time. Easy."])]
        if arm in ("C1", "C2", "CALL"): o.append((7 if stoic else 3, ["It asked again", "Asked again"], ["I said it was probably nothing and it asked what I was actually feeling."]))
        if arm == "C2": o.append((4, ["Felt safe saying"], ["It said lots of people find this awkward to talk about, so I told it."]))
        if arm == "CALL": o.append((4, ["Summary read back"], ["They read it back to me and I added the bit I'd left out."]))
        return pick(o)
    if out == "low":
        if kind == "question" or not run["misses"]:
            return pick([(5 if stoic else 2, ["No fuss needed"], ["I don't want to waste anyone's time."]),
                         (3, ["Probably nothing", "It's probably nothing"], ["It's probably nothing. I'd give it a day."])])
        m = run["misses"][0]; lab = LABEL.get(m["concept"], "that")
        return pick({"never_asked": [(1, ["Never asked", "It never asked", "Was never asked"], [f"Nobody asked about {lab}, so I didn't bring it up."])],
                     "misunderstood": [(1, ["Misread the question", "Question misread"], [f"I thought the question about {lab} meant something else, so I said no."])],
                     "downplayed": [(1, ["Played it down", "Playing it down"], [f"When it asked about {lab} I said it wasn't too bad. I don't like making a fuss."])],
                     "engine_missed": [(1, ["Said it, ignored"], [f"I did tell it about {lab}. It still sent me somewhere lower."])],
                     "unmeasured": [(1, ["Nothing was measured", "No measurements"], ["I told it everything I could. Nobody took my pulse or my blood pressure.", "It only had my word for it. There was nothing to measure me with."])]}[m["tag"]])
    if out == "high":
        if kind == "question":
            return pick([(5 if anxious else 1, ["Feared the worst"], ["What if it's something serious? I'm not waiting to find out."]),
                         (3, ["Better safe"], ["Better safe than sorry."])])
        o = [(6 if anxious else 1, ["Feared the worst"], ["I couldn't rule it out, so I said yes to be safe."]), (2, ["Better safe"], ["Better safe than sorry."])]
        if arm != "F2": o.append((3, ["Picked the worst"], ["It's the worst I've felt, so I picked severe."]))
        return pick(o)
    # quit
    o = [(2, ["Rather phone someone"], ["I'd rather speak to a person."])]
    if low_dig: o.append((5, ["Too many questions"], ["I gave up around question ten."]))
    if lim_eng: o.append((4, ["Could not follow"], ["I did not understand the questions."]))
    if arm == "F3" or kind == "agent_prompt": o.append((3, ["Too much typing"], ["Typing it all out on my phone, no."]))
    short, full = pick(o)
    return short, f'{full} I\'ll {DEST[run["abandon_destination"]][1]} instead.'


def t_move_why(move, run, pr):
    stoic, anxious = pr["reporting_style"] == "stoic", pr["reporting_style"] == "anxious"
    low_lit, lim_eng, low_dig = pr["health_literacy"] == "low", pr["english"] == "limited", pr["digital_confidence"] == "low"
    if move == "notsure":
        return pick([(6 if low_lit else .5, ["Didn't know the word", "Didn't know a word"], ["I didn't know what one of the words meant, so I put Not sure."]),
                     (5 if anxious else .5, ["Could not rule out"], ["It sounded frightening and I couldn't say for certain it wasn't me."]),
                     (4 if lim_eng else .3, ["Question too long"], ["Long question. I understood only the start."]),
                     (2, ["Couldn't tell"], ["I honestly couldn't tell whether that was me."])])
    if move == "skip":
        return pick([(6 if low_dig else .5, ["Ran out of patience"], ["Too many questions. I started skipping."]),
                     (3 if run["arm"] == "F3" else 0, ["Left box empty"], ["I left the big text box empty."]),
                     (2, ["Seemed irrelevant"], ["That one had nothing to do with why I came."])])
    if move == "clarify":
        return pick([(6 if low_lit else .5, ["Didn't know the word", "Didn't know a word"], ["It used a word I didn't know, so I asked."]),
                     (5 if lim_eng else .3, ["Question too long"], ["Too many parts in one question. I asked it to say it again."]),
                     (2, ["Two things at once"], ["It asked two things in one go."])])
    return pick([(7 if stoic else .5, ["Didn't want fuss"], ["I said it was probably nothing. I don't like to make a fuss."]),
                 (2, ["Hard to describe"], ["I wasn't sure how to put it into words."]),
                 (1.5, ["Not sure myself"], ["I didn't know if it counted."])])


def build_triage():
    vars_ = [axis_var("sex"), axis_var("age_band"), case_var(), axis_var("reporting_style"), axis_var("health_literacy"),
             axis_var("english"), axis_var("digital_confidence")]
    order, people = people_for(vars_)
    acts, qs = [a["id"] for a in T_ACTS], [q["id"] for q in T_QS]
    tb = Table(order, acts, qs)
    vix = {a["id"]: i for i, a in enumerate(T_ARMS)}
    stats = {a["id"]: [] for a in T_ARMS}  # (profile, outcome, why short, why full, persona)
    for run in res["triage_runs"]:
        p = P[run["patient_id"]]; v = VIG[p["vignette_id"]]; pr = p["profile"]; arm = run["arm"]
        out = t_outcome(run, v)
        if out == "quit" and arm == "T0": out = "right"
        short, full = t_why(run, v, pr, out)
        ans = [("why", out, full, short)]
        moves = [MOVE[m] for m in run.get("moves", [])]
        for m in moves:
            s2, f2 = t_move_why(m, run, pr); ans.append(("why", m, f2, s2))
        if out == "quit":
            ans.append(("where", None, f'I stopped part-way and decided to {DEST[run["abandon_destination"]][1]}.', DEST[run["abandon_destination"]][0]))
        else:
            ans.append(("where", None, ("I'd choose: " if arm == "T0" else "It said: ") + SERVICE[run["disposition"]]["label"] + ".", SVC[run["disposition"]]))
        if arm != "T0":
            na = next((m for m in run["misses"] if m["tag"] == "never_asked"), None)
            if na and out == "low":
                lab = LABEL.get(na["concept"], "that")
                ans.append(("unasked", None, f"It never asked about {lab}.", lab[0].upper() + lab[1:]))
            elif out != "quit":
                ans.append(("unasked", None, R.choice(["No, it covered everything I had.", "No, I think it asked about everything."]), R.choice(["Nothing missed", "Nothing was missed"])))
        tb.add(vix[arm], run["patient_id"], [out, *moves], ans)
        stats[arm].append((pr, out, short, full, people[tb.pid[run["patient_id"]]][0], v))

    rate = lambda rows, o: pct(sum(1 for r in rows if r[1] == o), len(rows))
    PH = {("reporting_style", "stoic"): "stoic patients", ("reporting_style", "neutral"): "plain reporters", ("reporting_style", "anxious"): "anxious patients",
          ("health_literacy", "low"): "patients with low health literacy", ("health_literacy", "adequate"): "patients with adequate health literacy",
          ("english", "limited"): "patients with limited English", ("english", "fluent"): "fluent English speakers",
          ("digital_confidence", "low"): "patients with low digital confidence", ("digital_confidence", "high"): "confident users of forms and chat"}
    VID = {"reporting_style": "style", "health_literacy": "literacy", "english": "english", "digital_confidence": "digital"}
    cap = lambda s: s[0].upper() + s[1:]
    arm_of = {a["id"]: a for a in T_ARMS}
    notes = {}
    for i, a in enumerate(T_ARMS):
        rows, L = stats[a["id"]], LETTERS[i]
        r, lo, hi, q = (rate(rows, o) for o in ("right", "low", "high", "quit"))
        ns = []
        # widest gap between groups on being sent too low
        best = None
        for ax in VID:
            segs = [(rate([x for x in rows if x[0][ax] == l["id"]], "low"), l["id"]) for l in axis(ax)["levels"]]
            top, bot = max(segs), min(segs)
            if not best or top[0] - bot[0] > best[0]: best = (top[0] - bot[0], ax, top, bot)
        gap, ax, top, bot = best
        if gap >= 8:
            ex = typical([x for x in rows if x[0][ax] == top[1] and x[1] == "low"])
            ns.append({"t": f"{cap(PH[(ax, top[1])])} were sent too low {top[0]}% of the time",
                       "p": f"{cap(PH[(ax, bot[1])])}: {bot[0]}%. That {gap}-point gap is the widest between any two groups for this version; across everyone it is {lo}%.",
                       "q": ex[3] if ex else "", "by": ex[4] if ex else "", "m": "low", "s": VID[ax]})
        else:
            ns.append({"t": f"Sent too low: {lo}%, and even across groups", "p": f"The widest gap between any two groups is {gap} points ({AXIS_VAR[ax][2].lower()}).", "q": "", "by": "", "m": "low", "s": "none"})
        # what this version changes, against the baseline of its class
        base = {"F1": "F0", "F2": "F0", "F3": "F0", "C1": "C0", "C2": "C0"}.get(a["id"])
        if base:
            b = stats[base]; bn = T_NAME[base]
            ns.append({"t": f"Right service {r}%, against {rate(b, 'right')}% for {bn}",
                       "p": f"What changes: {a['changes_from_baseline']} Expected: {a['hypothesis']} Observed: too low {lo}% against {rate(b, 'low')}%, too high {hi}% against {rate(b, 'high')}%, gave up {q}% against {rate(b, 'quit')}%.",
                       "q": "", "by": "", "m": "right", "s": "none"})
        elif a["id"] == "T0":
            ns.append({"t": f"Leak check: {r}% right with no tool",
                       "p": "Real lay people pick the right urgency level about 61% of the time (Schmieding 2021). A figure far above that would mean the synthetic patients know their own diagnosis, and every other number here would be too good.",
                       "q": "", "by": "", "m": "right", "s": "none"})
        elif a["id"] == "F0":
            ns.append({"t": f"Anchor: {r}% right, published symptom checkers average 58%",
                       "p": f"The baseline form should land near real symptom checkers (Schmieding 2021). Expected: {a['hypothesis']}",
                       "q": "", "by": "", "m": "right", "s": "none"})
        elif a["id"] == "C0":
            b = stats["F0"]
            ns.append({"t": f"Right service {r}%, against {rate(b, 'right')}% for the baseline form",
                       "p": f"Expected: {a['hypothesis']} Observed: too low {lo}% against {rate(b, 'low')}%, gave up {q}% against {rate(b, 'quit')}%.",
                       "q": "", "by": "", "m": "right", "s": "none"})
        else:
            subs = [(rate(stats[x["id"]], "right"), x["id"]) for x in T_ARMS if x["id"] not in ("T0", "CALL")]
            br, bid = max(subs)
            ns.append({"t": f"The benchmark: {r}% right, {lo}% sent too low",
                       "p": f"The simulated call is the bar the substitutes are measured against. The closest substitute is {T_NAME[bid]} at {br}% right and {rate(stats[bid], 'low')}% sent too low.",
                       "q": "", "by": "", "m": "right", "s": "none"})
        notes[L] = ns

    variants = []
    for i, a in enumerate(T_ARMS):
        text = (D / a["file"]).read_text().strip()
        variants.append({"id": LETTERS[i], "name": T_NAME[a["id"]], "field": field_of(a), "note": T_ROLE.get(a["id"], "") + a["one_line"],
                         "vals": {field_of(a): {"text": text, "file": pathlib.Path(a["file"]).name, "words": len(text.split())}}})
    gold = {}
    for v in vig["vignettes"]: gold.setdefault(v["gold_service"], []).append(SHORT[v["id"]])
    s = {
        "name": "111 triage: authored cases",
        "fields": T_FIELDS, "split": True,
        "variants": variants, "nextField": 1, "tab": "form", "dropField": "form", "confirm": None, "diff": False,
        "count": len(P), "vars": [clean(v) for v in vars_],
        "prompt": ("You are {name}, a {age}-year-old {sex} using an NHS service to find out what to do. You are not a clinician and you do not know what is wrong. "
                   "{situation} How you come across: {reporting_style} {health_literacy} {english} {digital_confidence} "
                   "Volunteer only your first words. If a question does not match how you would describe the feeling, answer the question as asked. "
                   "Never add a symptom that is not on your fact sheet. You may stop at any point if a person like you would."),
        "llm": {"model": "claude-opus-5-5", "effort": "medium", "temp": 1, "runs": 1},  # the mock holds one answer per participant per version
        "actions": T_ACTS, "questions": T_QS, "nextQ": 1, "open": None, "main": "right", "metric": None,
        "seed": 17, "running": False, "nextVar": 1, "nextAct": 1,
        "copy": {"who": "Who is asking for help?",
                 "whoHint": "Every participant gets one hidden condition and is never told its name. Sex, age and the mix of conditions can follow real NHS 111 figures. Drag the dividers to change a split.",
                 "acts": "What can happen?",
                 "actsHint": "Where a patient is sent is scored by a fixed judge, not chosen by them. The rest are moves they make on the way, grouped by the type that allows them. Pick one as the main metric: it decides the winner."},
        "judge": {"name": "A fixed judge reads each record and names the service",
                  "why": "The same judge scores every version, so versions differ only in what the patient ends up telling it. The result is right when the service is at the urgency level of the condition's own service, too low when below it, too high when above.",
                  "text": arms["engine"]["prompt"],
                  "labels": [{"name": x["label"], "group": LEVEL[x["level"]]["label"], "share": x.get("real_share"), "note": x.get("real_note", ""),
                              "cases": gold.get(x["id"], [])} for x in exp["services"]],
                  "src": f'Share of real 111 phone outcomes: {exp["services_source"]["label"]}. {exp["services_source"]["note"]}'},
        "notes": notes,
        "caveat": "Mock results. Sampled from assumed effects to show what a run looks like; no model has been run yet. Right answers were written against nhs.uk pages and are not clinician-reviewed.",
    }
    return {"id": "authored", "status": "done", "date": "Today", "preload": False, "toggle": True, "label": "Authored cases: 111 triage on 17 written conditions", "s": s, "people": people, "strings": tb.strings, "rows": tb.rows}


# ---------- run 2: advice message ----------
M_ARMS = msgs["arms"]
M_ACTS = [
    {"id": "proceed", "name": "Do what it says", "on": True, "icon": "yes"},
    {"id": "escalate", "name": "Go to A&E or 999 anyway", "on": True, "bad": True, "icon": "up"},
    {"id": "downgrade", "name": "Do less than it says", "on": True, "bad": True, "icon": "down"},
    {"id": "second_opinion", "name": "Get a second opinion first", "on": True, "bad": True, "icon": "people"},
    {"id": "ignore", "name": "Do nothing", "on": True, "bad": True, "icon": "no"},
]
_detail = {x["id"]: x["detail"] for c in load("actions.json")["classes"] if c["id"] == "message" for x in c["actions"]}
for _a in M_ACTS: _a["desc"] = _detail[_a["id"]]
M_QS = [{"id": "why", "text": "Why did you do that?", "each": True},
        {"id": "when", "text": "When would you actually do it?", "each": False},
        {"id": "urgent", "text": "How serious does this feel now?", "each": False}]
M_SHORT = {
    ("proceed", "trust"): ["NHS said so", "The NHS said so"], ("proceed", "perceived_severity"): ["Sounds serious", "It sounds serious"],
    ("proceed", "access"): ["Made it easy", "It was made easy"], ("proceed", "wait_time"): ["Shorter wait", "A shorter wait"],
    ("escalate", "trust"): ["Want a doctor", "Wanted a doctor"], ("escalate", "perceived_severity"): ["Could be worse", "It could be worse"],
    ("escalate", "past_experience"): ["Sent away before", "Was sent away before"],
    ("downgrade", "perceived_severity"): ["Not that bad", "It's not that bad"], ("downgrade", "access"): ["No way there", "No way to get there"],
    ("downgrade", "wait_time"): ["Won't wait hours", "Won't wait for hours"],
    ("second_opinion", "trust"): ["Ask a person", "Asking a person"], ("second_opinion", "did_not_understand"): ["Too much text", "Way too much text"],
    ("second_opinion", "perceived_severity"): ["Ask family first", "Asking family first"],
    ("ignore", "perceived_severity"): ["It will pass", "This will pass"], ("ignore", "access"): ["No time off", "No time off work"],
    ("ignore", "did_not_understand"): ["Didn't follow it", "Didn't follow"],
}
M_SHORT_BY_TEXT = {  # lines the mock uses when the message lacked the block the usual reason cites
    "I'm not sure what it wants me to do. I'd ask someone.": ["Did not understand", "Did not understand it"],
    "I do not understand some of the words. I would ask.": ["Did not understand", "Did not understand it"],
    "It's easy enough for me to get there.": ["Easy to reach", "Easy for me to reach"],
    "That's close to me anyway.": ["Easy to reach", "Easy for me to reach"],
}
WHEN = {"Right now": "Right now", "Later today": "Later today", "In the next few days": "Next few days", "Not at all": "Not at all"}
URG = {5: "Life-threatening", 4: "Serious", 3: "Needs seeing today", 2: "Minor", 1: "Nothing much"}


def fill(template, v):
    parts = {**msgs["by_service"][v["gold_service"]], **v["advice"]}
    out = template
    for k, x in parts.items(): out = out.replace("{" + k + "}", x)
    return out.strip()


def build_message():
    vars_ = [axis_var("sex"), axis_var("age_band"), case_var(), axis_var("reporting_style"), axis_var("health_literacy"),
             axis_var("english"), axis_var("nhs_trust"), axis_var("access")]
    order, people = people_for(vars_)
    acts, qs = [a["id"] for a in M_ACTS], [q["id"] for q in M_QS]
    tb = Table(order, acts, qs)
    vix = {a["id"]: i for i, a in enumerate(M_ARMS)}
    stats = {a["id"]: [] for a in M_ARMS}
    for run in res["message_runs"]:
        p = P[run["patient_id"]]; v = VIG[p["vignette_id"]]; pr = p["profile"]
        short = R.choice(M_SHORT_BY_TEXT.get(run["reason_text"]) or M_SHORT[(run["action"], run["reason_code"])])
        ans = [("why", run["action"], run["reason_text"], short),
               ("when", None, "Not at all." if run["when_act"] == "Not at all" else f'{run["when_act"]}.', WHEN[run["when_act"]]),
               ("urgent", None, f'{run["perceived_urgency"]} out of 5.', URG[run["perceived_urgency"]])]
        tb.add(vix[run["arm"]], run["patient_id"], [run["action"]], ans)
        stats[run["arm"]].append((pr, run["action"], short, run["reason_text"], people[tb.pid[run["patient_id"]]][0], v))

    rate = lambda rows, o: pct(sum(1 for r in rows if r[1] in ([o] if isinstance(o, str) else o)), len(rows))
    now = lambda rows: [r for r in rows if r[5]["gold_service"] in ACT_NOW]
    down = lambda rows: [r for r in rows if r[5]["gold_service"] not in ACT_NOW]
    PH = {("reporting_style", "stoic"): "stoic patients", ("reporting_style", "neutral"): "plain reporters", ("reporting_style", "anxious"): "anxious patients",
          ("english", "limited"): "patients with limited English", ("english", "fluent"): "fluent English speakers",
          ("nhs_trust", "low"): "patients with low trust in NHS advice", ("nhs_trust", "high"): "patients with high trust",
          ("access", "hard"): "patients with hard access to care", ("access", "easy"): "patients with easy access"}
    VID = {"reporting_style": "style", "english": "english", "nhs_trust": "trust", "access": "access"}
    cap = lambda s: s[0].upper() + s[1:]
    b0 = stats["M0"]
    notes = {}
    for i, a in enumerate(M_ARMS):
        rows, L = stats[a["id"]], LETTERS[i]
        ns = []
        n, d = now(rows), down(rows)
        ns.append({"t": f"Urgent cases: {rate(n, 'proceed')}% followed it. Step-down cases: {rate(d, 'proceed')}%",
                   "p": f"When the advice was urgent (999, A&E, same-day care), {rate(n, ['downgrade', 'ignore'])}% did less or nothing. When it was to step down (GP, pharmacy, self-care), {rate(d, 'escalate')}% went to A&E or 999 anyway.",
                   "q": "", "by": "", "m": "proceed", "s": "case"})
        best = None
        for ax in VID:
            segs = [(rate([x for x in rows if x[0][ax] == l["id"]], "proceed"), l["id"]) for l in axis(ax)["levels"]]
            top, bot = max(segs), min(segs)
            if not best or top[0] - bot[0] > best[0]: best = (top[0] - bot[0], ax, top, bot)
        gap, ax, top, bot = best
        ex = typical([x for x in rows if x[0][ax] == bot[1] and x[1] != "proceed"])
        ns.append({"t": f"{cap(PH[(ax, bot[1])])} followed it least: {bot[0]}%",
                   "p": f"{cap(PH[(ax, top[1])])}: {top[0]}%. That {gap}-point gap is the widest between any two groups for this message.",
                   "q": ex[3] if ex else "", "by": ex[4] if ex else "", "m": ex[1] if ex else "proceed", "s": VID[ax]})
        if a["id"] == "M0":
            ns.append({"t": f"Anchor: {rate(d, 'escalate')}% went to A&E anyway, real callers 11%",
                       "p": "Among real 111 callers told to use primary care or self-care, about 11% attend an emergency department anyway (Lewis 2021). The bare message should land near that.",
                       "q": "", "by": "", "m": "escalate", "s": "none"})
        else:
            ns.append({"t": f"Followed by {rate(rows, 'proceed')}%, against {rate(b0, 'proceed')}% for the bare directive",
                       "p": f"What it adds: {a['changes_from_baseline']} Expected: {a['hypothesis']} Observed: A&E anyway on step-down cases {rate(d, 'escalate')}% against {rate(down(b0), 'escalate')}%; did less or nothing on urgent cases {rate(n, ['downgrade', 'ignore'])}% against {rate(now(b0), ['downgrade', 'ignore'])}%.",
                       "q": "", "by": "", "m": "proceed", "s": "none"})
        notes[L] = ns

    blocks = {c["id"]: c["label"].lower() for c in msgs["components"]}
    variants = []
    for i, a in enumerate(M_ARMS):
        tpl = (D / a["file"]).read_text().strip()
        variants.append({"id": LETTERS[i], "name": {"M0": "Bare directive", "M1": "+ Reason", "M2": "+ Safety net", "M3": "+ Made easy", "M4": "+ Consequence", "M5": "+ Authority", "M6": "All combined"}[a["id"]],
                         "note": "Blocks: " + ", ".join(blocks[c] for c in a["components"]) + ". Each block is filled in for the patient's own condition and service.",
                         "vals": {"f1": {"text": tpl, "file": pathlib.Path(a["file"]).name, "words": len(tpl.split())},
                                  "f2": {"text": fill(tpl, VIG["P1"]), "file": ""}, "f3": {"text": fill(tpl, VIG["E1"]), "file": ""}}})
    s = {
        "name": "Which advice message gets followed?",
        "fields": [{"id": "f2", "name": "Message, pharmacy example", "type": "text"}, {"id": "f3", "name": "Message, 999 example", "type": "text"},
                   {"id": "f1", "name": "Template", "type": "file"}],
        "variants": variants, "nextField": 4, "tab": "f2", "dropField": "f2", "confirm": None, "diff": False,
        "count": len(P), "vars": [clean(v) for v in vars_],
        "prompt": ("You are {name}, a {age}-year-old {sex}. {situation} How you come across: {reporting_style} {health_literacy} {english} {nhs_trust} {access} "
                   "You have just finished an NHS 111 online check about how you feel, and a message appears on your screen. "
                   "Decide what you do next. Answer as the person you are, not as the person you think you should be."),
        "actions": M_ACTS, "questions": M_QS, "nextQ": 1, "open": None, "main": "proceed", "metric": None,
        "seed": 23, "running": False, "nextVar": 1, "nextAct": 1,
        "copy": {"who": "Who gets the message?",
                 "whoHint": "The same patients as the triage run. Every message names the right service for that patient's condition, so a wrong triage cannot blur the effect of the wording.",
                 "acts": "What can they do next?",
                 "actsHint": "Each patient picks exactly one. Following the advice is the main metric: it decides the winner."},
        "notes": notes,
        "caveat": "Mock results. Sampled from assumed effects to show what a run looks like; no model has been run yet. Place names, distances and waiting times in the messages are invented placeholders.",
    }
    return {"id": "advice", "status": "done", "date": "Today", "preload": False, "label": "111 advice messages", "s": s, "people": people, "strings": tb.strings, "rows": tb.rows}


# ---------- the main run: real patients, the real nurse as control, our substitutes, then the advice messages ----------
M_NAME = {"M0": "Message: bare", "M1": "Message: + reason", "M2": "Message: + safety net", "M3": "Message: + made easy",
          "M4": "Message: + consequence", "M5": "Message: + authority", "M6": "Message: all combined"}
TRIAGE_TYPES = ["form", "chat", "real"]
# the main run tests the substitutes against the real nurse. The simulated 111 call and "no tool" are left out:
# they were simulated references, and the real nurse now does that job with measured data.
MAIN_ARMS = [a for a in T_ARMS if a["id"] not in ("T0", "CALL")]
MAIN_FIELDS = [f for f in T_FIELDS if f["id"] in ("form", "chat")]
# one real patient, to show what a filled-in message looks like: tummy pain, 6 out of 10, right level 3, so A&E
MSG_EXAMPLE = {"gold_service": "ae", "advice": {
    "reason": "You told us you have pain in your tummy and that it is about 6 out of 10. Pain like this needs a doctor to examine you today.",
    "safety_net": "If the pain suddenly gets much worse, you faint, or you are sick and cannot keep anything down, call 999."}}
CTL_LABEL = {"vital_signs": "blood pressure, pulse or oxygen", "main_problem": "what the main problem is", "pain_severity": "how bad the pain is", "injury": "whether there was an accident",
             "alertness": "how alert the patient is", "fever": "a temperature", "racing_heart": "the heartbeat", "faintness": "feeling faint"}
NHS_ROUTE = {1: "999 ambulance", 2: "A&E, straight away", 3: "A&E", 4: "Urgent treatment centre or urgent GP", 5: "GP or pharmacy"}
NURSE_TEXT = """REAL RECORD, NOT A TEXT SHOWN TO PARTICIPANTS

What happened: a triage nurse in one of two Korean emergency departments saw this patient in person between October 2016
and September 2017 and gave a level on the Korean Triage and Acuity Scale (KTAS), 1 (resuscitation) to 5 (non-urgent).

What the nurse had: the patient in front of them, the complaint, alertness, the pain score, and measured blood pressure,
pulse, breathing rate, temperature and, for about half the patients, oxygen saturation.

What it is scored against: the level three triage experts gave the same record afterwards.

Source: Moon S-H, Shim JL, Park K-S, Park C-S (2019). Triage accuracy and causes of mistriage using the Korean Triage and
Acuity Scale. PLOS ONE 14(9): e0216972. CC BY 4.0. 1,267 records."""


MODEL_NAME = {"claude-haiku-5-5": "Claude Haiku 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-opus-5-5": "Claude Opus 5.5", "claude-fable-5-2": "Claude Fable 5.2"}


def build_main():
    cs, cr = json.loads((D / "control" / "cases.json").read_text()), json.loads((D / "control" / "results.json").read_text())
    cases = cs["cases"]; CASE = {c["id"]: c for c in cases}; PC = cr["patients"]; n = len(cases)
    # a real run (scripts/run_real.py) replaces the mock rows of every form, chat and message; the nurse's rows are real either way
    rp = D / "control" / "results_real.json"
    real = json.loads(rp.read_text()) if rp.exists() else None
    LABEL.update(CTL_LABEL)
    src = cs["source"]
    REAL = f'Real: taken from each patient\'s record ({src["label"]}).'

    def real_var(vid, key, name, levels, get, says=None, note=REAL):
        """levels: [(id, label)]; get(case) -> level id"""
        k = [sum(1 for c in cases if get(c) == l) for l, _ in levels]
        pcts = shares(k)
        return {"id": vid, "key": key, "name": name, "_get": get, "_levels": [l for l, _ in levels],
                "opts": [{"name": lab, "pct": q, **({"say": says[i]} if says else {})} for i, ((_, lab), q) in enumerate(zip(levels, pcts))],
                "note": note, "ref": {"pcts": pcts, "src": f'{src["label"]}; {src["what"]}', "url": src["url"]}}

    band = lambda c: PC[c["id"]]["profile"]["age_band"]
    pain = lambda c: "none" if not c["real"]["pain_score"] else "mild" if c["real"]["pain_score"] <= 3 else "moderate" if c["real"]["pain_score"] <= 6 else "severe"
    arr = lambda c: {"walked in": "walk", "private vehicle": "car", "public ambulance": "amb", "private ambulance": "amb"}.get(c["real"]["arrival"], "other")
    groups = list(cs["groups"].items())
    vars_ = [
        real_var("sex", "sex", "Sex", [("female", "Female"), ("male", "Male")], lambda c: c["real"]["sex"], ["woman", "man"]),
        real_var("age", "age", "Age", [(l["id"], l["label"]) for l in axis("age_band")["levels"]], band),
        real_var("case", "situation", "Problem", groups, lambda c: c["derived"]["group"],
                 [f"Your problem is of this kind: {lab.lower()}. Your first words and your private fact sheet come from your own record." for _, lab in groups],
                 note="Real, grouped by us: each patient's recorded complaint, sorted into eleven kinds. What the patient says is written by rule from the record, one line per recorded field; the published file holds no conversation."),
        real_var("level", "right_level", "Right level", [(k, f"{k}: {KTAS_NAME[k]}") for k in (1, 2, 3, 4, 5)], lambda c: c["real"]["ktas_expert"],
                 note="Real and hidden from the participant: the level three triage experts gave the record. Levels 1 to 3 count as emergency, 4 and 5 as non-emergency. Nobody here is a pharmacy or self-care case, because everyone went to an emergency department."),
        real_var("pain", "pain", "Pain score", [("none", "No pain"), ("mild", "Mild, 1 to 3"), ("moderate", "Moderate, 4 to 6"), ("severe", "Severe, 7 to 10")], pain,
                 ["You are not in pain.", "Your pain is mild.", "Your pain is moderate.", "Your pain is severe."]),
        real_var("arrival", "arrival", "How they arrived", [("walk", "Walked in"), ("car", "Private vehicle"), ("amb", "Ambulance"), ("other", "Other")], arr),
    ]
    for aid in ("reporting_style", "health_literacy", "english", "digital_confidence", "nhs_trust", "access"):
        v = axis_var(aid); v["_get"] = (lambda a: lambda c: PC[c["id"]]["profile"][a])(aid)
        v["note"] = "Synthetic: not in the record. Drawn at random in equal groups, as in the main run."
        vars_.append(v)

    order = [c["id"] for c in cases]
    people = []
    for c in cases:
        pr = PC[c["id"]]["profile"]; r = c["real"]
        traits = [r["complaint"].lower() if c["derived"]["complaint_readable"] else "complaint not recorded", f'pain {r["pain_score"]}/10']
        if c["derived"]["respondent"] == "other": traits.append("someone else answers")
        if pr["reporting_style"] == "stoic": traits.append("plays things down")
        if pr["reporting_style"] == "anxious": traits.append("fears the worst")
        if pr["health_literacy"] == "low": traits.append("low health literacy")
        if pr["english"] == "limited": traits.append("limited English")
        if pr["digital_confidence"] == "low": traits.append("low digital confidence")
        if pr["nhs_trust"] == "low": traits.append("low trust")
        if pr["access"] == "hard": traits.append("hard access")
        name = f'{NAMES[h(c["id"]) % len(NAMES)]} {"ABCDEFGHJKLMNPRSTW"[h("s" + c["id"]) % 18]}.'
        people.append([", ".join([name, str(r["age"]), r["sex"], *traits]), [v["_levels"].index(v["_get"](c)) for v in vars_]])

    acts = [a for a in json.loads(json.dumps(T_ACTS)) if a["id"] in ("right", "low", "high", "quit")]   # the four that decide a roll-out
    for a in acts:
        if a.get("fields"): a["fields"] = [f for f in a["fields"] if f in ("form", "chat")]
        a["desc"] = {"right": "The level given equals the expert panel's level.", "low": "The level given is less urgent than the expert panel's. The safety risk.",
                     "high": "The level given is more urgent than the expert panel's. Adds demand."}.get(a["id"], a["desc"])
        if a["id"] in ("right", "low", "high"):
            a["name"] = {"right": "Given the right level", "low": "Given too low a level", "high": "Given too high a level"}[a["id"]]
            a["fields"] = TRIAGE_TYPES   # the triage scores do not apply to an advice message
    acts += [{"id": "proceed", "name": "Went as told", "on": True, "icon": "yes", "fields": ["msg"], "desc": "Goes to emergency care as the message says, in the time it gives."},
             {"id": "notgo", "name": "Did not go", "on": True, "bad": True, "icon": "no", "fields": ["msg"], "desc": "Waits, asks someone else first, or does nothing."}]
    QS = [T_QS[0], T_QS[2], M_QS[1]]   # one shared "why", what a substitute never asked, when they would go
    aids, qs = [a["id"] for a in acts], [q["id"] for q in QS]
    # What a patient does is not what is measured. The six above are the metrics: three set by the judge, three counted
    # from what patients do. These are the things a patient can do with each type (role "do"): offered in the prompt, never ranked.
    # They go after the metrics, so the rows of results still point at the same six.
    DO = {"form": [("answer", "Tick an answer", "yes", "Picks one of the listed options."),
                   ("own_words", "Write in own words", "quote", "Types into a free-text box."),
                   ("not_sure", "Tick \u201cNot sure\u201d", "help", "Does not know which option fits."),
                   ("skip", "Skip a question", "skip", "Leaves it unanswered and moves on."),
                   ("give_up", "Give up part-way", "away", "Closes the form before the end.")],
          "chat": [("reply", "Answer the question", "comment", "Replies to what was asked."),
                   ("vague", "Give a vague answer", "wave", "\u201cA bit\u201d, \u201cnot really\u201d, \u201cprobably nothing\u201d."),
                   ("dont_know", "Say \u201cI don't know\u201d", "help", "Cannot answer what was asked."),
                   ("add_more", "Mention something else", "quote", "Brings up a symptom nobody asked about."),
                   ("stop", "Stop replying", "away", "Leaves the chat before it ends.")],
          "msg": [("go_now", "Go now", "yes", "Sets off for emergency care in the time the message gives."),
                  ("go_later", "Go later", "hourglass", "Means to go, but waits first."),
                  ("ask_first", "Ask someone first", "phone", "Rings a GP or a relative before deciding."),
                  ("do_nothing", "Do nothing", "no", "Stays at home.")]}
    FROM = {"quit": ["give_up", "stop"], "proceed": ["go_now"], "notgo": ["go_later", "ask_first", "do_nothing"]}
    for a in acts:
        if a["id"] in FROM: a["from"] = FROM[a["id"]]
    acts += [{"id": i, "name": nm, "on": True, "icon": ic, "fields": [f], "desc": d, "role": "do"} for f, rows in DO.items() for i, nm, ic, d in rows]
    tb = Table(order, [a["id"] for a in acts], qs)
    ARMS = [a["id"] for a in MAIN_ARMS] + ["NURSE"] + [a["id"] for a in M_ARMS]
    told = {c["id"] for c in cases if c["real"]["ktas_expert"] <= 3}   # the closing message is tested on patients told to go to emergency care
    vix = {a: i for i, a in enumerate(ARMS)}
    lvl = lambda rank_: f"level {5 - rank_}, {KTAS_NAME[5 - rank_].lower()}"
    CAUSE = {4: ("Pain score misapplied", "Record: the experts' comment was that the pain score had been applied wrongly to the scale."),
             2: ("Symptoms misjudged", "Record: the experts' comment was that the physical symptoms that go with the complaint had been misjudged.")}
    for run in (real["triage_runs"] if real else []):
        # a real row: the judge's level against the expert panel's, what the patient did, and their own answers afterwards
        c = CASE[run["patient_id"]]; gr = 5 - c["real"]["ktas_expert"]
        out = "quit" if run["final_action"] == "abandon" else "right" if run["disposition"] == gr else "low" if run["disposition"] < gr else "high"
        ans = [("why", out, run["why"], run["why_short"])]
        if run.get("unasked"): ans.append(("unasked", None, run["unasked"], run.get("unasked_short") or "Other"))
        tb.add(vix[run["arm"]], c["id"], [out] + run["moves"], ans)
    for run in (real["message_runs"] if real else []):
        c = CASE[run["patient_id"]]; did = "proceed" if run["action"] == "go_now" else "notgo"
        tb.add(vix[run["arm"]], c["id"], [did, run["action"]], [("why", did, run["why"], run["why_short"]), ("when", None, run["when"], run["when_short"])])
    for run in cr["triage_runs"]:
        c = CASE[run["patient_id"]]; pr = PC[c["id"]]["profile"]; arm = run["arm"]; gr = 5 - c["real"]["ktas_expert"]
        if arm not in vix or (real and arm != "NURSE"): continue
        if run["final_action"] == "abandon": out = "quit"
        else: out = "right" if run["disposition"] == gr else "low" if run["disposition"] < gr else "high"
        if arm == "NURSE":
            if out == "right": short, full = "Matched the experts", "Record: the nurse's level matched the expert panel's. No comment is recorded for a correct decision."
            else: short, full = CAUSE.get(run["error_group"], ("Other recorded cause", f'Record: cause code {run["error_group"]} in the published file. The paper\'s text describes only the two most common causes.'))
            tb.add(vix[arm], c["id"], [out], [("why", out, full, short)])
            continue
        v = {"gold_service": "self_care" if gr == 0 else "ae", "facts": c["derived"]["facts"]}   # t_why only asks whether the case is minor
        short, full = t_why(run, v, pr, out)
        ans = [("why", out, full, short)]
        na = next((m for m in run["misses"] if m["tag"] == "never_asked"), None)
        if na and out == "low":
            lab = LABEL.get(na["concept"], "that")
            ans.append(("unasked", None, f"It never asked about {lab}.", lab[0].upper() + lab[1:]))
        elif out != "quit":
            ans.append(("unasked", None, R.choice(["No, it covered everything I had.", "No, I think it asked about everything."]), R.choice(["Nothing missed", "Nothing was missed"])))
        tb.add(vix[arm], c["id"], [out], ans)
    for run in ([] if real else cr["message_runs"]):
        c = CASE[run["patient_id"]]; pr = PC[c["id"]]["profile"]
        if c["id"] not in told: continue
        short = R.choice(M_SHORT_BY_TEXT.get(run["reason_text"]) or M_SHORT[(run["action"], run["reason_code"])])
        did = "proceed" if run["action"] == "proceed" else "notgo"
        tb.add(vix[run["arm"]], c["id"], [did],
               [("why", did, run["reason_text"], short),
                ("when", None, "Not at all." if run["when_act"] == "Not at all" else f'{run["when_act"]}.', WHEN[run["when_act"]])])

    k = cs["nurse"]; A = cs["assumptions"]

    nurse_text = NURSE_TEXT + f"""

Result: the nurse's level matched the experts' for {k["agree"]:,} of {k["n"]:,} patients ({k["agree"] * 100 / k["n"]:.1f}%), was too low for {k["under"]} and too high for {k["over"]}.

Assumptions when this nurse is used as the control:
1. A Korean emergency nurse stands in for the 111 call handler a substitute would replace.
2. The expert panel's level is the right answer.
3. {"The nurse measured vital signs. A form or chat cannot: a patient can only say what they could know themselves." if real else f'The nurse measured vital signs. A form or chat cannot, so for the {A["abnormal_vitals"]} patients with an abnormal reading it is assumed to go one level too low {int(A["unseen"] * 100)}% of the time.'}
4. {"Each patient is played by a model that knows only a fact sheet written by rule from their record." if real else "What each patient says to a form or chat is written by rule from their record."}
5. Everyone here went to an emergency department, so nothing here tests pharmacy or self-care advice."""
    variants = []
    for a in MAIN_ARMS:
        text = (D / a["file"]).read_text().strip()
        variants.append({"id": LETTERS[len(variants)], "name": T_NAME[a["id"]], "field": field_of(a), "note": a["one_line"],
                         "vals": {field_of(a): {"text": text, "file": pathlib.Path(a["file"]).name, "words": len(text.split())}}})
    variants.append({"id": LETTERS[len(variants)], "name": "Triage nurse (real)", "field": "real", "role": "control",
                     "note": "Real control. What an emergency-department nurse decided for each of these patients, face to face and with measured vital signs.",
                     "vals": {"real": {"text": nurse_text, "file": "moon2019_ktas.csv", "words": len(nurse_text.split())}}})
    blocks = {c["id"]: c["label"].lower() for c in msgs["components"]}
    for a in M_ARMS:
        text = fill((D / a["file"]).read_text().strip(), MSG_EXAMPLE)
        variants.append({"id": LETTERS[len(variants)], "name": M_NAME[a["id"]], "field": "msg",
                         "note": "Blocks: " + ", ".join(blocks[c] for c in a["components"]) + ". Shown to patients told to go to emergency care, filled in for their own problem; here for one patient with tummy pain at level 3.",
                         "vals": {"msg": {"text": text, "file": pathlib.Path(a["file"]).name, "words": len(text.split())}}})
    by_level = {kk: sum(1 for c in cases if c["real"]["ktas_expert"] == kk) for kk in (1, 2, 3, 4, 5)}
    s = {
        "name": "Which 111 substitute triages best?",
        "fields": MAIN_FIELDS + [{"id": "real", "name": "Real control", "type": "file"}, {"id": "msg", "name": "Closing message", "type": "file", "viz": {"name": "message.html", "src": "viz/message.html"}}], "split": True,
        # the results come in two stages, each with its own versions, its own main score and its own number of patients
        "stages": [{"id": "triage", "name": "Triage", "ask": "Which substitute gives patients the right urgency level?", "main": "right", "types": ["form", "chat", "real"]},
                   {"id": "msg", "name": "Closing message", "ask": "Told to go to emergency care: which message gets them to go?", "main": "proceed", "types": ["msg"]}],
        # how one patient goes through each stage, drawn as a flow on the Prompt page: who asks the questions, who decides.
        # A row is a chain of steps; every row of a stage runs into its "end". A short row reaches it by one long arrow ("via").
        "flow": [
            {"name": "Triage", "rows": [
                [{"t": "Patient", "d": "Speaks from one real emergency record", "ref": "prompt"},
                 {"t": "Form or chat asks", "d": ["Form: its fixed questions, filled in", "Chat: up to 12 questions, one at a time"], "kind": "treat", "out": "may give up part-way"},
                 {"t": "Record", "d": "Only what the patient said"},
                 {"t": "Judge decides", "d": "\u201cGive one urgency level, 1 to 5, from the record alone.\u201d", "kind": "judge", "ref": "judge"}],
                [{"t": "Real nurse", "d": "Control: saw the patient in person", "via": "the level she recorded"}]],
             "end": {"t": "Scored", "d": "Against the expert panel's level: right, too low or too high"}},
            {"name": "Closing message", "rows": [
                [{"t": "Patient", "d": "Told to go to emergency care", "ref": "prompt"},
                 {"t": "Closing message", "d": "One of 7 wordings", "kind": "treat"}]],
             "end": {"t": "Patient decides", "d": "Went as told, or did not go"}}],
        "variants": variants, "nextField": 1, "tab": "form", "dropField": "form", "confirm": None, "diff": False,
        "count": n, "vars": [clean(v) for v in vars_],
        "prompt": ("You are {name}, a {age}-year-old {sex} who needs to find out how urgently to be seen. You are not a clinician and you do not know what is wrong. "
                   "{situation} {pain} How you come across: {reporting_style} {health_literacy} {english} {digital_confidence} {nhs_trust} {access} "
                   "Volunteer only your first words. If a question does not match how you would describe the feeling, answer the question as asked. "
                   "Never add a symptom that is not on your fact sheet. If asked about something your fact sheet does not cover, say you do not know. You may stop at any point if a person like you would."),
        "llm": {"model": "claude-opus-5-5", "effort": "medium", "temp": 1, "runs": 1},
        "actions": acts, "questions": QS, "nextQ": 1, "open": None, "main": "right", "metric": None,
        "seed": 29, "running": False, "nextVar": 1, "nextAct": 1,
        "copy": {"who": "Who is asking for help?",
                 "whoHint": "Each participant is one real emergency-department patient. Sex, age, problem, pain, arrival and the right level come from the record. The six behaviour traits are not in the record and are drawn at random.",
                 "acts": "What can happen?",
                 "actsHint": "Two stages. Triage: the level a patient is given is compared with the expert panel's; the patient does not choose it, but can give up part-way. Closing message: a patient told to go to emergency care either goes or does not."},
        "judge": {"name": "A fixed judge reads each record and names a level from 1 to 5",
                  "why": "The same judge scores every form and chat, so they differ only in what the patient ends up telling it. It answers on the scale the real nurse used, so all of them can be compared with her. Right when the level equals the expert panel's, too low when less urgent, too high when more urgent.",
                  "text": "Read the record of what the patient said. Give one urgency level on the Korean Triage and Acuity Scale:\n1 Resuscitation\n2 Emergent\n3 Urgent\n4 Less urgent\n5 Non-urgent\nUse only what is in the record. Reply with the number.",
                  "labels": [{"name": f"{kk}: {KTAS_NAME[kk]}", "group": ("Emergency · closing message sends to " + NHS_ROUTE[kk]) if kk <= 3 else "Non-emergency · no closing message tested", "share": round(by_level[kk] * 100 / n, 1),
                              "note": f"The NHS route is our mapping, not part of the dataset: {NHS_ROUTE[kk]}", "cases": []} for kk in (1, 2, 3, 4, 5)],
                  "src": f'Share of the {n:,} patients at each level, as set by the expert panel: {src["label"]}.'},
        "notes": {},   # no written-up findings: the page shows the scores and the participants' reasons only
        "caveat": (f"A real run on {len(real['patients'])} of the 1,267 patients, drawn with the same spread of right levels. Each patient was played by {MODEL_NAME[real['models']['patient']]}, speaking from a fact sheet written by rule from their record; "
                   f"the judge was {MODEL_NAME[real['models']['judge']]}. The nurse's decisions and the right levels are real (Moon 2019) and cover all 1,267."
                   if real else "The patients, the nurse's decisions and the right levels are real (Moon 2019, 1,267 emergency-department records). The results for the forms, chats and messages are simulated from assumed effects: no model has been run yet. What each patient says is written by rule from their record."),
    }
    return {"id": "triage", "status": "done", "date": "Today", "preload": True, "label": "111 substitution", "s": s, "people": people, "strings": tb.strings, "rows": tb.rows}


JS = """/* Generated by scripts/build_platform_runs.py from data/*.json and data/results/MOCK_results.json.
   Do not edit by hand: change the data and run the script again.
   Runs for the platform prototype (index.html), in its own scenario shape. The nurse's rows are real. The other rows of the main run are real
   when data/control/results_real.json exists (scripts/run_real.py), and MOCK otherwise. The two older runs are MOCK. */
(function () {
  const RAW = %s;
  window.STANDIN_IMPORTS = RAW.map(r => ({ id: r.id, status: r.status, date: r.date, preload: r.preload, toggle: r.toggle, label: r.label, s: r.s, responses() {
    if (!r.list) {
      const vars = r.s.vars.map(v => v.id), acts = r.s.actions.map(a => a.id), qs = r.s.questions.map(q => q.id);
      const prof = r.people.map(p => Object.fromEntries(vars.map((id, i) => [id, p[1][i]])));
      r.list = r.rows.map(([v, p, a, ans]) => ({ variant: r.s.variants[v].id, participant: p + 1, persona: r.people[p][0], profile: prof[p], actions: a.map(i => acts[i]),
        answers: ans.map(([q, x, f, sh]) => ({ question: qs[q], action: x < 0 ? null : acts[x], full: r.strings[f], short: r.strings[sh] })) }));
    }
    return r.list;
  } }));
})();
"""
_authored, _advice = build_triage(), build_message()   # built first, so their wording picks stay as they were
runs = [build_main(), _advice, _authored]
for _r in runs: _r["s"]["notes"] = {}   # the written-up finding cards are switched off for every triage run
out = D / "triage-runs.js"
out.write_text(JS % json.dumps(runs, ensure_ascii=False, separators=(",", ":")))
for r in runs:
    print(r["id"], len(r["s"]["variants"]), "versions,", len(r["people"]), "people,", len(r["rows"]), "rows,", len(r["strings"]), "strings")
print("wrote", out.relative_to(ROOT), f"{out.stat().st_size / 1024:.0f} KB")
