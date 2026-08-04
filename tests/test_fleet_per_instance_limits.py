"""Verifies that #4 (per-instance limits) works end to end:

1. Adapter: two fleet links pointing at the same catalog vehicle emit two
   PlanVehicle entries with the alias as `type`, each with its own
   route/behavior limits (no more last-write-wins collapse by name).
2. Wire-type map: aliases are resolvable back to the catalog vehicle id, so
   optimizer results can still be persisted against the right Vehicle row.
3. API: POST /fleets accepts multiple entries for the same catalog id when
   each carries a distinct alias, and rejects colliding aliases.
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("RDBMS_URL", "sqlite://")

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import models.company  # noqa: F401
import models.driver  # noqa: F401
import models.fleet  # noqa: F401
import models.milestone  # noqa: F401
import models.tenant  # noqa: F401
import models.vehicle  # noqa: F401
import models.delivery_plan  # noqa: F401

from libs.lot_plan_adapter import (
    build_plan_vehicles,
    build_wire_type_to_vehicle_id_map,
    resolve_vehicle_id,
)
from models.company import Company
from models.fleet import Fleet, FleetVehicle
from models.lot_config import (
    FleetRunProfile,
    LotConfig,
    VehicleBehaviorConfig,
    VehicleOverride,
    VehicleRouteConfig,
    VehicleRunConfig,
    VehiclesConfig,
)
from models.tenant import Tenant
from models.vehicle import Vehicle


def _link(*, alias: str, veh_id: int, name: str, qty: int, stops_max: int) -> SimpleNamespace:
    return SimpleNamespace(
        quantity=qty,
        alias=alias,
        vehicle=SimpleNamespace(
            id=veh_id,
            name=name,
            volume=None,
            volume_unit=None,
            weight=None,
            weight_unit=None,
            consumption=None,
            consumption_unit=None,
            engine_type=None,
        ),
        run_profile=FleetRunProfile(
            route=VehicleRouteConfig(stops_max=stops_max),
            behavior=None,
        ),
    )


def _lot_stub() -> SimpleNamespace:
    return SimpleNamespace(
        route_stops_min=None,
        route_stops_max=None,
        route_length_min=None,
        route_length_max=None,
        route_length_unit=None,
        route_time_min=None,
        route_time_max=None,
        route_time_unit=None,
    )


class TestAdapterPerInstance(unittest.TestCase):
    def test_two_links_same_catalog_emit_two_plan_vehicles(self):
        links = [
            _link(alias="Van-A", veh_id=1, name="Van", qty=1, stops_max=40),
            _link(alias="Van-B", veh_id=1, name="Van", qty=1, stops_max=80),
        ]
        vehicles = build_plan_vehicles(links, _lot_stub(), LotConfig())

        types = {v.type for v in vehicles}
        self.assertEqual(types, {"Van-A", "Van-B"})

        by_type = {v.type: v for v in vehicles}
        self.assertEqual(by_type["Van-A"].deliveries_qty.max, 40)
        self.assertEqual(by_type["Van-B"].deliveries_qty.max, 80)
        self.assertEqual(by_type["Van-A"].quantity, 1)
        self.assertEqual(by_type["Van-B"].quantity, 1)

    def test_single_link_without_alias_still_uses_catalog_name(self):
        link = SimpleNamespace(
            quantity=3,
            alias=None,
            vehicle=SimpleNamespace(
                id=1,
                name="Van",
                volume=None,
                volume_unit=None,
                weight=None,
                weight_unit=None,
                consumption=None,
                consumption_unit=None,
                engine_type=None,
            ),
            run_profile=None,
        )
        vehicles = build_plan_vehicles([link], _lot_stub(), LotConfig())
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0].type, "Van")
        self.assertEqual(vehicles[0].quantity, 3)

    def test_alias_override_beats_catalog_wide_override(self):
        links = [
            _link(alias="Van-A", veh_id=1, name="Van", qty=1, stops_max=40),
            _link(alias="Van-B", veh_id=1, name="Van", qty=1, stops_max=40),
        ]
        cfg = LotConfig(
            vehicles=VehiclesConfig(
                overrides=[
                    VehicleOverride(
                        vehicle_id="Van",
                        route=VehicleRouteConfig(stops_max=100),
                    ),
                    VehicleOverride(
                        vehicle_id="Van-B",
                        route=VehicleRouteConfig(stops_max=200),
                    ),
                ]
            )
        )
        vehicles = {v.type: v for v in build_plan_vehicles(links, _lot_stub(), cfg)}
        self.assertEqual(vehicles["Van-A"].deliveries_qty.max, 100)
        self.assertEqual(vehicles["Van-B"].deliveries_qty.max, 200)

    def test_wire_map_resolves_alias_to_catalog_id(self):
        links = [
            _link(alias="Van-A", veh_id=7, name="Van", qty=1, stops_max=40),
            _link(alias="Van-B", veh_id=7, name="Van", qty=1, stops_max=80),
        ]
        wire_map = build_wire_type_to_vehicle_id_map(links)
        self.assertEqual(resolve_vehicle_id(wire_map, "Van-A"), 7)
        self.assertEqual(resolve_vehicle_id(wire_map, "Van-B"), 7)
        self.assertEqual(resolve_vehicle_id(wire_map, "Van"), 7)
        self.assertEqual(resolve_vehicle_id(wire_map, "7"), 7)


class TestFleetRoutesAlias(unittest.TestCase):
    """Exercise POST/PATCH /fleets with aliased entries via TestClient."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        tenant = Tenant(alias="acme")
        self.session.add(tenant)
        self.session.commit()
        self.session.refresh(tenant)

        company = Company(alias="acme-main", tenant_id=tenant.id)
        self.session.add(company)
        self.session.commit()
        self.session.refresh(company)
        self.company_id = int(company.id)

        van = Vehicle(name="Van", company_id=self.company_id)
        self.session.add(van)
        self.session.commit()
        self.session.refresh(van)
        self.vehicle_id = str(van.id)

        # Wire up FastAPI with overridden deps so the router uses our sqlite
        # session and skips API-key auth.
        from fastapi import FastAPI
        from routes import fleets as fleets_route
        from libs.authorization.authorization import authorization
        from models.database import get_session

        app = FastAPI()
        app.include_router(fleets_route.router)
        app.dependency_overrides[get_session] = lambda: self.session
        app.dependency_overrides[authorization] = lambda: self.company_id
        self.client = TestClient(app)

    def tearDown(self):
        self.session.close()

    def test_post_accepts_duplicate_catalog_with_distinct_aliases(self):
        payload = {
            "name": "mixed",
            "vehicles": [
                {"id": self.vehicle_id, "qty": 1, "alias": "Van-A",
                 "route": {"stops_max": 40}},
                {"id": self.vehicle_id, "qty": 1, "alias": "Van-B",
                 "route": {"stops_max": 80}},
            ],
        }
        r = self.client.post("/fleets", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        vehicles = body["vehicles"]
        self.assertEqual(len(vehicles), 2)
        aliases = {v["alias"] for v in vehicles}
        self.assertEqual(aliases, {"Van-A", "Van-B"})
        by_alias = {v["alias"]: v for v in vehicles}
        self.assertEqual(by_alias["Van-A"]["route"]["stops_max"], 40)
        self.assertEqual(by_alias["Van-B"]["route"]["stops_max"], 80)

    def test_post_rejects_duplicate_aliases(self):
        payload = {
            "name": "conflict",
            "vehicles": [
                {"id": self.vehicle_id, "qty": 1, "alias": "same"},
                {"id": self.vehicle_id, "qty": 1, "alias": "same"},
            ],
        }
        r = self.client.post("/fleets", json=payload)
        self.assertEqual(r.status_code, 409, r.text)

    def test_post_without_alias_defaults_to_catalog_name(self):
        payload = {
            "name": "legacy",
            "vehicles": [
                {"id": self.vehicle_id, "qty": 2},
            ],
        }
        r = self.client.post("/fleets", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        vehicles = r.json()["vehicles"]
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["alias"], "Van")

    def test_patch_upserts_by_alias(self):
        create = self.client.post(
            "/fleets",
            json={
                "name": "mixed",
                "vehicles": [
                    {"id": self.vehicle_id, "qty": 1, "alias": "Van-A",
                     "route": {"stops_max": 40}},
                ],
            },
        )
        self.assertEqual(create.status_code, 201, create.text)
        fleet_id = int(create.json()["id"])

        patch = self.client.patch(
            f"/fleets/{fleet_id}",
            json={
                "vehicles": [
                    {"id": self.vehicle_id, "qty": 2, "alias": "Van-A",
                     "route": {"stops_max": 55}},
                    {"id": self.vehicle_id, "qty": 1, "alias": "Van-B",
                     "route": {"stops_max": 90}},
                ]
            },
        )
        self.assertEqual(patch.status_code, 200, patch.text)
        vehicles = patch.json()["vehicles"]
        by_alias = {v["alias"]: v for v in vehicles}
        self.assertEqual(set(by_alias), {"Van-A", "Van-B"})
        self.assertEqual(by_alias["Van-A"]["qty"], 2)
        self.assertEqual(by_alias["Van-A"]["route"]["stops_max"], 55)
        self.assertEqual(by_alias["Van-B"]["qty"], 1)
        self.assertEqual(by_alias["Van-B"]["route"]["stops_max"], 90)

    def test_patch_deletes_links_missing_from_payload(self):
        """The editor always PATCHes the full list, so an absent alias is a delete."""
        create = self.client.post(
            "/fleets",
            json={
                "name": "boston",
                "vehicles": [
                    {"id": self.vehicle_id, "qty": 1, "alias": "Van-A"},
                    {"id": self.vehicle_id, "qty": 48, "alias": "Van-B"},
                    {"id": self.vehicle_id, "qty": 20, "alias": "Van-C"},
                ],
            },
        )
        self.assertEqual(create.status_code, 201, create.text)
        fleet_id = int(create.json()["id"])
        self.assertEqual(len(create.json()["vehicles"]), 3)

        patch = self.client.patch(
            f"/fleets/{fleet_id}",
            json={
                "vehicles": [
                    {"id": self.vehicle_id, "qty": 48, "alias": "Van-B"},
                    {"id": self.vehicle_id, "qty": 20, "alias": "Van-C"},
                ]
            },
        )
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual({v["alias"] for v in patch.json()["vehicles"]}, {"Van-B", "Van-C"})

        # And it must stay deleted on a fresh read, not just in the PATCH response.
        after = self.client.get(f"/fleets/{fleet_id}")
        self.assertEqual(after.status_code, 200, after.text)
        self.assertEqual({v["alias"] for v in after.json()["vehicles"]}, {"Van-B", "Van-C"})

    def test_patch_can_empty_the_fleet(self):
        create = self.client.post(
            "/fleets",
            json={
                "name": "solo",
                "vehicles": [{"id": self.vehicle_id, "qty": 1, "alias": "Van-A"}],
            },
        )
        fleet_id = int(create.json()["id"])

        patch = self.client.patch(f"/fleets/{fleet_id}", json={"vehicles": []})
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual(patch.json()["vehicles"], [])

    def test_patch_without_vehicles_key_leaves_links_untouched(self):
        """A name-only PATCH must not wipe the fleet."""
        create = self.client.post(
            "/fleets",
            json={
                "name": "keep",
                "vehicles": [{"id": self.vehicle_id, "qty": 3, "alias": "Van-A"}],
            },
        )
        fleet_id = int(create.json()["id"])

        patch = self.client.patch(f"/fleets/{fleet_id}", json={"name": "renamed"})
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual(patch.json()["name"], "renamed")
        self.assertEqual(len(patch.json()["vehicles"]), 1)


if __name__ == "__main__":
    unittest.main()
