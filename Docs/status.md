# Project status

Last updated: 2026-09-12. Written for a developer joining the project.

Raqeeb detects prohibited items in X-ray baggage scans and drives the response: a YOLOv8-OBB
model flags an item, an employee physically verifies it, and a voice agent collects details,
writes a report, routes it to the correct authority, and phones that authority to request
dispatch.

Start with the README. It covers installation, the model results, the tracking benchmark, and
how to run the app. This document covers the things the README does not: why recent decisions
were made, what is deliberately unfinished, and the traps that have already cost someone a day.

## Where the project is

Everything is merged to `main`. There are no open branches or pull requests. `origin/agentVoice`
still exists but is fully contained in `main` and is safe to delete.

Three people have contributed. Nawaf built the report generator. Yazeed built the voice agent,
the OpenAI Realtime provider with SIP bridging, and the dashboard. Khalid built the detection
model, the tracking and MOT benchmark, and owns the repo.

The test suite is three tests, all passing, all driving the LangGraph workflow with mock
providers. There is no CI. Nothing runs these automatically, so run `uv run pytest tests/`
yourself before pushing.

## How the pieces fit

`agent/graph/workflow.py` is the spine. Everything else is called by it.

```
YOLO detection -> display -> employee verification -> (rejected? end)
  -> voice agent collects and validates incident info
  -> generate report -> determine authority -> send report
  -> outbound call -> agent talks to authority -> update incident -> end
```

The graph pauses at two points and waits for outside input: employee verification, and
information collection. Both resume through HTTP routes, so the graph never blocks on a
human.

Detection, language model, and telephony are each reached only through the interfaces in
`agent/providers/base.py`, resolved in `agent/providers/factory.py`. Route and graph code never
imports a vendor SDK. If you add a provider, add a branch to the factory and a credential
requirement in `agent/config.py`; nothing else should need to change.

### The provider matrix

Two independent axes, set by environment variable.

| Axis | Options |
|---|---|
| `LLM_PROVIDER` | `mock`, `gemini`, `openai` |
| `TELEPHONY_PROVIDER` | `mock`, `twilio`, `signalwire` |

The language model choice changes the audio path, which is the least obvious thing in the
codebase and the thing most likely to confuse you.

With `gemini`, the telephony provider streams call audio into this server's own WebSocket at
`/ws/twilio-media/{incident_id}`, and `agent/voice/authority_call_session.py` bridges it to
Gemini Live, resampling between 8kHz mu-law and Gemini's 16kHz in / 24kHz out PCM.

With `openai`, the telephony provider instead dials `sip:$OPENAI_PROJECT_ID@sip.api.openai.com`
directly. Call audio never reaches this server at all. OpenAI announces the call through a
`realtime.call.incoming` webhook at `/api/openai/webhook`, matched back to the incident by an
`X-Incident-Id` SIP header. No resampling happens, because the Realtime API speaks the same
G.711 mu-law the telephony media streams already carry.

`signalwire` is a drop-in replacement for `twilio`; its compatibility API mirrors Twilio's and
both reuse the same webhook routes.

## Recent work, and why

Six commits on 2026-09-12, in order.

**Demo video was broken twice over** (`60ced97`, `78ec7ba`). The dashboard's showcase clip was
404ing on a fresh clone because both copies were gitignored, and once served it still would not
render: `track_video.py` wrote MPEG-4 Part 2, which no mainstream browser decodes. Chrome
reports that codec as unsupported outright. The clip only ever looked correct in VLC, so nobody
noticed. The tracker now writes H.264 and falls back only when no encoder exists, saying so when
it does. Note that OpenCV returns `isOpened()` as true even when the encoder failed to load, so
that flag cannot be trusted on its own. A `--fps` flag was added to motion-interpolate the
finished clip, which is how the committed 60fps demo is produced. Interpolation runs after
tracking, so no metric changes.

**OpenAI webhook accepted forged requests** (`1f9ffa4`). When `OPENAI_WEBHOOK_SECRET` was unset
it defaulted to an empty string, and the HMAC was computed with an empty key, which any caller
can reproduce. Every forged webhook verified. It now rejects outright when the secret is absent.

**Boot-time configuration validation** (`62f22a2`). `validate_settings()` in `agent/config.py`
refuses to start when the selected providers lack credentials, naming each missing variable.
There is deliberately no silent fallback to the mock providers. A dispatch system that quietly
stops phoning anyone is a worse failure than one that will not start. Keep that property if you
touch this.

