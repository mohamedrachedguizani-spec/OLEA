# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from database import db, init_sage_bfc_tables, init_forecast_tables
from ws_manager import manager
from modules.auth.security import decode_access_token

# ─── Import des routers modulaires ───
from modules.auth import router as auth_router, init_auth_tables
from modules.saisie_caisse import router as saisie_caisse_router
from modules.migration_sage import router as migration_sage_router
from modules.export_csv import router as export_csv_router
from modules.sage_bfc import router as sage_bfc_router
from modules.dashboard import router as dashboard_router
from modules.forecast import router as forecast_router
from modules.reporting import router as reporting_router
from modules.configuration import router as configuration_router, init_configuration_tables
from modules.audit import router as audit_router, init_audit_tables


app = FastAPI(title="Olea – Gestion de Caisse & BFC")

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialiser les tables
init_auth_tables()
init_sage_bfc_tables()
init_forecast_tables()
init_configuration_tables()
init_audit_tables()

# ─── Enregistrement des routers ───
app.include_router(auth_router)
app.include_router(saisie_caisse_router)
app.include_router(migration_sage_router)
app.include_router(export_csv_router)
app.include_router(sage_bfc_router)
app.include_router(dashboard_router)
app.include_router(forecast_router)
app.include_router(reporting_router)
app.include_router(configuration_router)
app.include_router(audit_router)


# ─── Enregistrer la boucle asyncio au démarrage ───
@app.on_event("startup")
async def on_startup():
    import asyncio
    manager.set_loop(asyncio.get_running_loop())


# ─── WebSocket temps réel ───
def _get_ws_current_user(ws: WebSocket):
    """Valide l'utilisateur à partir du cookie access token pour la connexion WebSocket."""
    token = ws.cookies.get("olea_access_token")
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id, is_active, token_version FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()

    if not user:
        return None
    if not user["is_active"]:
        return None
    if payload.get("tv") != user["token_version"]:
        return None

    return user


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    user = _get_ws_current_user(ws)
    if not user:
        await ws.close(code=1008)
        return

    await manager.connect(ws)
    try:
        while True:
            # Garder la connexion vivante ; ignorer les messages entrants
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)