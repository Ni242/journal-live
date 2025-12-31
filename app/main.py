from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.deps import engine
from app.models import Base

from app.routes.positions_routes import router as positions_router
from app.routes.pnl_routes import router as pnl_router
from app.routes.capital_routes import router as capital_router
from app.routes.risk_routes import router as risk_router
from app.routes.csv_import_routes import router as csv_import_router


app = FastAPI(title="Trading Journal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app.include_router(positions_router)
app.include_router(pnl_router)
app.include_router(capital_router)
app.include_router(risk_router)
app.include_router(csv_import_router)


@app.get("/")
def root():
    return {"message": "Trading Journal backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}
