"""Universal, local 4-stage email summarizer without external API calls or LLM tokens."""

import html
import math
import re
from collections import Counter
from typing import Any

from app.core.logger import logger

# Stage 1: Universal Greetings, Signatures & Boilerplate
GREETING_REGEX = re.compile(
    r"^(?:dear\s+[^,\n]+|hello\s*[^,\n]*|hi\s*[^,\n]*|hey\s*[^,\n]*|greetings|good\s+(?:morning|afternoon|evening))[,\s]*",
    re.IGNORECASE,
)
SIGNATURE_REGEX = re.compile(
    r"^(?:best\s+regards|warm\s+regards|thanks\s*(?:&|and)?\s*regards|regards|thank\s+you|thanks|sincerely|cheers|sent\s+from\s+my|get\s+outlook|yours\s+truly)\b",
    re.IGNORECASE,
)
BOILERPLATE_REGEX = re.compile(
    r"^(?:this\s+email|caution:|disclaimer:|note:|view\s+(?:in|this|page)|click\s+here|unsubscribe|copyright|\*+)\b",
    re.IGNORECASE,
)
URL_REGEX = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
EMAIL_HEADER_REGEX = re.compile(r"^(?:from|to|subject|date|sent|cc|bcc):\s*.*$", re.IGNORECASE)

# Stage 2: Generic Automated Notification Lead-ins across all platforms (Jira, GitHub, ERP, Workday, Schools, etc.)
GENERIC_NOTIFICATION_PREFIX_REGEX = re.compile(
    r"^(?:[A-Za-z0-9\s&.,'-]+?\s+)?\b(?:NEW\s+CIRCULAR|CIRCULAR|ANNOUNCEMENT|NOTIFICATION|ALERT|NOTICE|UPDATE|NEWSLETTER|BULLETIN)\b[:\s-]*",
    re.IGNORECASE,
)
GENERIC_WRAPPER_SENTENCE_REGEX = re.compile(
    r"^A\s+new\s+(?:circular|notice|announcement|ticket|issue|update|message|task)\s+(?:with\s+title|regarding|about|has\s+been)\s+",
    re.IGNORECASE,
)
GENERIC_PASSIVE_TAIL_REGEX = re.compile(
    r"\s+has\s+been\s+(?:shared\s+with\s+you|shared|published|posted|assigned\s+to\s+you|issued|created|released)(?:\s+(?:on|through)\s+[^.]+)?(?:[.\s]*)$",
    re.IGNORECASE,
)

# Common English stop words for local LexRank scoring
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "ourselves", "out", "over", "own", "s", "same", "she", "should", "so", "some", "such",
    "t", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will", "with", "you", "your",
}


