#!/bin/bash
set -e

DUMPS_DIR="/dumps"
DB_NAME="${MYSQL_DATABASE:-perseus}"
TMP_DIR="/tmp/perseus_import"

# MariaDB 11 dropped the `mysql` symlink; fall back to it for older images.
MYSQL_BIN=$(command -v mariadb || command -v mysql)
if [ -z "$MYSQL_BIN" ]; then
    echo "ERROR: neither 'mariadb' nor 'mysql' client found" >&2
    exit 1
fi

mkdir -p "$TMP_DIR"

echo "=== Perseus Database Loader ==="
echo "Database: $DB_NAME"
echo "Dumps dir: $DUMPS_DIR"
echo "Client:    $MYSQL_BIN"
echo ""

imported=0
skipped=0
failed=0

for archive in "$DUMPS_DIR"/*.tar.gz; do
    [ -f "$archive" ] || continue

    name=$(basename "$archive" .tar.gz)

    # Extract SQL file from archive. -a auto-detects compression, so archives
    # that were served uncompressed despite the .tar.gz name still work.
    rm -rf "${TMP_DIR:?}"/*
    if ! tar xaf "$archive" -C "$TMP_DIR" 2>/dev/null; then
        echo "SKIP: $name (corrupt or truncated archive)"
        skipped=$((skipped + 1))
        continue
    fi

    # Find the .sql file
    sql_file=$(find "$TMP_DIR" -name "*.sql" -type f | head -1)
    if [ -z "$sql_file" ]; then
        echo "SKIP: $name (no .sql file found in archive)"
        skipped=$((skipped + 1))
        continue
    fi

    # Check if the SQL file looks valid (has CREATE TABLE or INSERT)
    if ! grep -q -E "(CREATE TABLE|INSERT INTO)" "$sql_file" 2>/dev/null; then
        echo "SKIP: $name (SQL file appears invalid or empty)"
        skipped=$((skipped + 1))
        continue
    fi

    # Import into MariaDB. Errors are left on stderr so they show up in
    # `docker compose logs` instead of vanishing.
    echo -n "IMPORT: $name ... "
    if "$MYSQL_BIN" -u root -p"$MYSQL_ROOT_PASSWORD" "$DB_NAME" < "$sql_file"; then
        echo "OK"
        imported=$((imported + 1))
    else
        echo "FAILED"
        failed=$((failed + 1))
    fi
done

rm -rf "$TMP_DIR"

echo ""
echo "=== Import Summary ==="
echo "Imported: $imported"
echo "Skipped:  $skipped"
echo "Failed:   $failed"
echo "======================="

if [ "$failed" -gt 0 ] || [ "$skipped" -gt 0 ]; then
    echo "ERROR: $failed table(s) failed, $skipped skipped" >&2
    exit 1
fi
