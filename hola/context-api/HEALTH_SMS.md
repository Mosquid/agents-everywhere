# Health contact SMS

The agent can queue one Twilio SMS per call when a person reports a current
health concern. It uses prior consent saved by an administrator and a designated
contact; the model cannot choose a phone number, write the SMS, or grant consent.
This is a check-in feature, not diagnosis, clinical triage, or emergency dispatch.

## Enable and configure

The feature is off by default. Add these settings to the private root `.env`:

```dotenv
HEALTH_SMS_ENABLED=1
TWILIO_ACCOUNT_SID=<your account SID>
TWILIO_AUTH_TOKEN=<your auth token>
TWILIO_FROM_NUMBER=<your SMS-capable Twilio number in E.164 format>
```

Then run `docker compose up -d --build context-api agent`. The existing API
container hosts independent review and SMS workers, polling every five seconds.
OpenAI access to `gpt-5.6-luna` is also required for transcript review.
Provider credentials stay in the API container, outside the model's context.

Create the person first, then use the admin-authenticated API documentation at
`http://127.0.0.1:8090/docs` to `PUT /people/{person_id}/health-contact`:

```json
{
  "enabled": true,
  "contact_name": "Sam",
  "contact_phone": "+12025550124",
  "person_label": "Alex",
  "language": "en",
  "consent_note": "Prior consent recorded for automatic health check-in SMS to Sam."
}
```

These names and numbers are fictional. Record actual prior permission before
enabling a real profile. `language` supports `en` and `es`. `person_label` is the
name the contact will recognize. The fixed English message is:

> hola: Alex mentioned a health concern during a call. Please contact them to check in.

No medical details, model-written text, phone-call audio, or transcript go to
Twilio. The message still discloses that the named person reported a health concern.

Consent must exist **before the call starts**, with the feature enabled. New
consent does not apply retroactively. Every contact-settings replacement creates
a new revision and cancels pending work for prior calls, including when the phone
number changes. Normal profile edits leave these separate settings intact.
`GET /people/{person_id}/health-contact` retrieves settings using the admin token.

## During and after the call

- `notify_health_contact(timing="during_call")` queues the check-in immediately.
- `notify_health_contact(timing="after_call")` waits for finalized recordings and
  a transcript review that checks for a later refusal.
- The post-call worker also reviews new, consent-enrolled calls without a live
  notification. It sends the final transcript to OpenAI with `store=False` and
  requests a structured decision. Negated, historical, hypothetical, third-party,
  and agent-only health statements are excluded by the review instructions.
- `stop_health_notifications()` disables saved consent and cancels pending SMS
  when the caller refuses sharing. A refusal found in post-call review does the
  same. Messages already submitted or in flight cannot be recalled.

Tool calls use the existing call-writer token at
`POST /calls/{call_id}/health-notification` and
`POST /calls/{call_id}/health-notification/opt-out`. Only the administrator can
configure the contact or enable consent. The tool binds the current call ID;
the backend resolves its person and contact. Existing phone matching is not
caller identity verification; this feature adds no new identity verification.

## Inspect outcomes and recover

`GET /calls/{call_id}/health-notification` requires the admin token and returns
the review and notification records. SQLite stores consent revisions, a snapshot
of the configured contact/permission, source, timestamps, provider SID, and status.
There is at most one notification record and one provider-send attempt per call,
shared by live tools and post-call review.
Repeated tool calls return that original record and timing; they do not reschedule
or resend it.

| Status | Meaning |
| --- | --- |
| `queued` | Awaiting the worker, completion/review, or valid Twilio configuration |
| `sending` | A durable send attempt has started |
| `submitted` | Twilio accepted the request; delivery is not confirmed |
| `failed` | Twilio rejected the request; no automatic retry |
| `unknown` | Timeout, ambiguous response, or interrupted send; do not resend automatically |
| `cancelled` | Contact or consent changed before sending |
| `expired` | The call is older than 24 hours; no delayed automatic notification |

The integration uses Twilio's [Messages API](https://www.twilio.com/docs/messaging/api/message-resource).
It stores the initial provider status, without delivery callbacks or polling.
Check a known SID in Twilio for delivery. For `unknown`, reconcile the provider's
message log before any manual action; calling the tool again never retries it.
An interrupted send becomes `unknown` after two minutes. Missing configuration
leaves work queued until configured or expired. Review failures retry up to three
times, with a one-minute delay; review errors never manufacture a positive result.
Review jobs without final artifacts expire after 24 hours. Older calls are not
backfilled. `HEALTH_SMS_ENABLED=0` stops new enrollment and processing; revoke a
person's consent to cancel their queued messages permanently.

Detection is model-dependent and can miss concerns or misclassify conversation.
Mocked tests cover enforcement and worker behavior, not clinical accuracy or real
provider delivery. Before enabling real notifications, verify Twilio delivery and
exercise consenting test profiles with positive, negative, and refusal scenarios.

## Automated verification

After the Python test setup in [the agent guide](../README.md#troubleshooting-and-verification), run:

```sh
.venv-livekit/bin/python -m unittest discover -s hola/context-api -p 'test_health_sms.py' -v
```

The integration cases execute the real agent tool, authenticated API, SQLite
queue, workers, and OpenAI SDK response parser. Only the external OpenAI and
Twilio HTTP responses are simulated. They verify the configured SMS recipient
and exact message, post-call detection, one send attempt, and zero provider
requests after caller opt-out. No credentials or real messages are needed.
