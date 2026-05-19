from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from vai_agent.api.v1.schemas import ProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
def get_profile(request: Request) -> ProfileResponse:
    profile = getattr(request.app.state, "profile", None)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PROFILE_NOT_LOADED", "message": "No profile is loaded."},
        )
    groups = [g.name for g in profile.security_policy.user_access_groups]
    return ProfileResponse(
        profile_id=profile.meta.profile_id,
        display_name=profile.meta.database_name,
        dialect=profile.meta.dialect,
        table_count=len(profile.tables),
        allowed_groups=groups,
    )
