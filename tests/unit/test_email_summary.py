"""Unit tests for the clean email summary extraction."""

from app.services.email_summary import extract_clean_summary


def test_extract_clean_summary_removes_greetings_and_signatures():
    body = (
        "Dear Students,\n\n"
        "Please find attached the seating plan for the ST-2 examination scheduled on 17/11/2026.\n\n"
        "Best regards,\n"
        "Examination Cell"
    )
    summary = extract_clean_summary(body)
    assert summary == "Please find attached the seating plan for the ST-2 examination scheduled on 17/11/2026."


def test_extract_clean_summary_handles_html_and_boilerplate():
    body = (
        "<p>Hello Team,<br>"
        "The project deployment has been successfully completed and tested."
        "<br>Thanks & regards,<br>DevOps</p>"
        "<small>This email and any attachments are confidential.</small>"
    )
    summary = extract_clean_summary(body)
    assert "project deployment has been successfully completed" in summary
    assert "confidential" not in summary
    assert "Hello" not in summary


def test_extract_clean_summary_truncates_long_body_cleanly():
    body = (
        "This is an urgent announcement regarding the system maintenance schedule for the entire department "
        "covering all primary servers, secondary backup nodes, and related database clusters throughout the weekend."
    )
    summary = extract_clean_summary(body, max_length=60)
    assert len(summary) <= 61  # Complete sentence ending with period
    assert summary.endswith(".")
    assert not summary.endswith(" ...")


def test_extract_clean_summary_empty_or_none():
    assert extract_clean_summary("") == ""
    assert extract_clean_summary(None) == ""


def test_extract_clean_summary_removes_css_and_style_tags():
    body = (
        "<style>display: block; list-style-type: disc; margin: 0 auto; padding-left: 40px; "
        ".textVerdana12 { font-size:12px; font-family:Verdana, Arial, Helvetica; }</style>"
        "<p>Dear Students,<br>"
        "New circular regarding Seating Plan for Numerical Aptitude test in Block 3 on 17/11/2026."
        "</p>"
    )
    summary = extract_clean_summary(body)
    assert "display: block" not in summary
    assert "textVerdana" not in summary
    assert "font-size" not in summary
    assert "Seating Plan for Numerical Aptitude test in Block 3 on 17/11/2026." in summary


def test_extract_clean_summary_removes_plain_text_css_selectors_and_wrappers():
    body = (
        ".textVerdana12 .textVerdana14 hr.style-three "
        "Chitkara University NEW CIRCULAR A new circular with title Datesheet for BCA &amp; BCA (AIML) & MCA End Term Examinations December 2026 has been shared with you."
    )
    summary = extract_clean_summary(body)
    assert "textVerdana" not in summary
    assert "style-three" not in summary
    assert "Datesheet for BCA & BCA (AIML) & MCA End Term Examinations December 2026." in summary


def test_batch_summarize_emails_local():
    from app.services.email_summary import batch_summarize_emails
    from app.schemas.email import Email

    emails = [
        Email(id="e-1", provider_message_id="p-1", sender="admin@chitkara.edu.in",
              receiver="me@example.com", subject="Seating plan",
              body="Dear student, the exam will be held in Block 3. Best regards, Exam Cell."),
        Email(id="e-2", provider_message_id="p-2", sender="hr@company.com",
              receiver="me@example.com", subject="Offer letter",
              body="Hello Karthik, Please find the attached employment contract for Senior Engineer."),
    ]
    results = batch_summarize_emails(emails)
    assert "the exam will be held in Block 3." in results["e-1"]
    assert "Please find the attached employment contract" in results["e-2"]
