# Project status

Last updated: 2026-09-14. Written for a developer joining the project.

Raqeeb detects prohibited items in X-ray baggage scans and drives the response: a YOLOv8-OBB
model flags an item, an employee physically verifies it, and a voice agent collects details,
writes a report, routes it to the correct authority, and phones that authority to request
dispatch.

Start with the README. It covers installation, the model results, the tracking benchmark, and
how to run the app. This document covers the things the README does not: why recent decisions
were made, what is deliberately unfinished, and the traps that have already cost someone a day.

## Where the project is

It is live. The dashboard is at **https://raqeeb.khalid-ai.dev** (Vercel) and talks to the
backend at `https://khaliddosari2014--raqeeb-fastapi-app.modal.run` (Modal). Both deploy from
`main`: Vercel rebuilds on every push, Modal only when someone runs `modal deploy`.

**Production runs OpenAI and live Twilio calls.** Every run on the public site writes a report
with `gpt-4o-mini`, posts it to the authority endpoint, and places a real phone call handled by
`gpt-realtime`. It spends real money on every run, and nothing gates who can use it (see Traps).

- **Production and local `.env` are both `openai` + `twilio`.** The three OpenAI values,
  `OPENAI_API_KEY`, `OPENAI_PROJECT_ID` and `OPENAI_WEBHOOK_SECRET`, are filled in. Before they
  went to production, the key was confirmed against the OpenAI API: it belongs to that project
  and can use both `gpt-realtime` and `gpt-4o-mini`. The local `PUBLIC_BASE_URL` still names an
  old ngrok tunnel, so a local live call needs a fresh tunnel; calls are simpler through Modal.
- **Gemini is gone from configuration.** The Modal secret was replaced wholesale, and the
  Gemini key is no longer in it or in the local `.env`. Switching back to Gemini needs a new
  key. The Gemini code path is still in the repo, unused.
- **The OpenAI webhook for `realtime.call.incoming` points at the Modal URL**,
  `https://khaliddosari2014--raqeeb-fastapi-app.modal.run/api/openai/webhook`. Production was
  checked to reject unsigned and wrongly signed requests, which also proves the secret loaded.
- **The first live calls failed twice, for two different reasons.** On the evening of
  2026-09-13 Twilio refused to dial: `Account not authorized to call +966553225155`, most likely
  because the high-risk toll fraud category for Saudi Arabia was off in the geo permissions on
  Yazeed's account. By 2026-09-14 Twilio was dialling: the Modal logs show it fetching the call
  instructions from Modal and OpenAI posting `realtime.call.incoming` to Modal. That call died
  because the webhook crashed reading the incident (see the checkpointer trap). The fix is
  `0447e12`, deployed to Modal the same day. A call has not yet been confirmed connecting end to
  end since then.
- **Twilio credentials are Yazeed's full account**, which owns a voice-capable number; calls
  bill to him. Khalid's own Twilio account is a trial with no number. The credentials are in
  both the local `.env` and the Modal secret.
- **The call rings the employee's mobile, not the agency.** The number typed into the dashboard
  replaces the configured `AUTHORITY_*_PHONE` for that incident. The configured numbers are used
  only when a request arrives without one.

Everything is merged to `main`: the redesign, the Arabic call, the live transcript and the
webhook fix, from `single-page-dashboard-design`. Vercel rebuilds the dashboard on every push to
`main`; Modal only changes when someone runs `modal deploy`, so check the backend matches before
a demo, since the Arabic call and the live transcript both need it.
`origin/agentVoice` still exists but is fully contained in `main` and is safe to delete.

Four people are on the project. Nawaf built the report generator. Yazeed built the voice
agent and the OpenAI Realtime provider with SIP bridging. Khalid built the detection model,
the tracking and MOT benchmark, the dashboard and the deployment, and owns the repo. Omar is
the fourth contributor.

