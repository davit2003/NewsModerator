# Mountain Editor

Russian-language Telegram editorial assistant for a guided hiking/climbing community in Poland.
Beginner-friendly nature, education, events and short stories. Tatras first; Europe and world highlights
also welcome. Every group post requires the owner's approval of the exact current version.
Python 3.12, standard library only, one Railway worker with SQLite on `/data`.

## Daily use

- **📥 Подборка**: browse saved story cards; five per screen, more options and topic filters.
- **🔎 Найти материал** or `/find`: refresh collection and open the inbox. Refreshes have a 15-minute cooldown.
- **Подготовить пост**: generate a short Russian draft and find an illustrative Commons photograph.
- **Опубликовать**: approve this exact draft/photo version and publish. Nothing publishes from merely selecting an idea.
- **Без фото**: explicitly select text-only mode, review the new version, then approve.
- **📋 Черновики**: return to drafts. Text/photo edits revoke existing approval.
- **💵 Бюджет** or `/budget`: conservative estimated AI spend, reservations and monthly allowance.
- `/health`: latest collection counts, errors and status for each source.
- `/context details`: replace optional trip/Instagram context used when writing posts. Include destination,
  date, audience and the angle desired. The bot never invents trip availability.
- `/pause`, `/resume`: pause/resume automatic research and publishing.
- `/help`: advanced editing, scheduling and photo collection commands.

## Collection and editorial inbox

`sources.json` contains curated RSS feeds, official rolling bulletins, educational pages and news indexes.
The registry now uses TOPR (first priority), TPN, GOPR Karkonosze, SLF,
Alpenvereinaktiv, bergundsteigen, Petzl and UIAA. Supplemental search and new inbox candidates
are restricted to these organisations. Historical drafts are retained; old-source ideas are hidden.
Homepages and dynamic bulletins may yield only leads; search supplies substantive article URLs.
SLF uses public pages for now, not its authenticated data API. Educational materials are evergreen;
Alpenvereinaktiv user reports require official corroboration for safety alerts. Copied image links
are not sources or evidence of image reuse permission.

The collector checks robots.txt, skips unavailable/disallowed policies, uses an identifying User-Agent,
bounded responses/timeouts, same-host redirects and at most four network workers. It does not bypass
logins or paywalls or copy Instagram photos. Feeds provide dates and article text/excerpts; direct pages
use article/main text when available. Source text is untrusted data. HTML changes can require adapter fixes.

Automatic collection runs every four hours when AUTO_RESEARCH=true. Source status and extracted items
persist across restarts. Content hashes detect changes at the same URL. AI shortlists up to six items
per batch; one supplemental web-search request per UTC day can contribute up to six more. Each search
request has at most two tool calls. Source links must match collected/provider-cited URLs. Tracking
parameters are removed. Story keys and previous ideas help suppress duplicate events, with URL checks
as a second guard. This is model-assisted deduplication, not a perfect semantic duplicate detector.

The target is a useful rolling selection, not a guaranteed number of daily stories. News requires a
publication date within 14 days; timeless educational pieces are labelled accordingly. Ideas expire
(news at most 7 days in the inbox, evergreen 14 days, alerts 6 hours). Current warnings receive an
additional official-source check before drafting. Drafts expire after at most 3 days (alerts 6 hours,
and never after the source idea expiry). Recheck changed conditions during human approval.

The first screen favours topic/geography diversity. The brief aims for 60% Tatras/nearby, 25% Europe,
15% worldwide over time without forcing weak content. Skipped ideas remain in history. No automatic
engagement tracking or learned preference model is implemented yet.

## $30 operating ceiling

Default allocation: **$18/month AI/search, $12 hosting and buffer**. No paid scraping or image service.
The code caps AI_MONTHLY_BUDGET_USD at 18; lowering it is supported. Budget accounting is in UTC calendar
months, stored in SQLite, and survives restarts. It starts at deployment; it cannot recover prior spend
or track another app sharing the API key.

Only OpenAI `gpt-5.4-mini` (or `gpt-5.4-mini-2026-03-17`) is enabled for the priced budget path. Unknown
models and Gemini fail closed until their pricing/accounting is implemented. Published baseline rates
checked 2026-10-31: $0.75/M input, $4.50/M output, $0.01/search call.

