"""Write the form versions (F0-F3) as plain text files in data/versions/, from the question bank.

A form version is what the participant is given to fill in. Other versions (agent prompts,
the direct question, message templates) are plain text files edited by hand in the same folder.
"""
import json, pathlib

D = pathlib.Path(__file__).resolve().parent.parent / "data"
F = json.loads((D / "form_questions.json").read_text())
norm = lambda x: {"text": x, "options": ["Yes", "No"]} if isinstance(x, str) else x


def question(q, variant):
    if q["type"] == "scale":
        return F["scales"][q["scale"]][variant if variant in ("F1", "F2") else "F0"]
    return norm(q["F1" if variant == "F1" else "F0"])


def form_text(variant):
    lab = "F1" if variant == "F1" else "F0"
    out = ["NHS 111 ONLINE CHECK", "", 'You can answer "Not sure" to any question, or skip it.', "",
           "1. EMERGENCY CHECK", F["emergency_screen"][lab]]
    out += [f"[ ] {i[lab]}" for i in F["emergency_screen"]["items"]]
    out += ["", "2. MAIN SYMPTOM", F["topic_question"][lab]] + [f"( ) {m['label'][lab]}" for m in F["modules"]]
    out += ["", "3. QUESTIONS", "Only the section for the chosen symptom is shown."]
    for m in F["modules"]:
        out += ["", f"--- {m['label'][lab]} ---"]
        if variant == "F3":
            out += [m["describe_prompt"], "[free text]", ""]
        for n, q in enumerate(m["questions"], 1):
            x = question(q, variant)
            out += [f"Q{n}. {x['text']}", "    " + "   ".join(f"( ) {o}" for o in x["options"])]
        if variant == "F3":
            out += ["", F["final_open"], "[free text]"]
    return "\n".join(out) + "\n"


for v in ("F0", "F1", "F2", "F3"):
    (D / "versions" / f"{v}.txt").write_text(form_text(v))
print("wrote F0-F3.txt")
