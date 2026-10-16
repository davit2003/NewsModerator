# Mountain Editor — first working implementation

A Russian-language Telegram editorial assistant for a guided hiking/climbing community in Poland.
Tatras first, flexible geography, human approval required. Python 3.12, standard library only.

## What is implemented

- OpenAI Responses API web search and Gemini Google Search grounding adapters.
- Two-stage evidence gathering and Russian drafting with an editorial brief.
- Source URL must occur in provider search metadata; exact-URL duplicate suppression.
- Recent content and owner-supplied context passed into editorial generation.
- Owner-only private Telegram controls, button-driven edits and AI rewrites, rejection and scheduling.
- Reusable photo collection: normal Telegram uploads, session consent, automatic illustrative photo selection.
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

## Automatic photos — no uploads or extra API key required

Newly generated drafts now search Wikimedia Commons automatically using a location/subject query
produced during the existing drafting call. Demo posts use a generic mountain landscape query.
The bot sends a complete private preview with the selected image and full credit. Choose
**Изменить фото → Найти другое фото** to search for another candidate. Uploaded photos are optional.
Existing news drafts created before this update have no image query: generate a fresh draft to use this feature.

The default `AUTO_PHOTOS=true` requires no extra credentials or AI calls. Set it to `false` to disable
Commons access. `COMMONS_USER_AGENT` may optionally identify your own deployment/contact URL.

The filter accepts exact CC BY / CC BY-SA 2.0, 2.5, 3.0, 4.0 and CC0 metadata with matching license URLs,
known authors, no listed restrictions or custom attribution requirements, and JPEG/PNG images on
Wikimedia's image host. Complex credits, unsupported licenses, unknown authors and insufficient caption space
are skipped. The post includes author, license link, source page and an illustrative/resized label. Older licenses
also include the supplied title; a simple original-source URL is retained when provided.
No cropping, overlays or generated edits are applied. Reuse of CC BY-SA photos retains that license.
Do not remove the photo credit when copying a post outside the bot.

License metadata and retrieval time are saved with the draft version for audit. The image is first
uploaded to the private Telegram preview and stored as a Telegram file ID, so approval publishes that
same image rather than refetching a changing URL. Wikimedia metadata can be wrong and does not clear
personality/trademark rights; this is conservative automated filtering, not legal clearance. Review
relevance and visible people/logos during normal approval. Pictures are illustrations, not claimed to
show the specific news event. Matching is based on search relevance, not visual AI verification.

If Commons is unavailable or no qualifying photo is found, the draft is retained. An optional uploaded
photo collection can supply an illustrative fallback; otherwise nothing publishes until a photo is
selected. The bot never substitutes an unlicensed image. Long text may need shortening to fit attribution.
Photo discovery needs outbound HTTPS access to commons.wikimedia.org; Telegram retrieves the image
from upload.wikimedia.org or thumb.wikimedia.org. Live Commons discovery returned qualifying Tatra
photos, and 37 offline tests cover filters and workflow; Telegram delivery from Railway must
be checked on Railway.

References: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
and https://creativecommons.org/licenses/by/4.0/ .

## Daily use — buttons first

After Railway deploys this update, send `/start` once to show the new menu.
No new environment variables or manual database migration are needed. Existing drafts remain intact.

Optional photo collection setup:

1. Tap **🖼 Мои фотографии** and confirm you can reuse the photos you are about to upload.
2. Send your photos normally, individually or as an album, then tap **Готово**.
   Consent applies to that upload session for one hour; approved photos remain reusable afterward.
   Optional captions describe location, season, or subject to improve matching. No IDs or magic text.
3. Tap **🔎 Найти материал**. The bot prepares a draft and selects a photo from your collection.
4. Under the preview, choose **✅ Опубликовать**, **✏️ Изменить текст**, **🖼 Изменить фото**,
   **🔄 Переписать**, or **❌ Пропустить**. Text changes and rewrite instructions are normal replies.
5. **Изменить фото** offers another library image or a normal upload. For a draft-specific album,
   the first image is attached; remaining images are saved for later. Tap **Готово** for the preview.
