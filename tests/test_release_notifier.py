from __future__ import annotations

from typing import Any, Mapping

from deploy_diagnostics.release_notifier import CampaignRequest, ReleaseNotifier


class RecordingSms:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.lookups: list[str] = []

    def send(self, *, to: str, body: str, idempotency_key: str) -> Mapping[str, Any]:
        self.sent.append({"to": to, "body": body, "idempotency_key": idempotency_key})
        return {"message_id": f"msg-{len(self.sent)}"}

    def status(self, message_id: str) -> Mapping[str, Any]:
        self.lookups.append(message_id)
        return {"status": "queued"}


def test_dispatch_selects_pipeline_and_environment_owners() -> None:
    sms = RecordingSms()
    campaign = CampaignRequest.model_validate(
        {
            "build": {
                "build_id": "build-9421",
                "pipeline": "artifact-publisher",
                "commit_sha": "8f31c2a",
                "outcome": "passed",
            },
            "release": {
                "release_id": "artifact-publisher-3.7.0",
                "environment": "production",
                "state": "completed",
                "diagnostic": "Package index and provenance record are available.",
            },
            "routes": [
                {
                    "developer_id": "release-oncall",
                    "phone": "+14155550120",
                    "pipelines": ["artifact-publisher"],
                    "environments": ["production"],
                    "release_sms": True,
                },
                {
                    "developer_id": "staging-owner",
                    "phone": "+14155550121",
                    "pipelines": ["artifact-publisher"],
                    "environments": ["staging"],
                    "release_sms": True,
                },
                {
                    "developer_id": "opted-out-owner",
                    "phone": "+14155550122",
                    "pipelines": ["artifact-publisher"],
                    "environments": ["production"],
                    "release_sms": False,
                },
            ],
        }
    )

    report = ReleaseNotifier(sms).dispatch(campaign)

    assert report.eligible == 1
    assert report.suppressed == 2
    assert report.messages[0].model_dump() == {
        "developer_id": "release-oncall",
        "message_id": "msg-1",
        "status": "queued",
    }
    assert sms.lookups == ["msg-1"]
    assert sms.sent[0]["idempotency_key"] == (
        "release:artifact-publisher-3.7.0:developer:release-oncall"
    )
