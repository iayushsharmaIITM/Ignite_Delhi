"""Instant replies for the messages a company brain cannot be asked about.

One purpose, one table: given the social kind of a message and the reader's UI
locale, return the words. Nothing here retrieves, nothing here calls a model, and
nothing here stores anything from one request to the next — a greeting is answered
from this file or not at all, which is what keeps the citation path free of any
meaning-derived shortcut. Detection lives in `memory_layer.phatic_kind`, because
deciding WHAT a message is belongs with the rest of the classifier; deciding WHAT TO
SAY belongs here.

Two rules the table has to hold:

* Fail open. If there is any chance the message was a real question, it is not here,
  and it goes to the brain. A misroute to retrieval costs seconds; a misroute to a
  canned line costs trust.
* Never a citation, and never a promise of one. These replies must not mention
  sources, quotes or documents, because they have none.

Locale codes match `frontend/src/lib/i18n.ts` exactly (en, hi, es, fr, de, zh) so the
UI language and the reply language cannot drift apart.
"""
from __future__ import annotations

from datetime import datetime

LOCALES = ("en", "hi", "es", "fr", "de", "zh")

KINDS = ("greeting", "thanks", "howareyou", "farewell", "capability", "praise",
         "sorry", "welcome")

# Which part of the day a greeting names. Kept as thresholds rather than a library
# so the reply agrees with the server's own clock at every hour exactly once.
def _part(now: datetime | None) -> str:
    hour = (now or datetime.now()).hour
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"
    return "night"


def _from_tz(tz: str | None):
    if not tz:
        return None
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    except Exception:  # noqa: BLE001 - a bogus zone is not worth failing a greeting
        return None


