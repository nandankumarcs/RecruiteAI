"""
Twilio webhook signature validation dependency.

Usage:
    @router.post("/webhooks/twilio/voice", dependencies=[Depends(verify_twilio_signature)])
    async def voice_webhook(...): ...

When TWILIO_VALIDATE_SIGNATURES=False (the default for local dev), the check is
bypassed so that ngrok / mock flows continue to work without hassle.
Set TWILIO_VALIDATE_SIGNATURES=True in production .env.
"""
from __future__ import annotations

import logging

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)

try:
    from twilio.request_validator import RequestValidator as TwilioRequestValidator
except Exception:  # pragma: no cover
    TwilioRequestValidator = None  # type: ignore[assignment,misc]


async def verify_twilio_signature(
    request: Request,
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
    settings=Depends(get_settings),
) -> None:
    """
    FastAPI dependency that validates the X-Twilio-Signature header.

    Raises HTTP 403 if:
    - TWILIO_VALIDATE_SIGNATURES is True, AND
    - the signature is missing or invalid.

    Skips validation when:
    - TWILIO_VALIDATE_SIGNATURES is False (default for local development), OR
    - TWILIO_MOCK_MODE is True, OR
    - the Twilio SDK is not installed.
    """
    if not settings.TWILIO_VALIDATE_SIGNATURES or settings.TWILIO_MOCK_MODE:
        return

    if TwilioRequestValidator is None:
        logger.warning(
            "Twilio SDK not installed — cannot validate webhook signatures. "
            "Install 'twilio' or set TWILIO_VALIDATE_SIGNATURES=False."
        )
        return

    if not x_twilio_signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Twilio-Signature header",
        )

    validator = TwilioRequestValidator(settings.TWILIO_AUTH_TOKEN)

    # Reconstruct the exact URL Twilio signed (must match what Twilio sees)
    url = str(request.url)

    # For POST form requests Twilio signs the URL + sorted form params
    form_data: dict[str, str] = {}
    try:
        form = await request.form()
        form_data = dict(form)  # type: ignore[arg-type]
    except Exception:
        pass

    is_valid = validator.validate(url, form_data, x_twilio_signature)
    if not is_valid:
        logger.warning("Invalid Twilio webhook signature for URL %s", url)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio webhook signature",
        )
