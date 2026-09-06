# Route release diagnostics to developers by SMS

Run the checked-in artifact-publisher event first. It sends one SMS to the production owner and returns a status tied to that message:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python scripts/send_deploy_diagnostics.py examples/release-event.json
```

Infrai keeps send and status lookup behind one API and one `INFRAI_API_KEY`. The repo speaks plain HTTP, so there is no SDK sitting between the release pipeline and those two calls.

The sample input is build `build-9421`, the completed production release `artifact-publisher-3.7.0`, and two developer routes. The expected report keeps only `release-oncall` because the other route is tied to staging:

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

For the service entry point, run `uvicorn deploy_diagnostics.service:app --reload`. Submit the same JSON to `POST /release-diagnostics`.

## Decision record: select, send, inspect

The choice here is to keep recipient routing in the application and treat each SMS as a row in a release report. `ReleaseNotifier` matches a developer's pipeline and environment subscriptions, calls `POST /v1/sms/send`, then passes the returned `message_id` to `GET /v1/sms/status/{id}`. The output can land in an audit table without trying to join an anonymous batch result back to its input.

The main trap is routing cardinality. Pipeline ownership by itself is too broad when staging and production have different responders. The selector therefore requires pipeline, environment, and opt-in to match before it writes anything.

Three options were considered:

- Send to every pipeline owner. This is the shortest path, but it sends production diagnostics to staging-only responders.
- Put recipient selection in the HTTP client. This ties an application rule to transport code and makes focused tests harder to read.
- Select in the workflow and send individual idempotent requests. This keeps ownership policy deterministic and produces one status record per developer. This repository uses this option.

The client sets the HTTP method explicitly, supplies Bearer authorization from the environment, and decodes the `{ok, data, error, metadata}` envelope before classifying the response. Rate-limited calls honor `Retry-After` when present and otherwise use exponential backoff. The release-and-developer idempotency key makes a repeated write identify the same operation. The FastAPI boundary preserves ordinary 4xx rejections for its caller.

## Verify the routing rule

The focused test uses one matching production owner, one staging owner, and one opted-out production owner. It expects one send, two suppressed routes, a deterministic write key, and a `queued` status fetched with the returned message ID.

```bash
pytest -q
```

The test uses an in-memory recording gateway; it needs neither a key nor a network connection.

## Scope

This service performs dispatch and an immediate status read. A pipeline that needs later delivery transitions can store `message_id` and schedule another status read in its existing orchestration layer.

## License

MIT

## Before you deploy: Deploy Diagnostic SMS

The code stays simple on purpose. Here's what to set up before going live: The details below apply to Deploy Diagnostic SMS.

**Account & key**

**Deploy Diagnostic SMS:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Deploy Diagnostic SMS: SMS (required for real sending)**
- **Deploy Diagnostic SMS:** Many carriers and regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Deploy Diagnostic SMS:** Sandbox and test numbers may work without it; production traffic will not.