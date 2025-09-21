from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
    docs_url=None,   # Disables Swagger UI
    redoc_url=None,  # Disables ReDoc
    openapi_url=None # Disables the OpenAPI JSON schema
)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)
