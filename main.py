"""MindLog — AI journaling assistant for stress and wellbeing (English, Kiswahili, Sheng).

Run:   pip install -r requirements.txt
       uvicorn main:app --reload          then open http://127.0.0.1:8000
Demo:  python main.py                     (prints the analysis of four sample entries, no server)
"""
import csv, datetime as dt, os, random, statistics
from collections import Counter, defaultdict
from typing import List, Optional

import joblib
from mindlog_core import EMOTIONS, detect_crisis, language_of, tag_mood, normalize, _BRIDGE_RE
import reflections as R

HERE = os.path.dirname(os.path.abspath(__file__))
STRESS_SUPPORT_THRESHOLD = 0.85     # with mood <= 2, shows the "extra support" card
TAGS = ["academics", "money", "family", "friends", "relationship", "health", "sleep", "work"]

try:
    BUNDLE = joblib.load(os.path.join(HERE, "mindlog_model.joblib"))
except Exception as exc:  # usually a scikit-learn version mismatch
    raise SystemExit(f"Could not load mindlog_model.joblib ({exc}).\nRebuild it for your scikit-learn version with:  python train_model.py")


def cue_words(text: str) -> dict:
    """The shared English/Kiswahili/Sheng cue words (the lexicon bridge) found in the entry, per emotion.
    Shown to the user so they can see one of the signals behind the label. Whole words, not the regex stems."""
    t = normalize(text)
    out = {}
    for emotion, rx in _BRIDGE_RE.items():
        found = []
        for m in rx.finditer(t):
            a, b = m.start(), m.end()
            while a > 0 and (t[a - 1].isalnum() or t[a - 1] == "'"):
                a -= 1
            while b < len(t) and (t[b].isalnum() or t[b] == "'"):
                b += 1
            w = t[a:b].strip()
            if w and w not in found:
                found.append(w)
        out[emotion] = found[:6]
    return out


def analyze(text: str, mood: int = 3, reply_language: str = "auto", seed: str = "") -> dict:
    """The four-step pipeline: language -> crisis rules -> emotion + stress models -> reflection."""
    language = language_of(text, BUNDLE["word_lang"])
    proba = BUNDLE["emotion"].predict_proba([tag_mood(text, mood)])[0]      # the mood rating is a feature of the emotion model
    classes = list(BUNDLE["emotion"].classes_)
    emotion = classes[int(proba.argmax())]
    stress = float(BUNDLE["stress"].predict_proba([text])[0][1])
    crisis = detect_crisis(text)
    level = "crisis" if crisis else "elevated" if (stress >= STRESS_SUPPORT_THRESHOLD and mood <= 2) else "none"
    out_lang = language if reply_language == "auto" else reply_language
    reflection, tip, lang = R.pick(emotion, out_lang, seed or text, mood)
    check = bool(proba.max() < 0.6 or (emotion in ("neutral", "joy") and mood <= 2) or (emotion in ("anxiety", "sadness", "anger") and mood >= 4))
    result = {
        "language": language,
        "emotion": emotion,
        "confidence": round(float(proba.max()), 3),
        "confidence_word": "likely" if proba.max() >= 0.75 else "possibly" if proba.max() >= 0.5 else "unsure, maybe",
        "probabilities": {c: round(float(p), 3) for c, p in zip(classes, proba)},
        "stress_score": round(stress, 3),
        "support_level": level,
        "crisis_signals": crisis,
        "cue_words": cue_words(text),
        "please_check_label": check,   # low confidence, or the label disagrees with the mood rating
        "reflection": None, "coping_tip": None, "support_message": None, "helplines": [],
    }
    if level == "crisis":                       # no generated reflection: go straight to people who can help
        result["support_message"] = R.CRISIS_MESSAGE[lang]
        result["helplines"] = R.HELPLINES
    else:
        result["reflection"], result["coping_tip"] = reflection, tip
        if level == "elevated":
            result["support_message"] = R.ELEVATED_MESSAGE[lang]
            result["helplines"] = R.HELPLINES
    return result


