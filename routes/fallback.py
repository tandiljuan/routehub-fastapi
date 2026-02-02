from random import randint
from fastapi import APIRouter
from fastapi import HTTPException

router = APIRouter()

@router.api_route(
    "/{path:path}",
    methods=[
        "GET",
        "HEAD",
        "OPTIONS",
        #"TRACE",
        "PUT",
        "DELETE",
        "POST",
        "PATCH",
        #"CONNECT",
    ],
    include_in_schema=False,
)
async def catch_all(path: str):
    messages = [
        "Oops! '{}' has taken a leave of absence",
        "It seems '{}' is on a coffee break!",
        "Oops! '{}' couldn't be found. It's lost in the code!",
        "Whoops! '{}' has gone fishing. Try another!",
        "Where the heck is '{}'? Even our database is confused",
        "Whoops! '{}' is like a unicorn: it doesn't exist",
        "The data you seek is in another dimension!",
        "Sorry, no fortune cookie predictions here. Try a different path!",
        "Oops! '{}' is as elusive as a well-written documentation",
        "Looks like our server is playing hide and seek!",
        "Oops! '{}' is having a moment... it’s not found!",
        "You've wandered off the beaten path!",
        "Sorry, '{}' took a wrong turn at Albuquerque!",
        "Whoops! You’ve strayed from the beaten path at '{}'",
        "Sorry, '{}' is in a long-term relationship with invisibility",
        "Uh-oh! '{}' is experiencing a temporary identity crisis",
        "Whoops! '{}' went on a quest for the Holy Grail... still searching!",
        "Even our server is shaking its head at this one!",
        "Oops! You've hit a dead end",
        "We're not saying it's aliens, but... where's '{}'?",
    ]
    index = randint(0, len(messages)-1)
    raise HTTPException(
            status_code=404,
            detail=messages[index].format(f"/{path}"),
    )
