#!/bin/bash
# build-seed.sh — Runs inside Docker build to generate a seeded Postgres dump.
# Called from the Dockerfile seeder stage.
set -euo pipefail

PG_CTL=/usr/lib/postgresql/15/bin/pg_ctl
PSQL=/usr/lib/postgresql/15/bin/psql

api_status() {
    curl --max-time 10 -s -o /dev/null -w "%{http_code}" \
        -H "Content-Type: application/json" \
        -d '{"email":"admin@admin.com","password":"1234"}' \
        http://127.0.0.1:5003/api/v1/auth/login 2>/dev/null || true
}

echo "==> Starting Postgres..."
if ! runuser -u postgres -- "$PG_CTL" -D "$PGDATA" -o "-c listen_addresses=127.0.0.1" \
    -l /tmp/pg-seed.log start; then
    echo "ERROR: Postgres failed to start. Logs:"
    cat /tmp/pg-seed.log || true
    exit 1
fi
sleep 2

echo "==> Creating user and database..."
runuser -u postgres -- "$PSQL" -c "CREATE USER peppermint WITH PASSWORD 'peppermint';"
runuser -u postgres -- "$PSQL" -c "CREATE DATABASE peppermint OWNER peppermint;"
runuser -u postgres -- "$PSQL" -c "GRANT ALL PRIVILEGES ON DATABASE peppermint TO peppermint;"

echo "==> Starting Peppermint API (Prisma will run migrations)..."
export DB_USERNAME=peppermint
export DB_PASSWORD=peppermint
export DB_HOST=127.0.0.1
export DATABASE_URL="postgresql://peppermint:peppermint@127.0.0.1:5432/peppermint"
export SECRET=seed-secret-webarena-peppermint
export NODE_ENV=production

# Prisma expects to run from /apps/api where prisma/schema.prisma lives.
(
    cd /apps/api
    node dist/main.js
) >> /tmp/peppermint-api.log 2>&1 &
API_PID=$!

echo "==> Waiting for API to be ready..."
for i in $(seq 1 60); do
    STATUS=$(api_status)
    if [ -n "$STATUS" ] && [ "$STATUS" != "000" ] && [ "$STATUS" -lt 500 ] 2>/dev/null; then
        echo "  API is up (${i}x5s elapsed)."
        break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "ERROR: Peppermint API process died. Logs:"
        tail -50 /tmp/peppermint-api.log || true
        exit 1
    fi
    echo "  Still waiting... (${i}/60)"
    sleep 5
done

STATUS=$(api_status)
if [ -z "$STATUS" ] || [ "$STATUS" = "000" ] || [ "$STATUS" -ge 500 ] 2>/dev/null; then
    echo "ERROR: API not ready after 300s. Logs:"
    tail -50 /tmp/peppermint-api.log || true
    exit 1
fi

echo "==> Running seeder..."
if ! PEPPERMINT_URL=http://127.0.0.1:5003 \
ADMIN_EMAIL=admin@admin.com \
ADMIN_PASSWORD=1234 \
SEED_DATA_FILE=/tmp/seed_data.json \
SEED_EXPANSION_FILES=/tmp/glpi_tickets.json \
node /tmp/seed_peppermint.js; then
    echo "ERROR: Seeder failed. Peppermint API logs:"
    tail -100 /tmp/peppermint-api.log || true
    exit 1
fi

echo "==> Marking all users past first login (prevents onboarding redirect)..."
runuser -u postgres -- "$PSQL" -d peppermint -c 'UPDATE "User" SET "firstLogin" = false;'

echo "==> Adjusting ticket dates (older incidents + shuffled timeline)..."
runuser -u postgres -- "$PSQL" -d peppermint <<'SQL'
WITH randomized AS (
    SELECT
        id,
        type,
        row_number() OVER (ORDER BY random()) AS rn
    FROM "Ticket"
), new_times AS (
    SELECT
        id,
        CASE
            -- Incidents are intentionally older for realistic historical incident context.
            WHEN type = 'incident' THEN
                now() - interval '120 days' - ((rn % 240) * interval '1 day')
            -- Other tickets span recent weeks/months to produce a shuffled queue.
            ELSE
                now() - ((rn % 90) * interval '1 day') - (((rn * 13) % 24) * interval '1 hour')
        END AS created_at
    FROM randomized
)
UPDATE "Ticket" t
SET
    "createdAt" = n.created_at,
    "updatedAt" = LEAST(now(), n.created_at + ((abs(hashtext(t.id)) % 72) * interval '1 hour'))
