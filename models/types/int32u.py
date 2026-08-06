from typing import Annotated
from pydantic import Field

Int32u = Annotated[int, Field(ge=0, le=2**31 - 1)]
