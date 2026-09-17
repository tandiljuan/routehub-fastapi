#!/usr/bin/env python3
"""Test E2E: reproduce un payload del optimizer a través de routehub-fastapi.

Lee un archivo JSON con formato directo del optimizer y lo mapea al flujo
de routehub-fastapi (vehicles → fleet → milestone → deliveries → lot → plan).

Uso:
  python scripts/test_plan_flow.py --scenario 01 --wire-only

Sin ``--input``, usa el único ``*.json`` en ``scripts/`` (o el que empiece con ``addresses_aws``).
``--list-scenarios`` no necesita JSON.

Escenarios (misma matriz que explore_wire_request_matrix.py):
  python scripts/test_plan_flow.py --list-scenarios
  docker compose exec api python scripts/test_plan_flow.py --scenario 05 --wire-only
  docker compose exec api python scripts/test_plan_flow.py --scenario 05 --wire-only --post-plan

``--wire-only``: crea lote vía API y muestra el wire (sin optimizer).
``--post-plan``: además llama ``POST /lots/{id}/plan`` y espera respuesta (omití ``--wire-only`` = plan directo).

Parches ad-hoc (solo test):
  --config-patch '{"vehicles":{"overrides":[{"vehicle_id":"v3","route":{"stops_max":99}}]}}'
  --config-json scenario_overlay.json

El preview wire usa GET /lots/{id} + ``libs/plan_build.py`` (mismo pipeline que POST /plan).

HOST / AUTH (sin pasar flags):
  - Dentro del contenedor api (``docker compose exec api ...``): ``http://127.0.0.1:80``
    y ``ROUTEHUB_API_KEY`` (o ``AUTH``) del entorno.
  - Desde el host contra docker-compose (puerto 8001): ``http://127.0.0.1:8001``.
  - Override: ``HOST=... AUTH=...`` o ``--host`` / ``--auth``.
"""

import argparse
import json
import os
import runpy
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

# Permitir imports del proyecto desde scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.package_wire import address_extra_from_source

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_run_cap(max_lot: int, address_count: int) -> int:
    """Solo acota bulk+lote si --max-lot N > 0 (iteración rápida). Default: todas."""
    if max_lot > 0:
        return min(max_lot, address_count)
    return address_count


def _default_host() -> str:
    explicit = os.environ.get("HOST")
    if explicit:
        return explicit.rstrip("/")
    # docker-compose: API en el mismo contenedor escucha en :80
    if "@db" in os.environ.get("RDBMS_URL", ""):
        return "http://127.0.0.1:80"
    # API publicada en el host (docker-compose.yaml → 8001:80)
    return "http://127.0.0.1:8001"


def _default_auth() -> str:
    # The API key both authenticates and selects the workspace (company).
    return os.environ.get("ROUTEHUB_API_KEY") or os.environ.get("AUTH") or ""


HOST = _default_host()
AUTH = _default_auth()


def _req(method: str, path: str, body: dict | None = None):
    url = f"{HOST}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {AUTH}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode().strip()
        try:
            return e.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return e.code, {"detail": body} if body else {}
    except urllib.error.URLError as e:
        return 0, {"detail": str(e.reason)}


