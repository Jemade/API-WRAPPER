#!/usr/bin/env python3
"""CLI utility to create a new client API key and store its hash in the database."""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.security import extract_key_prefix, generate_raw_api_key, hash_api_key
from app.db.session import close_db_engine, get_session_maker
from app.models.api_key import ApiKey


async def create_key(client_name: str, rate_limit: int | None = None) -> None:
    """Generate and persist an API key record."""
    raw_key = generate_raw_api_key()
    key_hash = hash_api_key(raw_key)
    prefix = extract_key_prefix(raw_key)

    session_maker = get_session_maker()
    async with session_maker() as session:
        # Check for client name collision
        stmt = select(ApiKey).where(ApiKey.client_name == client_name)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Warning: A client named '{client_name}' already exists (ID: {existing.id}).")

        new_key = ApiKey(
            client_name=client_name,
            key_hash=key_hash,
            key_prefix=prefix,
            is_active=True,
            rate_limit_per_minute=rate_limit,
        )
        session.add(new_key)
        await session.commit()
        await session.refresh(new_key)

        print("\n" + "=" * 60)
        print("API KEY GENERATED SUCCESSFULLY")
        print("=" * 60)
        print(f"Client ID:    {new_key.id}")
        print(f"Client Name:  {new_key.client_name}")
        print(f"Key Prefix:   {new_key.key_prefix}")
        print(f"Rate Limit:   {new_key.rate_limit_per_minute or 'Global Default'} req/min")
        print("-" * 60)
        print(f"RAW API KEY:  {raw_key}")
        print("-" * 60)
        print("IMPORTANT: Save this key securely now. The raw key is NEVER stored")
        print("in the database and cannot be recovered if lost.")
        print("=" * 60 + "\n")

    await close_db_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a new API key for the LLM Gateway.")
    parser.add_argument("--name", required=True, help="Client or application name")
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=None,
        help="Optional custom rate limit per minute for this key (e.g. 100)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(create_key(client_name=args.name, rate_limit=args.rate_limit))
    except Exception as exc:
        print(f"Error creating API key: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
