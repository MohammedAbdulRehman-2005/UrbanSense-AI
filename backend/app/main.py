from fastapi import FastAPI

app = FastAPI(title="UrbanSense AI Backend")

@app.get("/health")
def health_check():
    return {"status": "ok"}
