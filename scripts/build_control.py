"""Build the control set: real emergency-department patients, each with a real nurse's triage level and an
expert panel's correct level, extended into patients our experiment can talk to.

    python3 scripts/build_control.py

Source: Moon S-H, Shim JL, Park K-S, Park C-S (2019), "Triage accuracy and causes of mistriage using the Korean
Triage and Acuity Scale", PLOS ONE 14(9): e0216972, CC BY 4.0. 1,267 adult records from two emergency departments.
The copy in data/control/moon2019_ktas.csv is the one published on Kaggle ("Emergency Service - Triage Application").

What is real, what is derived, what is synthetic (also written into cases.json, per field):
  real       sex, age, how they arrived, injury or not, recorded complaint, alertness, pain score, vital signs,
             diagnosis, the nurse's KTAS level, the expert panel's KTAS level, the recorded cause of a nurse's error
  derived    what the patient says. The record holds a few clinical words ("abd pain"), not the conversation, so
             each line of the fact sheet is written by a fixed rule from one real field (see FACT RULES below)
  synthetic  the behaviour traits (reporting style, health literacy, English, digital confidence), drawn at random
             as in the main experiment, and every result for our own versions: those are MOCK, no model was run

Writes data/control/cases.json and data/control/results.json.
"""
import collections, csv, json, pathlib, random, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import make_mock_results as M

ROOT = pathlib.Path(__file__).resolve().parent.parent
C = ROOT / "data" / "control"
SEED = 23
KTAS = {1: "Resuscitation", 2: "Emergent", 3: "Urgent", 4: "Less urgent", 5: "Non-urgent"}
ARRIVAL = {"1": "walked in", "2": "public ambulance", "3": "private vehicle", "4": "private ambulance"}
MENTAL = {"1": "alert", "2": "responds to voice", "3": "responds to pain", "4": "unresponsive"}
# the NHS route each KTAS level is read as when the advice message is written. Our mapping, not part of the dataset.
ROUTE = {1: "ambulance", 2: "ae", 3: "ae", 4: "utc", 5: "gp"}
# ASSUMPTION: when the record shows an abnormal vital sign, a version that cannot measure anything gives a level
# one step too low this often, even if the patient said everything they could. The nurse measured them.
UNSEEN = .6
GROUPS = {"chest": "Chest pain or palpitations", "breath": "Breathing", "gut": "Tummy and gut", "neuro": "Head, dizziness or weakness",
          "injury": "Injury or wound", "fever": "Fever, cough or infection", "limb": "Back, joint or limb pain",
          "urinary": "Urinary or women's health", "face": "Eye, ear, nose, mouth or skin", "mental": "Mental health or intoxication",
          "other": "Weakness, tests or other"}

