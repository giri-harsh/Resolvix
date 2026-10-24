"""RTC token minting. POST /rtc/token {channel, uid, role} -> {token, expires_at}."""
import time

from agora_token_builder import RtcTokenBuilder
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resolvix import settings

router = APIRouter()

TOKEN_TTL_SECONDS = 3600

ROLE_PUBLISHER = 1  # agora_token_builder.Role_Attendee == PUBLISHER for RTC


class TokenRequest(BaseModel):
    channel: str
    uid: int
    role: str = "publisher"


class TokenResponse(BaseModel):
    token: str
    expires_at: int


def build_token(channel: str, uid: int) -> TokenResponse:
    if not settings.AGORA_APP_ID or not settings.AGORA_APP_CERTIFICATE:
        raise HTTPException(status_code=500, detail="AGORA_APP_ID / AGORA_APP_CERTIFICATE not configured")
    expire_ts = int(time.time()) + TOKEN_TTL_SECONDS
    token = RtcTokenBuilder.buildTokenWithUid(
        settings.AGORA_APP_ID,
        settings.AGORA_APP_CERTIFICATE,
        channel,
        uid,
        ROLE_PUBLISHER,
        expire_ts,
    )
    return TokenResponse(token=token, expires_at=expire_ts)


@router.post("/rtc/token", response_model=TokenResponse)
def rtc_token(req: TokenRequest) -> TokenResponse:
    return build_token(req.channel, req.uid)
