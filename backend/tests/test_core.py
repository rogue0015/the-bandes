import base64
import sqlite3
from datetime import datetime, timezone
from datetime import timedelta

import requests
from app.security import hash_password, verify_password
from app import database
from app.main import keepalive
from app.config import settings
from app.routers import internal
from app.schemas import WhatsAppChannelPost, WhatsAppInbound, WhatsAppMediaAttachment
from app.services import notifications
from app.services import extractor
from app.services import greetings
from app.services import reminders
from app.services.opportunities import (
    _schedule_reminders,
    canonicalize_url,
    format_group_reply,
    list_reminders,
    save_opportunity,
)
from scraper_service.matching import classify_job, is_current, matches_entrepreneurship
from scraper_service import main as scraper_main


def test_public_keepalive_endpoint_returns_minimal_success(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_service_url", "https://whatsapp.example")
    monkeypatch.setattr(settings, "scraper_service_url", "https://scraper.example")
    probes = []

    def unavailable_service(url, timeout):
        probes.append((url, timeout))
        raise requests.ConnectionError("service is sleeping")

    monkeypatch.setattr("app.main.requests.get", unavailable_service)
    assert keepalive() == {"status": "ok"}
    assert probes == [
        ("https://whatsapp.example/health", 2),
        ("https://scraper.example/health", 2),
    ]


def test_password_hash_verifies_without_storing_plaintext():
    stored = hash_password("a-long-example-password")
    assert "a-long-example-password" not in stored
    assert verify_password("a-long-example-password", stored)
    assert not verify_password("wrong-password", stored)


def test_canonicalize_url_removes_fragment_and_normalizes_host():
    assert canonicalize_url("HTTPS://Example.COM/jobs/42/#apply") == "https://example.com/jobs/42/"


def test_group_reply_confirms_tracking_and_summarizes_deadline():
    reply = format_group_reply(
        {
            "title": "Innovation Fellowship",
            "organization": "Example Foundation",
            "deadline": None,
            "summary": "For early-career innovators.",
            "canonical_url": "https://example.org/fellowship",
        },
        True,
    )
    assert reply.startswith("Added to the opportunity registry: Innovation Fellowship")
    assert "Deadline: Not specified" in reply
    assert "Details: For early-career innovators." in reply
    assert "Source: https://example.org/fellowship" in reply


def test_group_reply_summarizes_articles_without_deadline_or_opportunity_claim():
    reply = format_group_reply(
        {
            "title": "Innovation trends",
            "record_type": "article",
            "organization": None,
            "deadline": None,
            "summary": "A short article summary.",
            "canonical_url": "https://example.org/article",
        },
        True,
    )
    assert reply.startswith("Added to the article summaries: Innovation trends")
    assert "Article summary: A short article summary." in reply
    assert "Deadline:" not in reply


def test_known_deadline_schedules_three_day_and_one_day_reminders():
    deadline = datetime.now(timezone.utc) + timedelta(days=10)
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            """CREATE TABLE reminders (
                opportunity_id INTEGER, offset_days INTEGER, scheduled_at TEXT,
                status TEXT, updated_at TEXT, UNIQUE(opportunity_id, offset_days)
            )"""
        )

        _schedule_reminders(conn, 1, deadline.isoformat())

        reminders = conn.execute(
            "SELECT offset_days, scheduled_at FROM reminders ORDER BY offset_days DESC"
        ).fetchall()
    assert [row[0] for row in reminders] == [3, 1]
    for offset, scheduled_at in reminders:
        assert datetime.fromisoformat(scheduled_at) == deadline - timedelta(days=offset)


def test_articles_do_not_schedule_deadline_reminders():
    deadline = datetime.now(timezone.utc) + timedelta(days=10)
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            """CREATE TABLE reminders (
                opportunity_id INTEGER, offset_days INTEGER, scheduled_at TEXT,
                status TEXT, updated_at TEXT, UNIQUE(opportunity_id, offset_days)
            )"""
        )

        _schedule_reminders(conn, 1, deadline.isoformat(), record_type="article")

        assert conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0] == 0


