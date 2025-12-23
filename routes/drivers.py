import re
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import JSONResponse
from models.database import Session as DbSession
from models.vehicle import Vehicle
from models.driver import (
    Driver,
    DriverCreate,
    DriverResponse,
    DriverVehicle,
)

router = APIRouter(prefix="/drivers")

@router.get("")
async def drivers_get(request: Request):
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
                "first_name": "John",
                "last_name": "Doe",
                "work_schedules": [
                    "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
                ],
                "start_point": "37.7749,-122.4194",
                "work_areas": [
                    [
                        "37.7749,-122.4194",
                        "37.7749,-122.4195",
                        "37.7750,-122.4194"
                    ]
                ],
                "vehicles": [
                    {
                        "vehicle_id": 1,
                        "quantity": 2
                    }
                ]
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
                "id": 1,
                "first_name": "Jane",
                "last_name": "Smith",
                "work_schedules": [
                    "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
                ],
                "start_point": "37.7749,-122.4194",
                "work_areas": [
                    [
                        "37.7749,-122.4194",
                        "37.7749,-122.4195",
                        "37.7750,-122.4194"
                    ]
                ],
                "vehicles": [
                    {
                        "vehicle_id": 1,
                        "quantity": 2
                    }
                ]
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post(
    "",
    response_model=DriverResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def drivers_post(db: DbSession, post_data: DriverCreate):
    # Dump submitted data as dictionary
    drv_dict = post_data.model_dump()
    # Add Company ID to submitted data
    drv_dict['company_id'] = 1
    # Create drivel object from dictionary
    drv_db = Driver.model_validate(drv_dict)

    # Save new Driver in the database
    db.add(drv_db)
    db.commit()

    # Create relations between Driver and Vehicles
    post_vehicles = post_data.vehicles or []
    for v in post_vehicles:
        veh_id = int(v.id)
        veh_qty = int(v.qty)

        if veh_qty < 1:
            continue

        veh_db = db.get(Vehicle, veh_id)
        if veh_db:
            link = DriverVehicle(
                fleet=drv_db,
                vehicle=veh_db,
                quantity=veh_qty,
            )
            drv_db.vehicles.append(link)
            db.add(drv_db)
            db.commit()

    # Return (custom serialized) Driver
    db.refresh(drv_db)
    return drv_db.model_dump()

@router.get("/{id}")
async def drivers_id_get(id: int, request: Request):
    key = ''
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'(\w+)=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            key = match.group(1)
            example = match.group(2)

    if 'code' == key:
        message = {"message": "..."}
        return JSONResponse(content=message, status_code=int(example))

    if 'driver-1.0' == example:
        return {
            "id": 1,
            "first_name": "John",
            "last_name": "Doe",
            "work_schedules": [
                "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
            ],
            "start_point": "37.7749,-122.4194",
            "work_areas": [
                [
                    "37.7749,-122.4194",
                    "37.7749,-122.4195",
                    "37.7750,-122.4194"
                ]
            ],
            "vehicles": [
                {
                    "vehicle_id": 1,
                    "quantity": 2
                }
            ]
        }
    elif 'driver-1.1' == example:
        return {
            "id": 1,
            "first_name": "Jane",
            "last_name": "Smith",
            "work_schedules": [
                "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
            ],
            "start_point": "37.7749,-122.4194",
            "work_areas": [
                [
                    "37.7749,-122.4194",
                    "37.7749,-122.4195",
                    "37.7750,-122.4194"
                ]
            ],
            "vehicles": [
                {
                    "vehicle_id": 1,
                    "quantity": 2
                }
            ]
        }

@router.patch("/{id}")
async def drivers_id_patch(id: int):
    return {
        "id": 1,
        "first_name": "Jane",
        "last_name": "Smith",
        "work_schedules": [
            "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
        ],
        "start_point": "37.7749,-122.4194",
        "work_areas": [
            [
                "37.7749,-122.4194",
                "37.7749,-122.4195",
                "37.7750,-122.4194"
            ]
        ],
        "vehicles": [
            {
                "vehicle_id": 1,
                "quantity": 2
            }
        ]
    }

@router.delete("/{id}")
async def drivers_id_delete(id: int):
    return {"message": "Fleet Deleted"}
