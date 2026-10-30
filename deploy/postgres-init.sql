\set ON_ERROR_STOP on
-- The fixed file path is read locally by psql; no password appears in argv.
\set app_password `cat /run/secrets/postgres_app_password`
CREATE ROLE cv_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER DATABASE cv_shortlisted OWNER TO cv_app;