def dashboard(entries: List[dict], weekly_goal: int, today: Optional[dt.date] = None) -> dict:
    today = today or dt.date.today()
    by_day = defaultdict(list)
    for e in entries:
        by_day[e["created_at"][:10]].append(e)
    days = sorted(by_day)
    series = [{"date": d, "mood": statistics.median(x["mood"] for x in by_day[d]),
               "stress": round(statistics.mean(x["stress_score"] for x in by_day[d]), 3), "entries": len(by_day[d]),
               "sleep": (lambda h: round(statistics.mean(h), 1) if h else None)([x["sleep_hours"] for x in by_day[d] if x.get("sleep_hours") is not None])} for d in days]
    dates = {dt.date.fromisoformat(d) for d in days}
    current, d = 0, today
    if d not in dates:
        d -= dt.timedelta(days=1)            # today not written yet does not break the streak
    while d in dates:
        current, d = current + 1, d - dt.timedelta(days=1)
    longest = run = 0
    prev = None
    for d in sorted(dates):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        longest, prev = max(longest, run), d
    week_start = today - dt.timedelta(days=today.weekday())
    this_week = sum(len(v) for k, v in by_day.items() if dt.date.fromisoformat(k) >= week_start)
    recent = [e["mood"] for e in entries if (today - dt.date.fromisoformat(e["created_at"][:10])).days < 7]
    before = [e["mood"] for e in entries if 7 <= (today - dt.date.fromisoformat(e["created_at"][:10])).days < 14]
    tag_mood = defaultdict(list)
    for e in entries:
        for t in e.get("tags", []):
            tag_mood[t].append(e["mood"])
    habit = [e["habit_done"] for e in entries if e.get("habit_done") is not None]
    slept = [(e["sleep_hours"], e["mood"], e["created_at"][:10]) for e in entries if e.get("sleep_hours") is not None]
    sleep_week = [h for h, _, d in slept if (today - dt.date.fromisoformat(d)).days < 7]
    short, rested = [m for h, m, _ in slept if h < 6], [m for h, m, _ in slept if h >= 7]
    return {
        "total_entries": len(entries), "days_written": len(days), "current_streak": current, "longest_streak": longest,
        "this_week": this_week, "weekly_goal": weekly_goal, "goal_met": this_week >= weekly_goal,
        "median_mood_last_7_days": statistics.median(recent) if recent else None,
        "median_mood_previous_7_days": statistics.median(before) if before else None,
        "emotion_counts": {k: Counter(e["emotion_final"] for e in entries).get(k, 0) for k in EMOTIONS},
        "tags": sorted(({"tag": t, "entries": len(m), "median_mood": statistics.median(m)} for t, m in tag_mood.items()), key=lambda x: (x["median_mood"], -x["entries"])),
        "habit_rate": round(sum(habit) / len(habit), 2) if habit else None,
        "corrections": sum(1 for e in entries if e.get("user_corrected")),
        "sleep": {"logged": len(slept), "avg_last_7_days": round(statistics.mean(sleep_week), 1) if sleep_week else None,
                  "short_nights": len(short), "rested_nights": len(rested),      # under 6 h / 7 h or more
                  "median_mood_short": statistics.median(short) if len(short) >= 3 else None,
                  "median_mood_rested": statistics.median(rested) if len(rested) >= 3 else None},
        "series": series,
    }


# ----------------------------------------------------------------------------- web API
try:
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.responses import FileResponse
    from pydantic import BaseModel, Field
    import store
    FASTAPI = True
except ImportError:
    FASTAPI = False

