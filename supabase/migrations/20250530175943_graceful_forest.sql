-- Create province code column in zones table if it doesn't exist
ALTER TABLE IF EXISTS zones 
ADD COLUMN IF NOT EXISTS prov_acr TEXT;

-- Create function to get zone multipliers with province codes
CREATE OR REPLACE FUNCTION get_zone_multipliers_with_codes()
RETURNS TABLE (
    zone_id UUID,
    multiplier NUMERIC,
    prov_acr TEXT
) 
LANGUAGE SQL
AS $$
    SELECT 
        zm.zone_id,
        zm.multiplier,
        z.prov_acr
    FROM 
        zone_multipliers zm
    LEFT JOIN 
        zones z ON zm.zone_id = z.id;
$$;

-- Add required columns to fixed_routes table if they don't exist
ALTER TABLE IF EXISTS fixed_routes
ADD COLUMN IF NOT EXISTS pickup_area JSONB;

ALTER TABLE IF EXISTS fixed_routes
ADD COLUMN IF NOT EXISTS dropoff_area JSONB;

ALTER TABLE IF EXISTS fixed_routes
ADD COLUMN IF NOT EXISTS bidirectional BOOLEAN DEFAULT true;

-- Function to execute SQL (this should be created by the database admin)
-- CREATE OR REPLACE FUNCTION exec_sql(sql text) RETURNS VOID AS $$
-- BEGIN
--   EXECUTE sql;
-- END;
-- $$ LANGUAGE plpgsql SECURITY DEFINER;

-- Example indexes for better performance
CREATE INDEX IF NOT EXISTS zones_prov_acr_idx ON zones(prov_acr);
CREATE INDEX IF NOT EXISTS vehicle_base_prices_vehicle_type_idx ON vehicle_base_prices(vehicle_type);
CREATE INDEX IF NOT EXISTS fixed_routes_vehicle_type_idx ON fixed_routes(vehicle_type);