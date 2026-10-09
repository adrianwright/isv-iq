from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.workiq import (
    WorkIQAnswer,
    WorkIQAttribution,
    WorkIQClient,
    WorkIQProtocolError,
    WorkIQRequestError,
    WorkIQTokenExchangeError,
    _extract_attributions,
    _markdown_attributions,
    ask_with_access_token,
)


class _OboSuccess:
    def acquire_token_on_behalf_of(self, *, user_assertion: str, scopes: list[str]) -> dict[str, str]:
        assert user_assertion == "incoming-token"
        assert scopes == ["api://workiq.svc.cloud.microsoft/.default"]
        return {"access_token": "work-iq-token"}


class _OboFailure:
    def acquire_token_on_behalf_of(self, *, user_assertion: str, scopes: list[str]) -> dict[str, str]:
        return {"error": "invalid_grant", "error_description": "consent is missing"}


def _settings() -> Settings:
    return Settings(_env_file=None, WORK_IQ_TIMEOUT_SECONDS=5)


def test_work_iq_success_parses_a2a_task_and_sends_required_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["A2A-Version"] == "1.0"
        assert request.headers["Authorization"].endswith("work-iq-token")
        assert payload["method"] == "SendMessage"
        assert payload["params"]["message"]["role"] == "ROLE_USER"
        return httpx.Response(
            200,
            request=request,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "task": {
                        "id": "task-1",
                        "contextId": "context-1",
                        "status": {
                            "state": "TASK_STATE_COMPLETED",
                            "message": {
                                "metadata": {
                                    "attributions": [
                                        {
                                            "attributionType": "Citation",
                                            "providerDisplayName": "Renewal huddle summary",
                                            "seeMoreWebUrl": "https://contoso.sharepoint.com/renewal-huddle",
                                        },
                                        {
                                            "attributionType": "Annotation",
                                            "providerDisplayName": "Dana",
                                            "seeMoreWebUrl": "https://contoso.example/people/dana",
                                        },
                                        {
                                            "attributionType": "Citation",
                                            "providerDisplayName": "Unsafe",
                                            "seeMoreWebUrl": "javascript:alert(1)",
                                        },
                                    ]
                                }
                            },
                        },
                        "artifacts": [
                            {
                                "artifactId": "answer-1",
                                "parts": [{"text": "Coordinator Dana owns the renewal forecast task."}],
                            }
                        ],
                    }
                },
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    answer = WorkIQClient(
        _settings(),
        obo_application=_OboSuccess(),
        http_client=http_client,
    ).ask(user_assertion="incoming-token", question="Find the owner")

    assert answer.text == "Coordinator Dana owns the renewal forecast task."
    assert answer.task_id == "task-1"
    assert answer.context_id == "context-1"
    assert answer.attributions == (
        WorkIQAttribution(
            title="Renewal huddle summary",
            url="https://contoso.sharepoint.com/renewal-huddle",
        ),
        WorkIQAttribution(
            title="Dana",
            url="https://contoso.example/people/dana",
            attribution_type="annotation",
        ),
    )


def test_work_iq_finds_nested_and_url_less_citations() -> None:
    response = {
        "result": {
            "task": {
                "artifacts": [
                    {
                        "parts": [
                            {
                                "text": "Answer",
                                "metadata": {
                                    "attributions": [
                                        {
                                            "attributionType": "Citation",
                                            "providerDisplayName": "Coordinator task",
                                        },
                                        {
                                            "attributionType": "Citation",
                                            "providerDisplayName": "Renewal huddle summary",
                                            "seeMoreWebUrl": "https://contoso.sharepoint.com/summary",
                                        },
                                    ]
                                },
                            }
                        ]
                    }
                ]
            }
        }
    }

    attributions, diagnostics = _extract_attributions(response)

    assert attributions == (
        WorkIQAttribution(title="Coordinator task", url=None),
        WorkIQAttribution(
            title="Renewal huddle summary",
            url="https://contoso.sharepoint.com/summary",
        ),
    )
    assert diagnostics.candidate_count == 2
    assert diagnostics.accepted_count == 2