def test_extract_opportunity_uses_gemini_structured_fields(monkeypatch):
    source_url = "https://example.org/fellowship"
    monkeypatch.setattr(
        extractor,
        "_fetch_page",
        lambda _url: (source_url, "<h1>Fellowship</h1><p>Apply by 2030-01-01.</p>"),
    )
    monkeypatch.setattr(
        extractor,
        "_gemini_extract",
        lambda url, _html: {
            "url": url,
            "title": "Innovation Fellowship",
            "organization": "Example Foundation",
            "summary": "Funding for innovators.",
            "record_type": "opportunity",
            "category": "fellowship",
            "location": None,
            "eligibility": "Early-career applicants",
            "deadline": datetime(2030, 1, 1, 23, 59, tzinfo=timezone.utc),
            "source": "group",
        },
    )

    extracted = extractor.extract_opportunity(source_url)

    assert extracted["title"] == "Innovation Fellowship"
    assert extracted["summary"] == "Funding for innovators."
    assert extracted["deadline"] == datetime(2030, 1, 1, 23, 59, tzinfo=timezone.utc)


def test_local_extract_classifies_articles_and_deadline_opportunities():
    article = extractor._local_extract(
        "https://example.org/article",
        "<h1>Innovation trends</h1><p>News about the local technology sector.</p>",
    )
    opportunity = extractor._local_extract(
        "https://example.org/apply",
        "<h1>Apply for the fellowship</h1><p>Deadline: 2030-01-01.</p>",
    )

    assert article["record_type"] == "article"
    assert opportunity["record_type"] == "opportunity"