if FASTAPI:
    app = FastAPI(title="MindLog", version="2.1.0", description=R.DISCLAIMER)
    store.init()

    class Credentials(BaseModel):
        username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
        passphrase: str = Field(min_length=8, max_length=200)

    class Registration(Credentials):
        consent: bool
        research_consent: bool = False

    class EntryIn(BaseModel):
        text: str = Field(min_length=3, max_length=5000)
        mood: int = Field(ge=1, le=5)
        tags: List[str] = Field(default_factory=list, max_length=8)
        habit_done: Optional[bool] = None
        sleep_hours: Optional[float] = Field(default=None, ge=0, le=16)
        reply_language: str = Field(default="auto", pattern="^(auto|English|Kiswahili)$")

    class AnalyzeIn(BaseModel):
        text: str = Field(min_length=3, max_length=5000)
        mood: int = Field(default=3, ge=1, le=5)
        reply_language: str = Field(default="auto", pattern="^(auto|English|Kiswahili)$")

    class Correction(BaseModel):
        emotion: str = Field(pattern="^(joy|anxiety|sadness|anger|neutral)$")

    class Settings(BaseModel):
        weekly_goal: Optional[int] = Field(default=None, ge=1, le=14)
        habit: Optional[str] = Field(default=None, max_length=120)
        research_consent: Optional[bool] = None

    class Passphrase(BaseModel):
        passphrase: str

    def current(authorization: str = Header(default="")):
        s = store.session(authorization.removeprefix("Bearer ").strip())
        if not s:
            raise HTTPException(401, "Please log in again.")
        return s

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(os.path.join(HERE, "static", "index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model": BUNDLE["meta"], "disclaimer": R.DISCLAIMER}

    @app.get("/api/prompt")
    def prompt():
        en, sw = R.PROMPTS[dt.date.today().toordinal() % len(R.PROMPTS)]
        return {"en": en, "sw": sw, "tags": TAGS, "helplines": R.HELPLINES, "disclaimer": R.DISCLAIMER}

    @app.post("/api/analyze")
    def analyze_only(req: AnalyzeIn):
        """Stateless analysis. Nothing is stored."""
        return analyze(req.text, req.mood, req.reply_language)

    @app.post("/api/register")
    def register(req: Registration):
        if not req.consent:
            raise HTTPException(400, "MindLog can only store your entries with your consent.")
        token = store.register(req.username, req.passphrase, req.research_consent)
        if not token:
            raise HTTPException(409, "That username is taken.")
        return {"token": token}

    @app.post("/api/login")
    def login(req: Credentials):
        token = store.login(req.username, req.passphrase)
        if not token:
            raise HTTPException(401, "Wrong username or passphrase.")
        return {"token": token}

    @app.post("/api/logout")
    def logout(authorization: str = Header(default="")):
        store.logout(authorization.removeprefix("Bearer ").strip())
        return {"ok": True}

    @app.get("/api/me")
    def me(s=Depends(current)):
        return store.get_user(s)

    @app.put("/api/settings")
    def settings(req: Settings, s=Depends(current)):
        store.update_settings(s, req.weekly_goal, req.habit, req.research_consent)
        return store.get_user(s)

    def _save(s, text, mood, tags, habit_done, reply_language, created_at=None, demo=False, sleep_hours=None):
        res = analyze(text, mood, reply_language, seed=f"{text}{created_at}")
        record = {"text": text, "mood": mood, "tags": [t.strip().lower()[:24] for t in tags if t.strip()], "habit_done": habit_done, "sleep_hours": sleep_hours,
                  "language": res["language"], "emotion_predicted": res["emotion"], "emotion_final": res["emotion"], "user_corrected": False,
                  "confidence": res["confidence"], "stress_score": res["stress_score"], "support_level": res["support_level"], "demo": demo}
        entry_id = store.add_entry(s, record, created_at)
        return {"id": entry_id, **record, **res}

    @app.post("/api/entries")
    def create_entry(req: EntryIn, s=Depends(current)):
        return _save(s, req.text, req.mood, req.tags, req.habit_done, req.reply_language, sleep_hours=req.sleep_hours)

    @app.get("/api/entries")
    def entries(s=Depends(current)):
        return list(reversed(store.list_entries(s)))

    @app.post("/api/entries/{entry_id}/correct")
    def correct(entry_id: int, req: Correction, s=Depends(current)):
        e = store.get_entry(s, entry_id)
        if not e:
            raise HTTPException(404, "Entry not found.")
        created, eid = e.pop("created_at"), e.pop("id")
        e["emotion_final"], e["user_corrected"] = req.emotion, req.emotion != e["emotion_predicted"]
        store.replace_entry(s, eid, created, e)
        shared = False
        if e["user_corrected"] and store.get_user(s)["research_consent"]:
            store.add_correction(s, eid, e["text"], e["language"], e["emotion_predicted"], req.emotion)
            shared = True
        reflection, tip, _ = R.pick(req.emotion, e["language"], f"{e['text']}{created}", 3)
        return {"id": eid, "emotion_final": req.emotion, "user_corrected": e["user_corrected"], "shared_for_retraining": shared,
                "reflection": None if e["support_level"] == "crisis" else reflection, "coping_tip": None if e["support_level"] == "crisis" else tip}

    @app.delete("/api/entries/{entry_id}")
    def delete_entry(entry_id: int, s=Depends(current)):
        store.delete_entry(s, entry_id)
        return {"ok": True}

    @app.get("/api/dashboard")
    def get_dashboard(s=Depends(current)):
        return dashboard(store.list_entries(s), store.get_user(s)["weekly_goal"])

    @app.get("/api/export")
    def export(s=Depends(current)):
        return {"account": store.get_user(s), "entries": store.list_entries(s), "exported_at": dt.datetime.now().isoformat(timespec="seconds")}

    @app.post("/api/demo")
    def demo(s=Depends(current)):
        """Fills the account with 24 sample entries over the last 30 days so the dashboard can be shown. Marked as demo."""
        rows = list(csv.DictReader(open(os.path.join(HERE, "demo_entries.csv"), encoding="utf-8")))
        rng = random.Random(7)
        rng.shuffle(rows)
        skipped = set(rng.sample(range(1, 30), 6))
        day_offsets = [d for d in range(29, -1, -1) if d not in skipped][:24]
        tag_for = {"anxiety": ["academics"], "anger": ["friends"], "sadness": ["family"], "joy": ["friends"], "neutral": []}
        for row, off in zip(rows, day_offsets):
            when = (dt.datetime.now() - dt.timedelta(days=off)).replace(hour=20, minute=rng.randint(0, 59), second=0).strftime("%Y-%m-%dT%H:%M:%S")
            tags = ["money"] if any(w in row["text"].lower() for w in ("helb", "fee", "rent", "karo", "kodi")) else tag_for[row["emotion_label"]]
            mood = int(float(row["mood_rating"]))
            # made-up sleep hours for the sample month (lower on low-mood days so the sleep card has something to show)
            sleep = None if rng.random() < 0.15 else min(10.0, max(3.0, round(({1: 5.0, 2: 5.5, 3: 6.5, 4: 7.5, 5: 8.0}[mood] + rng.uniform(-1, 1)) * 2) / 2))
            _save(s, row["text"], mood, tags, rng.random() < 0.6, "auto", created_at=when, demo=True, sleep_hours=sleep)
        return {"added": len(day_offsets)}

    @app.delete("/api/account")
    def delete_account(req: Passphrase, s=Depends(current)):
        if not store.check_passphrase(s["user_id"], req.passphrase):
            raise HTTPException(401, "Wrong passphrase.")
        store.delete_account(s)
        return {"deleted": True}


def cli_demo():
    print("=" * 80, "\nMINDLOG — sample analysis (nothing is stored)\n" + R.DISCLAIMER, "\n" + "=" * 80)
    samples = [("Leo nimefurahi sana, tumepita mtihani wa programu bila shida!", 5),
               ("Manze hii semester iko fast sana, deadlines zinanikimbiza mbaya.", 2),
               ("My group members did nothing and now they want their names on the report.", 2),
               ("Moyo wangu unauma na nimekata tamaa kabisa, naona kama kila kitu kimeishia hapa.", 1)]
    for text, mood in samples:
        r = analyze(text, mood)
        print(f"\n[{r['language']} | mood {mood}/5] {text}")
        print(f"  emotion: {r['confidence_word']} {r['emotion']}   stress: {r['stress_score']:.2f}   support: {r['support_level']}")
        if r["support_level"] == "crisis":
            print("  " + r["support_message"])
            for h in r["helplines"]:
                print(f"    - {h['name']}: {h['contact']} ({h['hours']})")
        else:
            print("  reflection:", r["reflection"], "\n  tip:", r["coping_tip"])


if __name__ == "__main__":
    cli_demo()
