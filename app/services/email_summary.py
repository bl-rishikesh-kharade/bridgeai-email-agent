"""Extract clean, concise summary snippets from email bodies."""

import html
import re

GREETING_REGEX = re.compile(
    r"^(?:dear\s+[^,\n]+|hello\s*[^,\n]*|hi\s*[^,\n]*|hey\s*[^,\n]*|greetings|good\s+(?:morning|afternoon|evening))[,\s]*",
    re.IGNORECASE,
)
SIGNATURE_REGEX = re.compile(
    r"^(?:best\s+regards|warm\s+regards|thanks\s*(?:&|and)?\s*regards|regards|thank\s+you|thanks|sincerely|cheers|sent\s+from\s+my|get\s+outlook)\b",
    re.IGNORECASE,
)
BOILERPLATE_REGEX = re.compile(
    r"^(?:this\s+email|caution:|disclaimer:|note:|view\s+(?:in|this)|click\s+here|unsubscribe|copyright|\*+)\b",
    re.IGNORECASE,
)
URL_REGEX = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
EMAIL_HEADER_REGEX = re.compile(r"^(?:from|to|subject|date|sent|cc|bcc):\s*.*$", re.IGNORECASE)


def extract_clean_summary(body: str | None, max_length: int = 150) -> str:
    """Extract a concise, clean summary snippet focusing on the core point without boilerplate."""
    if not body:
        return ""

    # Unescape HTML entities & strip HTML tags
    text = html.unescape(body)
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove raw URLs
    text = URL_REGEX.sub("", text)

    lines = [line.strip() for line in text.splitlines()]
    meaningful_sentences: list[str] = []

    for line in lines:
        if not line:
            continue
        # Skip header repeats like "Subject: ..." or "From: ..."
        if EMAIL_HEADER_REGEX.match(line):
            continue
        # Strip greetings like "Dear Students,"
        cleaned_line = GREETING_REGEX.sub("", line).strip()
        if not cleaned_line:
            continue
        # If signature or boilerplate reached, stop collecting
        if SIGNATURE_REGEX.match(cleaned_line) or BOILERPLATE_REGEX.match(cleaned_line):
            break

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", cleaned_line)
        for s in sentences:
            s_clean = s.strip()
            # Skip noise or separator characters
            if len(s_clean) < 5 or re.match(r"^[-=_*~#]{2,}$", s_clean):
                continue
            if SIGNATURE_REGEX.match(s_clean) or BOILERPLATE_REGEX.match(s_clean):
                break
            meaningful_sentences.append(s_clean)

        if sum(len(s) for s in meaningful_sentences) >= max_length:
            break

    combined = " ".join(meaningful_sentences)
    combined = re.sub(r"\s+", " ", combined).strip()

    if not combined:
        return ""

    if len(combined) <= max_length:
        return combined

    # Cleanly truncate at word boundary
    truncated = combined[:max_length].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{truncated}..."