def test_work_iq_extracts_grounded_markdown_links() -> None:
    text = (
        "[Renewal QBR](https://outlook.office365.com/owa/?ItemID=mail-1) "
        "[Microsoft Administrator](https://www.office.com/search?q=admin) "
        "[Recovery review](https://teams.microsoft.com/l/meeting/details?eventId=event-1) "
        "[1](https://outlook.office365.com/owa/?ItemID=mail-1#citation)"
    )

    assert _markdown_attributions(text) == (
        WorkIQAttribution(
            title="Renewal QBR",
            url="https://outlook.office365.com/owa/?ItemID=mail-1",
        ),
        WorkIQAttribution(
            title="Recovery review",
            url="https://teams.microsoft.com/l/meeting/details?eventId=event-1",
        ),
    )


def test_work_iq_extracts_unique_numbered_markdown_citations() -> None:
    text = (
        "[1](https://outlook.office365.com/owa/?ItemID=mail-1) "
        "[2](https://teams.microsoft.com/l/message/chat-1/message-1)"
    )

    assert _markdown_attributions(text) == (
        WorkIQAttribution(
            title="Work IQ citation 1",
            url="https://outlook.office365.com/owa/?ItemID=mail-1",
        ),
        WorkIQAttribution(
            title="Work IQ citation 2",
            url="https://teams.microsoft.com/l/message/chat-1/message-1",
        ),
    )


def test_work_iq_parses_reference_data_parts_and_logs_only_shape(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "task": {
                        "id": "task-reference",
                        "contextId": "context-reference",
                        "status": {"state": "TASK_STATE_COMPLETED"},
                        "artifacts": [
                            {
                                "artifactId": "answer",
                                "parts": [
                                    {"text": "The coordinator owns the next step."},
                                    {
                                        "mediaType": "application/vnd.workiq-reference",
                                        "data": {
                                            "references": [
                                                {
                                                    "title": "Coordinator handoff",
                                                    "webUrl": "https://contoso.sharepoint.com/private/handoff",
                                                }
                                            ]
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                },
            },
        )

    with caplog.at_level("INFO", logger="app.workiq"):
        answer = ask_with_access_token(
            access_token="work-iq-token",
            question="Find the owner",
            endpoint="https://workiq.example/a2a/",
            timeout_seconds=5,
            timezone_offset_minutes=-300,
            timezone="America/Chicago",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    assert answer.attributions == (
        WorkIQAttribution(
            title="Coordinator handoff",
            url="https://contoso.sharepoint.com/private/handoff",
            attribution_type="reference",
        ),
    )
    assert "candidates=1 accepted=1 types=reference=1 reference_parts=1 invalid_urls=0" in caplog.text
    assert "contoso.sharepoint.com" not in caplog.text


def test_work_iq_surfaces_obo_failure() -> None:
    with pytest.raises(WorkIQTokenExchangeError, match="invalid_grant"):
        WorkIQClient(_settings(), obo_application=_OboFailure()).ask(
            user_assertion="incoming-token",
            question="Find the owner",
        )


def test_work_iq_surfaces_http_failure() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    )
    with pytest.raises(WorkIQRequestError, match="HTTP 503"):
        WorkIQClient(
            _settings(),
            obo_application=_OboSuccess(),
            http_client=http_client,
        ).ask(user_assertion="incoming-token", question="Find the owner")


def test_work_iq_surfaces_quota_error_detail_and_request_id() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403,
                request=request,
                headers={"request-id": "request-123"},
                json={
                    "error": "QuotaExhausted",
                    "message": "No AI credits are currently available for this user.",
                },
            )
        )
    )
    with pytest.raises(
        WorkIQRequestError,
        match=r"QuotaExhausted.*No AI credits.*request-123",
    ):
        WorkIQClient(
            _settings(),
            obo_application=_OboSuccess(),
            http_client=http_client,
        ).ask(user_assertion="incoming-token", question="Find the owner")


def test_work_iq_surfaces_nested_error_detail() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403,
                request=request,
                json={
                    "error": {
                        "code": "QuotaExhausted",
                        "message": "The assigned spending policy has reached its limit.",
                    }
                },
            )
        )
    )
    with pytest.raises(
        WorkIQRequestError,
        match=r"QuotaExhausted.*assigned spending policy",
    ):
        WorkIQClient(
            _settings(),
            obo_application=_OboSuccess(),
            http_client=http_client,
        ).ask(user_assertion="incoming-token", question="Find the owner")


def test_work_iq_rejects_json_rpc_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": "agent unavailable"},
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(WorkIQProtocolError, match="agent unavailable"):
        WorkIQClient(
            _settings(),
            obo_application=_OboSuccess(),
            http_client=http_client,
        ).ask(user_assertion="incoming-token", question="Find the owner")