# The line that says where the product lives: answer from the user's own documents,
# with sources named. Every reply below either is that, or declines to claim more.
_TABLE: dict[str, dict[str, str]] = {
    "greeting": {
        "en_morning": "Good morning. Ask me anything about your company's documents — "
                      "I answer from your contracts, tickets and meetings, with the "
                      "sources named.",
        "en_afternoon": "Good afternoon. Ask me anything about your company's documents — "
                        "I answer from your contracts, tickets and meetings, with the "
                        "sources named.",
        "en_evening": "Good evening. Ask me anything about your company's documents — "
                      "I answer from your contracts, tickets and meetings, with the "
                      "sources named.",
        "en_night": "Still here. Ask me anything about your company's documents — I "
                    "answer from your contracts, tickets and meetings, with the sources "
                    "named.",
        "hi_morning": "सुप्रभात। अपनी कंपनी के दस्तावेज़ों से जुड़ा कुछ भी पूछें — मैं "
                      "अनुबंधों, टिकटों और बैठकों से जवाब देता हूँ, और स्रोत भी बताता हूँ।",
        "hi_afternoon": "नमस्ते। अपनी कंपनी के दस्तावेज़ों से जुड़ा कुछ भी पूछें — मैं "
                        "अनुबंधों, टिकटों और बैठकों से जवाब देता हूँ, और स्रोत भी बताता हूँ।",
        "hi_evening": "शुभ संध्या। अपनी कंपनी के दस्तावेज़ों से जुड़ा कुछ भी पूछें — मैं "
                      "अनुबंधों, टिकटों और बैठकों से जवाब देता हूँ, और स्रोत भी बताता हूँ।",
        "hi_night": "मैं यहाँ हूँ। अपनी कंपनी के दस्तावेज़ों से जुड़ा कुछ भी पूछें — मैं "
                    "अनुबंधों, टिकटों और बैठकों से जवाब देता हूँ, और स्रोत भी बताता हूँ।",
        "es_morning": "Buenos días. Pregúntame lo que quieras sobre los documentos de tu "
                      "empresa: respondo con contratos, tickets y reuniones, y digo de "
                      "dónde viene cada dato.",
        "es_afternoon": "Buenas tardes. Pregúntame lo que quieras sobre los documentos de "
                        "tu empresa: respondo con contratos, tickets y reuniones, y digo de "
                        "dónde viene cada dato.",
        "es_evening": "Buenas noches. Pregúntame lo que quieras sobre los documentos de tu "
                      "empresa: respondo con contratos, tickets y reuniones, y digo de dónde "
                      "viene cada dato.",
        "es_night": "Sigo aquí. Pregúntame lo que quieras sobre los documentos de tu "
                    "empresa: respondo con contratos, tickets y reuniones, y digo de dónde "
                    "viene cada dato.",
        "fr_morning": "Bonjour. Posez-moi vos questions sur les documents de votre "
                      "entreprise : je réponds à partir des contrats, tickets et réunions, "
                      "en citant mes sources.",
        "fr_afternoon": "Bon après-midi. Posez-moi vos questions sur les documents de votre "
                        "entreprise : je réponds à partir des contrats, tickets et réunions, "
                        "en citant mes sources.",
        "fr_evening": "Bonsoir. Posez-moi vos questions sur les documents de votre "
                      "entreprise : je réponds à partir des contrats, tickets et réunions, "
                      "en citant mes sources.",
        "fr_night": "Je suis là. Posez-moi vos questions sur les documents de votre "
                    "entreprise : je réponds à partir des contrats, tickets et réunions, en "
                    "citant mes sources.",
        "de_morning": "Guten Morgen. Fragen Sie mich zu den Dokumenten Ihres Unternehmens — "
                      "ich antworte aus Verträgen, Tickets und Meetings und nenne die "
                      "Quellen.",
        "de_afternoon": "Guten Tag. Fragen Sie mich zu den Dokumenten Ihres Unternehmens — "
                        "ich antworte aus Verträgen, Tickets und Meetings und nenne die "
                        "Quellen.",
        "de_evening": "Guten Abend. Fragen Sie mich zu den Dokumenten Ihres Unternehmens — "
                      "ich antworte aus Verträgen, Tickets und Meetings und nenne die "
                      "Quellen.",
        "de_night": "Ich bin da. Fragen Sie mich zu den Dokumenten Ihres Unternehmens — ich "
                    "antworte aus Verträgen, Tickets und Meetings und nenne die Quellen.",
        "zh_morning": "早上好。可以问我任何关于贵公司文档的问题——我会根据合同、工单和会议"
                      "记录回答，并说明出处。",
        "zh_afternoon": "下午好。可以问我任何关于贵公司文档的问题——我会根据合同、工单和"
                        "会议记录回答，并说明出处。",
        "zh_evening": "晚上好。可以问我任何关于贵公司文档的问题——我会根据合同、工单和会议"
                      "记录回答，并说明出处。",
        "zh_night": "我随时都在。可以问我任何关于贵公司文档的问题——我会根据合同、工单和"
                    "会议记录回答，并说明出处。",
    },
    "thanks": {
        "en": "Glad that helped. Anything else in your documents you want checked?",
        "hi": "अच्छा लगा कि इससे मदद मिली। अपनी दस्तावेज़ों से जुड़ा कुछ और पूछना "
              "चाहेंगे?",
        "es": "Me alegra que sirviera. ¿Quieres que revise algo más de tus documentos?",
        "fr": "Ravi que cela ait aidé. Souhaitez-vous que je vérifie autre chose dans vos "
              "documents ?",
        "de": "Freut mich, dass es geholfen hat. Soll ich noch etwas in Ihren Dokumenten "
              "prüfen?",
        "zh": "很高兴能帮上忙。还需要我查一下贵公司文档里的其他内容吗？",
    },
    "howareyou": {
        "en": "Running well, thank you. I am at my best on your documents — contracts, "
              "tickets, meeting notes: ask and I will show you where each line came from.",
        "hi": "बढ़िया, धन्यवाद। मैं अपनी कंपनी के दस्तावेज़ों पर सबसे अच्छा काम करता "
              "हूँ — अनुबंध, टिकट, बैठक नोट्स: पूछिए और मैं बताऊँगा हर बात कहाँ से आई।",
        "es": "Funcionando bien, gracias. Rindo mejor con tus documentos: contratos, "
              "tickets y notas de reuniones. Pregunta y te muestro de dónde sale cada dato.",
        "fr": "Tout va bien, merci. Je suis le plus utile sur vos documents — contrats, "
              "tickets, comptes rendus : demandez et je vous montrerai l'origine de chaque "
              "élément.",
        "de": "Alles in Ordnung, danke. Auf den Dokumenten Ihres Unternehmens bin ich am "
              "stärksten — Verträge, Tickets, Meeting-Notizen: Fragen Sie, und ich zeige "
              "Ihnen die Quelle jedes einzelnen Punkts.",
        "zh": "我状态不错，谢谢。我最擅长的是贵公司的文档——合同、工单、会议纪要：尽管问，"
              "我会告诉你每一条内容的来源。",
    },
    "farewell": {
        "en": "Goodbye. Your documents stay indexed — come back and ask whenever you need "
              "an answer with sources.",
        "hi": "अलविदा। आपकी दस्तावेज़ें सूचीबद्ध रहेंगी — जब भी स्रोतों के साथ जवाब "
              "चाहिए, लौटकर पूछ लीजिए।",
        "es": "Hasta luego. Tus documentos siguen indexados: vuelve cuando necesites una "
              "respuesta con fuentes.",
        "fr": "Au revoir. Vos documents restent indexés : revenez quand vous aurez besoin "
              "d'une réponse sourcée.",
        "de": "Auf Wiedersehen. Ihre Dokumente bleiben indexiert — kommen Sie zurück, wann "
              "immer Sie eine Antwort mit Quellen brauchen.",
        "zh": "再见。你的文档会一直保持索引——需要带出处的答案时随时回来问。",
    },
    "capability": {
        "en": "I am Kestrel, your company brain. I answer questions from the documents you "
              "upload — contracts, tickets, meeting notes — and I name the file each part "
              "of the answer came from. If something is not in your documents, I say so "
              "instead of guessing.",
        "hi": "मैं Kestrel हूँ, आपका कंपनी ब्रेन। मैं उन दस्तावेज़ों से जवाब देता हूँ जो "
              "आप अपलोड करते हैं — अनुबंध, टिकट, बैठक नोट्स — और हर जवाब बताता हूँ कि वह "
              "किस फ़ाइल से आया। आपकी दस्तावेज़ों में जो नहीं है, मैं उसके बारे में अनुमान "
              "नहीं लगाता, वही कहता हूँ।",
        "es": "Soy Kestrel, el cerebro de tu empresa. Respondo con los documentos que "
              "subas —contratos, tickets, notas de reuniones— y digo de qué archivo viene "
              "cada parte de la respuesta. Si algo no está en tus documentos, lo digo en "
              "lugar de adivinar.",
        "fr": "Je suis Kestrel, le cerveau de votre entreprise. Je réponds à partir des "
              "documents que vous téléversez — contrats, tickets, comptes rendus — et je "
              "dis de quel fichier vient chaque partie de la réponse. Ce qui n'est pas dans "
              "vos documents, je le dis plutôt que de le deviner.",
        "de": "Ich bin Kestrel, das Gehirn Ihres Unternehmens. Ich antworte aus den "
              "Dokumenten, die Sie hochladen — Verträge, Tickets, Meeting-Notizen — und "
              "sage zu jedem Teil der Antwort, aus welcher Datei er stammt. Was in Ihren "
              "Dokumenten nicht steht, errate ich nicht, sondern sage es offen.",
        "zh": "我是 Kestrel，你的公司大脑。我根据你上传的文档回答——合同、工单、会议纪要——"
              "并说明答案的每一部分来自哪个文件。你的文档里没有的内容，我不会猜测，而是直接"
              "告诉你。",
    },
    "praise": {
        "en": "Thank you. It comes from your documents being well organised — keep asking "
              "and I will keep citing.",
        "hi": "धन्यवाद। यह आपकी दस्तावेज़ें अच्छी तरह व्यवस्थित होने की वजह से है — "
              "पूछते रहिए, मैं स्रोत बताता रहूँगा।",
        "es": "Gracias. Es mérito de que tus documentos estén bien organizados: sigue "
              "preguntando y sigo citando fuentes.",
        "fr": "Merci. C'est que vos documents sont bien organisés : continuez à poser des "
              "questions, je continuerai à citer mes sources.",
        "de": "Danke. Das liegt daran, dass Ihre Dokumente gut geordnet sind — fragen Sie "
              "weiter, ich weiter zu zitieren.",
        "zh": "谢谢。这说明你的文档整理得很好——继续提问，我会继续标注出处。",
    },
    "sorry": {
        "en": "No need to apologise. Ask whenever you are ready — there is no queue and "
              "nothing is lost between questions.",
        "hi": "माफी की ज़रूरत नहीं। जब तैयार हो पूछ लेना — कोई कतार नहीं है, और सवालों के "
              "बीच कुछ खोता नहीं है।",
        "es": "No hace falta disculparse. Pregunta cuando quieras: no hay fila y nada se "
              "pierde entre pregunta y pregunta.",
        "fr": "Inutile de vous excuser. Demandez quand vous voulez : il n'y a pas de file "
              "d'attente et rien ne se perd entre deux questions.",
        "de": "Keine Entschuldigung nötig. Fragen Sie, wann Sie wollen — es gibt keine "
              "Warteschlange, und zwischen Fragen geht nichts verloren.",
        "zh": "不用道歉。你想问的时候随时问——这里没有排队，问题之间也不会丢失任何东西。",
    },
    "welcome": {
        "en": "Anytime. If another question comes up, your documents are already indexed.",
        "hi": "कोई बात नहीं। अगर कोई और सवाल हो, आपकी दस्तावेज़ें पहले से सूचीबद्ध हैं।",
        "es": "Cuando quieras. Si surge otra pregunta, tus documentos ya están indexados.",
        "fr": "Avec plaisir. Si une autre question vient, vos documents sont déjà indexés.",
        "de": "Jederzeit. Wenn eine weitere Frage auftaucht, Ihre Dokumente sind bereits "
              "indexiert.",
        "zh": "不客气。如果又想到别的问题，你的文档已经建好索引了。",
    },
}


