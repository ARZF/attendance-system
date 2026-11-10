# Attendance system

The backend through Phase 8 uses Python 3.13, Django 5.2.19 LTS, PostgreSQL 17,
and pytest-django. Authentication, scoped guard assignments, attendance workflows,
corrections, protected auditing, administrative user management, JSON dashboards,
reporting, and HTTP integration are available. There is no self-registration or
attendance frontend.

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
assignments. They also block request owners and currently assigned guards while they
have unresolved attendance requests.

Successful login/logout, development seed creation, role changes, and assignment
actions write minimal audit events inside their action transaction. Authenticated
sessions are saved inside the login transaction. Failed-login audit events and
append-only ORM/database enforcement remain Phase 6 work; **the Phase 2 audit model
is not yet immutable outside its read-only Django admin registration**.

The approved visual direction is recorded in `DESIGN.md`. HTMX 2.0.11 is vendored
with its license, without a CDN dependency. The shared body supplies the CSRF token
through `hx-headers`; partial endpoints apply the same authorization as full pages.
Expired sessions use `HX-Redirect`, and buttons disable while requests are in flight.

## Phase 3 attendance core

`AttendanceSession` stores approved attendance periods. An open session has no
`check_out_at`. PostgreSQL enforces one open session per user, positive duration, and
non-overlapping session ranges. Adjacent sessions are allowed.

`AttendanceRequest` stores check-in and check-out requests. `requested_at` is the
creation timestamp, so a duplicate `created_at` field is intentionally omitted.
Database constraints enforce valid request/review states, one pending request per
user and request type, no self-review, and valid links between requests and sessions.

The attendance service exposes:

- `submit_check_in_request(actor=..., attendance_at=...)`
- `submit_check_out_request(actor=..., attendance_at=...)`
- `approve_attendance_request(reviewer=..., request_id=...)`
- `reject_attendance_request(reviewer=..., request_id=..., reason=...)`

The actor is always the attendance subject; no employee ID is accepted for submission.
All roles may submit for themselves. Employee requests can be reviewed by their current
guard or any admin. Guard requests require an admin. Admin requests are approved by the
system in the submission transaction, with `reviewed_by=None`, `auto_approved=True`,
and the submitting admin as the audit actor. Human reviewers cannot review themselves.

Both request types use the requested `attendance_at`, never review time. Times must be
timezone-aware, not in the future, and at most 24 hours old when submitted. Approval
revalidates that window against the saved `requested_at`, so review delay does not make
a valid request stale. Check-in cannot overlap an active or previous session. Check-out
requires the original active session and must be later than its check-in.

Submission, approval, rejection, session creation, and session completion write audit
records in the same transaction. The write path locks the employee User row before the
request row, then rechecks request state and reviewer scope. Audit database immutability
remains Phase 6 work.

Phase 3 adds backend models, selectors, services, migration, and read-only Django admin
registrations only. HTTP forms/routes and dashboards are deferred.

## Corrections and forgotten check-outs

`AttendanceCorrection` preserves every check-in/check-out change with the actor,
previous value, new value, reason, and timestamp. Corrections lock the employee and
session, validate duration and overlaps, and write an audit row in the same transaction.
Guards may correct currently assigned employees through exactly 14 days after check-in;
admins have no age limit. Nobody may correct their own session.

An active session cannot receive an ordinary check-out correction. The explicit
`close_attendance_session()` service closes forgotten check-outs and refuses to run
while a check-out request is pending.

## Protected audit log

Audit rows include actor, target employee, generic target type/ID, action, details,
timestamp, and optional IP address. The audit service rejects sensitive detail keys.
Failed logins are recorded without passwords or authentication tokens.

`audit.0002_audit_protection` installs PostgreSQL triggers that reject UPDATE, DELETE,
and TRUNCATE in development and production. Ordinary test settings intentionally skip
the triggers because transactional Django tests flush tables. Production must use a
non-owner runtime database role with no audit mutation privileges; see
[`docs/audit-database-role.md`](docs/audit-database-role.md).

