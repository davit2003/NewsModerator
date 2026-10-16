# Mountain Editor — first working implementation

A Russian-language Telegram editorial assistant for a guided hiking/climbing community in Poland.
Tatras first, flexible geography, human approval required. Python 3.12, standard library only.

## What is implemented

- OpenAI Responses API web search and Gemini Google Search grounding adapters.
- Two-stage evidence gathering and Russian drafting with an editorial brief.
- Source URL must occur in provider search metadata; exact-URL duplicate suppression.
- Recent content and owner-supplied context passed into editorial generation.
- Owner-only private Telegram controls, photos, edits, AI rewrites, rejection and scheduling.
- Version-specific approval; edits revoke approval; expired drafts cannot publish.
- Single-instance SQLite persistence and a daily AI request count ceiling.
- Automatic discovery on Monday, Wednesday and Friday at/after 10:00 Europe/Warsaw (optional).
- Ambiguous sends are held for manual review, never automatically retried.
- Docker/Railway configuration; publishing and scheduled research disabled by default.

## Try locally without accounts

From this directory:

```bash
python -m mountain_editor demo
python -m unittest discover -s tests -v
```

The demo prints a clearly labeled example community post, makes no network requests,
and does not pretend to report current news. No dependencies to install.

## Deployment: Railway

1. Put this directory's contents at the root of a private GitHub repository.
2. Create your bot through Telegram's verified @BotFather. Keep the token private.
3. Determine your numeric Telegram user ID and the destination chat ID through your own
   Telegram Bot API updates (a private `/start` reveals `message.from.id`; a group command
   addressed to the bot reveals `message.chat.id`). Do this before running the worker,
   never run two getUpdates consumers. Avoid exposing the bot token in screenshots or logs.
4. Add the bot to the destination group with permission to send photos/messages.
   For a channel, grant the required administrator posting permission. Keep privacy mode enabled.
5. In Railway, create a project and deploy the GitHub repository. Dockerfile is included.
6. Attach a persistent volume mounted at `/data`. Use exactly ONE replica. Disable sleeping.
7. Configure the variables below using Railway's private variable settings.
8. Open the bot privately and send `/start`. Try `/find`, attach a photo, then `/preview ID`.
9. With real AI configured, validate at least one full post in a separate test group first.
10. Set the real target, `PUBLISH_ENABLED=true`, and optionally `AUTO_RESEARCH=true`.

The process runs on Railway; AI inference runs at your chosen provider.
GitHub stores code, not credentials. `.env.example` documents settings but is not auto-loaded.
For local execution, set environment variables through your shell or IDE securely.
No public domain or webhook is needed: Telegram long polling is used.

| Variable | Meaning |
|---|---|
| `AI_PROVIDER` | `demo`, `openai`, or `gemini` |
| `AI_MODEL` | Exact model ID available in your account, supporting that provider's search tool |
| `OPENAI_API_KEY` | Needed only for OpenAI |
| `GEMINI_API_KEY` | Needed only for Gemini |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `OWNER_TELEGRAM_ID` | Your numeric Telegram user ID; never assigned by first visitor |
| `TARGET_CHAT_ID` | Numeric group ID or supported channel identifier |
| `DB_PATH` | `/data/editor.db` on Railway |
| `PUBLISH_ENABLED` | `false` initially; `true` enables approved sends |
| `AUTO_RESEARCH` | `false` initially; `true` enables scheduled discovery |
| `MAX_AI_CALLS_PER_DAY` | Default 12; counts attempted provider calls in UTC |
| `RESEARCH_WEEKDAYS` | Default `0,2,4` (Monday=0) |
| `RESEARCH_HOUR` | Default 10, Europe/Warsaw with daylight saving |

Run `python -m mountain_editor check` for configuration presence checks (no API validation).
API billing is separate from chat subscriptions. The request count ceiling is NOT a currency
budget: search tool usage and output length still affect charges. Configure provider alerts too.

## Daily use

- `/find`: research one candidate and send its preview.
- `/queue`: list drafts and states. `/preview 1`: display the current version.
- Send a photo with caption `/photo 1 Фото: Davit. Иллюстрация. RIGHTS_OK`.
  The marker attests that you have reuse rights. It is removed from the public caption.
  Check that the image matches the subject; the app does not inspect its visual contents.
- `/edit 1 FULL NEW TEXT INCLUDING SOURCE LINK`: replace the text and revoke approval.
- `/rewrite 1 Сделай начало конкретнее, убери пафос`: AI rewrite, then fresh preview.
- Click **Опубликовать** to approve that exact version and send it.
- `/schedule 1 2 2026-12-01T18:00:00+01:00`: approve draft 1, version 2, for that time.
  A timezone offset is required. Time must be before expiry.
- `/context ...`: replace the stored style preferences, recent Instagram context and confirmed trips.
  Use this to supply representative captions; no automatic training or feedback learning is claimed.
- `/pause`: stop automatic research AND publishing; `/resume`: resume.
  Manual `/find` remains available while paused.

Drafts expire after 24 hours, or six hours when marked safety-sensitive by the model.
This is an upper limit after discovery, not evidence that a source is fresh. Verify event dates
and safety claims during review. Text is capped at 850 UTF-16 units to leave room for credits.
Long source URLs may cause a draft to be rejected rather than truncated.

## Reliability and recovery

Only owner private-chat commands work. Buttons encode draft ID and version; the database checks
both. Publication claims are atomic. A Telegram timeout, or restart during a send, results in
`uncertain` state. Check the group manually; this version intentionally has no blind retry command.
Commands are recorded before processing, so a crash can lose a command, but cannot replay a publish.
Use `/queue` after a restart. Provider requests are synchronous; research can delay button processing
and scheduled posts by several minutes. Scheduled delivery is best effort, not exact-time guaranteed.
Scheduled research attempts are recorded before execution; failures do not loop or accumulate AI charges.

Configure Railway volume backups before production. For a consistent manual backup, stop the worker
and copy the database plus any WAL/SHM files, or use SQLite's online backup API. Restore with the worker
stopped. Backups contain private editorial context and Telegram identifiers; keep them private.

## Honest scope and next steps

This is a runnable MVP, not a deployed service. No credentials are bundled. Offline tests and the demo
have been run; live model access, model output quality, Telegram permissions, Docker build and Railway
deployment still require validation in your accounts.

Not yet included: direct RSS ingestion, automatic photo licensing/discovery, photo library selection,
Instagram account ingestion, engagement analytics, semantic duplicate clustering, independent source
fact-checking, automatic learning from edits, or automated backups. Grounded search and a second writing
pass help quality but are not an independent fact-check. Owner review remains necessary.

Google Search grounding can return redirect URLs and search suggestion metadata. Before enabling Gemini
in production, review Google's current grounding attribution/display requirements for your interface.
This MVP retains source links but does not render Google's HTML search suggestions in Telegram.

Recommended next milestone: connect one provider, collect ten representative story dossiers, compare
Russian drafts from the candidate models with a fixed rubric (accuracy, relevance, hook, naturalness,
editing effort, cost), and choose from observed results. The model ID is deliberately not hardcoded.
Then add photo-library selection and RSS sources based on the pilot's actual gaps.

## Documentation used

- https://developers.openai.com/api/docs/guides/tools-web-search
- https://ai.google.dev/gemini-api/docs/google-search
- https://core.telegram.org/bots/api
- https://docs.railway.com/services
- https://docs.railway.com/volumes

Checked 2026-10-16. Provider capabilities and billing can change.
