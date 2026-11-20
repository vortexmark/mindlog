"""Reflections and coping tips. These are fixed, reviewed sentences, not generated text:
nothing here can invent advice, give a diagnosis, or say something unsafe."""
import hashlib

DISCLAIMER = ("MindLog is a journaling assistant for reflection. It is not a therapist and does not give a medical "
              "diagnosis. If you are struggling, please talk to a counsellor or someone you trust.")

# Edit these to match your campus. Numbers checked November 2026.
HELPLINES = [
    {"name": "SPU Student Counselling", "contact": "Dean of Students office", "hours": "Weekdays, office hours"},   # TODO: add the campus phone number
    {"name": "Kenya Red Cross", "contact": "1199", "hours": "Toll-free"},
    {"name": "Befrienders Kenya", "contact": "+254 722 178 177", "hours": "Call, SMS or WhatsApp, weekdays 9am-5pm"},
    {"name": "Emergency services", "contact": "999 or 112", "hours": "Any time"},
]

CRISIS_MESSAGE = {
    "en": "What you wrote sounds very heavy, and you do not have to carry it alone. Please reach out to one of these people now. "
          "They are there for exactly this.",
    "sw": "Ulichoandika kinaonekana kizito sana, na huhitaji kukibeba peke yako. Tafadhali wasiliana na mmoja wa hawa sasa hivi. "
          "Wapo kwa ajili ya hali kama hii.",
}
ELEVATED_MESSAGE = {
    "en": "This sounds like a lot to carry. If it would help to talk to someone, these options are open to you.",
    "sw": "Inaonekana umebeba mengi. Kama ungependa kuzungumza na mtu, njia hizi ziko wazi kwako.",
}

BANK = {
    "joy": {
        "en": (["It is good to see a bright moment today. Noticing what went well is a habit worth keeping.",
                "You sound lighter today. Small wins like this are what build confidence over a semester.",
                "That is a good day, and you earned it."],
               ["Write down one thing you did that helped today go well, so you can repeat it.",
                "Share the good news with one person who has supported you.",
                "Take five minutes to enjoy this before moving to the next task."]),
        "sw": (["Ni vizuri kuona wakati mzuri leo. Kutambua yaliyokwenda vyema ni tabia ya kudumisha.",
                "Unaonekana mwenye furaha leo. Ushindi mdogo kama huu hujenga kujiamini.",
                "Hii ni siku njema, na umeistahili."],
               ["Andika jambo moja ulilofanya lililosaidia siku iende vizuri, ili ulirudie.",
                "Mshirikishe habari njema mtu mmoja ambaye amekuunga mkono.",
                "Chukua dakika tano kufurahia hili kabla ya kuendelea na kazi nyingine."]),
    },
    "anxiety": {
        "en": (["It sounds like a lot is pressing on you at once. Feeling stretched in a week like this makes sense.",
                "Worry about what is coming is tiring. You are not behind for feeling this way.",
                "That is a heavy load of deadlines and unknowns. It is okay to take it one piece at a time."],
               ["Pick the smallest next step and work on only that for 20 minutes, then take a 5-minute break.",
                "Write every task on paper, then circle the one that is due first. Start there.",
                "Try slow breathing for two minutes: in for 4 seconds, hold for 4, out for 6."]),
        "sw": (["Inaonekana mambo mengi yanakusonga kwa wakati mmoja. Ni kawaida kuhisi hivyo katika wiki kama hii.",
                "Wasiwasi kuhusu yanayokuja huchosha. Hujabaki nyuma kwa kuhisi hivi.",
                "Huo ni mzigo mzito wa kazi na mambo usiyoyajua. Ni sawa kuushughulikia kipande kimoja kwa wakati."],
               ["Chagua hatua ndogo kabisa inayofuata, ifanyie kazi kwa dakika 20 tu, kisha pumzika dakika 5.",
                "Andika kazi zote kwenye karatasi, kisha zungushia ile inayohitajika kwanza. Anzia hapo.",
                "Jaribu kupumua polepole kwa dakika mbili: vuta pumzi sekunde 4, shikilia 4, toa pumzi 6."]),
    },
    "sadness": {
        "en": (["Thank you for being honest about how heavy today feels. Be gentle with yourself.",
                "That sounds painful. Feeling low after something like this is a human response, not a weakness.",
                "It is hard when things feel empty or lonely. Writing it down was a good step."],
               ["Send a short message to one person you trust, even just to say hello.",
                "Do one small kind thing for yourself tonight: a warm meal, a shower, or early sleep.",
                "Step outside for ten minutes of fresh air and daylight if you can."]),
        "sw": (["Asante kwa kuwa mkweli kuhusu jinsi siku ya leo ilivyo nzito. Jihurumie.",
                "Hilo linaumiza. Kujisikia chini baada ya jambo kama hili ni hali ya kibinadamu, si udhaifu.",
                "Ni vigumu mambo yanapoonekana matupu au ya upweke. Kuyaandika ilikuwa hatua nzuri."],
               ["Mtumie ujumbe mfupi mtu mmoja unayemwamini, hata wa kumsalimia tu.",
                "Jifanyie jambo moja dogo la wema usiku wa leo: chakula cha moto, kuoga, au kulala mapema.",
                "Toka nje kwa dakika kumi upate hewa safi na mwanga wa jua ukiweza."]),
    },
    "anger": {
        "en": (["That would frustrate most people. Your reaction makes sense.",
                "It is draining when things are unfair or out of your control.",
                "You have a right to be annoyed about this. Naming it is the first step to dealing with it."],
               ["Step away for ten minutes before you reply to anyone about it.",
                "Write down exactly what you want to change, then decide who can actually change it.",
                "Move your body for a few minutes: a brisk walk or some stretches can lower the tension."]),
        "sw": (["Jambo hilo lingemkera karibu kila mtu. Hisia zako zinaeleweka.",
                "Inachosha mambo yanapokuwa si ya haki au nje ya uwezo wako.",
                "Una haki ya kukerwa na hili. Kulitaja ni hatua ya kwanza ya kulishughulikia."],
               ["Ondoka kwa dakika kumi kabla ya kumjibu yeyote kuhusu jambo hili.",
                "Andika hasa unachotaka kibadilike, kisha amua nani anaweza kukibadilisha.",
                "Sogeza mwili kwa dakika chache: kutembea haraka au kujinyoosha hupunguza msongo."]),
    },
    "neutral": {
        "en": (["Thank you for checking in today. Ordinary days are part of the record too.",
                "A steady day. Keeping the habit going is what makes patterns visible later.",
                "Noted. Showing up to write is the win for today."],
               ["Set one small goal for tomorrow and write it here.",
                "Drink a glass of water and take a short screen break.",
                "Add a tag to this entry so you can spot what fills your days."]),
        "sw": (["Asante kwa kuandika leo. Siku za kawaida pia ni sehemu ya kumbukumbu.",
                "Siku tulivu. Kuendeleza tabia hii ndiko kunakofanya mienendo ionekane baadaye.",
                "Imepokelewa. Kujitokeza kuandika ndio ushindi wa leo."],
               ["Weka lengo moja dogo la kesho na uliandike hapa.",
                "Kunywa glasi ya maji na upumzishe macho kidogo.",
                "Ongeza alama kwenye maandishi haya ili uone kinachojaza siku zako."]),
    },
}

