#!/usr/bin/env python3
import json

with open('openapi_bc.json') as f:
    spec = json.load(f)

schemas = spec['components']['schemas']

# 1. route_metrics
schemas['route_metrics'] = {
    "description": "Per-route metrics from the optimizer",
    "type": "object",
    "properties": {
        "route_id": {"type": "string"},
        "route_index": {"type": "integer"},
        "total_distance_km": {"type": "number"},
        "total_duration_sec": {"type": "number"},
        "total_packages": {"type": "integer"},
        "load_percentage": {"type": "number"},
        "route_volume_cm3": {"type": "number"},
        "executor_capacity_cm3": {"type": "number"},
        "avg_speed_kmh": {"type": "number"},
        "stops_per_hour": {"type": "number"},
        "duration_formatted": {"type": "string"},
        "duration_hours": {"type": "number"},
        "duration_minutes": {"type": "number"},
        "route_geometry": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "number"}}
        },
        "tw_stats": {"type": "object"}
    }
}

# 2. fleet_metrics
schemas['fleet_metrics'] = {
    "description": "Fleet efficiency metrics",
    "type": "object",
    "properties": {
        "fleet_size": {"type": "integer"},
        "fleet_capacity_total_cm3": {"type": "number"},
        "fleet_volume_used_cm3": {"type": "number"},
        "fleet_efficiency_percentage": {"type": "number"},
        "fleet_usage_percentage": {"type": "number"},
        "routes_count": {"type": "integer"}
    }
}

# 3. tw_global_metrics
schemas['tw_global_metrics'] = {
    "description": "Global time window violations metrics",
    "type": "object",
    "properties": {
        "total_tw": {"type": "integer"},
        "inserted_ok": {"type": "integer"},
        "violations": {"type": "integer"},
        "fallback_violations": {"type": "integer"},
        "total_tw_packages": {"type": "integer"},
        "violation_percentage": {"type": "number"},
        "status": {"type": "string"}
    }
}

# 4. delivery_plan_totals
schemas['delivery_plan_totals'] = {
    "description": "Delivery plan totals from the optimizer",
    "type": "object",
    "properties": {
        "total_routes": {"type": "integer"},
        "total_points": {"type": "integer"},
        "total_distance_km": {"type": "number"},
        "total_duration_sec": {"type": "number"},
        "execution_time_sec": {"type": "number"},
        "fleet_metrics": {"$ref": "#/components/schemas/fleet_metrics"},
        "time_windows_global": {"$ref": "#/components/schemas/tw_global_metrics"}
    }
}

# 5. Update delivery_route_response_only
route_props = schemas['delivery_route_response_only']['properties']
for field in ['route_id','route_index','total_distance_km','total_duration_sec',
              'total_packages','load_percentage','route_volume_cm3',
              'executor_capacity_cm3','avg_speed_kmh','stops_per_hour',
              'duration_formatted','duration_hours','duration_minutes',
              'route_geometry','tw_stats']:
    route_props[field] = schemas['route_metrics']['properties'][field]

# 6. Update delivery_plan_response_only
schemas['delivery_plan_response_only']['properties']['totals'] = {
    "$ref": "#/components/schemas/delivery_plan_totals"
}

with open('openapi_bc.json', 'w') as f:
    json.dump(spec, f, indent=2)
    f.write('\n')

print("Done. New schemas:", [k for k in schemas if k in ('route_metrics','fleet_metrics','tw_global_metrics','delivery_plan_totals')])