## Administrative user management

Business admins can create users, update profile fields, activate/deactivate accounts,
and change roles. Passwords are validated and hashed by Django. The services block
self-deactivation, removal of the last active business admin, role/deactivation changes
with active assignments or pending attendance responsibilities, and all non-admin
callers. Business roles remain independent of Django staff/superuser flags.

Existing assignment services continue to create, end, and replace active assignments
without deleting history. Guards cannot manage assignments.

## Dashboard and reporting backend

Employee, guard, and admin dashboard endpoints return JSON. Date-range reports use
PostgreSQL duration aggregation and clip completed sessions to the requested range.
History/report endpoints support authorized employee filters, allowlisted sorting,
and pagination up to 100 rows per page. Guard queries are limited to current assignments
and use related-object loading to avoid per-row lookups. Working-time totals include
completed sessions only; active-session state is returned separately.

## Backend HTTP endpoints

Authentication and existing management pages:

- `GET|POST /login/`, `POST /logout/`
- `GET|POST /assignments/`, admin assignment management
- `GET /employees/<id>/`, scoped assignment history
- `GET|POST /users/<id>/role/`, admin role page

Administrative user JSON endpoints:

- `POST /management/users/create/`
- `GET|POST /management/users/<id>/`
- `POST /management/users/<id>/status/`
- `POST /management/users/<id>/role/`

Attendance request and employee endpoints:

- `POST /attendance/requests/check-in/`
- `POST /attendance/requests/check-out/`
- `GET /attendance/requests/`
- `GET /attendance/requests/<id>/`
- `POST /attendance/requests/<id>/cancel/`
- `GET /attendance/history/`
- `GET /attendance/dashboard/employee/`

Guard and shared reviewer endpoints:

- `GET /attendance/guard/employees/`
- `GET /attendance/guard/requests/pending/`
- `GET /attendance/guard/employees/<id>/history/`
- `POST /attendance/requests/<id>/approve/`
- `POST /attendance/requests/<id>/reject/`
- `POST /attendance/sessions/<id>/correct/`
- `POST /attendance/sessions/<id>/close/`
- `GET /attendance/dashboard/guard/`

Admin and reporting endpoints:

- `GET /attendance/admin/requests/`
- `GET /attendance/admin/assignments/`
- `GET /attendance/admin/audit/`
- `GET /attendance/dashboard/admin/`
- `GET /attendance/reports/attendance/`

State-changing endpoints require POST and Django CSRF protection. Views validate forms
and pass the authenticated user into services; client-supplied roles, actors, reviewers,
and attendance employee IDs are never trusted for authorization. Out-of-scope employee,
request, and session IDs return 404 where disclosure would create an IDOR risk.

Apply the migration before using these services:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

## Agreed phase boundaries

Implementation stops after each phase for approval.

1. Foundation (accepted).
2. Authentication and assignments (accepted); minimal `AuditLog`/`log_activity`, including
   role-change and assignment-change auditing. Assignment history belongs in
   `attendance`, with an employee/range PostgreSQL exclusion constraint using
   `tstzrange(started_at, ended_at, '[)')`, `&&`, and `btree_gist`.
3. Attendance requests, sessions, submission, approval/rejection services, constraints,
   timestamp validation, and audit integration (implemented).
4. Corrections and forgotten check-out closure (implemented).
5. Audit metadata, failed-login events, database mutation triggers, and audit filtering
   (implemented; restricted production role setup remains a deployment step).
6. Administrative user and guard-assignment management (implemented).
7. Scoped dashboard selectors, aggregation, filtering, pagination, and JSON endpoints
   (implemented).
8. Attendance, correction, cancellation, management, reporting, and audit HTTP endpoints
   (implemented). Frontend work remains separate.

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
TRUNCATE. Production must use the documented restricted application role. Privileged
database-owner tampering is outside that guarantee.
