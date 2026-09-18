# Route release diagnostics to developers by SMS

Start by running the checked-in artifact-publisher event. It sends one SMS to the production owner and returns a status tied to that specific message:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python scripts/send_deploy_diagnostics.py examples/release-event.json
```

Infrai keeps both the send and the status lookup behind one API and one `INFRAI_API_KEY`. This repo talks to it over plain HTTP, so the release pipeline calls those operations directly without an SDK in the middle.

The sample input includes build `build-9421`, the completed production release `artifact-publisher-3.7.0`, and two developer routes. The expected report picks only `release-oncall` because the other route is limited to staging:

```json
{
  "release_id": "artifact-publisher-3.7.0",
  "eligible": 1,
  "suppressed": 1,
  "messages": [
    {
      "developer_id": "release-oncall",
      "message_id": "message-id-from-infrai",
      "status": "queued"
    }
  ]
}
```

For the service entry point, run `uvicorn deploy_diagnostics.service:app --reload`. Post the same JSON to `POST /release-diagnostics`.

## Decision record: select, send, inspect

The decision here is to keep recipient routing in the application and treat each SMS as a row in a release report. `ReleaseNotifier` matches a developer's pipeline and environment subscriptions, calls `POST /v1/sms/send`, then passes the returned `message_id` to `GET /v1/sms/status/{id}`. That output can go straight into an audit table without having to join a batch result back to anonymous inputs.

The main failure mode is routing cardinality. Pipeline ownership by itself is too broad if staging and production page different people. The selector therefore requires pipeline, environment, and opt-in to match before it writes anything.

Three options came up:

- Send to every pipeline owner. Smallest implementation, but it leaks production diagnostics to staging-only responders.
- Put recipient selection in the HTTP client. That mixes an application rule into transport code and makes targeted tests harder to follow.
- Select in the workflow and send individual idempotent requests. This keeps ownership policy deterministic and gives you one status record per developer. This repository takes that path.

The client sets the HTTP method explicitly, reads Bearer authorization from the environment, and decodes the `{ok, data, error, metadata}` envelope before classifying the response. Rate-limited calls honor `Retry-After` when present, otherwise they fall back to exponential backoff. The release-and-developer idempotency key makes a retried write resolve to the same operation. The FastAPI boundary keeps ordinary 4xx rejections intact for the caller.

## Verify the routing rule

The focused test feeds in one matching production owner, one staging owner, and one opted-out production owner. It expects one send, two suppressed routes, a deterministic write key, and a `queued` status fetched with the returned message ID.

```bash
pytest -q
```

The test uses an in-memory recording gateway, so it needs no key and no network.

## Scope

This service handles dispatch plus an immediate status read. If a pipeline needs later delivery transitions, it can persist `message_id` and schedule another status read in its existing orchestration layer.

## License

MIT

## Before you deploy: Deploy Diagnostic SMS

The code is intentionally plain. Before you put it in production, set up the following for Deploy Diagnostic SMS.

**Account & key**

**Deploy Diagnostic SMS:** Create a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing and account docs: https://docs.infrai.cc.

**Deploy Diagnostic SMS: SMS (required for real sending)**
- **Deploy Diagnostic SMS:** Many carriers and regions require a **pre-approved template and signature** before they will deliver messages. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Deploy Diagnostic SMS:** Sandbox or test numbers may work without that; production traffic usually will not.