def strip_system_note(query: str) -> str:
    """Drop the additive hints the web tier prepends before the model sees a question.

    The ask route attaches the caller's browser timezone so "what time is it?" can be
    answered without asking where the user is. That note is about the message, not in
    it, and it must never reach a classifier that decides whether the message needs the
    documents at all — which is exactly how every greeting in the shipping app ended up
    paying a full retrieval round trip.
    """
    q = (query or "").strip()
    if not q:
        return q
    lines = q.splitlines()
    # Case-insensitive on purpose: the web tier writes "[Client local time: …]" with a
    # capital C, and a comparison that happens to disagree with your own producer is
    # how this note ended up inside the classifier in the first place.
    marker = "[client local time"
    while lines and lines[0].lstrip().lower().startswith(marker):
        lines = lines[1:]
    stripped = "\n".join(lines).strip()
    # A note can also arrive folded onto the same line as the message.
    if not stripped and marker in q.lower():
        tail = q.split("]", 1)
        stripped = tail[1].strip() if len(tail) > 1 else ""
    if not stripped:
        # Nothing left but the note itself: say so by returning empty rather than
        # handing the classifier a bracketed timestamp to interpret as a greeting.
        return ""
    return stripped


def reply(kind: str, lang: str | None = None, now: datetime | None = None,
           tz: str | None = None) -> str | None:
    # `tz` is the caller's browser timezone (zoneinfo name). It is used for nothing
    # except choosing which part of the day a greeting names: "Good evening" to
    # someone it is 09:00 for is a small lie the server tells on purpose otherwise.
    # Resolved here rather than in the route so one clock source governs all six
    # locales. An unknown zone falls back to the server, never raises.
    """The words for a social kind of message, or None if we do not claim to know it.

    Returning None is a real answer: the caller must then take the normal route. A
    half-known social case is not worth inventing text for.
    """
    if kind not in _TABLE:
        return None
    loc = (lang or "en").strip().lower().split("-")[0].split("_")[0]
    if loc not in LOCALES:
        loc = "en"
    table = _TABLE[kind]
    if kind == "greeting":
        key = f"{loc}_{_part(now or _from_tz(tz))}"
    else:
        key = loc
    return table.get(key)