# ---------- the recorded complaint, in the patient's own words ----------
# whole complaints first: (group, what the patient would say)
FULL = {
    "dyspnea": ("breath", "I can't get my breath."), "acute dyspnea": ("breath", "I suddenly can't get my breath."),
    "orthopnea": ("breath", "I can't breathe when I lie down."), "hyperventilation": ("breath", "I'm breathing too fast and can't slow it down."),
    "desaturation": ("breath", "I'm short of breath and they said my oxygen is low."), "pneumothorax": ("breath", "I've got a sharp pain in my chest and I can't breathe properly."),
    "hemoptysis": ("breath", "I've been coughing up blood."), "blood tinged sputum": ("breath", "There's blood in what I'm coughing up."),
    "dizziness": ("neuro", "I feel dizzy."), "light headness": ("neuro", "I feel light-headed."),
    "whirling type vertigo": ("neuro", "The room is spinning."), "rotatory vertigo": ("neuro", "The room is spinning."),
    "headache": ("neuro", "I've got a bad headache."), "ha": ("neuro", "I've got a bad headache."), "head pain": ("neuro", "I've got a bad headache."),
    "occipital area headache": ("neuro", "I've got a bad headache at the back of my head."),
    "mental change": ("neuro", "They're not themselves. They've gone confused and drowsy."), "altered mentality": ("neuro", "They're not themselves. They've gone confused and drowsy."),
    "altered mental change": ("neuro", "They're not themselves. They've gone confused and drowsy."), "confusion state": ("neuro", "They've become confused."),
    "confuse mentality": ("neuro", "They've become confused."), "confused mental status": ("neuro", "They've become confused."),
    "mental confusion": ("neuro", "They've become confused."), "confusion mentality": ("neuro", "They've become confused."),
    "drowsy mentality": ("neuro", "They're very drowsy and hard to wake."), "sleeping tendency": ("neuro", "They keep falling asleep and are hard to wake."),
    "decreased activity": ("neuro", "They've stopped moving about and are barely responding."), "behavior change": ("neuro", "They're behaving strangely, not like themselves."),
    "acute delirium": ("neuro", "They've suddenly become confused and agitated."),
    "syncope": ("neuro", "I fainted."), "near syncope": ("neuro", "I nearly fainted."), "loc": ("neuro", "I blacked out."), "loss of consciousness": ("neuro", "I blacked out."),
    "post seizure": ("neuro", "I've had a fit."), "seizure": ("neuro", "I've had a fit."), "convulsion": ("neuro", "I've had a fit."),
    "seizure like activity": ("neuro", "I had something like a fit."), "sezure like motion": ("neuro", "I had something like a fit."),
    "involuntary movt.": ("neuro", "Part of my body keeps moving on its own."),
    "dysarthria": ("neuro", "My speech has gone slurred."), "motor aphasia": ("neuro", "I can't get my words out."), "voice changes": ("neuro", "My voice has changed."),
    "facial palsy": ("neuro", "One side of my face has dropped."), "amnesia": ("neuro", "I can't remember what happened."),
    "motor weakness": ("neuro", "Part of my body has gone weak."), "numbness": ("neuro", "Part of my body has gone numb."),
    "decreased sensory": ("neuro", "I've lost feeling in part of my body."), "lower extremity paraparesis": ("neuro", "Both my legs have gone weak."),
    "limb paresthesia": ("neuro", "I've got pins and needles in my arm or leg."), "hand tingling sense": ("neuro", "My hand is tingling."),
    "cerebral concussion": ("injury", "I banged my head and I've felt off since."),
    "general weakness": ("other", "I feel weak all over."), "weakness": ("other", "I feel weak all over."),
    "fever": ("fever", "I've got a temperature."), "fever & chill": ("fever", "I've got a temperature and the shivers."),
    "fever/chills": ("fever", "I've got a temperature and the shivers."), "f/c, c/s": ("fever", "I've got a temperature, the shivers and a chesty cough."),
    "cough": ("fever", "I've got a cough."), "coughing": ("fever", "I've got a cough."), "cold": ("fever", "I've got a bad cold."),
    "sorethroat": ("fever", "I've got a sore throat."), "throat pain": ("fever", "I've got a sore throat."), "throat discomfort": ("fever", "My throat feels uncomfortable."),
    "myalgia": ("fever", "I ache all over."), "general ache": ("fever", "I ache all over."),
    "vomiting": ("gut", "I keep being sick."), "nausea": ("gut", "I feel sick."), "hematemesis": ("gut", "I've been sick and there was blood in it."),
    "melena": ("gut", "My poo has gone black and tarry."), "hematochezia": ("gut", "There's blood when I go to the toilet."), "anal bleeding": ("gut", "I'm bleeding from my bottom."),
    "diarrhea": ("gut", "I've got diarrhoea."), "watery diarrhea": ("gut", "I've got watery diarrhoea."),
    "abd distension": ("gut", "My tummy has swollen up."), "abdomen distension": ("gut", "My tummy has swollen up."), "distended abdomen": ("gut", "My tummy has swollen up."),
    "abd. distension": ("gut", "My tummy has swollen up."), "foreign body ingestion": ("gut", "I've swallowed something I shouldn't have."),
    "fb in esophagus": ("gut", "Something is stuck in my gullet."), "hiccup": ("gut", "I can't stop hiccuping."),
    "palpitation": ("chest", "My heart is racing."), "chest palpitation": ("chest", "My heart is racing."), "tachycardia": ("chest", "My heart is racing."),
    "with chest discomfort": ("chest", "I've got an uncomfortable feeling in my chest."),
    "vaginal bleeding": ("urinary", "I'm bleeding from down below."), "vaginal spotting": ("urinary", "I'm spotting blood from down below."),
    "vaginal discharge": ("urinary", "I've got a discharge from down below."), "pprom": ("urinary", "I'm pregnant and my waters have broken early."),
    "midmenstrual pain": ("urinary", "I've got pain in the middle of my cycle."),
    "dysuria": ("urinary", "It hurts when I pee."), "voiding pain": ("urinary", "It hurts when I pee."), "voiding difficulty": ("urinary", "I'm struggling to pee."),
    "difficulty in voiding": ("urinary", "I'm struggling to pee."), "voiding failure": ("urinary", "I can't pee at all."), "bladder retention": ("urinary", "I can't pee at all."),
    "hematuria": ("urinary", "There's blood in my pee."), "urinary frequency": ("urinary", "I keep needing to pee."), "urinary sx.-symptom": ("urinary", "Something's wrong when I pee."),
    "oliguria": ("urinary", "I'm hardly passing any pee."), "free voiding": ("urinary", "I've got a problem with peeing."), "penile erection": ("urinary", "I've got an erection that won't go down."),
    "urticarial rash": ("face", "I've come out in itchy hives."), "generalized urticaria": ("face", "I've come out in itchy hives all over."),
    "skin rash": ("face", "I've got a rash."), "whole body skin rash": ("face", "I've got a rash all over."), "skin eruption": ("face", "I've got a rash."),
    "erythematous papule": ("face", "I've got red spots on my skin."), "itching": ("face", "I'm itching all over."), "itching sensation": ("face", "I'm itching."),
    "drug allergy": ("face", "I think I'm reacting to a medicine."), "bee sting": ("face", "I've been stung by a bee."), "painful skin lesion": ("face", "I've got a sore patch on my skin."),
    "skin defect": ("injury", "I've lost a piece of skin."), "epistaxis": ("face", "I've got a nosebleed that won't stop."), "nasal bleeding": ("face", "I've got a nosebleed that won't stop."),
    "blurred vision": ("face", "My vision has gone blurry."), "visual disturbance": ("face", "Something's wrong with my sight."), "visual acuity abnormality": ("face", "I can't see properly."),
    "decerased visual acuity": ("face", "I can't see properly."), "diplopia": ("neuro", "I'm seeing double."), "sudden hearing loss": ("face", "I've suddenly gone deaf in one ear."),
    "fb in eye": ("face", "I've got something in my eye."), "eye foreign body": ("face", "I've got something in my eye."), "eye discomfort": ("face", "My eye feels uncomfortable."),
    "foreign body sense": ("face", "It feels like something is stuck."), "foreign body sensation in neck": ("face", "It feels like something is stuck in my throat."),
    "foreign body sensation in throat": ("face", "It feels like something is stuck in my throat."), "foreign body in throat": ("face", "Something is stuck in my throat."),
    "fb in pharynx": ("face", "Something is stuck in my throat."), "dental problem": ("face", "I've got a problem with my teeth."), "toothache": ("face", "I've got toothache."), "tooth pain": ("face", "I've got toothache."),
    "gingival bleeding": ("face", "My gums are bleeding."), "oral bleeding": ("face", "My mouth is bleeding."), "dislocation of jaw": ("injury", "My jaw has come out of place."),
    "anxiety": ("mental", "I'm having really bad anxiety."), "depression": ("mental", "I'm feeling very low."), "mood depression": ("mental", "I'm feeling very low."),
    "suicidal attempt": ("mental", "I tried to end my life."), "suicidal ideation": ("mental", "I've been thinking about ending my life."),
    "suicidal thoughts": ("mental", "I've been thinking about ending my life."), "hallucination": ("mental", "I'm seeing or hearing things that aren't there."),
    "delusional idea": ("mental", "They believe things that aren't real."), "alcohol smelling state, drunken state": ("mental", "They've had a lot to drink."),
    "alcohol smell": ("mental", "They've had a lot to drink."), "drug intoxication": ("mental", "I've taken too much of a drug."),
    "sexual violence": ("mental", "I've been sexually assaulted."), "sexual abuse of adult": ("mental", "I've been sexually assaulted."),
    "post-cpr state": ("other", "They collapsed and had to be resuscitated."), "arrest": ("other", "They've collapsed and aren't breathing."),
    "hypoglycemic symptom": ("other", "I'm shaky and sweaty. I think my sugar is low."), "hypoglycemic": ("other", "I'm shaky and sweaty. I think my sugar is low."),
    "high bsl": ("other", "My blood sugar is very high."), "bst high": ("other", "My blood sugar is very high."), "hypertension": ("other", "My blood pressure is very high."),
    "low blood pressure": ("other", "I was told my blood pressure is low."), "abnormal lab.": ("other", "I was told a blood test came back wrong."),
    "low hb": ("other", "I was told my blood count is low."), "anemia w/u": ("other", "I was told my blood count is low."), "hyperkalemia": ("other", "I was told a blood test came back wrong."),
    "ascites tapping": ("other", "I'm here to have fluid drained from my tummy."), "for a/tapping": ("other", "I'm here to have fluid drained from my tummy."),
    "for ascites tapping": ("other", "I'm here to have fluid drained from my tummy."), "catheter removal": ("other", "I'm here to have a catheter taken out."),
    "avf malfunction": ("other", "My dialysis line has stopped working."), "avf site bleeding": ("other", "My dialysis line is bleeding."),
    "ptbd malfunction": ("other", "My drain has stopped working."), "ptbd leaukage": ("other", "My drain is leaking."), "perm cath. malfunction": ("other", "My dialysis line has stopped working."),
    "for peg tube change": ("other", "I'm here to have a feeding tube changed."), "for l-tube insertion": ("other", "I'm here to have a feeding tube put in."),
    "po medication": ("other", "I'm here about my medicine."), "for medication": ("other", "I'm here about my medicine."), "medication": ("other", "I'm here about my medicine."),
    "for iv injection": ("other", "I'm here for an injection."), "ct film copy": ("other", "I'm here for a copy of my scan."), "copy": ("other", "I'm here for a copy of my records."),
    "for examination": ("other", "I'm here to be checked over."), "swelling": ("other", "Part of me has swollen up."), "femur lesion": ("limb", "Something is wrong with my thigh."),
    "open wound": ("injury", "I've got an open wound."), "scratch wound": ("injury", "I've got a scratch that needs looking at."), "needle stick injury": ("injury", "I pricked myself with a used needle."),
    "chemical burn": ("injury", "I've been burned by a chemical."), "head trauma": ("injury", "I've hit my head."), "head injury": ("injury", "I've hit my head."),
    "eye trauma": ("injury", "I've hurt my eye."),
}
# then single words, turned into the words a patient would use
SITE = {"abd": "tummy", "abd.": "tummy", "abdomen": "tummy", "abdominal": "tummy", "epigastric": "upper tummy", "periumbilical": "tummy around the belly button",
        "ruq": "upper right tummy", "rlq": "lower right tummy", "llq": "lower left tummy", "luq": "upper left tummy", "flank": "side",
        "ocular": "eye", "facial": "face", "nasal": "nose", "gingival": "gum", "mandibular": "jaw", "tmj": "jaw", "coccygeal": "tailbone",
        "scrotal": "testicle", "testis": "testicle", "pelvic": "pelvis", "?nus": "bottom", "ant.": "", "anterior": "",
        "post": "", "low": "lower", "quadrant": "", "abd.pain": "tummy", "lac.": "cut", "otalgia": "ear pain", "backache": "back pain",
        "area": "", "acute": "", "joint": "", "wall": "", "sense": "", "wound": "", "diffuse": "", "generalized": ""}
