from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import re

app = FastAPI(
    docs_url=None,   # Disables Swagger UI
    redoc_url=None,  # Disables ReDoc
    openapi_url=None # Disables the OpenAPI JSON schema
)

@app.get("/vehicles")
async def vehicles_get(request: Request):
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'example=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            example = match.group(1)

    if 'empty' == example:
        return []
    elif 'list-1.0' == example:
        return [
            {
                "id": 1,
                "name": "pickup",
                "volume": 1230000,
                "volume_unit": "CUBIC_CENTIMETER",
                "consumption": 12,
                "consumption_unit": "LITERS_PER_100KM",
                "category_type": "PICKUP",
                "engine_type": "DIESEL"
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

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