def test_gemini_extract_uses_declared_function_call(monkeypatch):
    source_url = "https://example.org/fellowship"
    function_args = {
        "title": "Innovation Fellowship",
        "organization": "Example Foundation",
        "summary": "Funding for innovators.",
        "record_type": "opportunity",
        "category": "fellowship",
        "location": None,
        "eligibility": "Early-career applicants",
        "deadline": "2030-01-01T23:59:00Z",
    }
    request_data = {}

    class GeminiResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "extract_opportunity",
                                        "args": function_args,
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(_url, **kwargs):
        request_data.update(kwargs)
        return GeminiResponse()

    monkeypatch.setattr(extractor.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(extractor.requests, "post", fake_post)

    extracted = extractor._gemini_extract(source_url, "<p>Apply by 2030-01-01.</p>")

    assert extracted["title"] == "Innovation Fellowship"
    assert extracted["deadline"] == datetime(2030, 1, 1, 23, 59, tzinfo=timezone.utc)
    assert request_data["json"]["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"


def test_gemini_extract_attaches_channel_media_inline(monkeypatch):
    source_url = "https://whatsapp.com/channel/123?post=message-1"
    request_data = {}

    class GeminiResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "extract_opportunity",
                                        "args": {
                                            "title": "IT Support Internship",
                                            "organization": None,
                                            "summary": "Entry-level support role.",
                                            "record_type": "opportunity",
                                            "category": "job",
                                            "location": None,
                                            "eligibility": None,
                                            "deadline": None,
                                        },
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(_url, **kwargs):
        request_data.update(kwargs)
        return GeminiResponse()

    monkeypatch.setattr(extractor.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(extractor.requests, "post", fake_post)
    extracted = extractor._gemini_extract(
        source_url,
        "<p>Channel post caption</p>",
        [{"mime_type": "image/png", "data": "aGVsbG8="}],
    )

    parts = request_data["json"]["contents"][0]["parts"]
    assert parts[1] == {
        "inlineData": {"mimeType": "image/png", "data": "aGVsbG8="}
    }
    assert extracted["title"] == "IT Support Internship"


def test_channel_media_validation_enforces_supported_payload_size_and_encoding():
    valid = WhatsAppMediaAttachment(mime_type="image/png", data="aGVsbG8=")
    assert valid.mime_type == "image/png"
    oversized = base64.b64encode(b"a" * (2 * 1024 * 1024 + 1)).decode("ascii")
    for data in ("not-base64", oversized):
        try:
            WhatsAppMediaAttachment(mime_type="image/png", data=data)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid or oversized media should be rejected")


def test_channel_history_posts_are_deduped_without_broadcast(monkeypatch, tmp_path):
    monkeypatch.setattr(database.settings.__class__, "database_path", tmp_path / "bandes.db")
    monkeypatch.setattr(internal.settings, "whatsapp_channel_name", "IT Opportunities Zim")
    monkeypatch.setattr(internal, "_authorized", lambda _token: None)
    monkeypatch.setattr(
        internal,
        "extract_channel_post",
        lambda channel_name, post_url, message, media, urls: {
            "url": post_url,
            "title": "IT Support Internship",
            "summary": "An entry-level IT opportunity.",
            "record_type": "opportunity",
            "category": "job",
            "deadline": datetime.now(timezone.utc) + timedelta(days=10),
            "source": f"whatsapp_channel:{channel_name}",
        },
    )
    database.initialize_database()
    post = WhatsAppChannelPost(
        channel_name="IT Opportunities Zim",
        channel_id="123@newsletter",
        message_id="message-1",
        post_url="https://whatsapp.com/channel/123?post=message-1",
        message="Entry-level IT support position.",
        media=[],
        notify_group=False,
    )

    first = internal.receive_whatsapp_channel_post(post)
    second = internal.receive_whatsapp_channel_post(post)

    assert first["created"] is True
    assert second["duplicate"] is True
    assert second["title"] == "IT Support Internship"
    assert [item["offset_days"] for item in list_reminders()] == [3, 1]
    with database.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0] == 0


def test_live_channel_opportunity_uses_explicit_group_broadcast(monkeypatch, tmp_path):
    monkeypatch.setattr(database.settings.__class__, "database_path", tmp_path / "bandes.db")
    monkeypatch.setattr(internal.settings, "whatsapp_channel_name", "IT Opportunities Zim")
    monkeypatch.setattr(internal, "_authorized", lambda _token: None)
    monkeypatch.setattr(
        internal,
        "extract_channel_post",
        lambda channel_name, post_url, message, media, urls: {
            "url": post_url,
            "title": "IT Support Internship",
            "summary": "An entry-level IT opportunity.",
            "record_type": "opportunity",
            "category": "job",
            "source": f"whatsapp_channel:{channel_name}",
        },
    )
    database.initialize_database()
    post = WhatsAppChannelPost(
        channel_name="IT Opportunities Zim",
        channel_id="123@newsletter",
        message_id="live-message",
        post_url="https://whatsapp.com/channel/123?post=live-message",
        message="Entry-level IT support position.",
        notify_group=True,
    )

    result = internal.receive_whatsapp_channel_post(post)

    assert result["created"] is True
    with database.connection() as conn:
        row = conn.execute(
            "SELECT recipients_json, broadcast FROM notification_outbox"
        ).fetchone()
    assert row["recipients_json"] == "[]"
    assert row["broadcast"] == 1


def test_classifies_requested_job_roles():
    feli = {"title": "Graduate Trainee - ICT Support", "summary": "Entry level role"}
    brandon = {"title": "Business Analyst", "summary": "Strategy team"}
    assert classify_job(feli)[0] == "Feli"
    assert classify_job(brandon)[0] == "Brandon"


def test_job_classifier_rejects_non_entry_it_and_non_business_analysis_roles():
    assert classify_job(
        {"title": "IT Support Specialist", "summary": "Requires 5+ years experience"}
    )[0] is None
    assert classify_job(
        {"title": "Senior IT Support Intern", "summary": "Entry-level placement"}
    )[0] is None
    assert classify_job(
        {"title": "Entry Level Marketing Assistant", "summary": "No experience required"}
    )[0] is None
    assert classify_job(
        {"title": "Project Manager", "summary": "Business analysis experience is helpful"}
    )[0] is None
    assert classify_job(
        {"title": "Business Analysis Intern", "summary": "Entry-level placement"}
    )[0] == "Brandon"


def test_scraper_submits_only_classified_vacancy_listings(monkeypatch):
    submitted = []
    monkeypatch.setattr(scraper_main, "_submit", submitted.append)
    unrelated = {"title": "Marketing Assistant", "summary": "Entry-level role"}
    relevant = {"title": "Junior IT Support", "summary": "Entry-level role"}
    project_manager = {"title": "Project Manager", "summary": "Business analysis"}

    assert scraper_main.process_listing(unrelated) is False
    assert scraper_main.process_listing(project_manager) is False
    assert scraper_main.process_listing(relevant) is True
    assert len(submitted) == 1
    assert submitted[0]["matched_recipient"] == "Feli"


def test_quoted_whatsapp_completion_clears_pending_reminders(monkeypatch, tmp_path):
    monkeypatch.setattr(database.settings.__class__, "database_path", tmp_path / "bandes.db")
    database.initialize_database()
    deadline = datetime.now(timezone.utc) + timedelta(days=10)
    record, created = save_opportunity(
        {
            "url": "https://example.org/fellowship",
            "title": "Innovation Fellowship",
            "summary": "Funding for innovators.",
            "record_type": "opportunity",
            "deadline": deadline,
        }
    )
    assert created is True
    assert [item["status"] for item in list_reminders()] == ["pending", "pending"]

    monkeypatch.setattr(internal, "_authorized", lambda _token: None)
    unquoted = internal.receive_whatsapp_message(
        WhatsAppInbound(
            chat_name="The Bandeees",
            sender="group-member",
            message="Applied",
            urls=[],
        )
    )
    assert unquoted["completion"]["updated"] is False
    assert list_reminders()[0]["opportunity_status"] == "active"
    result = internal.receive_whatsapp_message(
        WhatsAppInbound(
            chat_name="The Bandeees",
            sender="group-member",
            message="Done",
            urls=[],
            quoted_message=f"Opportunity summary\nSource: {record['canonical_url']}",
        )
    )

    assert result["completion"]["updated"] is True
    assert "Innovation Fellowship" in result["completion"]["reply"]
    assert [item["opportunity_status"] for item in list_reminders()] == [
        "completed",
        "completed",
    ]
    assert [item["status"] for item in list_reminders()] == ["skipped", "skipped"]


def test_unscoped_notifications_are_skipped_instead_of_broadcast(monkeypatch, tmp_path):
    monkeypatch.setattr(database.settings.__class__, "database_path", tmp_path / "bandes.db")
    database.initialize_database()
    notifications.enqueue_notification("no-recipient", "not sent")
    now = datetime.now(timezone.utc).isoformat()
    with database.connection() as conn:
        conn.execute(
            """INSERT INTO notification_outbox
               (idempotency_key, message, recipients_json, status, scheduled_at, updated_at)
               VALUES (?, ?, '[]', 'pending', ?, ?)""",
            ("legacy-pending", "not sent", now, now),
        )

    assert notifications._claim_pending() == []
    with database.connection() as conn:
        statuses = {
            row["idempotency_key"]: row["status"]
            for row in conn.execute(
                "SELECT idempotency_key, status FROM notification_outbox"
            )
        }
    assert statuses == {"no-recipient": "skipped", "legacy-pending": "skipped"}


def test_group_broadcast_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(database.settings.__class__, "database_path", tmp_path / "bandes.db")
    database.initialize_database()
    notifications.enqueue_notification(
        "intentional-broadcast", "Relevant entrepreneurship opportunity", broadcast=True
    )

    pending = notifications._claim_pending()

    assert len(pending) == 1
    assert pending[0]["broadcast"] is True
    assert pending[0]["recipients"] == []


def test_reminders_use_matched_recipient_or_explicit_group_source(monkeypatch):
    monkeypatch.setattr(reminders.settings, "whatsapp_feli_phone", "+263 77 123 4567")
    feli = {
        "matched_recipient": "Feli",
        "source": "VacancyMail",
        "category": "job",
    }
    group = {"source": "group", "category": "opportunity"}
    managed_site = {"source": "managed_site:1", "category": "opportunity"}

    assert reminders._notification_target(feli) == {
        "recipients": ["263771234567"],
        "broadcast": False,
    }
    assert reminders._notification_target(group) == {
        "recipients": [],
        "broadcast": True,
    }
    assert reminders._notification_target(managed_site) is None


def test_filters_expired_and_unrelated_entrepreneurship_listings():
    old = {"deadline": "2000-01-01T23:59:00+00:00"}
    current = {"deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    assert not is_current(old)
    assert is_current(current)
    assert matches_entrepreneurship({"title": "Innovation fellowship", "summary": "For leaders"})
    assert not matches_entrepreneurship({"title": "Office administrator", "summary": "Full-time role"})


def test_detail_link_candidates_prioritize_application_links():
    html = (
        '<a href="/about">About us</a>'
        '<a href="/fellowship/apply">Apply for this fellowship</a>'
        '<a href="mailto:info@example.org">Email us</a>'
    )
    candidates = extractor._detail_link_candidates(html, "https://example.org/fellowship")
    assert candidates[0] == "https://example.org/fellowship/apply"
    assert all(not candidate.startswith("mailto:") for candidate in candidates)


def test_find_deadline_follows_detail_links_until_found(monkeypatch):
    base = "https://example.org/fellowship"
    detail = "https://example.org/fellowship/apply"
    html = '<a href="/fellowship/apply">How to apply</a>'
    calls = []

    def fake_fetch(url):
        assert url == detail
        return detail, "<p>The application deadline is 2030-01-01.</p>"

    def fake_gemini(url, _html, media=None):
        calls.append(url)
        return {
            "url": url,
            "title": "Innovation Fellowship",
            "summary": "Description: funding. Requirements: early-career. Deadline: 01 Jan 2030.",
            "record_type": "opportunity",
            "category": "fellowship",
            "deadline": datetime(2030, 1, 1, 23, 59, tzinfo=timezone.utc),
            "source": "group",
        }

    monkeypatch.setattr(extractor, "_fetch_page", fake_fetch)
    monkeypatch.setattr(extractor, "_gemini_extract", fake_gemini)

    result = extractor._find_deadline(
        {"url": base, "record_type": "opportunity", "deadline": None, "summary": "thin"},
        base,
        html,
    )

    assert result["deadline"] == datetime(2030, 1, 1, 23, 59, tzinfo=timezone.utc)
    assert "Requirements:" in result["summary"]
    assert result["url"] == base
    assert calls == [detail]


def test_find_deadline_does_not_follow_when_deadline_known(monkeypatch):
    def fail_fetch(_url):
        raise AssertionError("A detail page must not be fetched when a deadline is present")

    monkeypatch.setattr(extractor, "_fetch_page", fail_fetch)
    result = {
        "url": "https://example.org/fellowship",
        "record_type": "opportunity",
        "deadline": datetime(2030, 1, 1, 23, 59, tzinfo=timezone.utc),
    }
    assert (
        extractor._find_deadline(result, "https://example.org/fellowship", "<a href='/apply'>apply</a>")
        is result
    )


def test_daily_greetings_schedule_remaining_messages_for_feli(monkeypatch):
    captured = []

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 14, 8, 0, tzinfo=tz)

    monkeypatch.setattr(greetings, "datetime", FrozenDateTime)
    monkeypatch.setattr(greetings.settings, "whatsapp_feli_phone", "+263 77 123 4567")
    monkeypatch.setattr(
        greetings,
        "enqueue_notification",
        lambda key, text, recipients, **kwargs: captured.append(
            (key, text, recipients, kwargs.get("scheduled_at"))
        ),
    )

    greetings.schedule_daily_greetings()

    assert [item[0] for item in captured] == [
        "greeting:afternoon:2026-11-14",
        "greeting:night:2026-11-14",
    ]
    assert captured[0][1] == "Good afternoon my Queen Feli"
    assert captured[0][2] == ["263771234567"]
    assert captured[0][3].hour == 13
    assert captured[1][1] == "Good night my Queen Feli"
    assert captured[1][3].hour == 21


def test_daily_greetings_skip_without_feli_phone(monkeypatch):
    captured = []
    monkeypatch.setattr(greetings.settings, "whatsapp_feli_phone", "")
    monkeypatch.setattr(
        greetings, "enqueue_notification", lambda *args, **kwargs: captured.append(args)
    )

    greetings.schedule_daily_greetings()

    assert captured == []


def test_scheduled_notification_is_held_until_due(monkeypatch, tmp_path):
    monkeypatch.setattr(database.settings.__class__, "database_path", tmp_path / "bandes.db")
    database.initialize_database()
    when = datetime.now(timezone.utc) + timedelta(hours=3)

    notifications.enqueue_notification(
        "greeting:morning:2026-11-14",
        "Good morning my Queen Feli",
        ["263771234567"],
        scheduled_at=when,
    )

    with database.connection() as conn:
        row = conn.execute(
            "SELECT scheduled_at, status FROM notification_outbox"
        ).fetchone()
    assert datetime.fromisoformat(row["scheduled_at"]) == when
    assert row["status"] == "pending"
    assert notifications._claim_pending() == []
