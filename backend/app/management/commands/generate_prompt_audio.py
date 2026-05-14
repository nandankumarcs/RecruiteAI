"""Generate cached prompt audio assets."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from app.services.prompt_audio_service import get_prompt_audio_service
from app.services.prompt_templates import (
    DEFAULT_CLARIFICATION_TEXTS,
    DEFAULT_CLOSING_TEXTS,
    DEFAULT_FILLER_TEXTS,
    DEFAULT_OPENER_TEXT,
    DEFAULT_REPROMPT_TEXTS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", help="Comma-separated category list")
    parser.add_argument("--template-key", help="Specific template key to generate")
    parser.add_argument("--job-id", help="Generate question audio for a job")
    parser.add_argument("--force-regenerate", action="store_true")
    return parser


def _template_definition(template_key: str) -> tuple[str, str] | None:
    if template_key == "opener_consent":
        return ("opener", DEFAULT_OPENER_TEXT)
    for category, mapping in (
        ("reprompt", DEFAULT_REPROMPT_TEXTS),
        ("clarification", DEFAULT_CLARIFICATION_TEXTS),
        ("closing", DEFAULT_CLOSING_TEXTS),
        ("filler", DEFAULT_FILLER_TEXTS),
    ):
        if template_key in mapping:
            return (category, mapping[template_key])
    return None


async def _run(args: argparse.Namespace) -> int:
    service = get_prompt_audio_service()
    assets = []

    if args.template_key:
        template = _template_definition(args.template_key)
        if template is None:
            raise SystemExit(f"Unknown template key: {args.template_key}")
        category, text = template
        assets.append(
            await service.ensure_prompt_audio(
                template_key=args.template_key,
                category=category,
                text=text,
                force_regenerate=args.force_regenerate,
            )
        )
    elif args.job_id:
        assets = await service.ensure_question_audio_for_job(
            args.job_id,
            force_regenerate=args.force_regenerate,
        )
    else:
        categories = {
            value.strip().lower()
            for value in (args.category or "").split(",")
            if value.strip()
        }
        assets = await service.ensure_default_templates(
            categories=categories,
            force_regenerate=args.force_regenerate,
        )

    counts = Counter(asset.status for asset in assets)
    print(
        {
            "generated": len(assets),
            "success_count": counts.get("ready", 0),
            "failure_count": counts.get("failed", 0),
        }
    )
    return 0 if counts.get("failed", 0) == 0 else 1


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
