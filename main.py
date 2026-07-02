import os
from fastapi import Depends
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from libs.authorization import authorization as auth
from libs.openapi_docs import enrich_openapi
from routes import vehicles
from routes import fleets
from routes import drivers
from routes import milestones
from routes import deliveries
from routes import delivery_lots
from routes import fallback

ENVIRONMENT = os.environ.get("ENVIRONMENT", "PRD")

IS_LCL = True if 'LCL' == ENVIRONMENT.upper() else False

_OPENAPI_DESCRIPTION = os.environ.get(
    "OPENAPI_DESCRIPTION",
    "RouteHub is a route planning and optimization API designed for logistics, "
    "delivery services, and mobility applications.",
)
_OPENAPI_VERSION = os.environ.get("OPENAPI_VERSION", "0.21.0")

app = FastAPI(
    docs_url = "/docs" if IS_LCL else None,
    redoc_url = "/redoc" if IS_LCL else None,
    openapi_url = "/openapi.json" if IS_LCL else None,
    title = "RouteHub",
    description = _OPENAPI_DESCRIPTION,
    version = _OPENAPI_VERSION,
    swagger_ui_parameters =  {
        "docExpansion": "none",
    },
    openapi_tags=[
        {"name": "vehicles", "description": "Vehicle catalog."},
        {"name": "fleets", "description": "Fleet composition and per-type run_profile."},
        {"name": "drivers", "description": "Drivers and vehicle assignments."},
        {"name": "milestones", "description": "Depots and route origins."},
        {"name": "deliveries", "description": "Delivery stops."},
        {"name": "lots", "description": "Delivery lots, optimizer plans, and routes."},
    ],
    dependencies=[Depends(auth)],
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    app.openapi_schema = enrich_openapi(schema, is_lcl=IS_LCL)
    return app.openapi_schema


app.openapi = custom_openapi

app.include_router(vehicles.router)
app.include_router(fleets.router)
app.include_router(drivers.router)
app.include_router(milestones.router)
app.include_router(deliveries.router)
app.include_router(delivery_lots.router)
app.include_router(fallback.router)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    from fastapi.encoders import jsonable_encoder
    message = {
        "code": 422,
        "message": "Validation Error",
        "errors": [
            {
                "msg": error["msg"],
                "inp": error["input"],
                "loc": error["loc"],
            } for error in exc.errors()
        ],
    }
    return JSONResponse(content=message, status_code=422)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    message = {"code": exc.status_code, "message": exc.detail}
    return JSONResponse(content=message, status_code=exc.status_code)
