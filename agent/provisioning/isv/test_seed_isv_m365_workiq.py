from __future__ import annotations

from seed_isv_m365_workiq import (
    HUDDLE_THREAD_TAG,
    MAIL_SUBJECT,
    MARKER,
    SeedContext,
    build_events,
    build_huddle_event,
    build_huddle_thread_message,
    build_mail,
    build_self_chat_messages,
    build_tasks,
    select_exact,
)


def test_huddle_thread_and_meeting_are_alder_creek_only() -> None:
    alder = SeedContext(user_address="demo@example.invalid")
    fabrikam = SeedContext(
        user_address="demo@example.invalid",
        account_id="ACC-1002",
        account_name="Fabrikam Unified School District",
        renewal_id="REN-1002",
    )

    thread = build_huddle_thread_message(alder)
    event = build_huddle_event(alder)

    assert thread is not None and event is not None
    assert HUDDLE_THREAD_TAG in thread["body"]["content"]
    assert "USD 2.2M" in thread["body"]["content"]
    assert event["isOnlineMeeting"] is True
    assert "attendees" not in event
    assert build_huddle_thread_message(fabrikam) is None
    assert build_huddle_event(fabrikam) is None


def test_builds_complete_isv_work_iq_seed_package() -> None:
    context = SeedContext(user_address="demo@example.invalid")

    mail = build_mail(context)
    events = build_events(context)
    tasks = build_tasks(context)
    messages = build_self_chat_messages(context)

    assert mail["message"]["subject"] == MAIL_SUBJECT
    assert mail["message"]["toRecipients"][0]["emailAddress"]["address"] == "demo@example.invalid"
    assert len(events) == 2
    assert len(tasks) == 3
    assert len(messages) == 2
    combined = str(mail) + str(events) + str(tasks) + str(messages)
    for token in ("ACC-1001", "REN-1001", "COM-1001", "COM-1002", "COM-1003", "AI Automation"):
        assert token in combined
    assert MARKER in combined


def test_exact_selection_is_case_insensitive() -> None:
    items = [{"id": "one", "subject": MAIL_SUBJECT.upper()}]
    assert select_exact(items, "subject", MAIL_SUBJECT)["id"] == "one"
    assert select_exact(items, "subject", "unrelated") is None


def test_builds_positive_fabrikam_expansion_evidence() -> None:
    context = SeedContext(
        user_address="demo@example.invalid",
        account_id="ACC-1002",
        account_name="Fabrikam Unified School District",
        renewal_id="REN-1002",
    )

    combined = str(build_mail(context)) + str(build_events(context))
    combined += str(build_tasks(context)) + str(build_self_chat_messages(context))

    for token in ("Fabrikam Unified School District", "ACC-1002", "REN-1002", "COM-2001", "COM-2002"):
        assert token in combined
    assert "USD 300,000" in combined
    assert "complete" in combined
