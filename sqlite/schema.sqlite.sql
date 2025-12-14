CREATE TABLE IF NOT EXISTS tenant (
  id INTEGER PRIMARY KEY,
  alias TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS tenant_user (
  id INTEGER PRIMARY KEY,
  tenant_id INTEGER NOT NULL,
  alias TEXT NOT NULL,
  FOREIGN KEY(tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS company (
  id INTEGER PRIMARY KEY,
  tenant_id INTEGER NOT NULL,
  alias TEXT NOT NULL,
  FOREIGN KEY(tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS company_user (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  alias TEXT NOT NULL,
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS vehicle (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  volume INTEGER,
  volume_unit TEXT CHECK( volume_unit IN ( 'CUBIC_CENTIMETER', 'CUBIC_METER', 'LITER', 'CUBIC_INCH', 'CUBIC_FEET', 'GALLON' ) ),
  consumption INTEGER,
  consumption_unit TEXT CHECK( consumption_unit IN ( 'LITERS_PER_100KM', 'KILOMETERS_PER_LITER', 'MILES_PER_GALLON', 'GALLONS_PER_MILE' ) ),
  category_type TEXT CHECK( category_type IN ( 'TRUCK', 'VAN', 'PICKUP', 'MOTORCYCLE', 'BICYCLE' ) ),
  engine_type TEXT CHECK( engine_type IN ( 'GASOLINE', 'DIESEL', 'CNG', 'ELECTRIC', 'HYBRID', 'MECHANIC' ) ),
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS fleet (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS fleet_vehicle (
  fleet_id INTEGER,
  vehicle_id INTEGER,
  quantity INTEGER NOT NULL,
  FOREIGN KEY(fleet_id) REFERENCES fleet(id) ON DELETE CASCADE,
  FOREIGN KEY(vehicle_id) REFERENCES vehicle(id) ON DELETE CASCADE
  PRIMARY KEY (fleet_id, vehicle_id)
);
CREATE TABLE IF NOT EXISTS driver (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT,
  work_schedules TEXT,
  start_point TEXT,
  end_point TEXT,
  work_areas TEXT,
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS driver_vehicle (
  driver_id INTEGER,
  vehicle_id INTEGER,
  quantity INTEGER NOT NULL,
  FOREIGN KEY(driver_id) REFERENCES driver(id) ON DELETE CASCADE,
  FOREIGN KEY(vehicle_id) REFERENCES vehicle(id) ON DELETE CASCADE
  PRIMARY KEY (driver_id, vehicle_id)
);
CREATE TABLE IF NOT EXISTS milestone (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  location TEXT NOT NULL,
  category TEXT CHECK( category IN ( 'DEPOT', 'DISTRIBUTION_CENTER', 'LOADING_POINT', 'WAREHOUSE', 'TRANSFER_POINT' ) ),
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS delivery (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  method TEXT CHECK( method IN ( 'DELIVERY', 'PICKUP', 'SIGNATURE' ) ),
  milestone_id INTEGER,
  destination TEXT,
  schedules TEXT,
  width INTEGER,
  height INTEGER,
  depth INTEGER,
  length_unit TEXT CHECK( length_unit IN ( 'CENTIMETER', 'METER', 'KILOMETER', 'INCH', 'FEET', 'MILE' ) ),
  volume INTEGER,
  volume_unit TEXT CHECK( volume_unit IN ( 'CUBIC_CENTIMETER', 'CUBIC_METER', 'LITER', 'CUBIC_INCH', 'CUBIC_FEET', 'GALLON' ) ),
  weight INTEGER,
  weight_unit TEXT CHECK( weight_unit IN ( 'GRAMS', 'KILOGRAMS', 'OUNCES', 'POUNDS' ) ),
  packaging TEXT CHECK( packaging IN ( 'BOX', 'ENVELOPE', 'BAG', 'CARTON', 'PALLET', 'SHRINK_WRAP' ) ),
  handling TEXT, /* CHECK( handling IN ( 'FRAGILE', 'PERISHABLE', 'HAZARDOUS', 'REFRIGERATED' ) ),*/
  value_cents INTEGER,
  value_currency TEXT,
  extra TEXT,
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE,
  FOREIGN KEY(milestone_id) REFERENCES milestone(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS delivery_lot (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL,
  milestone_id INTEGER,
  fleet_id INTEGER,
  state TEXT CHECK( state IN ( 'UNPROCESSED', 'PROCESSING', 'OPTIMIZING', 'PROCESSED', 'CANCELED' ) ) NOT NULL,
  vehicle_volume_min INTEGER,
  vehicle_volume_max INTEGER,
  vehicle_capacity_min INTEGER,
  vehicle_capacity_max INTEGER,
  route_stops_min INTEGER,
  route_stops_max INTEGER,
  route_length_min INTEGER,
  route_length_max INTEGER,
  route_length_unit TEXT CHECK( route_length_unit IN ( 'CENTIMETER', 'METER', 'KILOMETER', 'INCH', 'FEET', 'MILE' ) ),
  route_time_min INTEGER,
  route_time_max INTEGER,
  route_time_unit TEXT CHECK( route_time_unit IN ( 'SECOND', 'MINUTE', 'HOUR' ) ),
  FOREIGN KEY(company_id) REFERENCES company(id) ON DELETE CASCADE,
  FOREIGN KEY(milestone_id) REFERENCES milestone(id) ON DELETE SET NULL,
  FOREIGN KEY(fleet_id) REFERENCES fleet(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS delivery_lot_delivery (
  delivery_lot_id INTEGER,
  delivery_id INTEGER,
  FOREIGN KEY(delivery_lot_id) REFERENCES delivery_lot(id) ON DELETE CASCADE,
  FOREIGN KEY(delivery_id) REFERENCES delivery(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS delivery_lot_driver (
  delivery_lot_id INTEGER,
  driver_id INTEGER,
  FOREIGN KEY(delivery_lot_id) REFERENCES delivery_lot(id) ON DELETE CASCADE,
  FOREIGN KEY(driver_id) REFERENCES driver(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS delivery_plan (
  id INTEGER PRIMARY KEY,
  delivery_lot_id INTEGER NOT NULL,
  optimizer_id TEXT NOT NULL,
  FOREIGN KEY(delivery_lot_id) REFERENCES delivery_lot(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS delivery_path (
  id INTEGER PRIMARY KEY,
  delivery_plan_id INTEGER NOT NULL,
  milestone_id INTEGER NOT NULL,
  vehicle_id INTEGER,
  driver_id INTEGER,
  FOREIGN KEY(delivery_plan_id) REFERENCES delivery_plan(id) ON DELETE CASCADE,
  FOREIGN KEY(milestone_id) REFERENCES milestone(id) ON DELETE CASCADE,
  FOREIGN KEY(vehicle_id) REFERENCES vehicle(id) ON DELETE SET NULL,
  FOREIGN KEY(driver_id) REFERENCES driver(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS delivery_path_delivery (
  delivery_path_id INTEGER,
  delivery_id INTEGER,
  delivery_order INTEGER NOT NULL,
  FOREIGN KEY(delivery_path_id) REFERENCES delivery_path(id) ON DELETE CASCADE,
  FOREIGN KEY(delivery_id) REFERENCES delivery(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__tenant_user______tid_ualias ON tenant_user (tenant_id, alias);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__company__________tid_calias ON company (tenant_id, alias);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__company_user_____cid_ualias ON company_user (company_id, alias);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__fleet_vehicle_______fid_vid ON fleet_vehicle (fleet_id, vehicle_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__driver_vehicle______did_vid ON driver_vehicle (driver_id, vehicle_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__lot_delivery________lid_did ON delivery_lot_delivery (delivery_lot_id, delivery_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__lot_driver__________lid_did ON delivery_lot_driver (delivery_lot_id, driver_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__path_delivery_______pid_did ON delivery_path_delivery (delivery_path_id, delivery_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx__path_delivery_____pid_order ON delivery_path_delivery (delivery_path_id, delivery_order);
