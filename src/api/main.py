from fastapi import FastAPI

app = FastAPI(title="Nifty 100 API Stub")


@app.get("/health")
def health_check():
    return {"status": "ok"}
