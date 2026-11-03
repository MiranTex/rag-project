from fastapi import APIRouter, Depends, HTTPException

from backend.api.security import require
from backend.auth.permissions import SETTINGS_MANAGE, AuthenticatedUser
from backend.config import get_env_settings, refresh_settings
from backend.dependencies import get_settings_repository
from backend.models import SettingInfo, SettingsUpdate
from backend.settings_catalog import CATALOG, validate_setting

router = APIRouter(prefix="/settings", tags=["settings"])

manage_settings = require(SETTINGS_MANAGE)


def _current() -> list[SettingInfo]:
    env = get_env_settings()
    effective = refresh_settings()
    overridden = get_settings_repository().load()
    return [
        SettingInfo(
            key=s.key,
            label=s.label,
            help=s.help,
            group=s.group,
            kind=s.kind,
            choices=list(s.choices),
            minimum=s.minimum,
            maximum=s.maximum,
            value=getattr(effective, s.key),
            default=getattr(env, s.key),
            overridden=s.key in overridden,
        )
        for s in CATALOG
    ]


@router.get("", response_model=list[SettingInfo], dependencies=[Depends(manage_settings)])
def list_settings() -> list[SettingInfo]:
    return _current()


@router.put("", response_model=list[SettingInfo])
def update_settings(payload: SettingsUpdate, user: AuthenticatedUser = Depends(manage_settings)) -> list[SettingInfo]:
    """Valida tudo antes de gravar: ou ficam todas as alterações, ou nenhuma."""
    try:
        values = {key: validate_setting(key, value) for key, value in payload.values.items()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_settings_repository().save(values, user.user_id)
    return _current()


@router.delete("/{key}", response_model=list[SettingInfo], dependencies=[Depends(manage_settings)])
def reset_setting(key: str) -> list[SettingInfo]:
    """Volta ao valor do .env."""
    get_settings_repository().delete(key)
    return _current()