Before each request the app reserves a conservative amount for input/output and up to two search calls.
Successful responses reconcile token usage with full-price input (no cached-input discount), an extra
128k-token search allowance per tool call, and a 20% buffer. Missing usage, errors and ambiguous timeouts
retain the full reservation. Thus `/budget` is usually higher than the invoice, and may stop AI early.
It is an application guard based on configured rates, **not a guarantee about the provider invoice**.
No automatic retries of chargeable calls. MAX_AI_CALLS_PER_DAY is an additional guard (default 24,
maximum 24; an existing environment value of 12 remains respected).

At the allowance boundary new AI operations stop; the inbox and prepared drafts stay available and
approved drafts can still publish. Generating a new draft from an idea still requires AI allowance.

**Railway billing must also be bounded:** Workspace Usage → Set Usage Limits → Compute hard limit
$10, email alert $5. This workspace-wide limit can stop all workspace workloads. Confirm that this is
appropriate if the workspace hosts anything else. The code cannot set or inspect that account billing
limit through the connected OAuth tools. $2 remains as a buffer. Taxes and unrelated subscriptions are
not included; provider billing cycles may differ. Do not assume the total ceiling is enforced until
Railway's limit is configured. Keep the API key/project dedicated to this bot and review provider billing.

Official pricing: https://developers.openai.com/api/docs/models/gpt-5.4-mini
https://developers.openai.com/api/docs/pricing
https://docs.railway.com/pricing/cost-control

## Photos and approval

Commons search requires no extra key. Only supported CC BY / CC BY-SA / CC0 metadata, identifiable
authors, matching licence URLs and supported image hosts pass the filter. Attribution includes the
source, licence, author and illustration/resizing label; complex attribution and oversized captions
are skipped. The app does not crop images. Metadata is saved with the draft version.

The actual image is uploaded to the private preview and stored as a Telegram file ID before approval.
Group publication uses the same image, not a mutable external URL. Metadata filtering is not legal
clearance; review image relevance, visible people/logos and attribution. Search matching is text-based.
Use **Изменить фото → Найти другое фото** or optional **Мои фотографии** uploads with rights confirmation.
If no suitable image is found, the draft is preserved and **Без фото** remains available.

Only the configured owner in their private chat can operate controls. Stale approval buttons fail.
Editing text or images revokes approval. Claims are atomic, and uncertain Telegram sends are held
for manual review without automatic reposting. Demo mode cannot publish.

## Deployment

Existing installations: push the code to the linked GitHub main branch. The Dockerfile includes
`sources.json`. SQLite tables and the text_only column are migrated automatically without removing drafts.
Keep ONE replica and retain the volume at `/data`. Never run two Telegram getUpdates consumers.

New installation: create a Telegram bot, add it to the destination group with posting permission,
connect this repo to Railway, attach `/data`, configure variables, and send `/start` privately.

| Variable | Meaning |
|---|---|
| `AI_PROVIDER` | `openai` for live budgeted operation, `demo` for offline demo |
| `AI_MODEL` | `gpt-5.4-mini` |
| `OPENAI_API_KEY` | Dedicated OpenAI API key; never commit it |
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `OWNER_TELEGRAM_ID` | Numeric owner ID |
| `TARGET_CHAT_ID` | Destination group/channel ID |
| `DB_PATH` | `/data/editor.db` |
| `PUBLISH_ENABLED` | `false` initially; `true` permits approved sends |
| `AUTO_RESEARCH` | `false` initially; `true` enables four-hour collection |
| `AI_MONTHLY_BUDGET_USD` | Default and maximum `18`; may be lowered |
| `MAX_AI_CALLS_PER_DAY` | Default/max 24; existing lower limits remain honoured |
| `AUTO_PHOTOS` | Default `true` |
| `COMMONS_USER_AGENT` | Optional deployment/contact identity for Commons |

Old RESEARCH_WEEKDAYS/RESEARCH_HOUR settings are superseded by four-hour collection; the bot sends
at most one automatic inbox summary per Warsaw date, during a collection at/after 10:00.
No public domain or webhook is necessary. Python runs on Railway; model inference/search runs at OpenAI.

## Verification

`python -m unittest discover -s tests -v` runs offline tests for approval, source/date handling,
persistence, budget reservations, provider errors, photo licensing and inbox operations.
`python -m mountain_editor demo` runs a clearly labelled offline example.
`python -m mountain_editor check` checks configuration presence, not API access or billing.
