-- Vehicle clock on the catalog (models/vehicle.py): the type's own average speed (km/h) and minutes per stop,
-- inherited by every plan that uses the vehicle unless the plan's vehicle override says otherwise.
-- Idempotent: safe to run again.
ALTER TABLE vehicle ADD COLUMN IF NOT EXISTS avg_speed_kph DOUBLE PRECISION;
ALTER TABLE vehicle ADD COLUMN IF NOT EXISTS service_time_min DOUBLE PRECISION;