**Authority routing could ring a real person** (`4fdede7`). Three related problems. The YAML
shipped a routable Saudi mobile as the default for every class, so a fresh clone with live
telephony would call an actual phone; defaults are now unassignable placeholders. The
`AUTHORITY_*` environment overrides never worked from `.env`, because `authority_mapping.py`
expands them against `os.environ` and pydantic-settings does not populate it; `load_dotenv()`
fixes that, with `override=False` so real environment variables still win in production. And
fixing that exposed a third problem: an unreachable report endpoint raised out of `send_report`
and killed the graph before the dispatch call was placed. It now returns `False`, so the
incident records `report_send_failed` and still phones the authority, which is the half that
actually gets a team moving.

## Traps

**The app will not start if credentials are missing.** That is intended. Read the error; it
names every variable it wants.

**`AUTHORITY_*` overrides only work because of `load_dotenv()`.** If you refactor configuration
loading, keep that call or those overrides silently stop applying again. Silently is the
problem: nothing errors, routing just quietly uses the YAML defaults.

**Report delivery is skipped entirely when `LLM_PROVIDER=mock`.** `send_report` returns early.
If you are testing an endpoint and seeing nothing arrive, this is why. It also short circuits
for any endpoint starting `https://example-authority.local`, which is the sentinel the defaults
use.

**`PUBLIC_BASE_URL` must be HTTPS with no trailing slash.** URLs are built by concatenation, so
a trailing slash produces a doubled separator, and the media stream URL is derived by swapping
the scheme, so plain HTTP yields `ws://` which Twilio rejects. Locally this means a tunnel;
ngrok issues a new URL on every restart, so this value is per-session.

**Twilio trial accounts only dial verified numbers.** A live call to an unverified destination
fails without an obvious explanation.

**Model output language is not pinned.** With a real Gemini key, report generation has produced
a 2,500 character Arabic summary where the mock produces roughly 250 characters of English.
Nothing breaks, but the dashboard renders that field and the voice agent reads it aloud to the
authority. This is inferred by the model rather than chosen by us, so it is not stable
run to run. See future work.

**Model weights are committed directly, not via LFS.** A `.gitattributes` marking them as LFS
was removed because the raw blobs were already in history, so LFS would have added cost with no
benefit. A plain clone gets the weights. Do not reintroduce LFS without rewriting history.

## Tools

Python 3.12 or newer, managed with `uv`. `uv sync` installs the locked dependency set including
the dev group.

Ultralytics YOLOv8-OBB for detection, trained on Modal via `modal_train.py`. OpenCV and a
retuned BoT-SORT for tracking. FastAPI, SQLAlchemy over SQLite, and LangGraph for the
application. Provider SDKs are `google-genai` for Gemini and `twilio` for telephony; the OpenAI
path deliberately uses `httpx` and `websockets` directly rather than the OpenAI SDK. `ffmpeg`
arrives through `imageio-ffmpeg` in the dev group and is needed only for `--fps`. Deployment is
Render, configured by `render.yaml`. The dataset comes from Roboflow and needs a key only for
the notebooks.

## Future work

**Test the SIP path.** This is the most valuable gap. The webhook signature verification in
`agent/routes/openai_routes.py` has been checked only by hand: a valid signature is accepted,
forgeries with an empty or wrong key are rejected, and stale timestamps are rejected. None of
that is in `tests/`, so nothing prevents a regression on security-relevant code.

**Pin the report language and length.** Decide whether reports are Arabic or English and say so
explicitly in the instruction in `agent/report.py`, and cap the summary. Right now the model
chooses, and the result is both long for a spoken call and inconsistent between runs.

**Add CI.** There is none. Three tests that nobody runs automatically will rot.

**Counting still lags association.** From the tracking benchmark: identities hold well, IDF1
around 0.87, but the distinct-object count that a screening log would record is still off by a
few. Confirmation thresholds only trade false alarms against misses; they cannot recover an
object the detector never saw. This needs detector work, not tracker tuning.

**Consider moving weights out of git.** Fine at the current size and churn, three commits ever.
If retraining becomes frequent, push weights to the Modal volume or a GitHub release rather than
reaching for LFS.

**`tests/conftest.py` uses a US placeholder number** for the Twilio origin. That is defensible,
since Twilio does not readily sell Saudi numbers, but it is worth a deliberate decision rather
than an accident.
