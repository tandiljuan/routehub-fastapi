from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from routes import vehicles
from routes import fleets

app = FastAPI(
    docs_url=None,   # Disables Swagger UI
    redoc_url=None,  # Disables ReDoc
    openapi_url=None # Disables the OpenAPI JSON schema
)

app.include_router(vehicles.router)
app.include_router(fleets.router)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)
