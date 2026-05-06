# moxfield-compare

Compare a Magic: The Gathering card list against a [Moxfield](https://www.moxfield.com)
collection CSV export. Each entry is classified into one of five tiers and
written to its own output file.

## Install

```bash
uv sync
```

## Usage

```bash
uv run moxfield-compare <list.txt> <collection.csv> [--out-dir DIR]
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

The CLI is the canonical interface. A minimal local web UI is available as an
opt-in feature for users who prefer paste-and-click ergonomics.

```bash
uv sync --group ui
uv run --group ui moxfield-compare-ui [--host ...] [--port ...] [--db ...]
```

By default the server binds to `127.0.0.1:8000` and stores binders in
`./binders.db`. Override with `--host`, `--port`, `--db`, or the corresponding
`MOXFIELD_COMPARE_HOST`, `MOXFIELD_COMPARE_PORT`, `MOXFIELD_COMPARE_DB`
environment variables. See `.env.example` for the variable list.

The UI is single-user, local-only, and has no authentication. Do not bind it
to a public interface.

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