6. **📋 Черновики** opens active drafts. **↩️ Отмена** cancels the current interaction.

Only send photos you own or may reuse with the generic attribution
“Фото из коллекции организатора. Иллюстрация.” Photos requiring special attribution should use the
legacy `/photo ID CREDIT RIGHTS_OK` command with the full required credit instead of the collection.
Collection selection uses caption word matching and least-recently-selected ordering, not visual AI
recognition. If no captions match it selects an illustrative image by rotation: verify relevance before
approval. All collection photos are explicitly labeled illustrative, not evidence of the news event.
File IDs, descriptions, consent records and selection timestamps are stored in the persistent database;
image bytes stay on Telegram. File IDs are tied to this bot and cannot be migrated to a different bot.

Advanced commands remain available:

- `/find`, `/queue`, `/preview ID`, `/photos`, `/cancel`.
- `/edit ID FULL TEXT`: replace text; the button-based edit flow automatically preserves source links.
- `/rewrite ID feedback`: rewrite using AI.
- `/schedule ID VERSION 2026-12-01T18:00:00+01:00`: approve an exact version for a future time.
- `/context ...`: replace style examples, Instagram context and confirmed trip information.
- `/pause` and `/resume`: stop/resume scheduled research and publishing; manual discovery still works.

Any photo or text change revokes approval. Stale controls cannot mutate a newer draft. Upload/edit
conversations survive restarts but expire after one hour. Publishing remains disabled unless explicitly
configured. No Telegram or AI credentials are changed by this update.

Drafts expire after 24 hours, or six hours when marked safety-sensitive by the model.
This is an upper limit after discovery, not evidence that a source is fresh. Verify event dates
and safety claims during review. Text is capped at 850 UTF-16 units to leave room for credits.
Long source URLs may cause a draft to be rejected rather than truncated.

## Reliability and recovery

Only owner private-chat commands work. Buttons encode draft ID and version; the database checks
both. Publication claims are atomic. A Telegram timeout, or restart during a send, results in
`uncertain` state. Check the group manually; this version intentionally has no blind retry command.
Commands are recorded before processing, so a crash can lose a command, but cannot replay a publish.
Use **📋 Черновики** after a restart; database states include `uncertain` for manual recovery. Provider requests are synchronous; research can delay button processing
and scheduled posts by several minutes. Scheduled delivery is best effort, not exact-time guaranteed.
Scheduled research attempts are recorded before execution; failures do not loop or accumulate AI charges.

Configure Railway volume backups before production. For a consistent manual backup, stop the worker
and copy the database plus any WAL/SHM files, or use SQLite's online backup API. Restore with the worker
stopped. Backups contain private editorial context and Telegram identifiers; keep them private.

## Honest scope and next steps

This is a runnable MVP, not a deployed service. No credentials are bundled. Offline tests and the demo
have been run; live model access, model output quality, Telegram permissions, Docker build and Railway
deployment still require validation in your accounts.

Not yet included: direct RSS ingestion, visual AI photo tagging,
Instagram account ingestion, engagement analytics, semantic duplicate clustering, independent source
fact-checking, automatic learning from edits, or automated backups. Grounded search and a second writing
pass help quality but are not an independent fact-check. Owner review remains necessary.

Google Search grounding can return redirect URLs and search suggestion metadata. Before enabling Gemini
in production, review Google's current grounding attribution/display requirements for your interface.
This MVP retains source links but does not render Google's HTML search suggestions in Telegram.

Recommended next milestone: connect one provider, collect ten representative story dossiers, compare
Russian drafts from the candidate models with a fixed rubric (accuracy, relevance, hook, naturalness,
editing effort, cost), and choose from observed results. The model ID is deliberately not hardcoded.
Then consider visual photo tagging and RSS sources based on the pilot's actual gaps.

## Documentation used

- https://developers.openai.com/api/docs/guides/tools-web-search
- https://ai.google.dev/gemini-api/docs/google-search
- https://core.telegram.org/bots/api
- https://docs.railway.com/services
- https://docs.railway.com/volumes

Checked 2026-10-16. Provider capabilities and billing can change.

