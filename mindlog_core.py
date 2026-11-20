"""MindLog core: text cleaning, bilingual lexicon-bridge features, crisis safeguard, language tagging.
Shared by the evaluation notebook and the MindLog app so both run exactly the same logic."""
import re, unicodedata
import numpy as np
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

EMOTIONS = ["joy", "anxiety", "sadness", "anger", "neutral"]
_MOOD_TAG = re.compile(r"^<m([1-5])>")


def tag_mood(text: str, mood) -> str:
    """Prefixes the text with the user's 1-5 mood rating, e.g. "<m2>Exams start on Monday...".
    Public datasets have no mood, so their rows carry no tag and MoodFeature sees 'unknown'."""
    return f"<m{int(mood)}>{text}" if mood is not None and mood == mood else str(text)


def normalize(text: str) -> str:
    """Light cleaning that keeps Kiswahili/Sheng tokens, negations and emojis intact."""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    t = _MOOD_TAG.sub("", t)                        # the mood tag is read by MoodFeature, not by the text features
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"@\w+", " @user ", t)
    t = t.replace("’", "'").replace("#", " ")
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)          # sooooo -> soo
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- lexicon bridge
# One list per emotion mixing English, Kiswahili and Sheng cues. Because the SAME four counters fire
# for all languages, what the classifier learns about them from English rows transfers to Kiswahili.
BRIDGE = {
    "joy": r"\b(happy|happi\w*|glad|reliev\w*|relief|proud|grateful|thankful|excit\w*|joy\w*|wonderful|awesome|amazing|smil\w*|laugh\w*|enjoy\w*|blessed|delighted|thrilled)\b"
           r"|furah|shukur|\bamani\b|\braha\b|pongez|fanikiw|\bvizuri\b|\bvyema\b|\bnzuri\b|\bpoa\b|\bfiti\b|baraka|jivuni|farijik|\bheri\b|shangwe|tukachek|tukichek",
    "anxiety": r"\b(anxious|anxiety|worr\w+|nervous\w*|scared|afraid|fear\w*|panic\w*|terrified|stress\w*|overwhelm\w*|dread\w*|shaking|tense|pressure)\b"
               r"|wasiwasi|\bhofu\b|ogop|\bwoga\b|tetemek|presha|mashaka|hangaik|nisumbu|nidund|kutulia|siwezi (ku)?lala|stress|panic",
    "sadness": r"\b(sad|sadness|sadly|lonely|alone|cry|cried|crying|tears|heartbroken|depress\w*|grief|griev\w*|drained|empty|hopeless|unhappy|miserable|disappoint\w*|miss)\b"
               r"|huzun|majonzi|mpweke|upweke|\b(nimelia|nalia|nikalia|kulia)\b|simanzi|msiba|vunjika moyo|uchungu|inaniuma|unauma|imeniuma|sikitik|fariki|sina hamu|\blow\b|\bdown\b",
    "anger": r"\b(angry|anger|mad|furious|annoy\w*|irritat\w*|hate\w*|frustrat\w*|unfair|ridiculous|pissed|rage|outrag\w*|fed up)\b"
             r"|kasir|hasira|udhi|kerwa|\bkero\b|ghadhab|chuki|nachukia|boek|\b(nimejam|najam|imenijam)\b|dharau|choshwa",
}
_BRIDGE_RE = {k: re.compile(v) for k, v in BRIDGE.items()}


class LexiconBridge(BaseEstimator, TransformerMixin):
    """4 features: log(1 + number of joy / anxiety / sadness / anger cue hits) x weight."""
    def __init__(self, weight=2.0):
        self.weight = weight

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = [[len(_BRIDGE_RE[e].findall(normalize(t))) for e in ("joy", "anxiety", "sadness", "anger")] for t in X]
        return sparse.csr_matrix(np.log1p(np.array(rows, dtype=float)) * self.weight)


class MoodFeature(BaseEstimator, TransformerMixin):
    """6 one-hot features: mood 1..5 from a leading <mN> tag, or 'unknown' when there is none."""
    def __init__(self, weight=3.0):
        self.weight = weight

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []
        for t in X:
            m = _MOOD_TAG.match(str(t).lower())
            v = [0.0] * 6
            v[int(m.group(1)) if m else 0] = 1.0
            rows.append(v)
        return sparse.csr_matrix(np.array(rows) * self.weight)


def tfidf_union(bridge=True, mood=False):
    parts = [
        ("word", TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), min_df=2, max_features=60000, sublinear_tf=True)),
        ("char", TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(2, 5), min_df=3, max_features=120000, sublinear_tf=True)),
    ]
    if bridge:
        parts.append(("bridge", LexiconBridge()))
    if mood:
        parts.append(("mood", MoodFeature()))
    return FeatureUnion(parts)


def build_classifier(bridge=True, C=4.0, mood=False):
    return Pipeline([("features", tfidf_union(bridge, mood)),
                     ("clf", LogisticRegression(C=C, max_iter=2000, class_weight="balanced"))])


# ---------------------------------------------------------------- crisis safeguard (deterministic)
CRISIS_PATTERNS = {
    "self_harm_or_suicide": r"\b(kill(ing)? myself|end(ing)? my (own )?life|tak(e|ing) my (own )?life|suicid\w*|self[- ]?harm\w*|(hurt|harm)(ing)? myself)\b"
                            r"|kujiua|nijiue|najiua|nitajiua|kujitoa uhai|kujinyonga|kujiumiza|kujidhuru",
    "not_wanting_to_live": r"\b(do not|don'?t|dont) want to (be alive|live|be here|exist)\b|\bwish i (was|were) dead\b|\bwant to (die|disappear|end it( all)?)\b"
                           r"|\bbetter off (without me|bila mimi)\b|\bno (reason|point) (to|in) (live|living|keep going|go on|going on|continue)\b"
                           r"|\bany reason to (live|keep going|go on|continue)\b"
                           r"|(sioni|sina) (sababu|haja|maana) ya (kuendelea|kuishi|maisha)|(sitaki|sipendi) (tena )?(kuendelea )?kuishi"
                           r"|nisingekuwepo|nisingezaliwa|(natamani|nataka) kufa|(bora|heri|afadhali) nife",
    "despair": r"\b(i feel|i am|i'm|im|feeling|niko|naskia|najisikia|najihisi)\s+(\w+\s+){0,2}hopeless\b"
               r"|\b(can'?t|cannot|can not) (cope|go on)\b|\bgiv(e|ing|en) up (on|na) (life|everything|maisha|kila kitu)\b"
               r"|\b(nime|tume|na)kata tamaa\b|(nimechoka|nimechoshwa) (na|kwa) maisha|\b\w*ishia hapa\b",
}
_CRISIS_RE = {k: re.compile(v) for k, v in CRISIS_PATTERNS.items()}


def detect_crisis(text: str):
    """Returns the list of crisis categories found. Rules, not a model: a missed crisis costs far more
    than a false alarm, and rules can be read, audited and extended by a counsellor."""
    t = normalize(text)
    return [name for name, rx in _CRISIS_RE.items() if rx.search(t)]


# ---------------------------------------------------------------- language tagging
def language_of(text: str, word_clf) -> str:
    """English / Kiswahili / Mixed from the share of words a word-level classifier calls Kiswahili."""
    words = [w for w in re.findall(r"[a-z']+", normalize(text)) if len(w) >= 3 and w != "user"]
    if not words:
        return "English"
    share = float(np.mean(word_clf.predict(words) == "sw"))
    return "Kiswahili" if share >= 0.8 else "English" if share <= 0.2 else "Mixed"
