# Local operation and deployment readiness

Use [user-checklist.md](user-checklist.md) for first startup. Compose publishes frontend/backend only to loopback, retains PostgreSQL and Ollama in named volumes, and requests all NVIDIA GPUs for Ollama. Backend readiness checks database connectivity; run migrations and seeds explicitly before using the UI. Core planning does not wait for Ollama readiness.

Images are pinned to public registry manifest digests. Dependencies are pinned in `backend/requirements.lock` and `frontend/package-lock.json`. The dependency lock was exercised on Python 3.11 in the coding environment; the Python 3.12 container still needs a real build/smoke check. Secrets stay in user-managed configuration.

## Back up and restore-check

After configuring and starting your database, create a custom-format database dump from the root:

```sh
docker compose exec -T db pg_dump -U interrail -Fc interrail > interrail-backup.dump
```

Keep this dump outside Git and copy important backups off the host. Restore into a separate check database before relying on a backup:

```sh
docker compose exec db createdb -U interrail interrail_restore_check
docker compose exec -T db pg_restore -U interrail -d interrail_restore_check < interrail-backup.dump
docker compose exec db psql -U interrail -d interrail_restore_check -c 'SELECT count(*) FROM trips;'
```

A backup/restore cycle has not been executed in this workspace. Do not restore over your active database without an intentional recovery plan. Volume deletion is not a backup strategy.

## Test environments

Backend application tests use temporary SQLite databases with foreign keys enabled. Opt-in PostgreSQL tests create a randomly named schema, apply actual migrations, check metadata drift, exercise JSONB/money/persistence/cascade behavior and race two edits. Set TEST_DATABASE_URL only to a disposable test database where schema creation is allowed.

Playwright starts a migrated/seeded temporary SQLite backend and the built standalone frontend, then tests create/edit/reopen, error atomicity and mobile/settings. Its temp database is removed when the helper exits. Tests require Chromium and its host runtime libraries. Browser installation/host permissions are left to the user.

## Public deployment

Not configured in this iteration. Before exposing the app, add proper authentication and authorization, HTTPS, secret management, access/rate controls, off-host backups and private inference connectivity. UUID read links and edit tokens are intended for local use; a UUID is not authentication. Do not assume a home GPU server is continuously available.
