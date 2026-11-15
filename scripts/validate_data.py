"""Cross-check the experiment data files. Exit 1 on any error."""
import json, pathlib, sys

D = pathlib.Path(__file__).resolve().parent.parent / "data"
load = lambda n: json.loads((D / n).read_text())
exp, vig, forms, arms, prof, acts, msgs = (load(n) for n in (
    "experiment.json", "vignettes.json", "form_questions.json", "triage_arms.json",
    "profiles.json", "actions.json", "messages.json"))
errors = []
services = {s["id"] for s in exp["services"]}
modules = {m["id"]: m for m in forms["modules"]}
screen_concepts = {i["concept"] for i in forms["emergency_screen"]["items"]}

def concepts(module):
    out = set()
    for q in module["questions"]:
        out.add(forms["scales"][q["scale"]]["concept"] if q["type"] == "scale" else q["concept"])
    return out

for q in (q for m in forms["modules"] for q in m["questions"]):
    if q["type"] == "scale":
        if q["scale"] not in forms["scales"]: errors.append(f"{q['id']}: unknown scale")
    elif not (q.get("F0") and q.get("F1")):
        errors.append(f"{q['id']}: needs F0 and F1 text")

for v in vig["vignettes"]:
    if v["gold_service"] not in services: errors.append(f"{v['id']}: bad gold_service")
    asked = set(screen_concepts)
    for m in v["correct_modules"]:
        if m not in modules: errors.append(f"{v['id']}: unknown module {m}"); continue
        asked |= concepts(modules[m])
    for f in v["facts"]:
        if f["critical"] and f["concept"] not in asked:
            errors.append(f"{v['id']}: critical fact '{f['concept']}' has no question in {v['correct_modules']}")
    # every module question should have an answer on the fact sheet
    have = {f["concept"] for f in v["facts"]}
    for m in v["correct_modules"]:
        for c in concepts(modules.get(m, {"questions": []})) - have:
            errors.append(f"{v['id']}: module {m} asks '{c}' but the fact sheet has no answer")
    if not v.get("eligible"): errors.append(f"{v['id']}: missing eligible")
    for f in v["facts"]:
        if f["concept"] not in vig["concept_labels"]: errors.append(f"{v['id']}: no lay label for {f['concept']}")
    for k in ("reason", "safety_net"):
        if not v["advice"].get(k): errors.append(f"{v['id']}: missing advice.{k}")

arm_ids = {a["id"] for a in arms["arms"]}
types = {t["id"] for t in exp["version_types"]}
for a in arms["arms"] + msgs["arms"]:
    if a.get("type") not in types: errors.append(f"{a['id']}: unknown version type")
    if not (D / a["file"]).exists(): errors.append(f"{a['id']}: missing {a['file']} (run scripts/build_versions.py)")
for t in {a["type"] for a in arms["arms"] + msgs["arms"]}:
    if not any(c.get("type") == t for c in acts["classes"]): errors.append(f"actions: no action set for type {t}")
for c in acts["classes"]:
    for a in c["arms"]:
        if a not in arm_ids and not a.startswith("M"): errors.append(f"actions: unknown arm {a}")
comp = {c["id"] for c in msgs["components"]}
for a in msgs["arms"]:
    for c in a["components"]:
        if c not in comp: errors.append(f"{a['id']}: unknown component {c}")
for s in {v["gold_service"] for v in vig["vignettes"]}:
    for c in ("directive", "facilitation", "consequence", "authority"):
        if not msgs["by_service"].get(s, {}).get(c): errors.append(f"messages: {s} missing {c}")

n_q = sum(len(m["questions"]) for m in forms["modules"]) + len(forms["emergency_screen"]["items"])
print(f"{len(vig['vignettes'])} vignettes, {n_q} questions, {len(arms['arms'])} triage arms, "
      f"{len(msgs['arms'])} message arms, {len(prof['axes'])} profile axes")
for e in errors: print("ERROR", e)
sys.exit(1 if errors else 0)
