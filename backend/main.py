# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from database import init_sage_bfc_tables
from ws_manager import manager

# ─── Import des routers modulaires ───
from modules.auth import router as auth_router, init_auth_tables
from modules.saisie_caisse import router as saisie_caisse_router
from modules.migration_sage import router as migration_sage_router
from modules.export_csv import router as export_csv_router
from modules.sage_bfc import router as sage_bfc_router


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

# ─── Enregistrement des routers ───
app.include_router(auth_router)
app.include_router(saisie_caisse_router)
app.include_router(migration_sage_router)
app.include_router(export_csv_router)
app.include_router(sage_bfc_router)


# ─── Enregistrer la boucle asyncio au démarrage ───
@app.on_event("startup")
async def on_startup():
    import asyncio
    manager.set_loop(asyncio.get_running_loop())


# ─── WebSocket temps réel ───
@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
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