-- Drop unused KTC devy boolean columns.
-- These fields are never surfaced in the dashboard UI or trade analyzer.
ALTER TABLE players DROP COLUMN IF EXISTS "isDevyReturningToSchool";
ALTER TABLE players DROP COLUMN IF EXISTS "isDevyYearDecrement";
