"""Extract clean, concise summary snippets from email bodies."""

import html
import re

from typing import Any
from pydantic import BaseModel
from app.core.logger import logger

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


class EmailBatchSummaryItem(BaseModel):
    id: str
    summary: str


class EmailBatchSummaryResponse(BaseModel):
    summaries: list[EmailBatchSummaryItem] = []


def extract_clean_summary(body: str | None, max_length: int = 150) -> str:
    """Extract a concise, clean summary snippet focusing on the core point without boilerplate."""
    if not body:
        return ""

    # Remove <style>...</style>, <script>...</script>, <head>...</head> blocks and comments completely
    text = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", body)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities (&amp;, &nbsp;, etc.)
    text = html.unescape(text)
    # Remove CSS rules with selector and block: e.g. .className { ... } or hr.style { ... }
    text = re.sub(r"(?s)[^{};<>\n]*\{[^}]*\}", " ", text)
    # Remove stray CSS declarations: e.g. display: block; margin: 0 auto;
    text = re.sub(r"(?i)\b[a-z-]+\s*:\s*[^;:<\n]+;", " ", text)
    # Remove orphaned CSS selectors/classes: e.g. .textVerdana12 or hr.style-three or #id
    text = re.sub(r"(?:\.[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+|#[a-zA-Z0-9_-]+)", " ", text)
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


def batch_summarize_emails(emails: list[Any], ai_service=None) -> dict[str, str]:
    """Generate concise 1-sentence abstractive summaries in own words using a single Gemini call.

    Falls back instantly to deterministic extraction if Gemini is unavailable or rate-limited.
    """
    if not emails:
        return {}

    # Target the top 8 emails for fast LLM summarization (rest use clean extraction)
    target_emails = emails[:8]

    try:
        if ai_service is None:
            from app.services.ai_service import get_ai_service
            service = get_ai_service()
        else:
            service = ai_service
    except Exception as exc:
        logger.info("AI service unavailable for batch summary (%s); using in-memory extractor", exc)
        return {e.id: extract_clean_summary(e.body) for e in emails}

    email_blocks = []
    for e in target_emails:
        clean_text = extract_clean_summary(e.body, max_length=400) or e.subject
        email_blocks.append(f"[Email ID: {e.id}]\nSubject: {e.subject}\nSnippet: {clean_text}")

    prompt = (
        "Summarize each of the following emails in a single concise sentence in your own words. "
        "Focus strictly on the primary announcement, update, or action required. "
        "Do not repeat greetings, signatures, or raw metadata.\n\n"
        + "\n\n".join(email_blocks)
    )

    try:
        from google.genai import types
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EmailBatchSummaryResponse,
            http_options=types.HttpOptions(timeout=10000),  # 10s minimum allowed by Google API
        )
        resp = service._generate_content("batch_email_summary", prompt, config=config)
        parsed = EmailBatchSummaryResponse.model_validate_json(resp.text)
        summaries = {item.id: item.summary.strip() for item in parsed.summaries if item.id and item.summary}
        # Fill any missing email IDs with the fast extractor
        for e in emails:
            if e.id not in summaries or not summaries[e.id]:
                summaries[e.id] = extract_clean_summary(e.body)
        return summaries
    except Exception as exc:
        logger.info("Batched Gemini summarization skipped or timed out (%s); using clean extractor", exc)
        return {e.id: extract_clean_summary(e.body) for e in emails}