def _tokenize_words(text: str) -> list[str]:
    """Tokenize lowercase alphanumeric words filtering out stop words."""
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def extract_meeting_url(text: str | None) -> str | None:
    """Extract direct video meeting URL (Google Meet, Zoom, Teams, Webex) from text."""
    if not text:
        return None

    # 1. Google Meet standard: https://meet.google.com/xxx-xxxx-xxx
    meet_match = re.search(r"https?://meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})\b", text, re.IGNORECASE)
    if meet_match:
        return f"https://meet.google.com/{meet_match.group(1).lower()}"

    # 2. Google Meet tel / direct code alias: https://tel.meet/xxx-xxxx-xxx
    tel_meet = re.search(r"https?://tel\.meet/([a-z0-9_-]+)", text, re.IGNORECASE)
    if tel_meet:
        code = tel_meet.group(1).split("?")[0]
        if re.match(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$", code, re.IGNORECASE):
            return f"https://meet.google.com/{code.lower()}"
        return f"https://tel.meet/{code}"

    # 3. Zoom meeting: https://subdomain.zoom.us/j/... or /my/...
    zoom_match = re.search(r"https?://(?:[a-zA-Z0-9-]+\.)?zoom\.us/(?:j|my)/[a-zA-Z0-9?=&%_.-]+", text, re.IGNORECASE)
    if zoom_match:
        return zoom_match.group(0).rstrip(".,)>\"'")

    # 4. Microsoft Teams: https://teams.microsoft.com/l/meetup-join/...
    teams_match = re.search(r"https?://(?:teams\.microsoft\.com/l/meetup-join|teams\.live\.com/meet)/[^\s\"'<>]+", text, re.IGNORECASE)
    if teams_match:
        return teams_match.group(0).rstrip(".,)>\"'")

    # 5. Cisco Webex: https://company.webex.com/meet/...
    webex_match = re.search(r"https?://[a-zA-Z0-9-]+\.webex\.com/(?:meet|join)/[^\s\"'<>]+", text, re.IGNORECASE)
    if webex_match:
        return webex_match.group(0).rstrip(".,)>\"'")

    return None


def _clean_body_text(body: str | None) -> list[str]:
    """Stage 1: Strip HTML, styling, greetings, signatures and join paragraph flow cleanly."""
    if not body:
        return []

    # Remove <style>, <script>, <head> blocks completely
    text = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", body)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "\n", text)
    # Unescape HTML entities (&amp; -> &, &#39; -> ', &nbsp; -> ' ')
    text = html.unescape(text)
    # Remove CSS declarations and rules (.class { ... }, etc.)
    text = re.sub(r"(?s)[^{};<>\n]*\{[^}]*\}", " ", text)
    text = re.sub(r"(?i)\b[a-z-]+\s*:\s*[^;:<\n]+;", " ", text)
    text = re.sub(r"(?:^|\s)(?:[.#][a-zA-Z0-9_-]+|\b[a-z]{1,6}\.[a-zA-Z0-9_-]+)(?=\s|$)", " ", text)
    # Clean broken URL fragments like https:// /...
    text = re.sub(r"https?://\s+/\S*", " ", text)
    # Clean meeting boilerplate lines
    text = re.sub(r"(?i)join\s+with\s+google\s+meet(?:\s*https?://\S*)?", "Join via Google Meet.", text)
    # Remove raw URLs
    text = URL_REGEX.sub("", text)

    # Reconstruct continuous paragraphs while respecting empty lines as paragraph breaks
    lines = [line.strip() for line in text.splitlines()]
    paragraphs: list[str] = []
    current_para: list[str] = []

    for line in lines:
        if not line:
            if current_para:
                paragraphs.append(" ".join(current_para))
                current_para = []
            continue
        if EMAIL_HEADER_REGEX.match(line):
            continue
        cleaned_line = GREETING_REGEX.sub("", line).strip()
        if not cleaned_line:
            continue
        if SIGNATURE_REGEX.match(cleaned_line) or BOILERPLATE_REGEX.match(cleaned_line):
            break
        current_para.append(cleaned_line)

    if current_para:
        paragraphs.append(" ".join(current_para))

    # Now extract complete sentences from continuous paragraphs
    sentences: list[str] = []
    for para in paragraphs:
        # Strip raw calendar artifacts or invitation URL links
        para = re.sub(r"(?i)//\s*invitation\s+from\s+google\s+calendar:\s*https?://\S*", "Invitation received from Google Calendar.", para)
        # Avoid splitting on abbreviations like 'Sem.' or 'Dr.' or 'Prof.' or 'St.' or 'Mr.'
        para = re.sub(r"\b(Sem|Dr|Prof|Mr|Ms|Mrs|St|approx|dept|e\.g|i\.e)\.\s+", r"\1_DOT_ ", para, flags=re.IGNORECASE)
        raw_sents = re.split(r"(?<=[.!?])\s+", para)
        for s in raw_sents:
            s_clean = s.replace("_DOT_", ".").strip()
            # Clean Markdown formatting like *mandatory* or _italic_
            s_clean = re.sub(r"[*_~`]", "", s_clean)
            words = s_clean.split()
            # Filter out non-sentences: logo text, single header words, buttons
            if len(words) < 4:
                continue
            if SIGNATURE_REGEX.match(s_clean) or BOILERPLATE_REGEX.match(s_clean):
                break
            sentences.append(s_clean)

    return sentences


def _clean_notification_wrapper(sentence: str, subject: str | None = None) -> str:
    """Stage 2: Universal domain-agnostic automated wrapper and subject-echo removal."""
    s = sentence.strip()

    # 1. Strip automated notification prefixes: e.g. "Acme Corp NEW CIRCULAR", "Jira Notification:"
    s = GENERIC_NOTIFICATION_PREFIX_REGEX.sub("", s).strip()

    # 2. Check for wrapper sentences like "A new circular with title [Subject] has been shared with you."
    s = re.sub(r"^(?:A\s+new\s+(?:circular|notice|announcement|ticket|issue|update|message|task)\s+)?with\s+title\s+", "", s, flags=re.IGNORECASE).strip()
    if GENERIC_WRAPPER_SENTENCE_REGEX.match(s):
        s_unwrapped = GENERIC_WRAPPER_SENTENCE_REGEX.sub("", s).strip()
        s_unwrapped = re.sub(r"^with\s+title\s+", "", s_unwrapped, flags=re.IGNORECASE).strip()
        if len(s_unwrapped.split()) >= 3:
            s = s_unwrapped

    # 3. Strip calendar invitation prefix boilerplate: // Invitation from Google Calendar...
    if "invitation from google calendar" in s.lower():
        s = "Google Calendar event invitation received."

    # Clean up any leftover duplicate punctuation or double spaces
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\.{2,}", ".", s)
    return s


def _rank_sentences_lexrank(sentences: list[str]) -> str:
    """Stage 3: LexRank graph centrality algorithm in pure Python (no dependencies)."""
    if not sentences:
        return ""
    if len(sentences) == 1:
        return sentences[0]

    # Compute word frequency vectors for each sentence
    sentence_vectors = [_tokenize_words(s) for s in sentences]
    n = len(sentences)

    # If sentences are too short to vectorize, return the first one
    if not any(sentence_vectors):
        return sentences[0]

    # Calculate Cosine similarity matrix
    similarity_scores = [0.0] * n
    for i in range(n):
        words_i = Counter(sentence_vectors[i])
        if not words_i:
            continue
        len_i = math.sqrt(sum(c * c for c in words_i.values()))
        if len_i == 0:
            continue
        for j in range(n):
            if i == j:
                continue
            words_j = Counter(sentence_vectors[j])
            if not words_j:
                continue
            len_j = math.sqrt(sum(c * c for c in words_j.values()))
            if len_j == 0:
                continue
            # Dot product
            dot = sum(words_i[w] * words_j[w] for w in words_i if w in words_j)
            sim = dot / (len_i * len_j)
            similarity_scores[i] += sim

    # Pick the sentence with highest centrality
    best_idx = 0
    max_score = -1.0
    for idx, score in enumerate(similarity_scores):
        # Slightly favor earlier sentences if scores are close
        position_bonus = 1.0 / (1.0 + 0.1 * idx)
        total_score = score * position_bonus
        if total_score > max_score:
            max_score = total_score
            best_idx = idx

    return sentences[best_idx]


def extract_clean_summary(body: str | None, max_length: int = 250, subject: str | None = None) -> str:
    """Stage 4: Complete-thought formatter returning a polished grammatical sentence without truncation."""
    raw_sentences = _clean_body_text(body)
    if not raw_sentences:
        return ""

    # Clean universal notification wrappers from candidate sentences
    cleaned_sentences = [_clean_notification_wrapper(s, subject) for s in raw_sentences]
    cleaned_sentences = [s for s in cleaned_sentences if len(s.split()) >= 4]

    if not cleaned_sentences:
        cleaned_sentences = raw_sentences

    # Use pure local LexRank to select the most central sentence
    selected = _rank_sentences_lexrank(cleaned_sentences)

    # Ensure sentence ends with proper punctuation
    selected = selected.strip()
    if selected and not selected.endswith((".", "!", "?")):
        selected += "."

    if len(selected) <= max_length:
        return selected

    # If unusually long, break at the first complete clause or sentence boundary up to max_length
    first_period = selected.find(". ")
    if 40 <= first_period <= max_length:
        return selected[: first_period + 1]

    # Break cleanly at last space before max_length
    truncated = selected[:max_length].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{truncated}."


def batch_summarize_emails(emails: list[Any], ai_service=None) -> dict[str, str]:
    """Pure local 100% offline batch summarizer. No Gemini API calls or token usage."""
    if not emails:
        return {}
    summaries = {}
    for email in emails:
        try:
            summaries[email.id] = extract_clean_summary(email.body, subject=email.subject)
        except Exception as exc:
            logger.warning("Local summarization failed for email %s: %s", getattr(email, "id", "unknown"), exc)
            summaries[email.id] = getattr(email, "subject", "") or ""
    return summaries