SIDES = {"lt": "left", "lt.": "left", "l": "left", "left": "left", "rt": "right", "rt.": "right", "right": "right", "rigth": "right", "both": "both"}
KINDS = ["pain", "injury", "laceration", "burn", "swelling", "edema", "discomfort", "distension", "bleeding", "numbness", "eczema",
         "retention", "abnormality", "aphasia", "sensory", "erection", "otalgia"]
GROUP_BY_SITE = [("chest", r"\bchest\b"), ("gut", r"\b(tummy|bottom)\b"), ("urinary", r"\b(side|testicle|pelvis)\b"),
                 ("face", r"\b(eyes?|ear|nose|tooth|gum|jaw|chin|lip|face|cheek|throat|eyelids?|eyebrow)\b"), ("neuro", r"\bhead\b")]
HALVES = {"chest", "face", "tummy", "neck", "head", "back", "upper tummy", "lower tummy"}   # "the left side of my chest", not "my left chest"


def third(s):
    """the same line, said by someone answering for the patient"""
    for a, b in ((r"\bI'm\b", "they are"), (r"\bI've\b", "they have"), (r"\bI was\b", "they were"), (r"\bI don't\b", "they don't"),
                 (r"\bI can't\b", "they can't"), (r"\bI\b", "they"), (r"\bmyself\b", "themselves"), (r"\b[Mm]y\b", "their"), (r"\bme\b", "them")):
        s = re.sub(a, b, s)
    return re.sub(r"(^|[.!?] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)


def patient_words(raw, injured):
    """recorded complaint -> (group, what the patient says first, whether the complaint was readable)"""
    c = " ".join(raw.strip().lower().split())
    if not c or "?" in c.replace("?nus", ""):
        return "other", "I don't feel right and I want to be checked.", False
    c = re.sub(r"\s*\((finding|disorder|\+)\)", "", c)
    c = re.sub(r",?\s*\b(nos|undetermined|unspecified)\b", "", c).strip(" ,")
    if c not in FULL:
        m = re.match(r"^(?:[a-z]{1,3}|[a-z]/[a-z])\s*-\s*(.+)$", c)   # "dz - dizziness", "f/c-fever/chills"
        if m: c = m.group(1)
        if c.startswith("di, "): c = c[4:]
    side = ""
    words = []
    for w in re.split(r"[\s]+", c.replace(",", " , ").replace(".", ". ").replace(" .", ".")):
        w = w.strip()
        if w in SIDES: side = SIDES[w]
        elif w: words.append(w)
    c2 = " ".join(words).replace(" , ", ", ").strip(" ,")
    if "," in c2:                                                      # "pain, chest" -> "chest pain"
        a, b = [x.strip() for x in c2.split(",", 1)]
        if a.split()[-1] in KINDS or a in KINDS: c2 = f"{b} {a}".strip()
        elif a == "blood pressure": c2 = f"{b} {a}"
        else: c2 = f"{a} {b}".strip()
    if c2 in FULL or c in FULL:
        g, say = FULL.get(c2) or FULL[c]
        if side in ("left", "right") and c2 == "motor weakness": say = f"My {side} side has gone weak."
        return g, say, True
    toks = []
    for w in c2.split():
        for t in SITE.get(w, w).split():
            if t not in toks: toks.append(t)     # "rlq abd. pain" names the tummy twice
    phrase = " ".join(toks)
    kind = next((k for k in ["cut", "laceration", "burn", "injury", "trauma", "swelling", "edema", "cellulitis", "redness", "weakness", "hemiparesis",
                             "monoparesis", "palsy", "numbness", "discomfort", "bleeding", "pain"] if re.search(rf"\b{k}\b", phrase)), None)
    site = re.sub(r"\b(cut|laceration|burn|injury|trauma|painful|swelling|edema|cellulitis|redness|motor|weakness|hemiparesis|monoparesis|palsy|numbness|discomfort|bleeding|pain|on)\b", "", phrase)
    if kind in ("weakness", "hemiparesis", "monoparesis", "numbness", "palsy"): site = re.sub(r"\bside\b", "", site)
    site = " ".join(site.split())
    if side == "both": w = f"both my {site if site.endswith('s') else site + 's'}" if site else ""
    elif side and site in HALVES: w = f"the {side} side of my {site}"
    elif side and not site: w = f"my {side} side"
    else: w = f"my {side + ' ' if side else ''}{site}" if site else ""
    has = "have" if side == "both" else "has"
    if kind in ("weakness", "hemiparesis", "monoparesis"):
        g, say = "neuro", (f"{w[0].upper() + w[1:]} {has} gone weak." if w else "Part of my body has gone weak.")
    elif kind == "palsy": g, say = "neuro", f"The {side + ' ' if side else ''}side of my face has dropped."
    elif kind == "numbness": g, say = "neuro", (f"{w[0].upper() + w[1:]} {has} gone numb." if w else "Part of my body has gone numb.")
    elif kind in ("cut", "laceration"): g, say = "injury", (f"I've cut {w}." if w else "I've cut myself.")
    elif kind == "burn": g, say = "injury", (f"I've burned {w}." if w else "I've burned myself.")
    elif kind in ("injury", "trauma"): g, say = "injury", (f"I've hurt {w}." if w else "I've hurt myself.")
    elif kind == "redness": g, say = "limb", (f"{w[0].upper() + w[1:]} {has} gone red." if w else "Part of me has gone red.")
    elif kind in ("swelling", "edema", "cellulitis"):
        g, say = "limb", (f"{w[0].upper() + w[1:]} {has} swollen up{' and it hurts' if 'painful' in phrase or kind == 'cellulitis' else ''}." if w else "Part of me has swollen up.")
    elif kind == "bleeding": g, say = "injury", (f"{w[0].upper() + w[1:]} is bleeding." if w else "I'm bleeding.")
    elif kind == "discomfort": g, say = "limb", (f"I've got an uncomfortable feeling in {w}." if w else "I feel uncomfortable.")
    elif kind == "pain": g, say = "limb", (f"I've got pain in {w}." if w else "I'm in pain.")
    else: return ("injury" if injured else "other"), f"I've come in about this: {c2}.", True
    for gid, rx in GROUP_BY_SITE:
        if re.search(rx, site) and g in ("limb", "injury" if not injured else "limb"): g = gid; break
    if injured and g in ("limb", "other"): g = "injury"
    return g, say, True


# ---------- FACT RULES: one line of the fact sheet per real field ----------
def num(x):
    try: return float(str(x).replace(",", "."))
    except ValueError: return None


def abnormal_vitals(r):
    sbp, hr, rr, bt, sat = (num(r[k]) for k in ("SBP", "HR", "RR", "BT", "Saturation"))
    return any([sbp is not None and (sbp < 90 or sbp >= 200), hr is not None and (hr >= 120 or hr < 50), rr is not None and rr >= 24,
                bt is not None and (bt >= 38.5 or bt < 35), sat is not None and sat < 92])


def fact_sheet(r, say, other):
    """other: someone else is answering, because the patient was not alert"""
    who, my = ("They", "their") if other else ("I", "my")
    f = [{"concept": "main_problem", "value": True, "critical": True, "lay": say, "from": "Chief_complain"}]
    nrs = num(r["NRS_pain"]) if r["Pain"] == "1" else 0
    if nrs is None: nrs = 0
    word = "no" if not nrs else "mild" if nrs <= 3 else "moderate" if nrs <= 6 else "severe"
    f.append({"concept": "pain_severity", "value": word, "critical": nrs >= 4, "from": "Pain, NRS_pain",
              "lay": (f"No, {who.lower()}'re not in pain." if other else "No, I'm not in pain.") if not nrs else
                     f"{'They say it is' if other else 'It is'} about {int(nrs)} out of 10. {'Mild, I can put up with it.' if nrs <= 3 else 'It stops me doing things.' if nrs <= 6 else 'It is the worst I have had.'}"})
    f.append({"concept": "injury", "value": r["Injury"] == "2", "critical": r["Injury"] == "2", "from": "Injury",
              "lay": f"Yes, {who.lower()} hurt {'themselves' if other else 'myself'}. It started with an accident." if r["Injury"] == "2" else "No, nothing happened to cause it. It came on by itself."})
    if r["Mental"] != "1":
        f.append({"concept": "alertness", "value": MENTAL[r["Mental"]], "critical": True, "from": "Mental",
                  "lay": {"2": "They only open their eyes when I speak to them, and they are not making sense.",
                          "3": "They do not answer me. They only stir if I pinch or shake them.", "4": "They are not responding at all."}[r["Mental"]]})
    bt, rr, hr, sbp, sat = (num(r[k]) for k in ("BT", "RR", "HR", "SBP", "Saturation"))
    if bt is not None:
        hot = bt >= 38.0
        f.append({"concept": "fever", "value": hot, "critical": bt >= 39.0, "from": "BT",
                  "lay": f"Yes, {who.lower()} feel{'' if who == 'They' or who == 'I' else 's'} hot and shivery. The thermometer said {bt:.1f}." if hot else "No temperature."})
    if rr is not None or sat is not None:
        short = (rr is not None and rr >= 24) or (sat is not None and sat < 92)
        f.append({"concept": "breathlessness", "value": short, "critical": short, "from": "RR, Saturation",
                  "lay": (f"Yes. {who} {'are' if other else 'am'} struggling for breath even sitting still." if short else f"{'Their' if other else 'My'} breathing is fine.")})
    if hr is not None and hr >= 120:
        f.append({"concept": "racing_heart", "value": True, "critical": True, "from": "HR", "lay": f"{'Their' if other else 'My'} heart is pounding very fast."})
    if sbp is not None and sbp < 90:
        f.append({"concept": "faintness", "value": True, "critical": True, "from": "SBP",
                  "lay": f"{who} {'look' if other else 'feel'} faint and clammy, as if about to pass out."})
    return f


def main():
    rng = random.Random(SEED)
    rows = list(csv.DictReader((C / "moon2019_ktas.csv").read_text(encoding="latin-1").splitlines(), delimiter=";"))
    draw = lambda axis: rng.choices([l["id"] for l in axis["levels"]], [l.get("pct", 1) for l in axis["levels"]])[0]
    band = lambda a: next(b for b, (lo, hi) in M.BANDS.items() if a <= hi or b == "80+")
    cases, patients, runs, message = [], {}, [], []
    M.rng = random.Random(SEED + 1)   # the mock outcomes of our versions, on a stream of their own
    r2 = random.Random(SEED + 2)
    kind = {a["id"]: a["type"] for a in M.arms["arms"]}
    for i, r in enumerate(rows):
        cid = f"c{i + 1:04d}"
        age, sex = int(r["Age"]), "female" if r["Sex"] == "1" else "male"
        other = r["Mental"] != "1"
        group, say, readable = patient_words(r["Chief_complain"], r["Injury"] == "2")
        if other and re.search(r"\b(I|I'm|I've|[Mm]y)\b", say):   # a relative or bystander speaks for a patient who is not alert
            say = "They can't tell you themselves. " + third(say)
        facts = fact_sheet(r, say, other)
        expert, nurse = int(r["KTAS_expert"]), int(r["KTAS_RN"])
        profile = {"age_band": band(age), "sex": sex, **{a["id"]: draw(a) for a in M.prof["axes"] if a["id"] not in ("age_band", "sex")}}
        cases.append({
            "id": cid,
            "real": {"sex": sex, "age": age, "arrival": ARRIVAL.get(r["Arrival mode"], "other"), "injury": r["Injury"] == "2",
                     "complaint": r["Chief_complain"].strip(), "alertness": MENTAL[r["Mental"]],
                     "pain_score": int(num(r["NRS_pain"])) if r["Pain"] == "1" and num(r["NRS_pain"]) is not None else 0,
                     "vitals": {k2: num(r[k]) for k, k2 in (("SBP", "sbp"), ("DBP", "dbp"), ("HR", "hr"), ("RR", "rr"), ("BT", "temp"), ("Saturation", "spo2"))},
                     "abnormal_vitals": abnormal_vitals(r),
                     "diagnosis": r["Diagnosis in ED"].strip(), "ktas_nurse": nurse, "ktas_expert": expert,
                     "error_group": int(r["Error_group"].strip() or 0)},
            "derived": {"group": group, "complaint_readable": readable, "respondent": "other" if other else "self", "opening": say, "facts": facts},
            "synthetic": {k: v for k, v in profile.items() if k not in ("age_band", "sex")},
        })
        patients[cid] = {"case_id": cid, "age": age, "profile": profile}
        gr = 5 - expert   # 0 = non-urgent ... 4 = resuscitation
        v = {"facts": facts}
        for a in M.arms["arms"]:
            run = {"patient_id": cid, **M.triage_run(v, profile, a["id"], gr=gr, top=4)}
            if run["final_action"] == "submit" and run["disposition"] == gr and gr > 0 and abnormal_vitals(r) and M.rng.random() < UNSEEN:
                run["disposition"] = gr - 1; run["misses"] = [{"concept": "vital_signs", "tag": "unmeasured"}]
            runs.append(run)
        for run in runs[-len(M.arms["arms"]):]:
            run["moves"] = M.moves_for(run, profile, kind[run["arm"]], r2)
        # the advice message: every message names the route for the patient's right level, so a wrong triage cannot blur it
        for a in M.msgs["arms"]:
            run = {"patient_id": cid, **M.message_run({"gold_service": ROUTE[expert]}, profile, a["id"])}
            run["reason_text"] = M.reason_line(run, r2) or run["reason_text"]
            message.append(run)
        runs.append({"patient_id": cid, "arm": "NURSE", "real": True, "final_action": "submit", "disposition": 5 - nurse,
                     "misses": [], "moves": [], "error_group": int(r["Error_group"].strip() or 0)})

    n = len(rows)
    agree = sum(c["real"]["ktas_nurse"] == c["real"]["ktas_expert"] for c in cases)
    under = sum(c["real"]["ktas_nurse"] > c["real"]["ktas_expert"] for c in cases)
    source = {"label": "Moon et al. 2019, PLOS ONE 14(9): e0216972", "url": "https://doi.org/10.1371/journal.pone.0216972", "licence": "CC BY 4.0",
              "copy": "https://www.kaggle.com/datasets/ilkeryildiz/emergency-service-triage-application",
              "what": "1,267 adult records from two Korean emergency departments, October 2016 to September 2017"}
    (C / "cases.json").write_text(json.dumps({
        "source": source,
        "provenance": {
            "real": "Taken from the record unchanged: sex, age, arrival, injury, recorded complaint, alertness, pain score, vital signs, diagnosis, the nurse's KTAS level, the expert panel's KTAS level, the cause of a nurse's error.",
            "derived": "Written by a fixed rule from one real field, named in each fact's 'from': the patient's opening words (from the recorded complaint) and the fact sheet (pain from the pain score, fever from temperature, breathlessness from breathing rate or oxygen, racing heart from pulse, faintness from blood pressure, alertness from the mental-state code).",
            "synthetic": "Not in the record: the behaviour traits, drawn at random as in the main experiment. Onset, duration, medical history and medicines are not in the published file and are left out of the fact sheet.",
        },
        "limits": ["Everyone here went to an emergency department, so there are no pharmacy or self-care cases.",
                   "The nurse saw the patient and measured blood pressure, pulse, temperature and oxygen. A form or chat gets only what the patient can say.",
                   "The right level is the Korean KTAS scale (1 to 5), not an NHS service.",
                   f"{sum(not c['derived']['complaint_readable'] for c in cases)} complaints were lost in the published file (Korean text saved as question marks); those patients open with a generic line."],
        "levels": [{"ktas": k, "name": v, "rank": 5 - k, "emergency": k <= 3, "nhs_route": ROUTE[k]} for k, v in KTAS.items()],
        "assumptions": {"unseen": UNSEEN, "abnormal_vitals": sum(c["real"]["abnormal_vitals"] for c in cases)},
        "groups": GROUPS,
        "nurse": {"agree": agree, "under": under, "over": n - agree - under, "n": n},
        "cases": cases}, separators=(",", ":")))
    (C / "results.json").write_text(json.dumps({
        "label": "Control set. The NURSE rows are real. Every other row is MOCK: sampled from assumed effects, no model was run.",
        "seed": SEED, "participants": n, "patients": patients, "triage_runs": runs, "message_runs": message}, separators=(",", ":")))
    print(f"{n} cases; nurse agrees with the experts on {agree} ({agree * 100 / n:.1f}%), too low {under}, too high {n - agree - under}")
    by = collections.Counter(c["derived"]["group"] for c in cases)
    print({GROUPS[g]: by[g] for g in GROUPS})
    return cases


if __name__ == "__main__":
    cases = main()
    if "--show" in sys.argv:
        seen = {}
        for c in cases: seen.setdefault((c["real"]["complaint"].lower(), c["derived"]["opening"], c["derived"]["group"]), 0)
        for (raw, say, g) in sorted(seen): print(f"{raw:42s} {g:8s} {say}")
