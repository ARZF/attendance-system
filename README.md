# Attendance system

Phases 1 and 2: Python 3.13, Django 5.2.19 LTS, PostgreSQL 17, and pytest-django.
Authentication, scoped assignment history, and administrator assignment/role management
are available. There is no self-registration or attendance/dashboard implementation yet.

## Development setup (PowerShell)

Docker Desktop must be running with Linux containers enabled.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `.env` before continuing:

- Set `DJANGO_SECRET_KEY` to a fresh random secret, at least 50 characters.
- Set `POSTGRES_PASSWORD` to a fresh random password.
- Set each `SEED_*_PASSWORD` if you want development accounts.
- Set `POSTGRES_PORT` to another free local port if 5432 is already occupied.

Generate a secret with `.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"`.
Do not share or commit the generated secrets. `.env` is ignored by git.
Development/test settings load `.env` without replacing already-exported environment variables.
Production settings do not load `.env`; supply their environment explicitly.

```powershell
docker compose up -d --wait db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py seed
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe manage.py runserver
```

On Linux/macOS, use `python3.13` to create the virtual environment and
`.venv/bin/python` for subsequent commands.

The Compose file contains a **development database only**. Its port binds to
127.0.0.1, and its data persists in a named Docker volume. The initialized database
role has privileges needed to create pytest's separate test database; it must not
be reused as a production application role. Changing `.env` credentials does not
change credentials in an already-initialized database volume.

`docker compose stop db` stops the database without removing its data.
Do not remove the named volume unless you intend to delete its data.

## Users and seed behavior

`accounts.User` is configured before the first migration. It inherits Django's
unique username, optional/non-unique email, session authentication support,
password hashing, groups, and permission fields.

Business roles are `EMPLOYEE`, `GUARD`, and `ADMIN`, independent of Django's
staff/superuser flags. `role` has length 16 and a database check constraint.
`createsuperuser` creates an ADMIN and rejects an explicitly different role:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

`seed` creates `demo_employee`, `demo_guard`, and `demo_admin`. These are business
accounts, not Django staff/superusers. All new passwords pass Django's password
validators. Missing or invalid passwords roll back the entire seed operation.
Existing usernames are left completely unchanged, even when their role differs
from the intended seed role; their password variables are then unnecessary.
The command refuses to run outside development/test settings and never prints
passwords. There is no self-registration route.

## Settings and checks

- `config.settings.base`: shared configuration with secure cookie defaults and
  required environment-driven secrets/database credentials.
- `config.settings.development`: localhost HTTP and debugging enabled.
- `config.settings.test`: no debugging; PostgreSQL only; pytest uses this module.
- `config.settings.production`: no debugging, explicit allowed hosts, HTTPS-only
  cookies, HTTPS redirect, and HSTS. Deployment is not complete until Phase 8.

The production `check --deploy` currently reports `security.W021`: HSTS preload
is deliberately not enabled. Registering a real domain for browser preloading
requires a separate deployment decision; this warning is not silenced.

`USE_TZ=True`; database connections use UTC, and organization display time is
`Asia/Tehran`. Forwarded headers are ignored by default. Axes 9.0.0 uses
`AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]`, a five-failure limit,
and `timedelta(minutes=15)`. Correct passwords cannot bypass lockout. A successful
login clears failures for that pair; attempts during lockout do not extend it.

