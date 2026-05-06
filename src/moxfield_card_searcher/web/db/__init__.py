"""SQLite persistence for the web UI.

The package re-exports a flat surface so call sites use
`from moxfield_card_searcher.web import db` and then `db.<name>`. Internal modules
are split by responsibility:

- `_connection`: schema bootstrap + WAL/foreign-keys connection factory
- `_rows`: frozen dataclasses for the three tables
- `_binders`: CRUD for binders + their cards
- `_jobs`: CRUD for the fetch_jobs table
"""

from moxfield_card_searcher.web.db._binders import (
    create_binder,
    delete_binder,
    delete_cards_for_binder,
    insert_cards,
    list_binders,
    list_cards,
    update_binder_metadata,
)
from moxfield_card_searcher.web.db._connection import connect, init_schema
from moxfield_card_searcher.web.db._jobs import (
    cancel_job,
    create_job,
    fail_job,
    finish_job,
    get_job,
    has_active_job,
    list_jobs,
    update_job_progress,
)
from moxfield_card_searcher.web.db._rows import BinderRow, CardRow, JobRow

__all__ = [
    "BinderRow",
    "CardRow",
    "JobRow",
    "cancel_job",
    "connect",
    "create_binder",
    "create_job",
    "delete_binder",
    "delete_cards_for_binder",
    "fail_job",
    "finish_job",
    "get_job",
    "has_active_job",
    "init_schema",
    "insert_cards",
    "list_binders",
    "list_cards",
    "list_jobs",
    "update_binder_metadata",
    "update_job_progress",
]
