"""Question hygiene: people wrap a question in chatter ("Hi, could you help me? ... Thank you!"), dictate it without punctuation, or mistype a
small word. The rule parser knows the dataset's exact templates, so a question that does not parse is cleaned once and tried again. A question
that already parses is never touched (the benchmark phrasing keeps its exact path).

Only words AROUND place names change: a place name is never edited, and the floor in "(Ground floor)" is only put back into parentheses."""

import re

LEAD = [
    r"(?:hi|hello|hey|hallo|moin)\b[,!.\s]*",
    r"(?:could|can|would|will) you (?:please )?(?:help me|tell me|show me|help)\s*[?:,.!]*\s*",
    r"(?:please|bitte)\b[,:\s]*",
    r"(?:um+|uh+|er+|erm|so|well|okay|ok|right)\b[,.\s]+",
    r"(?:kurze frage|quick question|question|frage|short question)\s*[:,.]\s*",
    r"i'?m in a (?:hurry|rush)\s*[.!]\s*",
]
TAIL = [
    r"\s*(?:thanks(?: a lot)?|thank you(?: very much)?|danke|many thanks|cheers)\s*[!.]*\s*$",
    r"\s*(?:please|bitte)\s*[!.?]*\s*$",
]
TYPOS = {"form": "from", "teh": "the", "rotue": "route", "hwo": "how", "clsoed": "closed", "maintainance": "maintenance", "step free": "step-free"}
FLOOR = r"(?:ground floor|floor\s*-?\d+|basement\s*\d*|level\s*-?\d+|storey\s*-?\d+|(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|\d+(?:st|nd|rd|th))\s+(?:floor|storey|level|basement))"


def has_chatter(question: str) -> bool:
    """True when the question starts or ends with filler, or holds a known typo, that the rule parser would swallow into a place name."""
    text = " ".join(question.split())
    typo = any(re.search(rf"(?<![\w(-]){re.escape(w)}(?![\w)-])", text) for w in TYPOS)
    return typo or any(re.match(p, text, re.I) for p in LEAD) or any(re.search(p, text, re.I) for p in TAIL)


def clean_question(question: str) -> str:
    text = " ".join(question.split())
    for _ in range(4):
        before = text
        for pattern in LEAD:
            text = re.sub(rf"^{pattern}", "", text, flags=re.I)
        for pattern in TAIL:
            text = re.sub(pattern, "", text, flags=re.I)
        text = text.strip()
        if text == before:
            break
    for wrong, right in TYPOS.items():
        text = re.sub(rf"(?<![\w(-]){re.escape(wrong)}(?![\w)-])", right, text)
    if "(" not in text:  # dictated: the floor of each place was spoken without brackets (never "on the ground floor" of a count question)
        text = re.sub(rf"(?<!\bthe )(?<!\bon )(?<!\bof )(?<!\bin )\b({FLOOR})\b(?=\s+(?:to|then|visit|and|in this order|is|are|would)\b|\s*[?.]?\s*$)", r"(\1)", text, flags=re.I)
    # dictated: a sentence break the speaker did not type, before the second sentence of the benchmark shapes
    text = re.sub(r"(?<=[\w)])\s+(?=(?:how do i get|what is the route|is there a step-free|how many rooms|which room)\b)", ". ", text, flags=re.I)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    if text and text[-1] in ".!":
        last = re.split(r"(?<=[.!?])\s+", text)[-1].rstrip(".!")
        if re.match(r"(?:how|where|which|is|what|can)\b", last, re.I):
            text = text[: len(text) - (len(text) - len(text.rstrip(".!")))] + "?"
    elif text and text[-1] != "?":
        last = re.split(r"(?<=[.!?])\s+", text)[-1]
        text += "?" if re.match(r"(?:how|where|which|is|what|can)\b", last, re.I) else "."
    return text
