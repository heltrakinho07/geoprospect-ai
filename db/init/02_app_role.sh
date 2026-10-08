# /usr/bin/env bash
set -euo pipefail
: "${APP_DB_PASSWORD:?Required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE gp_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE gpdb TO gp_app;
GRANT USAGE, CREATE ON SCHEMA public TO gp_app;
SQL