PROMPTS = [
    ("What took most of your energy today?", "Ni nini kilichochukua nguvu zako nyingi leo?"),
    ("What is one thing that went well today, however small?", "Ni jambo gani moja lililokwenda vizuri leo, hata kama ni dogo?"),
    ("What are you worried about this week?", "Una wasiwasi kuhusu nini wiki hii?"),
    ("Who did you talk to today, and how did it leave you feeling?", "Uliongea na nani leo, na ulijisikiaje baadaye?"),
    ("What would make tomorrow a little easier?", "Ni nini kingefanya kesho iwe rahisi kidogo?"),
    ("What are you avoiding right now, and why?", "Unakwepa nini kwa sasa, na kwa nini?"),
    ("What are you proud of from the last few days?", "Unajivunia nini katika siku chache zilizopita?"),
]


# Used when the words read as neutral or positive but the person rated their mood 1 or 2:
# the model may have missed something, so MindLog says so and invites a correction.
LOW_MOOD = {
    "en": (["You rated today as a low day, but I could not tell why from the words alone. I may have read this wrong.",
            "Your mood rating says today was hard. If the label above does not fit, please correct it so I learn."],
           ["Add one sentence about how this left you feeling. Naming it often takes some of the weight off.",
            "Do one small kind thing for yourself tonight: a warm meal, a shower, or early sleep."]),
    "sw": (["Umeipa siku ya leo alama ya chini, lakini sikuweza kuelewa sababu kutoka kwa maneno pekee. Huenda nimekosea.",
            "Alama yako ya hisia inaonyesha leo ilikuwa ngumu. Kama lebo hapo juu haifai, tafadhali irekebishe ili nijifunze."],
           ["Ongeza sentensi moja kuhusu jinsi jambo hili lilivyokufanya ujisikie. Kulitaja hupunguza uzito wake.",
            "Jifanyie jambo moja dogo la wema usiku wa leo: chakula cha moto, kuoga, au kulala mapema."]),
}


def pick(emotion: str, language: str, seed: str, mood: int = 3):
    lang = "sw" if language == "Kiswahili" else "en"
    refl, tips = LOW_MOOD[lang] if (emotion in ("neutral", "joy") and mood <= 2) else BANK.get(emotion, BANK["neutral"])[lang]
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return refl[h % len(refl)], tips[(h // 7) % len(tips)], lang
