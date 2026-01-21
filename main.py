import os
from fastapi import Depends
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from libs.authorization import authorization as auth
from routes import vehicles
from routes import fleets
from routes import drivers
from routes import milestones
from routes import deliveries
from routes import delivery_lots
from routes import fallback

ENVIRONMENT = os.environ.get("ENVIRONMENT", "PRD")

IS_LCL = True if 'LCL' == ENVIRONMENT.upper() else False

app = FastAPI(
    docs_url = "/docs" if IS_LCL else None,
    redoc_url = "/redoc" if IS_LCL else None,
    openapi_url = "/openapi.json" if IS_LCL else None,
    title = "RouteHub",
    swagger_ui_parameters =  {
        # Make the operations in the docs UI closed by default
        "docExpansion": "none",
    },
    dependencies=[Depends(auth)],
)

app.include_router(vehicles.router)
app.include_router(fleets.router)
app.include_router(drivers.router)
app.include_router(milestones.router)
app.include_router(deliveries.router)
app.include_router(delivery_lots.router)
app.include_router(fallback.router)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    message = {"code": exc.status_code, "message": exc.detail}
    return JSONResponse(content=message, status_code=exc.status_code)
