from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from deploy_diagnostics.infrai_sms import InfraiSmsClient
from deploy_diagnostics.release_notifier import CampaignRequest, ReleaseNotifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Send release diagnostics by SMS")
    parser.add_argument("event", type=Path, help="build and release event JSON")
    args = parser.parse_args()

    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise SystemExit("INFRAI_API_KEY is required")
    with args.event.open(encoding="utf-8") as handle:
        campaign = CampaignRequest.model_validate(json.load(handle))
    report = ReleaseNotifier(InfraiSmsClient(api_key)).dispatch(campaign)
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