The test suite is 24 tests, all passing: four drive the LangGraph workflow with mock providers,
one drives the OpenAI call webhook over the on-disk checkpointer, four hold the call to Arabic and
check the live transcript's ordering, and the rest cover the intake rules in `agent/intake.py`
(which phone numbers and locations are accepted) and the class-to-agency routing. No other route, no WebSocket, and none of the frontend is tested. There is no CI, so run `uv run pytest tests/` yourself before pushing.

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
human. Paused incidents are persisted in SQLite through LangGraph's `AsyncSqliteSaver`, at the
path in `CHECKPOINT_DB`, so an incident survives the process restarting between the pause and
the resume. That was verified across two separate processes, not assumed.

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

### The call is Arabic end to end

Nothing about the authority call is English. The instructions in
`agent/voice/authority_prompts.py` are written in Arabic, tell the agent to stay in Saudi dialect
even if the other party speaks English, and introduce it as Raqeeb at that checkpoint, calling the
agency the class routes to. Every fact handed over is converted from its stored code first:
`agent/arabic.py` holds the Arabic for classes, checkpoints, agencies and dates, and `name_ar` in
`config/authority_mapping.yaml` names each responding unit. Keep `agent/arabic.py` identical to the
dashboard's Arabic dictionary so the call and the screen use the same words.
`tests/test_call_arabic.py` fails if any Latin text reaches the instructions other than the tool's
function name and the incident reference code.

**The transcript streams live.** On the OpenAI path the call is observed over a WebSocket, and
`LiveTranscript` in `agent/voice/sip_authority_call.py` publishes both sides as they speak: the
agent's words as it says them, the authority's as they are transcribed. Each line carries an
`item_id` and is re-sent whole as it grows, plus a `seq` for its place in the conversation, because
the authority's words usually finish transcribing after the agent has started replying.
`agent/monitor.py` keeps only the latest version of each line in its replay history, and the
dashboard keeps one line per `item_id`, ordered by `seq`. Anything new that publishes growing text
should follow the same shape rather than appending an event per word, or a late-joining dashboard
replays hundreds of fragments and a busy call can overflow a subscriber's queue.

## Deployment

**Backend on Modal**, defined entirely in `modal_app.py`. Redeploy with
`uv run modal deploy modal_app.py`.

- The whole FastAPI app is one `@modal.asgi_app()` function, because the graph, the media
  WebSocket and the monitor feed all have to live in the same process to see each other.
- A Volume named `raqeeb-state` holds the graph checkpoints, the SQLite incident database and
  uploaded frames. Without it, a paused incident would vanish the moment the container recycled.
- Credentials come from the Modal secret `raqeeb-secrets`, built from `.env` values.
  `modal secret create raqeeb-secrets --force` replaces the whole secret, and Modal never shows
  values back, so anything you leave out is lost. The least error-prone way is a copy of `.env`
  with `PUBLIC_BASE_URL` changed to the Modal URL and `ROBOFLOW_API_KEY` removed, passed with
  `--from-dotenv <file>`; delete the copy afterwards.
- The CLI must be logged in to the **`khaliddosari2014`** workspace, which is where the app,
  secret and volume live. Check with `uv run modal profile current` before deploying.
- `max_containers=1`, deliberately. The monitor fan-out is per process; a second container
  would serve a dashboard that never sees the call it is watching.
- `min_containers=0`, so it scales to zero and the first request after idle takes about ten
  seconds while torch and the model load. Set it to 1 before a demo.

**Frontend on Vercel**, project `raqeeb`, Root Directory `frontend`, configured by
`frontend/vercel.json`. It learns the backend URL from `VITE_API_BASE_URL` in
`frontend/.env.production`, which is committed on purpose since the URL is public.

**Domain.** `raqeeb.khalid-ai.dev` is a Cloudflare CNAME to `cname.vercel-dns.com`, proxy set
to DNS only so Vercel can issue the certificate. `render.yaml` is left over from an earlier
plan and no longer reflects how this deploys.

