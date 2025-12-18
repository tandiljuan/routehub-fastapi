import enum

class LengthUnit(str, enum.Enum):
    CENTIMETER = "CENTIMETER"
    METER = "METER"
    KILOMETER = "KILOMETER"
    INCH = "INCH"
    FEET = "FEET"
    MILE = "MILE"

class VolumeUnit(str, enum.Enum):
    CUBIC_CENTIMETER = "CUBIC_CENTIMETER"
    CUBIC_METER = "CUBIC_METER"
    LITER = "LITER"
    CUBIC_INCH = "CUBIC_INCH"
    CUBIC_FEET = "CUBIC_FEET"
    GALLON = "GALLON"

class WeightUnit(str, enum.Enum):
    GRAMS = "GRAMS"
    KILOGRAMS = "KILOGRAMS"
    OUNCES = "OUNCES"
    POUNDS = "POUNDS"

class TimeUnit(str, enum.Enum):
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"

class VehicleConsumptionUnit(str, enum.Enum):
    LITERS_PER_100KM = "LITERS_PER_100KM"
    KILOMETERS_PER_LITER = "KILOMETERS_PER_LITER"
    MILES_PER_GALLON = "MILES_PER_GALLON"
    GALLONS_PER_MILE = "GALLONS_PER_MILE"

class VehicleCategoryType(str, enum.Enum):
    TRUCK = "TRUCK"
    VAN = "VAN"
    PICKUP = "PICKUP"
    MOTORCYCLE = "MOTORCYCLE"
    BICYCLE = "BICYCLE"

class VehicleEngineType(str, enum.Enum):
    GASOLINE = "GASOLINE"
    DIESEL = "DIESEL"
    CNG = "CNG"
    ELECTRIC = "ELECTRIC"
    HYBRID = "HYBRID"
    MECHANIC = "MECHANIC"

class MilestoneCategory(str, enum.Enum):
    DEPOT = "DEPOT"
    DISTRIBUTION_CENTER = "DISTRIBUTION_CENTER"
    LOADING_POINT = "LOADING_POINT"
    WAREHOUSE = "WAREHOUSE"
    TRANSFER_POINT = "TRANSFER_POINT"

class DeliveryMethod(str, enum.Enum):
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"
    SIGNATURE = "SIGNATURE"

class PackagingType(str, enum.Enum):
    BOX = "BOX"
    ENVELOPE = "ENVELOPE"
    BAG = "BAG"
    CARTON = "CARTON"
    PALLET = "PALLET"
    SHRINK_WRAP = "SHRINK_WRAP"

class SpecialHandling(str, enum.Enum):
    FRAGILE = "FRAGILE"
    PERISHABLE = "PERISHABLE"
    HAZARDOUS = "HAZARDOUS"
    REFRIGERATED = "REFRIGERATED"

class DeliveryLotState(str, enum.Enum):
    UNPROCESSED = "UNPROCESSED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    CANCELED = "CANCELED"
