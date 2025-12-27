from fastapi import FastAPI

app = FastAPI(title="Trading Journal API")

@app.get("/")
def root():
    return {"message": "API is live 🚀"}

@app.get("/health")
def health():
    return {"status": "ok"}