## The dashboard

`frontend/` is a separate Vite and React application, not templates served by FastAPI.
Components come from shadcn, installed through its CLI on the **Base UI** primitive layer rather
than Radix (`components.json` says `base-nova`). Do not mix the two. If you add a component,
use the CLI so it matches; hand-written Radix imports will pull a second primitive library into
the bundle.

**Two layouts.** On a window at least 1280px wide and 640px tall the page locks to the viewport
as a single-screen console: preview and a wide inference workspace across the top, report,
call monitor and judgment along the bottom in pipeline order. Nothing scrolls the page; long
content scrolls inside its panel. Below that size it becomes a stacked, scrolling column. The
breakpoints are the `desk` and `desk-short` custom variants at the top of
`frontend/src/index.css`; `desk-short` trims secondary text on short laptop windows so the
preview video keeps its room. Each section is one glass panel rendered by
`frontend/src/components/SectionShell.tsx`.

**Two languages.** The header toggle switches between English and Arabic, and Arabic is a full
right-to-left layout, not translated labels.

- Every visible string lives in `frontend/src/lib/i18n.ts`. English is the source of truth and
  the Arabic dictionary is typed against it, so a missing Arabic key fails the build.
- Codes that arrive from the backend (detection classes, severities, pipeline states,
  transcript roles) are translated through lookup tables in the same file. Data values such as
  locations, authority names and people's names are shown as they are, wrapped in `<bdi>` so
  English text inside an Arabic sentence keeps its order.
- Base UI's `DirectionProvider` wraps the app, and `dir` and `lang` are set on `<html>` in
  `main.tsx` before the first render, so a returning Arabic reader never sees an LTR flash.
  The choice is stored in `localStorage` under `raqeeb.lang`.
- Team names switch to their Arabic spelling in Arabic mode. Both spellings live in `TEAM` in
  `App.tsx`, not in the dictionary.
- Checkpoint locations and agency names travel as English codes (`Terminal 3`, `police`) and
  are translated only at display, through `t.location` and `t.agency`, so reports and calls
  stay in one language whatever the operator is viewing.

**Font.** Thmanyah Sans, loaded from `khaliddosari/thmanyah-fonts@v1` through jsDelivr in five
weights. It covers Latin and Arabic, so it is the only UI font. The monospace stack keeps
system mono for ids and codes but lists Thmanyah before the generic fallback, so any Arabic
inside a mono label still renders in it. The font's optional OpenType features (Arabic swash
letterforms, alternate fatha, discretionary ligatures, fractions) are on for headings (`h1` to
`h4`), buttons, tabs and placeholder titles only, set in `index.css`; body text and data stay
plain. In Arabic the status pills and the team's names get them too. Anything else that should
read as a button opts in with the `font-ornate` class, so mark new sub-headings up as real
`h3`/`h4` elements rather than styled paragraphs. The Raqeeb wordmark alone uses Thmanyah Serif
Display Black (`font-brand`), and only that one weight is fetched.

**Status pills use the universal four.** Grey idle, blue running, green done, red malfunction,
with a dot that repeats the state so colour is never the only cue. `StatusPill` and the `Tone`
type are in `SectionShell.tsx`; `pipelineTone()` in `App.tsx` maps backend statuses onto them.
Do not reintroduce amber for "waiting": waiting on the pipeline is running.

**Intake: employee number and location.** The employee number is required and must be a Saudi
mobile. It is the employee's identifier on the report and the number the dispatch call rings,
replacing the agency's configured number for that incident (`call_phone` in the graph state,
applied in `determine_authority_node`). The location picker offers Terminals 1 to 5 and the
Private Aviation Terminal. Both are validated in `agent/intake.py`, which is the gate; the
frontend copy in `lib/intake.ts` only lets the form explain itself early. Change the two
together.