FROM new_times n
WHERE t.id = n.id;
SQL

echo "==> Seeding knowledge base documents..."
if [ -s /tmp/knowledge_base_documents.json ]; then
    # Build a function that renders a full document JSON into rich BlockNote format:
    # summary paragraph, then h2 sections (Symptoms, Causes, Steps, etc.) with
    # bullet-list items drawn from every element of each array — not just [0].
    runuser -u postgres -- "$PSQL" -d peppermint -c "
CREATE OR REPLACE FUNCTION doc_to_blocknote(doc jsonb) RETURNS text AS \$\$
DECLARE
    result    jsonb   := '[]'::jsonb;
    item      text;
    section   jsonb;
    lbl       text;
    key       text;
    sections  text[]  := ARRAY['symptoms','probableCauses','verificationSteps',
                                'remediationSteps','validationChecklist','escalationCriteria'];
    labels    text[]  := ARRAY['Symptoms','Probable Causes','Verification Steps',
                                'Remediation Steps','Validation Checklist','Escalation Criteria'];
    i         int;
    tag_list  text;
BEGIN
    -- Summary (bold paragraph)
    IF trim(COALESCE(doc->>'summary','')) != '' THEN
        result := result || jsonb_build_array(jsonb_build_object(
            'id', gen_random_uuid()::text, 'type', 'paragraph',
            'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\"}'::jsonb,
            'content', jsonb_build_array(jsonb_build_object('type','text','text',doc->>'summary','styles','{\"bold\":true}'::jsonb)),
            'children', '[]'::jsonb));
    END IF;

    -- Overview h2
    result := result || jsonb_build_array(jsonb_build_object(
        'id', gen_random_uuid()::text, 'type', 'heading',
        'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\",\"level\":2}'::jsonb,
        'content', jsonb_build_array(jsonb_build_object('type','text','text','Document Overview','styles','{}'::jsonb)),
        'children', '[]'::jsonb));

    -- Category + tags metadata line
    tag_list := array_to_string(ARRAY(SELECT jsonb_array_elements_text(COALESCE(doc->'tags','[]'::jsonb))), ', ');
    result := result || jsonb_build_array(jsonb_build_object(
        'id', gen_random_uuid()::text, 'type', 'paragraph',
        'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\"}'::jsonb,
        'content', jsonb_build_array(jsonb_build_object('type','text',
            'text', 'Category: ' || COALESCE(doc->>'category','general') || '   |   Tags: ' || COALESCE(NULLIF(tag_list,''),'—'),
            'styles','{}'::jsonb)),
        'children', '[]'::jsonb));

    -- One h2 section per body array, with all bullet items
    FOR i IN 1..array_length(sections,1) LOOP
        key := sections[i];
        lbl := labels[i];
        IF doc->'body'->key IS NOT NULL AND jsonb_array_length(doc->'body'->key) > 0 THEN
            result := result || jsonb_build_array(jsonb_build_object(
                'id', gen_random_uuid()::text, 'type', 'heading',
                'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\",\"level\":2}'::jsonb,
                'content', jsonb_build_array(jsonb_build_object('type','text','text',lbl,'styles','{}'::jsonb)),
                'children', '[]'::jsonb));
            FOR item IN SELECT jsonb_array_elements_text(doc->'body'->key) LOOP
                result := result || jsonb_build_array(jsonb_build_object(
                    'id', gen_random_uuid()::text, 'type', 'bulletListItem',
                    'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\"}'::jsonb,
                    'content', jsonb_build_array(jsonb_build_object('type','text','text',item,'styles','{}'::jsonb)),
                    'children', '[]'::jsonb));
            END LOOP;
        END IF;
    END LOOP;

    -- Additive real-world documents use named sections instead of the
    -- troubleshooting-only body schema above. Existing documents do not have
    -- this field and therefore render exactly as before.
    IF jsonb_typeof(doc->'sections') = 'array' THEN
        FOR section IN SELECT value FROM jsonb_array_elements(doc->'sections') LOOP
            IF trim(COALESCE(section->>'title','')) != '' THEN
                result := result || jsonb_build_array(jsonb_build_object(
                    'id', gen_random_uuid()::text, 'type', 'heading',
                    'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\",\"level\":2}'::jsonb,
                    'content', jsonb_build_array(jsonb_build_object('type','text','text',section->>'title','styles','{}'::jsonb)),
                    'children', '[]'::jsonb));
            END IF;
            FOR item IN SELECT jsonb_array_elements_text(COALESCE(section->'items','[]'::jsonb)) LOOP
                result := result || jsonb_build_array(jsonb_build_object(
                    'id', gen_random_uuid()::text, 'type', 'paragraph',
                    'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\"}'::jsonb,
                    'content', jsonb_build_array(jsonb_build_object('type','text','text',item,'styles','{}'::jsonb)),
                    'children', '[]'::jsonb));
            END LOOP;
        END LOOP;
    END IF;

    -- Preserve visible source and license attribution for imported documents.
    IF trim(COALESCE(doc->>'attribution','')) != '' THEN
        result := result || jsonb_build_array(jsonb_build_object(
            'id', gen_random_uuid()::text, 'type', 'heading',
            'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\",\"level\":2}'::jsonb,
            'content', jsonb_build_array(jsonb_build_object('type','text','text','Source and License','styles','{}'::jsonb)),
            'children', '[]'::jsonb));
        result := result || jsonb_build_array(jsonb_build_object(
            'id', gen_random_uuid()::text, 'type', 'paragraph',
            'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\"}'::jsonb,
            'content', jsonb_build_array(jsonb_build_object('type','text','text',doc->>'attribution','styles','{}'::jsonb)),
            'children', '[]'::jsonb));
    END IF;

    -- Internal notes section
    IF trim(COALESCE(doc->>'exampleInternalNote','')) != '' THEN
        result := result || jsonb_build_array(jsonb_build_object(
            'id', gen_random_uuid()::text, 'type', 'heading',
            'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\",\"level\":2}'::jsonb,
            'content', jsonb_build_array(jsonb_build_object('type','text','text','Internal Notes','styles','{}'::jsonb)),
            'children', '[]'::jsonb));
        result := result || jsonb_build_array(jsonb_build_object(
            'id', gen_random_uuid()::text, 'type', 'paragraph',
            'props', '{\"textColor\":\"default\",\"backgroundColor\":\"default\",\"textAlignment\":\"left\"}'::jsonb,
            'content', jsonb_build_array(jsonb_build_object('type','text','text',doc->>'exampleInternalNote','styles','{}'::jsonb)),
            'children', '[]'::jsonb));
    END IF;

    RETURN result::text;
