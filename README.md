# moxfield-card-searcher

Compare a Magic: The Gathering card list against a [Moxfield](https://www.moxfield.com)
collection CSV export. Each entry is classified into one of five tiers and
written to its own output file.

## Install

```bash
uv sync
```

## Usage

```bash
uv run moxfield-card-searcher <list.txt> <collection.csv> [--out-dir DIR]
```

`<list.txt>` is one entry per line. Recognised forms:

```
4 Lightning Bolt
4 Lightning Bolt (M21) 162
4 Lightning Bolt (M21) 162 *F*
Lightning Bolt
# comment lines and blank lines are ignored
```

`<collection.csv>` is a Moxfield collection export.

## Fetching someone else's binder

The core tool needs a CSV. If you already have a Moxfield collection export, use
that. If you want to compare against **someone else's public binder** (which
Moxfield does not let you export directly), there is a helper script that
shares its fetcher with the web UI:

```bash
uv sync --group ui
uv run scripts/fetch_binder.py <binder-id-or-url> <output.csv> [--limit-pages N]
```

`<binder-id>` accepts either the bare ID or a full URL, e.g. either
`YR6dKVcP8UK9Hg2qnSOsbA` or `https://moxfield.com/binders/YR6dKVcP8UK9Hg2qnSOsbA`.

The Moxfield API is rate-limited and sits behind Cloudflare, so a typical
12k-entry binder takes about two minutes to fetch.

## Web UI (optional)

A local web app that wraps the same matching pipeline. The CLI remains the
canonical interface; the web UI is a second consumer aimed at managing
multiple saved binders and searching across them without re-fetching each
time.

```bash
uv sync --group ui
uv run --group ui moxfield-card-searcher-ui [--host ...] [--port ...] [--db ...]
```

Defaults to `127.0.0.1:8000` and stores binders in `./binders.db`. Override
with the flags above or the `MOXFIELD_CARD_SEARCHER_HOST`,
`MOXFIELD_CARD_SEARCHER_PORT`, `MOXFIELD_CARD_SEARCHER_DB` environment
variables. See `.env.example` for the full list.

### What it does

- **Add binders by URL or ID.** Paste a Moxfield URL or bare binder id; the
  app fetches in the background and a live progress row updates every two
  seconds via HTMX polling.
- **Persistent multi-binder library.** Each saved binder lives in
  `binders.db` with its cards, owner username, and last-fetched timestamp.
  Refresh and Delete are one click each. Refresh is an atomic swap — old
  data stays live until the new fetch commits, so a failed or cancelled
  refresh never leaves you without your binder.
- **Cancel in flight.** Cancel a running fetch or refresh at any time. A
  cancelled refresh swaps the row right back into the original binder row
  with no reload required; a cancelled fresh fetch removes the row cleanly.
- **Search across every saved binder.** Paste a want list or upload a
  `.txt`. Results are grouped per binder with Scryfall card art, a narrative
  status line per card (`All 4 owned`, `Need 2 more`), set/printing details,
  and a separate monospace table for cards that aren't in any binder.
  Binders that contributed zero matches are hidden so the page only shows
  what's relevant.
- **List-format reference panel.** Sits next to the search input with
  grouped examples — with set + collector number, without set, and foil-only
  (`*F*`).

### Caveats

- **Single-user, local-only, no authentication.** Do not bind to a public
  interface.
- Card art is fetched from the public Scryfall CDN at render time, so pages
  need network access to display images. Matching itself is fully offline
  once a binder is saved.

## Tiers

| File                          | Meaning                                                         |
| ----------------------------- | --------------------------------------------------------------- |
| `hits-with-set.txt`           | Specific printing owned in sufficient quantity                  |
| `partial-hits-with-set.txt`   | Specific printing owned but quantity insufficient               |
| `hits.txt`                    | Sufficient total across printings (different from requested)    |
| `partial-hits.txt`            | Card owned but total insufficient                               |
| `non-hits.txt`                | Card not owned                                                  |

The tool picks the **best achievable tier**. If a specific-printing match is
partial but other printings cover the deficit, the entry lands in `hits.txt`,
not `partial-hits-with-set.txt`.

## Development

```bash
uv run pytest
uv run ruff check .
uv run pyright
```
