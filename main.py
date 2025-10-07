from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
    docs_url=None,   # Disables Swagger UI
    redoc_url=None,  # Disables ReDoc
    openapi_url=None # Disables the OpenAPI JSON schema
)

@app.get("/vehicles")
async def vehicles_get():
    return []

@app.post("/vehicles")
async def vehicles_post():
    return {
        "id": 1,
        "name": "pickup",
        "volume": 1230000,
        "volume_unit": "CUBIC_CENTIMETER",
        "consumption": 12,
        "consumption_unit": "LITERS_PER_100KM",
        "category_type": "PICKUP",
        "engine_type": "DIESEL"
    }

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)