END;
\$\$ LANGUAGE plpgsql;"

    # Preserve document visibility for the four interactive seed users.
    # Imported provenance-only accounts do not need private note copies.
    runuser -u postgres -- "$PSQL" -d peppermint -c "
WITH src AS (
    SELECT jsonb_array_elements(
        (pg_read_file('/tmp/knowledge_base_documents.json')::jsonb -> 'documents')
    ) AS doc
    UNION ALL
    SELECT jsonb_array_elements(
        (pg_read_file('/tmp/glpi_knowledge_documents.json')::jsonb -> 'documents')
    ) AS doc
),
users AS (
    SELECT id FROM \"User\"
    WHERE email IN (
        'admin@admin.com',
        'james@peppermint.local',
        'priya@peppermint.local',
        'marcus@peppermint.local'
    )
),
docs_users AS (SELECT doc, id AS uid FROM src CROSS JOIN users)
INSERT INTO \"Notes\" (id, title, note, \"userId\")
SELECT
    COALESCE(doc->>'id', 'DOC-' || substr(md5(random()::text), 1, 12)) || '-' || substr(uid::text, 1, 8),
    COALESCE(doc->>'title', 'Untitled Document'),
    doc_to_blocknote(doc),
    uid
FROM docs_users
ON CONFLICT (id) DO NOTHING;"

    KB_COUNT=$(runuser -u postgres -- "$PSQL" -d peppermint -tAc 'SELECT count(*) FROM "Notes";')
    echo "  Document notes in DB: ${KB_COUNT}"
else
    echo "  WARNING: /tmp/knowledge_base_documents.json not found; skipping document seed"
fi

echo "==> Stopping API..."
kill "$API_PID" 2>/dev/null || true
sleep 2

echo "==> Dumping seeded database..."
PGPASSWORD=peppermint pg_dump -h 127.0.0.1 -p 5432 -U peppermint -d peppermint --no-owner --no-acl \
    | gzip > /seed.sql.gz

DUMP_SIZE=$(wc -c < /seed.sql.gz)
echo "  Dump: ${DUMP_SIZE} bytes"
if [ "$DUMP_SIZE" -lt 1000 ]; then
    echo "ERROR: Dump is suspiciously small."
    exit 1
fi

echo "==> Stopping Postgres..."
runuser -u postgres -- "$PG_CTL" -D "$PGDATA" stop -m fast

echo "==> Seed stage complete."
