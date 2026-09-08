"""Actual FastapiAdmin host integration, not a replacement backend masquerading as the template."""
from fastapi import Depends
from .api import create_router
from .config import get_settings
from .database import Database


def create_app():
    # scripts/bootstrap.py assembles an unmodified pinned upstream plus additive Vue/entrypoint overlays.
    from app import create_app as create_upstream_app
    from app.core.dependencies import get_current_user
    settings = get_settings()
    settings.ensure_paths()
    db = Database(settings.database_url)
    app = create_upstream_app()

    async def actor(auth=Depends(get_current_user)) -> str:
        return str(auth.user.id)

    app.include_router(create_router(db, settings, actor))
    return app
