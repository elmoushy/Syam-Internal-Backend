-- ============================================================================
-- Oracle SQL Script: Remove Activities App Tables
-- ============================================================================
-- Run this script on the Oracle database to drop all activities tables
-- and remove migration records before deploying the updated code.
--
-- Usage: Connect to Oracle and run this script
--   sqlplus demouser/Demouser112233$@185.197.251.203:1521/prod @remove_activities_oracle.sql
--
-- Or run statements individually in your Oracle client.
-- ============================================================================

-- Step 1: Drop tables (order matters due to foreign keys)
-- Drop child tables first, then parent tables

-- ActivityRowAttachment depends on ActivitySheetRow
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYROWATTACHMENT CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF; -- Ignore "table does not exist"
END;
/

-- ActivitySheetRow depends on ActivitySheet
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYSHEETROW CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- ActivitySheet depends on ActivityTemplate
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYSHEET CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- ActivityTemplateColumn depends on ActivityTemplate and ActivityColumnDefinition
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYTEMPLATECOLUMN CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- ActivityColumnValidation depends on ActivityColumnDefinition
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYCOLUMNVALIDATION CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- ActivityTemplate (parent)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYTEMPLATE CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- ActivityColumnDefinition (parent)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_ACTIVITYCOLUMNDEFINITION CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- Department (parent)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ACTIVITIES_DEPARTMENT CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN
    IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- Step 2: Remove migration records from django_migrations
DELETE FROM DJANGO_MIGRATIONS WHERE app = 'activities';
COMMIT;

-- Step 3: Verify cleanup
SELECT COUNT(*) AS remaining_migrations FROM DJANGO_MIGRATIONS WHERE app = 'activities';

-- Check no tables remain
SELECT table_name FROM user_tables WHERE table_name LIKE 'ACTIVITIES_%';

PROMPT Activities app completely removed from Oracle database.
