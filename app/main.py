from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# IMPORT ROUTERS
from app.routes.positions_routes import router as positions_router
from app.routes.pnl_routes import router as pnl_router
from app.routes.capital_routes import router as capital_router
from app.routes.risk_routes import router as risk_router


app = FastAPI(
    title="Trading Journal API",
    version="0.1.0"
)

# CORS (VERY IMPORTANT)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# BASIC ROUTES
@app.get("/")
def root():
    return {"message": "Trading Journal API running"}

@app.get("/health")
def health():
    return {"status": "ok"}

# 🔥 INCLUDE ROUTERS (THIS WAS MISSING)
app.include_router(positions_router)
app.include_router(pnl_router)
app.include_router(capital_router)
app.include_router(risk_router)
