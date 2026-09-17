#!/usr/bin/env python3
"""Issue, list and revoke RouteHub API keys.

The key itself is never stored — only its SHA-256 hash — so the full key is
printed exactly once, at creation. Losing it means issuing a new one.

    RDBMS_URL=... python scripts/issue_api_key.py issue --company-id 1 --name "my app"
    RDBMS_URL=... python scripts/issue_api_key.py list --company-id 1
    RDBMS_URL=... python scripts/issue_api_key.py revoke --prefix rh_live_AbCd

Inside the container:

    docker compose exec api python scripts/issue_api_key.py list --company-id 1

ROLE: on Postgres with row-level security enabled the app connects as a
restricted role that cannot see other workspaces. Run this with the
owner/superuser role (the same one used for migrations), not with the app's
`RDBMS_URL`, or the inserts fail closed.

FORMAT: keys must stay byte-compatible with the ones vepathos-api-doc
provisions (`routehub-api-key-crypto.ts`) — same `rh_live_` prefix, same 24
random bytes as base64url, same SHA-256 hash — because both write to the same
`api_key` table and `libs/authorization` looks keys up by hash alone.
`tests/test_api_key_issue.py` pins that contract.
"""

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone

# Allow imports from the project root when run as `python scripts/issue_api_key.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, create_engine, select  # noqa: E402

from libs.authorization.authorization import API_KEY_PREFIX, hash_api_key  # noqa: E402
from models.api_key import ApiKey  # noqa: E402
from models.company import Company  # noqa: E402

# vepathos-api-doc revokes keys by (company_id, name) when it rotates its own,
# so a CLI key issued under either name would be silently revoked by it.
RESERVED_NAMES = {"vepathos-api-doc", "api-doc local dev"}

# 24 random bytes, base64url — matches `randomBytes(24).toString("base64url")`.
KEY_RANDOM_BYTES = 24
# `key_prefix` is the searchable, non-secret handle: prefix + 4 random chars.
KEY_PREFIX_LEN = 12


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw, key_hash, key_prefix). `raw` is shown once and not stored."""
    raw = f"{API_KEY_PREFIX}{secrets.token_urlsafe(KEY_RANDOM_BYTES)}"
    return raw, hash_api_key(raw), raw[:KEY_PREFIX_LEN]


def _engine():
    url = os.environ.get("RDBMS_URL")
    if not url:
        sys.exit("RDBMS_URL is not set. Point it at the RouteHub database (owner role).")
    return create_engine(url)


def _fmt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


def cmd_issue(args: argparse.Namespace) -> int:
    name = args.name.strip()
    if not name:
        sys.exit("--name cannot be blank")
    if len(name) > 100:
        sys.exit("--name is limited to 100 characters")
    if name in RESERVED_NAMES and not args.force:
        sys.exit(
            f"'{name}' is reserved by vepathos-api-doc, which revokes keys by "
            f"(company_id, name) when it rotates its own — your key would be "
            f"revoked without warning. Pick another name (or --force if you "
            f"really mean to replace api-doc's key)."
        )

    with Session(_engine()) as db:
        if db.get(Company, args.company_id) is None:
            sys.exit(f"Company {args.company_id} does not exist.")

        raw, key_hash, key_prefix = generate_api_key()
        db.add(ApiKey(
            company_id=args.company_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
        ))
        db.commit()

    print(f"Issued for company {args.company_id} — name: {name!r}, prefix: {key_prefix}")
    print("\nThis is the only time the full key is shown. Store it now:\n")
    print(f"  {raw}\n")
    print(f"  Authorization: Bearer {raw}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with Session(_engine()) as db:
        query = select(ApiKey).order_by(ApiKey.id)
        if args.company_id is not None:
            query = query.where(ApiKey.company_id == args.company_id)
        rows = db.exec(query).all()

    if not rows:
        print("No API keys found.")
        return 0

    print(f"{'ID':>5}  {'COMPANY':>7}  {'PREFIX':<14} {'CREATED':<17} {'LAST USED':<17} {'STATUS':<8} NAME")
    for r in rows:
        status = "revoked" if r.revoked_at else "active"
        print(
            f"{r.id:>5}  {r.company_id:>7}  {r.key_prefix:<14} {_fmt(r.created_at):<17} "
            f"{_fmt(r.last_used_at):<17} {status:<8} {r.name}"
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    with Session(_engine()) as db:
        rows = db.exec(
            select(ApiKey).where(
                ApiKey.key_prefix == args.prefix,
                ApiKey.revoked_at.is_(None),
            )
        ).all()
        if not rows:
            sys.exit(f"No active key with prefix {args.prefix!r}.")
        # key_prefix is not unique (only key_hash is); refuse to guess.
        if len(rows) > 1 and not args.all:
            ids = ", ".join(str(r.id) for r in rows)
            sys.exit(
                f"{len(rows)} active keys share prefix {args.prefix!r} (ids: {ids}). "
                f"Re-run with --all to revoke every one of them."
            )
        now = datetime.now(timezone.utc)
        for r in rows:
            r.revoked_at = now
            db.add(r)
        db.commit()
        print(f"Revoked {len(rows)} key(s) with prefix {args.prefix}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_issue = sub.add_parser("issue", help="Create a key (printed once)")
    p_issue.add_argument("--company-id", type=int, required=True)
    p_issue.add_argument("--name", required=True, help="What this key is for")
    p_issue.add_argument("--force", action="store_true", help="Allow a reserved name")
    p_issue.set_defaults(func=cmd_issue)

    p_list = sub.add_parser("list", help="List keys (never shows the key itself)")
    p_list.add_argument("--company-id", type=int, default=None)
    p_list.set_defaults(func=cmd_list)

    p_revoke = sub.add_parser("revoke", help="Revoke by key_prefix")
    p_revoke.add_argument("--prefix", required=True, help="e.g. rh_live_AbCd")
    p_revoke.add_argument("--all", action="store_true", help="Revoke every match")
    p_revoke.set_defaults(func=cmd_revoke)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
