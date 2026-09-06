from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .infrai_sms import InfraiError, InfraiSmsClient, InfraiTransportError
from .release_notifier import CampaignReport, CampaignRequest, ReleaseNotifier


app = FastAPI(title="Deploy Diagnostic SMS")


def notifier_from_environment() -> ReleaseNotifier:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("INFRAI_API_KEY is required")
    return ReleaseNotifier(InfraiSmsClient(api_key))


@app.post("/release-diagnostics", response_model=CampaignReport)
def send_release_diagnostics(campaign: CampaignRequest) -> CampaignReport:
    try:
        return notifier_from_environment().dispatch(campaign)
    except InfraiError as exc:
        caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=caller_status,
            detail={"code": exc.code, "error": dict(exc.details)},
        ) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail="SMS transport error") from exc