**Agencies.** Guns and knives route to the police, pliers, scissors and wrenches to airport
security, via the `agency` field in `config/authority_mapping.yaml`, surfaced to the dashboard
as `authority_agency`. The agency's mark appears beside the detection, in the report, in the
judgment and on the authority's turns in the call transcript. The police mark is the real Saudi
Public Security police emblem, `public/authorities/police.png`, taken from Wikimedia Commons under
CC BY-SA 4.0, which requires crediting it wherever the site is public; the credit is in
`public/authorities/CREDITS.md` but is not yet shown on the page. Airport security has no mark
yet, because no official, licensed source was found, so `components/AgencyMark.tsx` shows an icon
badge for it until a file is added there.

**The call panel is the conversation and nothing else.** `components/CallTranscript.tsx` shows
each turn as a chat bubble headed by Raqeeb or the agency and releases words one at a time, on a
beat that shortens when a backlog builds, since the call's text arrives several words per update.
It keeps the newest words in view; wheel, touch, keyboard or scrollbar input that moves away from
the bottom pauses that, and reaching the bottom again resumes it. Only finished turns are announced
to screen readers.

**The report record and the judgment never scroll.** Both are grids of `RecordItem`, a label over a
one-line value with the full text in its tooltip, so their height is fixed. On short windows the
report goes to four columns, and below 752px tall (`desk-tight`) the judgment's two-line clamps
drop to one line. The narrative tab is the one exception and still scrolls, because a full report
cannot fit.

**Branding and placeholders.** The logo is `components/Logo.tsx` (a shield holding an eye) and
`public/favicon.svg`, deliberately free of any national, ministry or company emblem because the
product is pitched to government and private security agencies alike; keep new artwork neutral
in the same way. Panels waiting on the pipeline show line illustrations from
`components/Illustrations.tsx` inside shadcn's `Empty`. At desk each placeholder is a size
container that drops its artwork, then its description, when its box gets short, via the
`box-short`, `box-tiny` and `box-micro` variants in `index.css`, so an empty panel never
scrolls. Text sizes are one step above Tailwind's defaults, set in an `@theme` block in
`index.css`: `text-xs` is 13px, `text-sm` 15px and `text-base` 17px.

**On phones** the header scrolls away instead of pinning its two rows of names, controls are
44px tall below the desk layout, and input text stays at 17px so iOS does not zoom on focus.

**You must build it before the backend can serve it.** `frontend/dist` is gitignored, so a
fresh clone has no dashboard at all until you run `npm run build`. FastAPI mounts that
directory at `/dashboard` only if it exists, so a missing build is a 404 rather than an error
that explains itself.

Two ways to run it locally:

| Port | What it serves | When |
|---|---|---|
| 8000 | the built bundle, via FastAPI | checking a build; needs `npm run build` first |
| 5173 | `frontend/src` directly, via Vite | changing the UI; hot reload, proxies API and WebSocket to 8000 |

The page talks to the backend through `frontend/src/lib/api.ts`. Two backend features exist
only to feed it: `detect()` writes a boxed render alongside the source image, exposed as
`annotated_filename`, and `agent/monitor.py` plus `/ws/monitor/{incident_id}` stream transcript
turns, status changes and the dispatch decision live, because the call transcript was
previously only visible after the call ended.

For demos, `frontend/public/test-image.png` backs the "Run test image" button, and the employee
name and suspect form are prefilled in Arabic in both interface languages (`PREFILL` in `App.tsx`),
so a full run needs only the employee's mobile number. The manual-info route's filler for missing
values is Arabic too.

## Recent work, and why

In roughly the order it landed, 2026-09-12 and 2026-09-13.

**Demo video was broken twice over** (`60ced97`, `78ec7ba`). The dashboard's showcase clip was
404ing on a fresh clone because both copies were gitignored, and once served it still would not
render: `track_video.py` wrote MPEG-4 Part 2, which no mainstream browser decodes. The tracker
now writes H.264 and falls back only when no encoder exists, saying so when it does. OpenCV
returns `isOpened()` as true even when the encoder failed to load, so that flag cannot be
trusted on its own. A `--fps` flag motion-interpolates the finished clip, which is how the
committed 60fps demo is produced. Interpolation runs after tracking, so no metric changes.

