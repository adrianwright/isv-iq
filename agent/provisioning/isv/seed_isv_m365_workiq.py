"""Seed synthetic ISV renewal evidence into the signed-in user's Microsoft 365 data.

The module is import-safe. Payload builders and idempotent selection helpers perform no network
work; only ``main`` signs in and writes. The seeder never sends content to another person: mail is
self-addressed, calendar events are private, tasks are personal, and Teams messages use self-chat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SUBJECT_VERSION = "v1"
MARKER = f"[Microsoft IQ for ISVs Demo {SUBJECT_VERSION}]"
MAIL_SUBJECT = (
    f"{MARKER} ACC-1001 / REN-1001 "
    "Contoso Unified School District decision evidence"
)
TODO_LIST_NAME = "Microsoft IQ for ISVs Demo"
SELF_CHAT_ID = "48:notes"
SCOPES = (
    "User.Read",
    "Mail.ReadBasic",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Tasks.ReadWrite",
    "Chat.Read",
    "ChatMessage.Send",
    "Chat.Create",
)
GRAPH_OBO_SCOPES = tuple(
    f"https://graph.microsoft.com/{scope}"
    for scope in (
        "User.Read",
        "Mail.ReadBasic",
        "Mail.Send",
        "Calendars.ReadWrite",
        "Tasks.ReadWrite",
        "Chat.Read",
        "ChatMessage.Send",
        "Chat.Create",
    )
)


@dataclass(frozen=True)
class SeedContext:
    user_address: str
    account_id: str = "ACC-1001"
    account_name: str = "Contoso Unified School District"
    renewal_id: str = "REN-1001"
    proposal_due: str = "2026-10-13"
    recovery_due: str = "2026-10-08"
    roadmap_due: str = "2026-10-10"
    event_time_zone: str = "Eastern Standard Time"


def mail_subject(ctx: SeedContext) -> str:
    return (
        f"{MARKER} {ctx.account_id} / {ctx.renewal_id} "
        f"{ctx.account_name} decision evidence"
    )


def recovery_event_subject(ctx: SeedContext) -> str:
    return f"{MARKER} {ctx.account_name} recovery evidence review"


def proposal_event_subject(ctx: SeedContext) -> str:
    if ctx.account_id == "ACC-1002":
        return f"{MARKER} {ctx.account_name} expansion acceleration approval"
    return f"{MARKER} {ctx.account_name} three-year proposal approval"


@dataclass
class GraphClient:
    access_token: str
    http_client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=30))
    sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:
        return "GraphClient()"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(5):
            response = self.http_client.request(
                method,
                url,
                json=json_body,
                params=params,
                headers=headers,
                follow_redirects=True,
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"{method} {path} failed with HTTP {response.status_code}: "
                        f"{response.text[:400]}"
                    )
                return response
            if attempt < 4:
                retry_after = response.headers.get("Retry-After")
                self.sleep(float(retry_after) if retry_after else min(2**attempt, 16))
        raise RuntimeError(f"{method} {path} exhausted retries")

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request("GET", path, params=params).json()


def build_mail(ctx: SeedContext) -> dict[str, Any]:
    body = (
        f"{MARKER}\n\nSynthetic customer-renewal evidence for {ctx.account_name} "
        f"({ctx.account_id}) and renewal {ctx.renewal_id}.\n\n"
        + (
            "Customer review: Elena Torres and Marcus Reed approved the AI Automation business "
            "case and requested an accelerated rollout. Analytics adoption is 88% with positive "
            "growth; no P1 case, SLA breach, overdue invoice, architecture gate, or capacity "
            "constraint blocks the USD 300,000 expansion.\n\nCOM-2001 Sam Rivera: commercial "
            "sponsorship complete.\nCOM-2002 Taylor Brooks: security, integration, capacity, and "
            "measurable-value validation complete.\n\nHuman approval is required for the phased "
            "rollout plan."
            if ctx.account_id == "ACC-1002"
            else (
                "District QBR: Maya Chen and Daniel Ortiz requested a three-year proposal with "
                f"price protection by {ctx.proposal_due}. Pricing, Finance, payment, recovery, "
                "and roadmap approvals are complete, so the proposal is ready to send. Support "
                "reliability and Analytics adoption still constrain the full-value forecast.\n\n"
                f"COM-1003 Casey Williams completed {ctx.recovery_due}: incident recovery summary "
                f"and service-credit recommendation.\nCOM-1002 Riley Nguyen completed "
                f"{ctx.roadmap_due}: Analytics resiliency roadmap response.\nCOM-1001 Jordan Lee "
                f"completed {ctx.proposal_due}: three-year renewal proposal.\n\nAI Automation "
                "remains a USD 450,000 ARR candidate pending funded workshop sponsorship and "
                "protected architecture capacity."
            )
        )
    )
    return {
        "message": {
            "subject": mail_subject(ctx),
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": ctx.user_address}}
            ],
        },
        "saveToSentItems": True,
    }


def build_events(ctx: SeedContext) -> list[dict[str, Any]]:
    return [
        {
            "subject": recovery_event_subject(ctx),
            "start": {"dateTime": "2026-10-08T10:00:00", "timeZone": ctx.event_time_zone},
            "end": {"dateTime": "2026-10-08T10:30:00", "timeZone": ctx.event_time_zone},
            "showAs": "busy",
            "sensitivity": "private",
            "body": {
                "contentType": "text",
                "content": (
                    f"{MARKER} Review {ctx.account_id}/{ctx.renewal_id}: customer demand, "
                    "adoption, support health, and architecture readiness are complete for "
                    "expansion acceleration."
                    if ctx.account_id == "ACC-1002"
                    else (
                        f"{MARKER} Review completed COM-1003 for "
                        f"{ctx.account_id}/{ctx.renewal_id}: incident summary, recovery plan, "
                        "and service-credit recommendation accepted by the district."
                    )
                ),
            },
        },
        {
            "subject": proposal_event_subject(ctx),
            "start": {"dateTime": "2026-10-13T14:00:00", "timeZone": ctx.event_time_zone},
            "end": {"dateTime": "2026-10-13T14:45:00", "timeZone": ctx.event_time_zone},
            "showAs": "busy",
            "sensitivity": "private",
            "body": {
                "contentType": "Text",
                "content": (
                    f"{MARKER} Approve acceleration for {ctx.account_id}/{ctx.renewal_id}: "
                    "commercial sponsorship and architecture validation are complete. Confirm "
                    "phased rollout and value checkpoints."
                    if ctx.account_id == "ACC-1002"
                    else (
                        f"{MARKER} Release completed COM-1001 for "
                        f"{ctx.account_id}/{ctx.renewal_id}: three-year proposal with price "
                        "protection. Payment, recovery, roadmap, Finance, and executive review "
                        "are complete."
                    )
                ),
            },
        },
    ]


def build_tasks(ctx: SeedContext) -> list[dict[str, Any]]:
    items = (
        (
            ("COM-2001", "Sam Rivera", "2026-10-12", "Commercial sponsorship complete."),
            (
                "COM-2002",
                "Taylor Brooks",
                "2026-10-15",
                "Architecture, security, capacity, and value validation complete.",
            ),
        )
        if ctx.account_id == "ACC-1002"
        else (
            (
                "COM-1003",
                "Casey Williams",
                ctx.recovery_due,
                "Incident recovery summary and service-credit recommendation completed.",
            ),
            (
                "COM-1002",
                "Riley Nguyen",
                ctx.roadmap_due,
                "Analytics resiliency roadmap date confirmed.",
            ),
            (
                "COM-1001",
                "Jordan Lee",
                ctx.proposal_due,
                "Three-year renewal proposal approved for release.",
            ),
        )
    )
    return [
        {
            "title": f"{commitment}: {text} {MARKER}",
            "body": {
                "contentType": "text",
                "content": (
                    f"Synthetic ISV commitment for {ctx.account_name} ({ctx.account_id}), renewal "
                    f"{ctx.renewal_id}. Owner: {owner}. Due: {due}. Human review required."
                ),
            },
            "dueDateTime": {"dateTime": f"{due}T17:00:00", "timeZone": ctx.event_time_zone},
            "status": "completed",
        }
        for commitment, owner, due, text in items
    ]


def build_self_chat_messages(ctx: SeedContext) -> list[dict[str, Any]]:
    return [
        {
            "body": {
                "contentType": "text",
                "content": (
                    f"{MARKER}[{ctx.account_id}-EXPANSION-READY] "
                    f"{ctx.account_id}/{ctx.renewal_id}: executive sponsorship, adoption, "
                    "architecture, support, payment, and capacity criteria are complete."
                    if ctx.account_id == "ACC-1002"
                    else (
                        f"{MARKER}[{ctx.account_id}-RENEWAL-PLAN] "
                        f"{ctx.account_id}/{ctx.renewal_id}: proposal release criteria are "
                        "complete; full-value forecast still depends on support stability, "
                        "adoption recovery, and the CIO response."
                    )
                ),
            }
        },
        {
            "body": {
                "contentType": "text",
                "content": (
                    f"{MARKER}[{ctx.account_id}-EXPANSION] AI Automation is a qualified "
                    "USD 300,000 ARR opportunity. Taylor Brooks completed architecture "
                    "validation and reserved capacity; proceed with phased rollout planning."
                    if ctx.account_id == "ACC-1002"
                    else (
                        f"{MARKER}[{ctx.account_id}-EXPANSION] AI Automation is a credible "
                        "USD 450,000 ARR candidate. Riley Nguyen owns architecture validation; "
                        "specialist capacity and workshop sponsorship remain unresolved."
                    )
                ),
            }
        },
    ]


HUDDLE_ACCOUNT_ID = "ACC-1001"
HUDDLE_THREAD_TAG = f"[{HUDDLE_ACCOUNT_ID}-HUDDLE-THREAD]"
HUDDLE_SCRIPT_PATH = "docs/isv-demo-huddle-script.md"


def huddle_event_subject(ctx: SeedContext) -> str:
    return f"{MARKER} {ctx.account_name} renewal forecast huddle"


def build_huddle_thread_message(ctx: SeedContext) -> dict[str, Any] | None:
    """Teams-conversation evidence for the Contoso forecast huddle (self-chat only)."""
    if ctx.account_id != HUDDLE_ACCOUNT_ID:
        return None
    lines = (
        f"{MARKER}{HUDDLE_THREAD_TAG} {ctx.account_name} / {ctx.renewal_id} - "
        "Forecast huddle thread",
        "",
        "Jordan Lee: Team, the three-year proposal is ready to send and all 3 of 3 "
        "commitments are complete. Do we keep the full USD 2.4M in the forecast?",
        "",
        "Morgan Patel: Not yet. Analytics adoption is 53% and trending -14%. I can't "
        "validate recovery with that trend.",
        "",
        "Casey Williams: Two P1 cases are still open and one SLA breach is under "
        "monitoring. The recovery package was approved, but the district hasn't "
        "confirmed closure.",
        "",
        "Alex Johnson: Maya Chen says the new CIO asked for the proposal but hasn't "
        "responded on value. I want the forecast held at USD 2.2M until we hear back.",
        "",
        f"Jordan Lee: Agreed. Hold at USD 2.2M. I'll own the forecast action, due "
        f"{ctx.proposal_due}. Morgan validates adoption, Alex does executive review.",
        "",
        "Riley Nguyen: Separately, AI Automation is still a credible USD 450K candidate, "
        "pending workshop sponsorship and architecture capacity.",
    )
    return {"body": {"contentType": "text", "content": "\n".join(lines)}}


def huddle_chat_topic(ctx: SeedContext) -> str:
    return "Contoso USD - Renewal forecast huddle"


def build_huddle_event(ctx: SeedContext) -> dict[str, Any] | None:
    """Private Teams meeting for a live, transcribed run (no attendees are invited)."""
    if ctx.account_id != HUDDLE_ACCOUNT_ID:
        return None
    return {
        "subject": huddle_event_subject(ctx),
        "start": {"dateTime": "2026-10-12T14:00:00", "timeZone": ctx.event_time_zone},
        "end": {"dateTime": "2026-10-12T14:30:00", "timeZone": ctx.event_time_zone},
        "showAs": "busy",
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "body": {
            "contentType": "text",
            "content": (
                f"{MARKER} Synthetic demo meeting for {ctx.account_id}/{ctx.renewal_id}. "
                "Turn on transcription at the start and read the script in "
                f"{HUDDLE_SCRIPT_PATH}. Agenda: forecast hold at USD 2.2M, 2 open P1 cases, "
                "Analytics adoption 53% (-14%), new CIO proposal response."
            ),
        },
    }


def select_exact(items: Sequence[dict[str, Any]], field: str, value: str) -> dict[str, Any] | None:
    expected = value.strip().casefold()
    return next(
        (
            item
            for item in items
            if str(item.get(field, "")).strip().casefold() == expected
        ),
        None,
    )


def _acquire_token(tenant_id: str, client_id: str) -> str:
    import msal
    from msal_extensions import PersistedTokenCache, build_encrypted_persistence

    user_assertion = os.environ.get("USER_ASSERTION", "").strip()
    certificate_pfx = os.environ.get("WORK_IQ_CLIENT_CERTIFICATE_PFX", "").strip()
    if user_assertion and certificate_pfx:
        from app.config import Settings
        from app.keyvault_certificate import create_certificate_credential_provider

        settings = Settings(
            _env_file=None,
            APP_ENVIRONMENT="production",
            AZURE_TENANT_ID=tenant_id,
            WORK_IQ_CLIENT_ID=client_id,
            WORK_IQ_CLIENT_CERTIFICATE_PFX=certificate_pfx,
        )
        credential = create_certificate_credential_provider(
            settings
        ).get_client_credential()
        application = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=credential,
        )
        result = application.acquire_token_on_behalf_of(
            user_assertion=user_assertion,
            scopes=list(GRAPH_OBO_SCOPES),
        )
        if result.get("access_token"):
            return str(result["access_token"])
        raise RuntimeError(
            "Graph OBO token exchange failed: "
            f"{result.get('error_description', result.get('error'))}"
        )

    cache_path = (
        Path.home()
        / ".copilot"
        / "microsoft-iq-isv"
        / f"msal-{client_id}.bin"
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = PersistedTokenCache(build_encrypted_persistence(str(cache_path)))
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    for account in app.get_accounts():
        result = app.acquire_token_silent(list(SCOPES), account=account)
        if result and result.get("access_token"):
            return str(result["access_token"])
    flow = app.initiate_device_flow(scopes=list(SCOPES))
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if not result.get("access_token"):
        raise RuntimeError(
            f"Device-code sign-in failed: {result.get('error_description', result.get('error'))}"
        )
    return str(result["access_token"])


def _seed_mail(graph: GraphClient, ctx: SeedContext) -> str:
    subject = mail_subject(ctx)
    escaped_subject = subject.replace("'", "''")
    existing = graph.get_json(
        "/me/messages",
        params={"$filter": f"subject eq '{escaped_subject}'", "$top": "1"},
    ).get("value", [])
    if select_exact(existing, "subject", subject):
        return "skipped"
    graph.request("POST", "/me/sendMail", json_body=build_mail(ctx))
    return "created"


def _seed_events(graph: GraphClient, ctx: SeedContext) -> list[str]:
    existing = graph.get_json(
        "/me/events",
        params={"$select": "id,subject", "$top": "100"},
    ).get("value", [])
    results: list[str] = []
    for event in build_events(ctx):
        match = select_exact(existing, "subject", event["subject"])
        if match:
            graph.request("PATCH", f"/me/events/{match['id']}", json_body=event)
            results.append("updated")
        else:
            graph.request("POST", "/me/events", json_body=event)
            results.append("created")
    return results


def _seed_tasks(graph: GraphClient, ctx: SeedContext) -> list[str]:
    lists = graph.get_json("/me/todo/lists").get("value", [])
    task_list = select_exact(lists, "displayName", TODO_LIST_NAME)
    if not task_list:
        task_list = graph.request(
            "POST",
            "/me/todo/lists",
            json_body={"displayName": TODO_LIST_NAME},
        ).json()
    tasks_path = f"/me/todo/lists/{task_list['id']}/tasks"
    existing = graph.get_json(tasks_path, params={"$top": "100"}).get("value", [])
    results: list[str] = []
    for task in build_tasks(ctx):
        match = select_exact(existing, "title", task["title"])
        if match:
            graph.request("PATCH", f"{tasks_path}/{match['id']}", json_body=task)
            results.append("updated")
        else:
            graph.request("POST", tasks_path, json_body=task)
            results.append("created")
    return results


def _seed_self_chat(graph: GraphClient, ctx: SeedContext) -> list[str]:
    path = f"/chats/{SELF_CHAT_ID}/messages"
    existing = graph.get_json(path, params={"$top": "50"}).get("value", [])
    existing_text = "\n".join(
        str(item.get("body", {}).get("content", ""))
        for item in existing
    )
    results: list[str] = []
    for message in build_self_chat_messages(ctx):
        content = message["body"]["content"]
        tag = re.search(rf"\[{ctx.account_id}-[A-Z-]+\]", content)
        marker = tag.group(0) if tag else f"[{ctx.account_id}-"
        if marker in existing_text:
            results.append("skipped")
        else:
            graph.request("POST", path, json_body=message)
            results.append("created")
    return results


def _seed_huddle_thread(graph: GraphClient, ctx: SeedContext) -> str:
    message = build_huddle_thread_message(ctx)
    if message is None:
        return "not-applicable"
    path = f"/chats/{SELF_CHAT_ID}/messages"
    existing = graph.get_json(path, params={"$top": "50"}).get("value", [])
    if any(
        HUDDLE_THREAD_TAG in str(item.get("body", {}).get("content", ""))
        for item in existing
    ):
        return "skipped"
    graph.request("POST", path, json_body=message)
    return "created"


def _seed_huddle_meeting(graph: GraphClient, ctx: SeedContext) -> str:
    event = build_huddle_event(ctx)
    if event is None:
        return "not-applicable"
    existing = graph.get_json(
        "/me/events",
        params={"$select": "id,subject", "$top": "100"},
    ).get("value", [])
    match = select_exact(existing, "subject", event["subject"])
    if match:
        # A body-only PATCH strips the Teams join block, so re-assert the online meeting.
        graph.request(
            "PATCH",
            f"/me/events/{match['id']}",
            json_body={
                "body": event["body"],
                "isOnlineMeeting": True,
                "onlineMeetingProvider": "teamsForBusiness",
            },
        )
        return "updated"
    graph.request("POST", "/me/events", json_body=event)
    return "created"


def _seed_huddle_group_chat(
    graph: GraphClient, ctx: SeedContext, member_upns: Sequence[str]
) -> str:
    message = build_huddle_thread_message(ctx)
    if message is None or not member_upns:
        return "not-applicable"
    topic = huddle_chat_topic(ctx)
    chats = graph.get_json(
        "/me/chats",
        params={"$filter": "chatType eq 'group'", "$select": "id,topic", "$top": "50"},
    ).get("value", [])
    chat = select_exact(chats, "topic", topic)
    if not chat:
        members = [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"{GRAPH_BASE}/users('{upn}')",
            }
            for upn in [graph.get_json("/me", params={"$select": "userPrincipalName"})["userPrincipalName"], *member_upns]
        ]
        chat = graph.request(
            "POST",
            "/chats",
            json_body={"chatType": "group", "topic": topic, "members": members},
        ).json()
    path = f"/chats/{chat['id']}/messages"
    existing = graph.get_json(path, params={"$top": "50"}).get("value", [])
    if any(
        HUDDLE_THREAD_TAG in str(item.get("body", {}).get("content", ""))
        for item in existing
    ):
        return "skipped"
    graph.request("POST", path, json_body=message)
    return "created"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument(
        "--huddle-members",
        default="",
        help="Comma-separated UPNs. When set, also posts the huddle thread to a group chat "
        "with these people. Omit to keep the seeder self-only.",
    )
    args = parser.parse_args(argv)
    huddle_members = [m.strip() for m in args.huddle_members.split(",") if m.strip()]

    token = _acquire_token(args.tenant_id, args.client_id)
    graph = GraphClient(token)
    profile = graph.get_json("/me", params={"$select": "mail,userPrincipalName"})
    address = str(profile.get("mail") or profile.get("userPrincipalName") or "")
    if not address:
        raise RuntimeError("Signed-in profile has no mail or userPrincipalName.")
    contexts = [
        SeedContext(user_address=address),
        SeedContext(
            user_address=address,
            account_id="ACC-1002",
            account_name="Fabrikam Unified School District",
            renewal_id="REN-1002",
            proposal_due="2026-10-20",
            recovery_due="2026-10-12",
            roadmap_due="2026-10-15",
        ),
    ]
    result = {
        context.account_id: {
            "mail": _seed_mail(graph, context),
            "events": _seed_events(graph, context),
            "tasks": _seed_tasks(graph, context),
            "selfChat": _seed_self_chat(graph, context),
            "huddleThread": _seed_huddle_thread(graph, context),
            "huddleMeeting": _seed_huddle_meeting(graph, context),
            "huddleGroupChat": _seed_huddle_group_chat(graph, context, huddle_members),
        }
        for context in contexts
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
