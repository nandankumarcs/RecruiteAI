"""Purge superseded cached prompt audio versions."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select

from app.database import async_session_factory
from app.models.audio_prompt_asset import AudioPromptAsset
from app.services.storage import get_storage_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-days", type=int, default=30)
    return parser


async def _run(args: argparse.Namespace) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    storage = get_storage_provider()

    async with async_session_factory() as session:
        max_versions = (
            select(
                AudioPromptAsset.template_key.label("template_key"),
                func.max(AudioPromptAsset.version).label("max_version"),
            )
            .group_by(AudioPromptAsset.template_key)
            .subquery()
        )
        result = await session.execute(
            select(AudioPromptAsset)
            .join(
                max_versions,
                AudioPromptAsset.template_key == max_versions.c.template_key,
            )
            .where(
                and_(
                    AudioPromptAsset.version < max_versions.c.max_version,
                    AudioPromptAsset.created_at < cutoff,
                )
            )
        )
        assets = list(result.scalars().all())
        purged = 0
        for asset in assets:
            await storage.delete_file(asset.file_path)
            await session.delete(asset)
            purged += 1
        await session.commit()

    print({"purged_count": purged, "retention_days": args.retention_days})
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