**OpenAI webhook accepted forged requests** (`1f9ffa4`). When `OPENAI_WEBHOOK_SECRET` was unset
it defaulted to an empty string, and the HMAC was computed with an empty key, which any caller
can reproduce. Every forged webhook verified. It now rejects outright when the secret is absent.

**Boot-time configuration validation** (`62f22a2`). `validate_settings()` in `agent/config.py`
refuses to start when the selected providers lack credentials, naming each missing variable.
There is deliberately no silent fallback to the mock providers. A dispatch system that quietly
stops phoning anyone is a worse failure than one that will not start. Keep that property if you
touch this.

**Authority routing could ring a real person** (`4fdede7`). The YAML shipped a routable Saudi
mobile as the default for every class, so a fresh clone with live telephony would call an
actual phone; defaults are now unassignable placeholders. The `AUTHORITY_*` environment
overrides never worked from `.env`, because `authority_mapping.py` expands them against
`os.environ` and pydantic-settings does not populate it; `load_dotenv()` fixes that, with
`override=False` so real environment variables still win in production. Fixing that exposed a
third problem: an unreachable report endpoint raised out of `send_report` and killed the graph
before the dispatch call was placed. It now returns `False`, so the incident records
`report_send_failed` and still phones the authority.

**Dashboard rebuilt as a React console** (`262c1fa`, `81e92ac`, then `d322529`, `b27a9b0`).
The single hand-written HTML file became the Vite app, with the annotated render and the live
monitor feed added to the backend to support it. Later: the navy light theme with glass
surfaces, and Riyadh time in the header and in report timestamps.

**Deployed, which forced the checkpointer swap** (`1185f86`). The graph used to keep paused
incidents in `MemorySaver`, which is in process memory. On a platform that scales to zero, the
resume request can land on a container that never saw the pause, so the incident is simply
lost. Two things went wrong on the way to `AsyncSqliteSaver`, both worth knowing: the sync
`SqliteSaver` raises `NotImplementedError` on every async method and the graph is driven with
`ainvoke`; and entering its context manager without keeping a reference lets garbage
collection close the connection underneath you, which is why `workflow.py` holds `_saver_cm`
at module level.

**Single-screen desktop layout, Arabic mode and Thmanyah Sans** (`e097750`, `ac725c6`,
`5b93c9b`). The console now fits one screen on desktop, the header carries only the brand, team,
language toggle and clock, and the interface runs fully in Arabic. Built and verified at
1920x950, 1440x780 and 1280x720 plus phone and tablet, in both languages, against a real stored
incident with a 2,800 character Arabic report. Merged to `main` and live.

**Configuration moved to OpenAI only.** The team settled on one vendor for both the report and
the call. The local `.env` was cleaned down to OpenAI, Twilio, authority overrides and the
Roboflow key; Gemini, SignalWire and a stray `DATABASE_URL` were removed. Twilio came from
Yazeed's account because Khalid's trial has no number.

**Production switched to OpenAI and live telephony** (deployed from `5b93c9b`). The Modal
secret was rebuilt from `.env` with `PUBLIC_BASE_URL` set to the Modal URL, replacing the old
`gemini` + `mock` configuration, and the OpenAI webhook was registered against the Modal URL
rather than a local tunnel, because that address never changes. Checked after deploying: the app
boots, which means `validate_settings()` found every required value, and the webhook rejects
both an unsigned request and a request with a forged signature. `ALLOWED_ORIGINS` was not set,
so CORS is still the `*` wildcard.

## Traps

**The app will not start if credentials are missing.** That is intended. Read the error; it
names every variable it wants.