Optional `DJANGO_TRUSTED_PROXY_CIDRS` lists only actual reverse-proxy addresses or
networks. From those peers, a valid single `X-Real-IP` is accepted. Missing/invalid
headers fall back to the peer address, and `X-Forwarded-For` is always ignored.
The proxy **must overwrite**, not append/pass through, `X-Real-IP`, and the backend
must be reachable only through trusted proxies in production. Invalid CIDRs and
universal-trust networks are refused at startup. HTTPS proxy trust is still disabled
until deployment configuration is approved in Phase 8.

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pytest --create-db tests/test_assignment_concurrency.py -v
```

Tests create/drop the separate `test_<POSTGRES_DB>` database and apply migrations.
They do not use SQLite. The suite verifies PostgreSQL major version 17 and UTC,
custom-user creation, superuser behavior, role constraints, seed rollback and
idempotence, authentication/CSRF, username+IP lockout, role/IDOR access, transactional
auditing, assignment exclusion constraints, and real threaded changes on distinct
PostgreSQL connections. The fresh test database migration creates `btree_gist` before
the exclusion constraint. CI runs the same stack with
an isolated PostgreSQL service and disposable test-only credentials.

## Phase 2 routes and safety boundaries

- `/login/`, POST `/logout/`, and `/`: session authentication and account details.
- `/employees/` and `/employees/<id>/`: assignment history scoped at access time.
  Employees see themselves, guards see current assignees, and admins have global scope.
  Out-of-scope IDs return 404, including HTMX requests.
- `/assignments/`: ADMIN-only create/replace/end actions, with preserved history.
- `/users/` and `/users/<id>/role/`: ADMIN-only audited role management.
- `/admin/`: requires both ADMIN and `is_staff=True`. User, assignment, and audit
  registrations are read-only, with no bulk mutations. Its login/logout use the same
  application authentication paths; Django flags never bypass business roles.

Assignments lock the employee User row first, then the proposed guard's User row,
then the assignment row. Locking the guard also serializes assignment creation with
guard-role changes. Submitters must supply the last-seen assignment ID (blank for
creation); stale/double submissions cannot overwrite newer decisions. Times are
generated after acquiring the locks, never accepted from submitted form data.
The database additionally enforces one open assignment, valid dates, no self-assignment,
and no overlapping open **or closed** employee assignment periods.

Role changes lock the target User and check both employee-side and guard-side open
assignments. **Pending-request checking is an explicit stub returning False until
Phase 3**, with a test showing that the future hook blocks a role change when True.

Successful login/logout, development seed creation, role changes, and assignment
actions write minimal audit events inside their action transaction. Authenticated
sessions are saved inside the login transaction. Failed-login audit events and
append-only ORM/database enforcement remain Phase 6 work; **the Phase 2 audit model
is not yet immutable outside its read-only Django admin registration**.

The approved visual direction is recorded in `DESIGN.md`. HTMX 2.0.11 is vendored
with its license, without a CDN dependency. The shared body supplies the CSRF token
through `hx-headers`; partial endpoints apply the same authorization as full pages.
Expired sessions use `HX-Redirect`, and buttons disable while requests are in flight.

## Agreed phase boundaries

Implementation stops after each phase for approval.

1. Foundation (accepted).
2. Authentication and assignments (current); minimal `AuditLog`/`log_activity`, including
   role-change and assignment-change auditing. Assignment history belongs in
   `attendance`, with an employee/range PostgreSQL exclusion constraint using
   `tstzrange(started_at, ended_at, '[)')`, `&&`, and `btree_gist`.
3. Attendance requests, sessions, submission/cancellation, constraints, validation.
4. Approval routing, locking, and real PostgreSQL concurrency tests.
5. Corrections and forgotten check-out closure.
6. Audit enforcement, failed-login events, read-only administration, audit pages.
7. Authorized template/HTMX dashboards and partials.
8. Operational hardening and production deployment/backup documentation.

Dependency direction: accounts may import attendance/audit; attendance may import
audit; audit imports neither. Swappable `AUTH_USER_MODEL` references are allowed.
Views handle HTTP, services handle transactional writes, selectors handle reads,
and permissions hold authorization. Django's user manager remains the standard
user/superuser creation integration point.

Assignments take effect immediately, with one active guard per employee. Current
assignments determine access to earlier records and pending requests. Role changes
are blocked while open assignments or pending requests exist. Admins may review
employee requests globally; admin submissions are system-approved with no human
reviewer and explicit auto-approval flags. Guards can correct only currently
assigned employees, never themselves; exactly 14 days from check-in is eligible.

Axes' installed parameter syntax is verified by tests for five failures per
username/IP pair and a 15-minute cooldown. Django's built-in admin does not bypass
business authorization; assignment and audit models are read-only there.

Phase 6's audit UPDATE/DELETE/TRUNCATE triggers will be active in development and
production, **not ordinary test settings**, because transaction tests flush with
TRUNCATE. A separate enforcement test will explicitly install and exercise the
triggers, then remove them before test teardown. Production will use a restricted
application DB role. Privileged database-owner tampering is outside that guarantee.
