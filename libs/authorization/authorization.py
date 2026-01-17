import os
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import APIKeyHeader

BEARER_TOKEN = os.environ.get("BEARER_TOKEN")

auth_header = APIKeyHeader(name="Authorization", auto_error=True)

def authorization(auth: str = Depends(auth_header)):
    auth = auth.split()[-1] if auth and len(auth) else ''
    if None != BEARER_TOKEN and BEARER_TOKEN == auth:
        return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key"
    )