**A locally built bundle talks to the deployed backend, not your local one.** `npm run build`
reads `frontend/.env.production`, so port 8000 serves a page whose API calls go to Modal. Use
port 5173 to exercise your local backend.

**The single-screen layout needs a big enough window.** Below 1280x640 you get the stacked
page, which looks like nothing changed. Maximise the window, or zoom out.

**Port 8000 shows stale UI until you rebuild.** It serves `frontend/dist`, so source edits
are invisible there until `npm run build`. Port 5173 always reflects source.

**Arabic mode breaks if you use physical direction classes.** Write `ms-`, `me-`, `ps-`, `pe-`,
`inset-s-` and `text-start`, never `ml-`, `pr-`, `left-` or `text-left`, or the element stays
put when the layout mirrors. Setting `dir="ltr"` on a block element for a phone number or id
has the same effect, so isolate the value in an inline `<span dir="ltr">` instead. Labels styled
`font-mono` that can hold Arabic need `rtl:font-sans`, or spaces come from the mono font and
open wide gaps between words. The Arabic letter-spacing override at the bottom of `index.css` is
deliberately outside any `@layer`; inside one it loses to Tailwind's utilities and joined
Arabic letters get pulled apart.

**`AUTHORITY_*` overrides only work because of `load_dotenv()`.** If you refactor configuration
loading, keep that call or those overrides silently stop applying again. Nothing errors;
routing just quietly uses the YAML defaults.

**Report delivery is skipped entirely when `LLM_PROVIDER=mock`.** `send_report` returns early.
If you are testing an endpoint and seeing nothing arrive, this is why. It also short circuits
for any endpoint starting `https://example-authority.local`, which is the sentinel the defaults
use.

**`PUBLIC_BASE_URL` must be HTTPS with no trailing slash, and differs between machines.** URLs
are built by concatenation, and the media stream URL is derived by swapping the scheme, so plain
HTTP yields `ws://`, which Twilio rejects. On Modal it is the Modal URL. The local `.env` points
at an ngrok address, which only works while that tunnel is running; ngrok is not part of the
project setup. Do not copy the local value into the Modal secret.

**The public site spends real money on every run.** Reports bill the OpenAI account, and every
run places a real call billed per minute by both OpenAI Realtime and Twilio. Anyone who finds
the link can do this.

