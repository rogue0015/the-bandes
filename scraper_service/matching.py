import re
from datetime import datetime, timezone

FELI_TERMS = (
    "information technology", "entry level it", "entry-level it", "it support",
    "ict", "helpdesk", "help desk",
    "software developer", "software engineer", "developer", "network technician",
    "systems administrator", "computer technician", "cybersecurity",
    "cyber security", "database administrator", "technical support", "it officer",
    "it intern", "it assistant",
)
ENTRY_TERMS = (
    "entry level", "entry-level", "junior", "intern", "internship",
    "graduate trainee", "graduate program", "graduate programme", "new graduate",
    "early career", "early-career", "0-2 years", "0 to 2 years",
    "no experience",
)
SENIOR_TERMS = (
    "senior", "lead", "head of", "director", "principal", "manager",
)
EXPERIENCE_TERMS = (
    "5+ years",
    "10+ years",
    "5 years' experience",
    "5 years experience",
    "minimum 5 years",
    "at least 5 years",
)
BRANDON_TERMS = (
    "business analyst",
    "business analysis",
    "business process analyst",
    "requirements analyst",
)
ENTREPRENEURSHIP_TERMS = (
    "innovator", "innovation", "entrepreneur", "entrepreneurship", "startup",
    "start-up", "developing leaders", "young leaders", "fellowship", "incubator",
    "accelerator", "business competition",
)


def _contains(text: str, phrases: tuple[str, ...]) -> str | None:
    normalized = re.sub(r"\s+", " ", text.lower())
    return next(
        (
            phrase
            for phrase in phrases
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized)
        ),
        None,
    )


def classify_job(item: dict) -> tuple[str | None, str | None]:
    title = item.get("title", "")
    text = f"{title} {item.get('summary', '')}"
    phrase = _contains(title, BRANDON_TERMS)
    if phrase:
        return "Brandon", f"Role title matches {phrase}"
    it_match = _contains(title, FELI_TERMS) or _contains(item.get("summary", ""), FELI_TERMS)
    if it_match:
        if _contains(title, SENIOR_TERMS) or _contains(
            item.get("summary", ""), EXPERIENCE_TERMS
        ):
            return None, None
        explicit_entry_role = _contains(text, ENTRY_TERMS)
        if not explicit_entry_role:
            return None, None
        return "Feli", f"Matches {it_match} entry-level IT criteria"
    return None, None


def is_current(item: dict) -> bool:
    deadline = item.get("deadline")
    if not deadline:
        return True
    try:
        return datetime.fromisoformat(deadline.replace("Z", "+00:00")) >= datetime.now(
            timezone.utc
        )
    except ValueError:
        return True


def matches_entrepreneurship(item: dict) -> bool:
    return _contains(f"{item.get('title', '')} {item.get('summary', '')}", ENTREPRENEURSHIP_TERMS) is not None