def ok(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    status, data = _req(method, path, body)
    if status == 0 or status >= 400:
        print(f"  ERROR {method} {path} -> {status}: {data}")
        sys.exit(1)
    return status, data


def _load_wire_matrix() -> dict[str, Any]:
    """Carga explore_wire_request_matrix.py (mismo directorio, sin paquete scripts)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explore_wire_request_matrix.py")
    return runpy.run_path(path, run_name="wire_matrix_for_plan_flow")


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _remap_vehicle_refs(obj: Any, id_map: dict[str, str]) -> Any:
    """Reemplaza vehicle_id / id de fixtures (65,67,v3,…) por ids reales del POST /vehicles."""
    if isinstance(obj, dict):
        out: dict = {}
        for key, val in obj.items():
            if key in ("vehicle_id", "id") and isinstance(val, str) and val in id_map:
                out[key] = id_map[val]
            else:
                out[key] = _remap_vehicle_refs(val, id_map)
        return out
    if isinstance(obj, list):
        return [_remap_vehicle_refs(item, id_map) for item in obj]
    return obj


def _vehicle_id_map(vehicle_ids: dict[str, str]) -> dict[str, str]:
    """v1/v2/v3 + ids simulados de la matriz → id de catálogo creado en este run."""
    m = dict(vehicle_ids)
    if "v1" in vehicle_ids:
        m["65"] = vehicle_ids["v1"]
    if "v2" in vehicle_ids:
        m["66"] = vehicle_ids["v2"]
    if "v3" in vehicle_ids:
        m["67"] = vehicle_ids["v3"]
    return m


def _resolve_scenario(query: str):
    matrix = _load_wire_matrix()
    matches = [s for s in matrix["SCENARIOS"] if query in s.name]
    if not matches:
        print(f"No hay escenario que matchee {query!r}")
        print("Disponibles:", ", ".join(s.name for s in matrix["SCENARIOS"]))
        sys.exit(1)
    if len(matches) > 1:
        print(f"Ambiguo ({len(matches)} matches); usá un substring más específico:")
        for s in matches:
            print(f"  - {s.name}")
        sys.exit(1)
    return matches[0], matrix


def _list_scenarios() -> None:
    matrix = _load_wire_matrix()
    matrix["print_scenario_catalog"]()


def _discover_scripts_json() -> str | None:
    """Un ``*.json`` en scripts/, o el único ``addresses_aws*.json`` si hay varios."""
    all_json = sorted(
        os.path.join(SCRIPTS_DIR, name)
        for name in os.listdir(SCRIPTS_DIR)
        if name.endswith(".json") and os.path.isfile(os.path.join(SCRIPTS_DIR, name))
    )
    if not all_json:
        return None
    aws = [p for p in all_json if os.path.basename(p).startswith("addresses_aws")]
    if len(aws) == 1:
        return aws[0]
    if len(all_json) == 1:
        return all_json[0]
    return None


def resolve_input_path(explicit: str | None) -> str:
    if explicit:
        return explicit
    discovered = _discover_scripts_json()
    if discovered:
        return discovered
    all_json = sorted(
        os.path.join(SCRIPTS_DIR, name)
        for name in os.listdir(SCRIPTS_DIR)
        if name.endswith(".json")
    )
    if not all_json:
        print("  ERROR: pasá --input o dejá un .json en scripts/")
        sys.exit(2)
    print("  ERROR: varios JSON en scripts/; elegí con --input:")
    for path in all_json:
        print(f"    {path}")
    sys.exit(2)


def load_payload(path: str) -> tuple[dict, str]:
    """Carga payload optimizer-shaped. Retorna (payload, ruta)."""
    resolved = resolve_input_path(path)
    with open(resolved) as f:
        return json.load(f), resolved


def parse_destination(lat: float, lng: float) -> str:
    """Convierte lat/lng a ISO 6709: +DD.DDDDDDD+DDD.DDDDDDD/"""
    slat = f"{lat:+011.7f}".rstrip("0").rstrip(".")
    slng = f"{lng:+012.7f}".rstrip("0").rstrip(".")
    return f"{slat}{slng}/"


def fmt_time(minutes: int) -> str:
    """Convierte minutos desde medianoche a HH:MM."""
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}:00"


def main():
    global HOST, AUTH

    host_default = _default_host()
    auth_default = _default_auth()

    parser = argparse.ArgumentParser(description="Reproduce un payload del optimizer vía routehub-fastapi")
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "JSON del optimizer (default: único addresses_aws*.json o *.json en scripts/)"
        ),
    )
    parser.add_argument("--limit", type=int, default=5, help="Direcciones a mostrar en el preview (default 5, 0=todas)")
    parser.add_argument(
        "--max-lot",
        type=int,
        default=0,
        help="Opcional: limitar bulk+lote a N direcciones (default 0=todas las del JSON)",
    )
    parser.add_argument("--no-cleanup", action="store_true", help="No borrar datos de prueba al finalizar")
    parser.add_argument("--host", default=None, help=f"Base URL del API (default: {host_default})")
    parser.add_argument(
        "--auth",
        default=None,
        help="Bearer token (default: ROUTEHUB_API_KEY o AUTH)",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="Substring del escenario en explore_wire_request_matrix.py (ej. 04, 05_fleet)",
    )
    parser.add_argument("--list-scenarios", action="store_true", help="Lista escenarios y sale")
    parser.add_argument(
        "--wire-only",
        action="store_true",
        help="Tras POST /lots: solo preview del wire (no llama al optimizer salvo --post-plan)",
    )
    parser.add_argument(
        "--post-plan",
        action="store_true",
        help="POST /lots/{id}/plan + poll GET /plan (respuesta del servicio). Default si no hay --wire-only",
    )
    parser.add_argument(
        "--config-json",
        default=None,
        help="JSON file mergeado sobre lot.config (después del escenario)",
    )
    parser.add_argument(
        "--config-patch",
        default=None,
        help='JSON inline mergeado sobre lot.config (ej. \'{"vehicles":{...}}\')',
    )
    parser.add_argument(
        "--expect-plan-status",
        type=int,
        default=None,
        help="HTTP esperado en POST /plan (ej. 422 para escenario 12)",
    )
    args = parser.parse_args()

    if args.wire_only and args.post_plan:
        pass  # preview wire y luego POST /plan
    elif not args.wire_only and not args.post_plan:
        args.post_plan = True  # flujo clásico: planificar al final

    if args.list_scenarios:
        _list_scenarios()
        return

    HOST = (args.host or host_default).rstrip("/")
    AUTH = args.auth or auth_default
    print(f"API: {HOST}")

    scenario = None
    wire_matrix = _load_wire_matrix()
    if args.scenario:
        scenario, wire_matrix = _resolve_scenario(args.scenario)
        profile = wire_matrix["scenario_e2e_profile"](scenario)
        print(f"Escenario: {scenario.name}")
        print(f"  {scenario.summary}")
        print(f"  modo E2E: {profile['mode']} — {profile['reason']}")
        print(f"  request: {' | '.join(profile['request_deltas'])}")
        _print_scenario_trace(scenario)
        if not scenario.fleet_links:
            print("  ERROR: este escenario no tiene fleet — usá explore_wire_request_matrix.py")
            sys.exit(1)
    expect_plan_status = args.expect_plan_status
    if expect_plan_status is None and scenario and scenario.name.startswith("12_legacy_bad"):
        expect_plan_status = 422

    # ── Cargar payload ──────────────────────────────────────────────
    payload, src = load_payload(args.input)
    tag = payload.get("tag", "TEST")
    address_count = len(payload.get("addresses", []))
    run_cap = _resolve_run_cap(args.max_lot, address_count)
    show_n = args.limit if args.limit > 0 else min(5, run_cap)
    if run_cap < address_count:
        cap_note = f"max-lot={run_cap}"
    else:
        cap_note = "todas"
    print(f"Payload: {tag} | fuente={src} | {address_count} direcciones ({cap_note}, preview {show_n})")

    # ── 1. Vehicles ─────────────────────────────────────────────────
    print("\n[1/6] Creando vehículos desde el payload...")
    vehicle_ids = {}
    for v in payload.get("vehicles", []):
        vtype = v["type"]
        body = {
            "name": vtype,
            "category_type": "TRUCK",
        }
        # Mapear volumen
        if v.get("max_volume"):
            body["volume"] = int(v["max_volume"]["value"])
            body["volume_unit"] = _volume_unit(v["max_volume"]["unit"])
        # Mapear peso
        if v.get("max_weight"):
            body["weight"] = int(v["max_weight"]["value"])
            body["weight_unit"] = _weight_unit(v["max_weight"]["unit"])
        # Mapear consumo
        if v.get("consumption"):
            body["consumption"] = int(v["consumption"]["value"])
            body["consumption_unit"] = "LITERS_PER_100KM"
            body["engine_type"] = _engine_type(v["consumption"]["fuel_type"])

        _, created = ok("POST", "/vehicles", body)
        vehicle_ids[vtype] = created["id"]
        print(f"  vehicle {vtype} -> id={created['id']}")

    # ── 2. Fleet (qty + route/behavior; escenario puede cambiar perfil o catálogo-only) ──
    print("\n[2/6] Creando flota...")
    id_map = _vehicle_id_map(vehicle_ids)
    fleet_vehicles = _fleet_vehicles_for_run(scenario, payload, id_map)
    fleet_name = f"fleet-{tag}"
    if scenario:
        api_fleet = scenario.api_public.get("POST /fleets", {})
        if api_fleet.get("name"):
            fleet_name = api_fleet["name"]

    _, fleet = ok("POST", "/fleets", {
        "name": fleet_name,
        "vehicles": fleet_vehicles,
    })
    fleet_id = fleet["id"]
    print(f"  fleet_id={fleet_id}")
    _print_fleet_run_profile(fleet_vehicles, vehicle_ids)

    # ── 3. Milestone ────────────────────────────────────────────────
    print("\n[3/6] Creando milestone (origen)...")
    origin_lat = payload["origin_lat"]
    origin_lng = payload["origin_lng"]
    _, milestone = ok("POST", "/milestones", {
        "name": f"{tag}",
        "location": parse_destination(origin_lat, origin_lng),
    })
    milestone_id = milestone["id"]
    print(f"  milestone_id={milestone_id} @ {origin_lat},{origin_lng}")

    # ── 4. Deliveries ───────────────────────────────────────────────
    print(f"\n[4/6] Creando {run_cap} entregas via bulk (de {address_count} en JSON)...")
    items = []
    for addr in payload["addresses"][:run_cap]:
        items.append({
            "milestone_id": milestone_id,
            "destination": parse_destination(addr["lat"], addr["lng"]),
            "extra": address_extra_from_source(addr),
        })
    _, bulk_resp = ok("POST", "/deliveries/bulk", items)
    delivery_ids = [item["id"] for item in bulk_resp.get("success", [])]
    if bulk_resp.get("failure"):
        print(f"  ⚠ {len(bulk_resp['failure'])} entregas fallaron")
    print(f"  {len(delivery_ids)} entregas creadas")

    # ── 5. Delivery Lot con config ──────────────────────────────────
    lot_config = _lot_config_for_run(
        payload,
        scenario,
        wire_matrix,
        id_map,
        vehicle_ids,
        config_json=args.config_json,
        config_patch=args.config_patch,
    )
    lot_body: dict = {
        "milestone_id": milestone_id,
        "fleet_id": fleet_id,
        "config": lot_config,
    }
    if scenario:
        lot_public = scenario.api_public.get("POST /lots", {})
        if lot_public.get("route_limits"):
            lot_body["route_limits"] = lot_public["route_limits"]
        if lot_public.get("vehicle_limits"):
            lot_body["vehicle_limits"] = lot_public["vehicle_limits"]
    lot_deliveries = delivery_ids
    lot_body["deliveries"] = lot_deliveries
    print(f"\n[5/6] Creando lote con {len(lot_deliveries)} deliveries...")
    t0 = time.time()
    _, lot = ok("POST", "/lots", lot_body)
    lot_id = lot["id"]
    linked = lot.get("delivery_count", "?")
    print(f"  lot_id={lot_id} deliveries_linked={linked} ({time.time() - t0:.1f}s)")
    _print_lot_config_input(lot_config, lot_body)

    patched_fleet_vehicles, patched_lot_body = _apply_scenario_patches(
        scenario, id_map, vehicle_ids, fleet_id, lot_id,
    )
    lot_body_for_preview = dict(lot_body)
    if patched_lot_body:
        lot_body_for_preview = _deep_merge(lot_body_for_preview, patched_lot_body)

    _, lot_get = ok("GET", f"/lots/{lot_id}")
    lot_config_preview = lot_get.get("config") or lot_config
    fleet_for_preview = (
        (lot_get.get("fleet") or {}).get("vehicles")
        or patched_fleet_vehicles
        or fleet_vehicles
    )
    if patched_fleet_vehicles or patched_lot_body:
        _section("ESTADO tras PATCH (lo que usa POST /plan)")
        if patched_fleet_vehicles:
            print("  Fleet actualizado en DB (GET /lots incluye fleet embed):")
            _print_fleet_run_profile(
                (lot_get.get("fleet") or {}).get("vehicles") or patched_fleet_vehicles,
                vehicle_ids,
            )
        if patched_lot_body:
            print(f"  Lot config mergeado: {json.dumps(lot_config_preview, indent=2, default=str)}")
    preview_cap = show_n if show_n > 0 else min(5, len(lot_deliveries))
    preview_rows = [
        (
            int(dlv_id),
            parse_destination(payload["addresses"][i]["lat"], payload["addresses"][i]["lng"]),
            address_extra_from_source(payload["addresses"][i]),
        )
        for i, dlv_id in enumerate(lot_deliveries[:preview_cap])
    ]

    # ── Mostrar la request que enviaría POST /lots/{id}/plan ──────────
    show_optimizer_wire_from_lot(
        lot_get,
        preview_rows,
        show_n,
        scenario=scenario,
        fleet_vehicles=fleet_for_preview,
        lot_config=lot_config_preview,
        lot_body=lot_body_for_preview,
        vehicle_ids=vehicle_ids,
        wire_matrix=wire_matrix,
    )

    # ── 6. Plan (POST /lots/{id}/plan → optimizer) ───────────────────
    if scenario and wire_matrix and not args.wire_only and args.post_plan:
        profile = wire_matrix["scenario_e2e_profile"](scenario)
        cap = profile.get("post_plan_max_deliveries")
        if profile["mode"] == "wire-only" and (cap is None or run_cap > cap):
            cap_hint = (
                f"cap route_limits ~{cap} del., tenés {run_cap}"
                if cap is not None
                else profile["reason"]
            )
            print(f"\n[6/6] POST /plan omitido: escenario {profile['mode']} ({cap_hint}).")
            if cap is not None:
                print(
                    f"  Usá --wire-only (validación trace OK) o --max-lot {cap} "
                    f"si querés probar POST /plan."
                )
            else:
                print("  Usá --wire-only para validar el wire sin POST /plan.")
            if not args.no_cleanup:
                print("\nLimpiando lote/fleet/vehicles...")
                _req("DELETE", f"/lots/{lot_id}")
                _req("DELETE", f"/fleets/{fleet_id}")
                for vid in vehicle_ids.values():
                    _req("DELETE", f"/vehicles/{vid}")
            print("\n✔ Completado (wire validado; POST /plan omitido).")
            return

    if args.wire_only and not args.post_plan:
        print("\n[6/6] --wire-only: omitiendo POST /plan (agregá --post-plan para llamar al servicio)")
        if args.no_cleanup:
            print("\n✔ Test completado (sin limpieza).")
        else:
            print("\nLimpiando lote/fleet/vehicles...")
            _req("DELETE", f"/lots/{lot_id}")
            _req("DELETE", f"/fleets/{fleet_id}")
            for vid in vehicle_ids.values():
                _req("DELETE", f"/vehicles/{vid}")
            print("\n✔ Wire-only completado.")
        return

    print("\n[6/6] POST /lots/{id}/plan (wire armado por la API desde el lote persistido)...")
    _run_post_plan(lot_id, expect_plan_status)

    if args.no_cleanup:
        print("\n✔ Test completado (sin limpieza).")
        return

    print("\nLimpiando datos de prueba...")
    lot_status, _ = _req("DELETE", f"/lots/{lot_id}")
    if lot_status in (200, 404):
        print(f"  lot {lot_id} eliminado")
    else:
        print(f"  ⚠ no se pudo borrar lot {lot_id} (HTTP {lot_status})")

    for label, path in (
        ("fleet", f"/fleets/{fleet_id}"),
        *[(f"vehicle {vid}", f"/vehicles/{vid}") for vid in vehicle_ids.values()],
    ):
        status, _ = _req("DELETE", path)
        if status in (200, 404):
            print(f"  {label} eliminado")
        elif status >= 400:
            print(f"  ⚠ {label}: HTTP {status}")

    print(
        "  milestone/deliveries dejados en DB "
        f"(milestone_id={milestone_id}, {len(delivery_ids)} entregas). "
        "Reset dev: docker compose down -v"
    )
    print("\n✔ Test completado.")


def _run_post_plan(lot_id: int, expect_plan_status: int | None) -> None:
    t0 = time.time()
    if expect_plan_status is not None:
        status, plan = _req("POST", f"/lots/{lot_id}/plan")
        if status != expect_plan_status:
            print(f"  ERROR POST /plan -> {status} (esperaba {expect_plan_status}): {plan}")
            sys.exit(1)
        print(f"  POST /plan -> {status} OK en {time.time() - t0:.1f}s: {plan.get('detail', plan)}")
        return

    status, plan = ok("POST", f"/lots/{lot_id}/plan")
    opt_id = plan.get("optimizer_id")
    state = plan.get("state") or "PROCESSING"
    print(f"  POST {status} en {time.time() - t0:.1f}s | optimizer_id={opt_id} state={state}")

    if state == "PROCESSED":
        _print_routes(plan)
        return
    if status != 202 and state not in ("PROCESSING", "OPTIMIZING", "PENDING"):
        print(f"  ⚠ Respuesta inesperada: {json.dumps(plan, indent=2)}")
        return

    print("  Esperando optimizer (PROCESSING es normal con muchas direcciones)...")
    for attempt in range(100):
        time.sleep(5)
        _, plan = ok("GET", f"/lots/{lot_id}/plan")
        state = plan.get("state", "")
        routes_n = len(plan.get("routes") or [])
        print(f"  intento {attempt+1}: state={state} routes={routes_n}")
        if state == "PROCESSED":
            _print_routes(plan, attempt + 1)
            return
    print("  ✗ No se completó después de 100 intentos (~8 min)")


# ── Helpers de mapeo ────────────────────────────────────────────────

_UNIT_MAP = {
    "cm3": "CUBIC_CENTIMETER",
    "m3": "CUBIC_METER",
    "l": "LITER",
    "in3": "CUBIC_INCH",
    "ft3": "CUBIC_FEET",
    "gal": "GALLON",
}

_WEIGHT_UNIT_MAP = {
    "g": "GRAMS",
    "kg": "KILOGRAMS",
    "oz": "OUNCES",
    "lb": "POUNDS",
}

_FUEL_MAP = {
    "GASOLINE": "GASOLINE",
    "DIESEL": "DIESEL",
    "CNG": "CNG",
    "GNC": "CNG",
    "ELECTRIC": "ELECTRIC",
    "HYBRID": "HYBRID",
}


def _volume_unit(wire: str) -> str:
    return _UNIT_MAP.get(wire, "CUBIC_CENTIMETER")


def _weight_unit(wire: str) -> str:
    return _WEIGHT_UNIT_MAP.get(wire, "KILOGRAMS")


def _engine_type(fuel: str) -> str:
    return _FUEL_MAP.get(fuel.upper(), "GASOLINE")


def _fleet_vehicles_for_run(scenario, payload: dict, id_map: dict[str, str]) -> list[dict]:
    if scenario is not None:
        api_fleet = scenario.api_public.get("POST /fleets", {})
        if api_fleet.get("vehicles"):
            return _remap_vehicle_refs(api_fleet["vehicles"], id_map)
    return [
        _fleet_vehicle_from_payload(v, id_map[v["type"]])
        for v in payload.get("vehicles", [])
    ]


def _normalize_vehicle_id_overrides(config: dict, vehicle_ids: dict[str, str]) -> dict:
    """Overrides por catalog id → wire name (v3) para no duplicar types en el wire."""
    vehicles = config.get("vehicles")
    if not isinstance(vehicles, dict):
        return config
    wire_by_catalog = {vid: name for name, vid in vehicle_ids.items()}
    for ov in vehicles.get("overrides") or []:
        if isinstance(ov, dict):
            vid = ov.get("vehicle_id")
            if isinstance(vid, str) and vid in wire_by_catalog:
                ov["vehicle_id"] = wire_by_catalog[vid]
    return config


def _default_start_time_minutes() -> int:
    from libs.plan_engine_defaults import engine_routing_defaults

    routing = engine_routing_defaults()
    return int(routing.get("start_time_minutes_route", 800))


def _schedule_from_payload(payload: dict) -> dict:
    routing = payload.get("routing", {})
    schedule: dict = {}
    if routing.get("optimize_time_windows") is not None:
        schedule["respect_delivery_windows"] = routing["optimize_time_windows"]
    if payload.get("date"):
        start_min = routing.get("start_time_minutes_route", _default_start_time_minutes())
        h, m = divmod(int(start_min), 60)
        schedule["start_at"] = f"{payload['date']}T{h:02d}:{m:02d}:00+00:00"
    return schedule


def _lot_config_for_run(
    payload: dict,
    scenario,
    wire_matrix,
    id_map: dict[str, str],
    vehicle_ids: dict[str, str],
    *,
    config_json: str | None,
    config_patch: str | None,
) -> dict:
    if scenario is not None and wire_matrix is not None:
        lot_public = scenario.api_public.get("POST /lots", {})
        if lot_public.get("config"):
            config = _remap_vehicle_refs(dict(lot_public["config"]), id_map)
        else:
            overlay = _remap_vehicle_refs(
                wire_matrix["_lot_config_dict_for_scenario"](scenario),
                id_map,
            )
            config = overlay if overlay else _build_lot_config(payload)
    else:
        config = _build_lot_config(payload)
    from libs.plan_engine_defaults import strip_engine_keys_from_config

    config = strip_engine_keys_from_config(config) or {}
    if config_json:
        with open(config_json) as f:
            config = _deep_merge(config, json.load(f))
    if config_patch:
        config = _deep_merge(config, json.loads(config_patch))
    config = strip_engine_keys_from_config(config) or {}
    return _normalize_vehicle_id_overrides(config, vehicle_ids)


def _apply_scenario_patches(
    scenario,
    id_map: dict[str, str],
    vehicle_ids: dict[str, str],
    fleet_id: str,
    lot_id: str,
) -> tuple[list[dict] | None, dict | None]:
    """Ejecuta PATCH /fleets y/o PATCH /lots definidos en scenario.api_public."""
    if not scenario:
        return None, None
    api = scenario.api_public
    patched_fleet_vehicles: list[dict] | None = None
    patched_lot_body: dict | None = None

    patch_fleet = api.get("PATCH /fleets/{id}") or api.get("PATCH /fleets")
    if patch_fleet:
        body = _remap_vehicle_refs(dict(patch_fleet), id_map)
        print(f"\n[5b] PATCH /fleets/{fleet_id} (estado DB para el próximo plan)...")
        ok("PATCH", f"/fleets/{fleet_id}", body)
        patched_fleet_vehicles = body.get("vehicles")
        if patched_fleet_vehicles:
            _print_fleet_run_profile(patched_fleet_vehicles, vehicle_ids)

    patch_lot = api.get("PATCH /lots/{id}") or api.get("PATCH /lots")
    if patch_lot:
        body = _remap_vehicle_refs(dict(patch_lot), id_map)
        if isinstance(body.get("config"), dict):
            body["config"] = _normalize_vehicle_id_overrides(body["config"], vehicle_ids)
        print(f"\n[5c] PATCH /lots/{lot_id} (merge en config_data)...")
        ok("PATCH", f"/lots/{lot_id}", body)
        patched_lot_body = body

    return patched_fleet_vehicles, patched_lot_body


def _fleet_vehicle_from_payload(v: dict, vehicle_id: str) -> dict:
    """Fleet row: catalog id + qty + operational profile (stops, distance, priority)."""
    entry: dict = {"id": vehicle_id, "qty": v.get("quantity", 0)}
    route: dict = {}
    if v.get("deliveries_qty"):
        route["stops_min"] = v["deliveries_qty"]["min"]
        route["stops_max"] = v["deliveries_qty"]["max"]
        if v.get("distance_limits"):
            dl = v["distance_limits"]
            route["distance_unit"] = "KILOMETER"
            if dl.get("min_km") is not None:
                route["distance_min"] = int(dl["min_km"])
            if dl.get("max_km") is not None:
                route["distance_max"] = int(dl["max_km"])
    if route:
        entry["route"] = route
    behavior: dict = {}
    if v.get("priority_vehicle") is not None:
        behavior["priority"] = v["priority_vehicle"]
    if v.get("overflow_vehicle") is not None:
        behavior["overflow_vehicle"] = v["overflow_vehicle"]
    if behavior:
        entry["behavior"] = behavior
    return entry


def _build_lot_config(payload: dict) -> dict:
    """Mapea clustering, routing, rebalance y settings del payload a LotConfig."""
    config: dict = {}

    if payload.get("zone"):
        config["zone"] = payload["zone"]

    # ── Rebalance ───────────────────────────────────────────────────
    #
    # Mapeo: cada flag booleano en el JSON del optimizer se convierte
    # en un objeto {enabled: bool, ...params} para LotConfig.
    # Solo los parámetros numéricos de cada dimensión se incluyen
    # en su rama correspondiente.
    #
    src = payload.get("rebalance", {})

    # Parámetros por rama
    _VOLUME_PARAMS = [
        "min_volume_capacity_ratio_vehicle_initial",
        "max_volume_capacity_ratio_vehicle_initial",
        "min_volume_capacity_ratio_vehicle",
        "max_volume_capacity_ratio_vehicle",
    ]
    _WEIGHT_PARAMS = [
        "min_weight_capacity_ratio_vehicle",
        "max_weight_capacity_ratio_vehicle",
    ]
    _TIME_PARAMS = [
        "min_time_minutes_per_route",
        "max_time_minutes_per_route",
    ]
    BRANCH_PARAMS = {
        "rebalance_by_volume": _VOLUME_PARAMS,
        "rebalance_by_size": [],
        "rebalance_by_weight": _WEIGHT_PARAMS,
        "rebalance_by_time": _TIME_PARAMS,
        "rebalance_by_distance": [],
    }

    rebalance = {}
    for flag, param_keys in BRANCH_PARAMS.items():
        val = src.get(flag)
        if val is not None:
            branch = {"enabled": bool(val) if val is not True and val is not False else val}
            for pk in param_keys:
                if pk in src:
                    branch[pk] = src[pk]
            rebalance[flag] = branch

    if rebalance:
        config["rebalance"] = rebalance

    # ── Schedule (date + routing time window flags) ─────────────────
    routing = payload.get("routing", {})
    schedule = {}
    if routing.get("optimize_time_windows") is not None:
        schedule["respect_delivery_windows"] = routing["optimize_time_windows"]
    if routing.get("early_tolerance_min") is not None or routing.get("late_tolerance_min") is not None:
        tw = {}
        if routing.get("early_tolerance_min") is not None:
            tw["early_tolerance_min"] = routing["early_tolerance_min"]
        if routing.get("late_tolerance_min") is not None:
            tw["late_tolerance_min"] = routing["late_tolerance_min"]
        if tw:
            schedule["time_windows"] = tw
    if payload.get("date"):
        start_min = routing.get("start_time_minutes_route", _default_start_time_minutes())
        h, m = divmod(int(start_min), 60)
        schedule["start_at"] = f"{payload['date']}T{h:02d}:{m:02d}:00+00:00"
    if schedule:
        config["schedule"] = schedule

    return config


def _section(title: str) -> None:
    width = 78
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def _catalog_id_to_wire_name(vehicle_ids: dict[str, str]) -> dict[str, str]:
    return {str(vid): name for name, vid in vehicle_ids.items()}


def _print_scenario_trace(scenario) -> None:
    if not scenario or not getattr(scenario, "trace_map", None):
        return
    _section("ESCENARIO  qué input controla el wire (trace map)")
    for row in scenario.trace_map:
        wire = row.get("wire", "?")
        val = row.get("value", "")
        src = row.get("from", "")
        print(f"  wire.{wire} = {val!r}")
        print(f"    ← {src}")
    print(
        "\n  Precedencia por vehículo: "
        "override > defaults > fleet.run_profile > route_limits > fallback (POST /plan)"
    )


def _print_fleet_run_profile(fleet_vehicles: list[dict], vehicle_ids: dict[str, str]) -> None:
    id_to_name = _catalog_id_to_wire_name(vehicle_ids)
    _section("INPUT  POST /fleets  (run_profile — valores base antes del lote)")
    print(
        "  type   qty   stops_min  stops_max   dist_max   pri  overflow"
    )
    print("  " + "─" * 66)
    for fv in fleet_vehicles:
        wire_type = id_to_name.get(str(fv.get("id")), str(fv.get("id")))
        route = fv.get("route") or {}
        beh = fv.get("behavior") or {}
        dist = route.get("distance_max", "—")
        pri = beh.get("priority", "—")
        ov = beh.get("overflow_vehicle", "—")
        print(
            f"  {wire_type:<5}  {fv.get('qty', 0):>3}   "
            f"{route.get('stops_min', '—'):>9}  {route.get('stops_max', '—'):>9}   "
            f"{dist!s:>8}   {pri!s:>3}  {ov!s}"
        )


def _print_lot_config_input(lot_config: dict, lot_body: dict) -> None:
    _section("INPUT  POST /lots  (capas que pueden SOBREESCRIBIR fleet.run_profile)")
    print(
        "  Orden de aplicación: override (por vehicle_id) > defaults (todos) "
        "> fleet > route_limits (global) > fallback"
    )
    rl = lot_body.get("route_limits")
    if rl:
        print(f"\n  route_limits (global): {json.dumps(rl, ensure_ascii=False)}")
    vl = lot_body.get("vehicle_limits")
    if vl:
        print(f"  vehicle_limits: {json.dumps(vl, ensure_ascii=False)}")

    vehicles = lot_config.get("vehicles") or {}
    defaults = vehicles.get("defaults")
    overrides = vehicles.get("overrides") or []
    if defaults:
        print(f"\n  config.vehicles.defaults → aplica a TODOS los types del fleet:")
        print(f"    {json.dumps(defaults, ensure_ascii=False)}")
    if overrides:
        print("\n  config.vehicles.overrides → pisa defaults y fleet para ese type:")
        for ov in overrides:
            print(f"    {json.dumps(ov, ensure_ascii=False)}")
    if not defaults and not overrides and not rl and not vl:
        print("\n  (sin vehicles.defaults/overrides ni route_limits — wire usa fleet tal cual)")


def _lot_overlay_for_type(
    lot_config: dict,
    wire_type: str,
    catalog_id: str,
) -> tuple[str, dict | None]:
    """Texto corto + route dict de la capa lot.config más específica (override > defaults)."""
    vehicles = lot_config.get("vehicles") or {}
    for ov in vehicles.get("overrides") or []:
        vid = ov.get("vehicle_id")
        if vid in (wire_type, catalog_id, str(catalog_id)):
            route = ov.get("route") or {}
            bits = []
            if route.get("stops_min") is not None:
                bits.append(f"stops_min={route['stops_min']}")
            if route.get("stops_max") is not None:
                bits.append(f"stops_max={route['stops_max']}")
            if route.get("distance_max") is not None:
                bits.append(f"dist_max={route['distance_max']}")
            label = f"override: {', '.join(bits) or json.dumps(ov)}"
            return label, route if route else None

    defaults = vehicles.get("defaults") or {}
    dr = defaults.get("route") or {}
    if dr:
        bits = []
        if dr.get("stops_min") is not None:
            bits.append(f"stops_min={dr['stops_min']}")
        if dr.get("stops_max") is not None:
            bits.append(f"stops_max={dr['stops_max']}")
        if dr.get("distance_max") is not None:
            bits.append(f"dist_max={dr['distance_max']}")
        return f"defaults: {', '.join(bits)}", dr
    return "—", None


def _resolve_stops_source(
    *,
    wire_type: str,
    catalog_id: str,
    fleet_route: dict,
    lot_config: dict,
    lot_body: dict,
    wire_stops_max,
    wire_stops_min,
    field: str,
) -> str:
    """Identifica qué capa ganó para stops_min o stops_max."""
    wire_val = wire_stops_max if field == "max" else wire_stops_min
    if wire_val is None:
        return "—"

    vehicles = lot_config.get("vehicles") or {}
    for ov in vehicles.get("overrides") or []:
        vid = ov.get("vehicle_id")
        if vid not in (wire_type, catalog_id, str(catalog_id)):
            continue
        key = f"stops_{field}"
        val = (ov.get("route") or {}).get(key)
        if val is not None and val == wire_val:
            return "override"

    dr = (vehicles.get("defaults") or {}).get("route") or {}
    key = f"stops_{field}"
    if dr.get(key) is not None and dr.get(key) == wire_val:
        return "defaults"

    rl = lot_body.get("route_limits") or {}
    rl_key = f"stops_{field}"
    if rl.get(rl_key) is not None and rl.get(rl_key) == wire_val:
        return "route_limits"

    fleet_key = f"stops_{field}"
    if fleet_route.get(fleet_key) is not None and fleet_route.get(fleet_key) == wire_val:
        return "fleet"

    return "fallback"


def _print_precedence_table(
    wire: dict,
    fleet_vehicles: list[dict],
    lot_config: dict,
    lot_body: dict,
    vehicle_ids: dict[str, str],
) -> None:
    id_to_name = _catalog_id_to_wire_name(vehicle_ids)
    fleet_by_type = {
        id_to_name.get(str(fv["id"]), str(fv["id"])): fv for fv in fleet_vehicles
    }
    _section("OUTPUT  fleet → lot.config → wire  (qué se sobreescribe)")
    print(
        "  type │ fleet.stops        │ lot.config (capa)              │ "
        "wire.deliveries_qty │ origen max"
    )
    print("  " + "─" * 74)
    for wv in sorted(wire.get("vehicles") or [], key=lambda v: v.get("type", "")):
        wire_type = wv.get("type", "?")
        fv = fleet_by_type.get(wire_type, {})
        fleet_route = fv.get("route") or {}
        catalog_id = vehicle_ids.get(wire_type, "")
        fleet_stops = (
            f"{fleet_route.get('stops_min', '—')}-{fleet_route.get('stops_max', '—')}"
        )
        overlay_label, _ = _lot_overlay_for_type(lot_config, wire_type, catalog_id)
        dq = wv.get("deliveries_qty") or {}
        wire_stops = f"{dq.get('min', '—')}-{dq.get('max', '—')}"
        src_max = _resolve_stops_source(
            wire_type=wire_type,
            catalog_id=catalog_id,
            fleet_route=fleet_route,
            lot_config=lot_config,
            lot_body=lot_body,
            wire_stops_max=dq.get("max"),
            wire_stops_min=dq.get("min"),
            field="max",
        )
        changed = (
            dq.get("max") is not None
            and fleet_route.get("stops_max") is not None
            and dq.get("max") != fleet_route.get("stops_max")
        )
        marker = " ⚡" if changed else ""
        print(
            f"  {wire_type:<4} │ {fleet_stops:<18} │ {overlay_label:<30} │ "
            f"{wire_stops:<19} │ {src_max}{marker}"
        )
    print("\n  ⚡ = wire distinto al fleet.run_profile (sobreescrito por lot.config u otra capa)")


def _resolve_lot_delivery_count(lot_get: dict | None, *, fallback: int | None = None) -> int | None:
    if not lot_get:
        return fallback
    from libs.plan_build import lot_delivery_count

    count = lot_delivery_count(lot_get, fallback=0)
    return count if count > 0 else fallback


def _print_wire_validation(
    scenario,
    wire: dict,
    wire_matrix: dict | None,
    lot_get: dict | None = None,
    *,
    delivery_count: int | None = None,
) -> None:
    if not scenario or not wire_matrix:
        return
    validate_wire = wire_matrix.get("validate_wire")
    if not validate_wire:
        return
    fallback_stops = None
    lot_config = None
    resolved_count = delivery_count if delivery_count is not None else _resolve_lot_delivery_count(lot_get)
    if lot_get:
        from libs.plan_build import compute_fallback_stops, lot_db_stub_from_api
        from models.lot_config import LotConfig

        fleet = lot_get.get("fleet") or {}
        v_sum = sum(int(v.get("qty", 0)) for v in fleet.get("vehicles") or [])
        if resolved_count and resolved_count > 0 and v_sum > 0:
            lot_db = lot_db_stub_from_api(lot_get)
            fallback_stops = compute_fallback_stops(resolved_count, v_sum, lot_db)
        if lot_get.get("config"):
            lot_config = LotConfig.model_validate(lot_get["config"])
    results = validate_wire(
        scenario,
        wire,
        fallback_stops=fallback_stops,
        delivery_count=resolved_count,
        lot_config=lot_config,
    )
    passed = failed = skipped = 0
    mode = (
        "full"
        if scenario.name in (wire_matrix.get("FULL_WIRE_VALIDATE_SCENARIOS") or frozenset())
        else "focus"
    )
    mode_label = "wire completo" if mode == "full" else "foco escenario (trace map + API)"
    _section(f"VALIDACIÓN  {mode_label}")
    for r in results:
        if r.skipped:
            skipped += 1
            print(f"  ○ SKIP  {r.label}")
            continue
        if r.ok:
            passed += 1
            print(f"  ✓ PASS  {r.label}")
        else:
            failed += 1
            detail = ""
            if r.expected is not None:
                detail = f"  (esperaba {r.expected!r}, obtuvo {r.actual!r})"
            print(f"  ✗ FAIL  {r.label}{detail}")
    summary = f"  → {passed} passed"
    if failed:
        summary += f", {failed} failed"
    if skipped:
        summary += f", {skipped} skipped"
    print(summary)


def _compact_wire_for_display(wire: dict, preview_rows: int, total_deliveries: int) -> dict:
    """Vehículos + tuning del optimizer; sin volcar miles de addresses."""
    keys = (
        "date",
        "time_slot",
        "origin_lat",
        "origin_lng",
        "tag",
        "zone",
        "clustering",
        "routing",
        "rebalance",
        "settings",
    )
    out = {k: wire[k] for k in keys if k in wire}
    out["vehicles"] = wire.get("vehicles")
    out["_addresses_note"] = (
        f"POST /plan enviaría {total_deliveries} direcciones "
        f"(preview armado con {preview_rows} filas)"
    )
    return out


def show_optimizer_wire_from_lot(
    lot_get: dict,
    delivery_rows: list[tuple[int, str, dict | None]],
    show_n: int,
    *,
    scenario=None,
    fleet_vehicles: list[dict] | None = None,
    lot_config: dict | None = None,
    lot_body: dict | None = None,
    vehicle_ids: dict[str, str] | None = None,
    wire_matrix: dict | None = None,
) -> None:
    """Wire JSON idéntico al pipeline de POST /lots/{id}/plan (estado persistido en API)."""
    from libs.plan_build import build_plan_context_from_lot_api
    from libs.plan_wire import plan_to_wire_payload

    rows = delivery_rows[:show_n] if show_n > 0 else delivery_rows
    plan = build_plan_context_from_lot_api(lot_get, rows)
    wire = plan_to_wire_payload(plan)
    total = _resolve_lot_delivery_count(lot_get, fallback=len(delivery_rows)) or len(delivery_rows)
    preview_rows = len(rows)

    if fleet_vehicles and lot_config is not None and lot_body is not None and vehicle_ids:
        _print_precedence_table(wire, fleet_vehicles, lot_config, lot_body, vehicle_ids)
    _print_wire_validation(
        scenario,
        wire,
        wire_matrix,
        lot_get=lot_get,
        delivery_count=total,
    )

    _section(
        f"WIRE al optimizer (clustering/routing con {total} entregas; "
        f"addresses preview {preview_rows})"
    )
    print(json.dumps(_compact_wire_for_display(wire, preview_rows, total), indent=2, default=str))
    print(
        "\n  Pipeline: GET /lots/{id} → build_plan_context_for_lot "
        "(mismo código que POST /lots/{id}/plan)"
    )


def _print_routes(plan: dict, attempt: int | None = None):
    if attempt:
        print(f"  → COMPLETED (intento {attempt})")
    routes = plan.get("routes", [])
    print(f"  rutas: {len(routes)}")
    for r in routes[:5]:
        print(f"    route id={r.get('id')} deliveries={len(r.get('deliveries', []))}")
    if len(routes) > 5:
        print(f"    ... y {len(routes)-5} más")


def show_optimizer_payload(original: dict, lot_config: dict, show_n: int = 5) -> None:
    """Preview offline (explore matrix / sin HTTP). Preferir show_optimizer_wire_from_lot en E2E."""
    from libs.lot_plan_adapter import (
        build_plan_clustering,
        build_plan_rebalance,
        build_plan_routing,
        build_plan_settings,
    )
    from libs.plan_engine_defaults import resolve_engine_config
    from libs.optimizer.models.plan_context import PlanContext
    from libs.optimizer.models.plan_vehicle import (
        DeliveriesQuantity,
        DistanceLimits,
        MeasuredQuantity,
        PlanVehicle,
        VehicleConsumption,
    )
    from libs.package_wire import wire_address_from_source
    from libs.plan_wire import plan_to_wire_payload
    from models.lot_config import LotConfig

    lc = LotConfig.model_validate(lot_config)
    vehicles = []
    for v in original.get("vehicles", []):
        kwargs: dict = {"type": v["type"], "quantity": v.get("quantity", 0)}
        if v.get("priority_vehicle") is not None:
            kwargs["priority_vehicle"] = v["priority_vehicle"]
        if v.get("overflow_vehicle") is not None:
            kwargs["overflow_vehicle"] = v["overflow_vehicle"]
        if v.get("deliveries_qty"):
            kwargs["deliveries_qty"] = DeliveriesQuantity(**v["deliveries_qty"])
        if v.get("max_volume"):
            kwargs["max_volume"] = MeasuredQuantity(**v["max_volume"])
        if v.get("max_weight"):
            kwargs["max_weight"] = MeasuredQuantity(**v["max_weight"])
        if v.get("distance_limits"):
            kwargs["distance_limits"] = DistanceLimits(**v["distance_limits"])
        if v.get("consumption"):
            kwargs["consumption"] = VehicleConsumption(**v["consumption"])
        vehicles.append(PlanVehicle(**kwargs))

    engine = resolve_engine_config()
    clustering = build_plan_clustering(
        engine_clustering=engine["clustering"],
        a_sum=len(original.get("addresses", [])),
        v_sum=sum(v.get("quantity", 0) for v in original.get("vehicles", [])),
    )
    routing = build_plan_routing(lc, engine_routing=engine["routing"])
    rebalance = build_plan_rebalance(lc)
    settings = build_plan_settings(
        engine_settings=engine["settings"],
        max_size_cluster=clustering.max_size_cluster,
    )
    src_addrs = original.get("addresses", [])[:show_n]
    addresses = [wire_address_from_source(a) for a in src_addrs]
    plan = PlanContext(
        date=original.get("date", ""),
        origin_lat=original["origin_lat"],
        origin_lng=original["origin_lng"],
        zone=original.get("zone", "MULTI"),
        tag=original.get("tag", ""),
        vehicles=vehicles,
        clustering=clustering,
        routing=routing,
        rebalance=rebalance,
        settings=settings,
        addresses=addresses,
    )
    print(json.dumps(plan_to_wire_payload(plan), indent=2, default=str))


if __name__ == "__main__":
    main()