**Live telephony is on, and the public site can ring any Saudi mobile.** The number typed into
the dashboard is dialled by the voice agent. Validation limits it to Saudi mobiles, but anyone
who finds the site can make it call someone else, on Yazeed's Twilio account. This is no longer
hypothetical. Gate it (an allowlist of the team's numbers, or a demo passcode), or switch the
Modal secret back to `TELEPHONY_PROVIDER=mock` when nobody is testing.

**Deploy the backend before the frontend.** When the dashboard and API change together, a
dashboard that reaches Vercel first talks to the old backend. The last time, the new dashboard
sent `employee_phone` and `location` to a backend that still required `employee_id` and
rejected every detection. Run `modal deploy` first, then push to `main`.

**Billed credentials live in the local `.env` and the Modal secret.** Calls placed with the
Twilio token charge Yazeed's account, and the OpenAI key bills the project. Move `.env` between
machines privately (USB or an encrypted note), never through chat or email, and never commit it;
`.env` is gitignored and must stay that way.

**A failed dispatch call shows up as "Failed to fetch".** `twilio_outbound_call_node` does not
catch Twilio errors, so the exception escapes the graph and the manual-info request returns 500.
Starlette sends that 500 from outside the CORS middleware, without CORS headers, so the browser
throws the response away and the dashboard shows only `TypeError: Failed to fetch`. The real
reason is in `uv run modal app logs raqeeb`. The incident is also left stuck partway through,
the same class of bug `send_report` had before it learned to return `False`.

**The Modal CLI can be logged in to the wrong workspace.** Production lives in
`khaliddosari2014`. A machine logged in to another workspace (Khalid's also has `swager2014`)
lists no `raqeeb` app, and `modal deploy` there would quietly create a second, empty copy with no
secret. Add the right profile with `uv run modal token new --profile khaliddosari2014`.

**Some networks block modal.com but not the Modal API.** The website's TLS handshake is reset
while `api.modal.com` works, so the CLI runs but its browser login page never loads. Open the
login link the CLI prints on another network (a phone on mobile data, or a VPN); the CLI
completes on its own once it is approved.

**`uv sync` fails on Windows with Python 3.13.** `twilio` pulls in `aiohttp` 3.9.5, which has no
prebuilt wheel for 3.13, so uv tries to compile it and stops with "Microsoft Visual C++ 14.0 or
greater is required". Use `uv sync --python 3.12`, which uv downloads for you.

**`uvicorn --reload` can hang the local backend.** Plain `--reload` watches the whole project,
`.venv` included, so any package change triggers a restart, and the restart waits forever for
an open dashboard monitor WebSocket to close. Every request then times out, and the dashboard
shows a connection reset. Run it as
`uv run uvicorn agent.main:app --reload --reload-dir agent --reload-dir config --timeout-graceful-shutdown 3`.

**Tests use in-memory checkpoints, which hid a real bug.** `tests/conftest.py` sets
`CHECKPOINT_DB=:memory:` so each run starts clean, but the in-memory saver tolerates things the
on-disk one does not. `AsyncSqliteSaver`, which Modal runs, raises `InvalidStateError` on any
synchronous read from the event loop, and `get_state()` from a route is exactly that. It made
the OpenAI call webhook return 500, so every live call rang, reached OpenAI and was never
accepted. Read graph state only through `await get_incident_snapshot()`, never `get_state()`.
`tests/test_call_webhook.py` runs the webhook over the on-disk saver to keep it that way.

**Twilio trial accounts only dial verified numbers.** A live call to an unverified destination
fails without an obvious explanation.

**The model emits markdown and the UI strips it at render.** `frontend/src/lib/plaintext.ts`
flattens it, and the report text uses `dir="auto"`. Both are safety nets over an unpinned
prompt, not the fix. If you pin the prompt, leave them anyway.

**Report timestamps are Riyadh local, stored timestamps are UTC.** `agent/report.py` uses a
fixed UTC+3 offset for `date_time` and the incident id, because Saudi Arabia has no DST and
Windows ships no IANA database. `created_at` and `updated_at` in `models.py` stay UTC on
purpose.

**Model weights are committed directly, not via LFS.** A `.gitattributes` marking them as LFS
was removed because the raw blobs were already in history. Do not reintroduce LFS without
rewriting history.

## Tools

Python 3.12, managed with `uv`. `pyproject.toml` allows newer, but 3.13 cannot install on
Windows without a C++ compiler (see Traps), and Modal's image is 3.12. `uv sync --python 3.12`
installs the locked dependency set including the dev group.

Ultralytics YOLOv8-OBB for detection, trained on Modal via `modal_train.py`. OpenCV and a
retuned BoT-SORT for tracking. FastAPI, SQLAlchemy over SQLite, and LangGraph with
`langgraph-checkpoint-sqlite` for the application. Provider SDKs are `google-genai` for Gemini
and `twilio` for telephony; the OpenAI path deliberately uses `httpx` and `websockets` directly
rather than the OpenAI SDK. `ffmpeg` arrives through `imageio-ffmpeg` in the dev group and is
needed only for `--fps`. The dataset comes from Roboflow and needs a key only for the notebooks.

The dashboard needs Node: Vite, React 19, TypeScript and Tailwind v4, with shadcn components on
Base UI primitives, Lucide icons and Thmanyah Sans. `npm install` then `npm run build` in
`frontend/`.

Hosting is Modal for the backend, Vercel for the frontend, and Cloudflare for DNS.

## Future work

**Gate caller-supplied numbers. Do this first.** Live telephony is already on in production,
so anyone with the link can make the system phone any Saudi mobile (see Traps).

**Confirm a live call end to end.** With the webhook fix deployed, run one incident on
https://raqeeb.khalid-ai.dev with a team member's mobile, and watch `uv run modal app logs raqeeb`
for `POST /api/openai/webhook -> 200` while it rings. If Twilio refuses to dial again, check the
Saudi high-risk category in the geo permissions (see Where the project is).

**Handle a failed dispatch call.** Catch the Twilio error in `twilio_outbound_call_node`, record
a `call_failed` status on the incident, and return it to the dashboard, so the operator sees why
instead of "Failed to fetch" (see Traps). If the call connects but the agent stays silent,
the webhook is the first suspect: check that OpenAI shows a delivery to the Modal URL, and that
the webhook, key and project id all come from the same OpenAI project.

**Finish hardening the OpenAI switch.**

1. Set `min_containers=1` in `modal_app.py` for demo sessions and redeploy. A cold start takes
   about ten seconds, which is too long while a call is ringing and waiting for the webhook.
   `scaledown_window` is already five minutes, so a container that has started stays up for
   the length of a call.
2. Add `ALLOWED_ORIGINS=https://raqeeb.khalid-ai.dev` to the Modal secret. CORS is still the
   `*` wildcard, so any site can call the API. Rebuilding the secret means passing every key
   again (see Deployment).
3. Decide whether to delete the Gemini provider code, now that no environment uses it.

**Test the webhook's rejection cases.** `tests/test_call_webhook.py` covers the success path:
a correctly signed `realtime.call.incoming` is accepted and matched to its incident, over the
on-disk checkpointer. The refusals are still untested.

The signature verification in `agent/routes/openai_routes.py` is security relevant and its
refusals have only ever been checked by hand. Those manual checks did pass: a correctly signed request is
accepted, forgeries signed with an empty or wrong key are rejected with 400, a stale
timestamp is rejected, and an unset secret fails closed with 500 rather than verifying
against an empty key. On 2026-09-13 production also rejected an unsigned request and a forged
signature. None of it is in `tests/`, so nothing stops a regression, and the bug this code
exists to prevent was live in the repo once already (see `1f9ffa4`). The four cases are
straightforward to drive against `_verify_signature` directly, no live call needed.

**Credit the police emblem on the page, and add an airport security mark.** The emblem's CC BY-SA
license needs a visible credit on the public site. The airport security mark needs an official
file the team may use, added under `frontend/public/authorities/` and set in `AgencyMark.tsx`.

**Protect the OpenAI and Twilio spend on the public site.** Rate limiting, or a demo mode that
replays a stored report, before sharing the link widely.

**Pin the report language and length.** Decide whether reports are Arabic or English and say so
explicitly in the instruction in `agent/report.py`, and cap the summary. Right now the model
chooses, and the result is long for a spoken call and inconsistent between runs. With the
dashboard now bilingual, the natural choice is to generate in the language the operator has
selected.

**Serve annotated renders smaller.** They are written as roughly 1.5 MB PNGs and load slowly
from Modal; the dashboard shows a placeholder until they finish. JPEG or WebP would cut that
by an order of magnitude.

**Add CI.** There is none. Tests that nobody runs automatically will rot.

**Counting still lags association.** From the tracking benchmark: identities hold well, IDF1
around 0.87, but the distinct-object count that a screening log would record is still off by a
few. Confirmation thresholds only trade false alarms against misses; they cannot recover an
object the detector never saw. This needs detector work, not tracker tuning.

**Consider moving weights out of git.** Fine at the current size and churn. If retraining
becomes frequent, push weights to the Modal volume or a GitHub release rather than reaching for
LFS.

**`tests/conftest.py` uses a US placeholder number** for the Twilio origin. Defensible, since
Twilio does not readily sell Saudi numbers, but worth a deliberate decision rather than an
accident.
