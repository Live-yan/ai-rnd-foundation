"""Real FastapiAdmin application plus generated, authenticated business routes."""
import json
from pathlib import Path
from fastapi import Depends
from app import create_app as upstream_app
from app.core.dependencies import get_current_user
from business_runtime import create_business_router
from delivery_db import make_engine


def create_app():
    app = upstream_app()
    engine = make_engine()
    spec = json.loads(Path(__file__).with_name('business_spec.json').read_text(encoding='utf-8'))

    async def actor(auth=Depends(get_current_user)):
        return str(auth.user.id)

    app.include_router(create_business_router(engine, spec, actor))
    return app
