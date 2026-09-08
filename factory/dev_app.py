"""Isolated diagnostic API, explicitly NOT the FastapiAdmin application or production auth."""
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .api import create_router
from .config import get_settings
from .database import Database
from .security import token_matches


def create_app():
    settings = get_settings()
    if len(settings.token) < 24:
        raise RuntimeError("Diagnostic API requires a random FACTORY_TOKEN of at least 24 characters")
    bearer = HTTPBearer()

    def actor(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
        if not token_matches(credentials.credentials, settings.token):
            raise HTTPException(401, "Invalid diagnostic token")
        return "diagnostic-admin"

    app = FastAPI(title="AI R&D diagnostic API - not FastapiAdmin")
    app.include_router(create_router(Database(settings.database_url), settings, actor))
    return app
