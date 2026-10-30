# Backend verification and hardening

The immediate milestone is a reliable foundation for Iran-first gym memberships
and paid single-entry visits. The gateway provider remains open. Online payment
is required before paid pilot sales; this verification gate does not implement
payments, deployment or settlements.

## First implemented slice

Customer API and legacy cancellation now use one atomic service and revoke only
the access granted by the cancelled booking. Customer/owner cancellation URLs are
distinct. Legacy owner/control actions refuse closed-booking reopening and make
repeated confirmation a no-op. Existing booking-cancellation semantics remain;
financial refund rules are not implemented by this change.

Local verification on 30 October 2026: **104 backend tests passed**, including
16 new cancellation/state regression tests. Django checks passed and migration
drift detection reported no changes. Verification used an isolated in-memory
SQLite database. This does not establish MySQL concurrency or deployed behavior.
No live database migration, historic-data repair or deployment was performed.

## Repository boundaries

In the current workspace, `backend/` has its own Git repository. The sibling
`frontend/` and parent planning documents are outside that repository; neither
the workspace root nor `frontend/` currently has a Git repository. The canonical
React source is `frontend/src/`.

`.github/workflows/backend-checks.yml` is relative to the backend repository
root. A clean checkout of that repository must work independently of sibling
folders, so this workflow checks only Django. It does not verify the React app
or the combined customer-to-reception journey. Establish the frontend's source
control and CI boundary deliberately before adding a full-stack release job.

## What the backend gate checks

The workflow installs Python 3.12, MySQL client build dependencies and
`requirements.txt` on Ubuntu, then runs:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
```

It uses test settings, a disposable SQLite filename and in-memory email. The
existing settings force Django's test runner to use an isolated in-memory SQLite
database when `USE_SQLITE_FOR_TESTS=True`. No deployment secrets or live database
credentials are required. The migration command reports missing migration files;
it does not apply migrations to the developer or production database.

This workflow is new and **has not yet been executed on GitHub**. It will run
after these files are committed and pushed to a GitHub repository with Actions
enabled. A green run should be recorded with its commit and run URL. Configuring
it as a required pull-request check is a separate repository setting.

The action versions and configuration were checked against the official
[checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) documentation. The job
uses read-only repository permissions and does not persist checkout credentials.

The gate does not establish production readiness, production-database locking
behavior, deployed end-to-end correctness or physical-device compatibility. It
does not enforce a warning-free OpenAPI schema; that baseline needs a separate
review first.

## Run the same checks locally

Run from the backend repository root in an activated Python 3.12 virtual
environment. Use the repository's existing virtual environment where appropriate.
On Ubuntu, installing `mysqlclient` from source requires `build-essential`,
`default-libmysqlclient-dev` and `pkg-config`, as installed in the workflow.

PowerShell:

```powershell
python -m pip install -r requirements.txt
$env:ENVIRONMENT = 'test'
$env:DEBUG = 'True'
$env:DB_ENGINE = 'sqlite'
$env:DB_NAME = 'validation.sqlite3'
$env:USE_SQLITE_FOR_TESTS = 'True'
$env:EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
```

POSIX shell:

```sh
python -m pip install -r requirements.txt
export ENVIRONMENT=test
export DEBUG=True
export DB_ENGINE=sqlite
export DB_NAME=validation.sqlite3
export USE_SQLITE_FOR_TESTS=True
export EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
```

The explicit environment values override a local `.env`, including a configured
MySQL database or an invalid inherited `DEBUG` value. Django's checks may open
the separate `validation.sqlite3` file; tests use their own in-memory database.
Use a separate shell for validation, or clear these variables before running the
application with its normal environment. Do not apply these test settings to a
deployed service.

For the sibling frontend, run these independently from `frontend/`:

```sh
npm ci
npm test
npm run build
```

These commands remain local frontend verification until its source-control and
CI arrangement is established. The build includes the existing UI contract and
TypeScript checks.

## Next hardening slices

1. **Cancellation and access consistency.** Cover customer, owner/admin and
   reachable legacy paths. Cancelled access must not remain usable, and cancelling
   one booking must preserve unrelated memberships. Verify retries and duplicate
   entry against the intended production database where locking differs from
   SQLite.
2. **Production configuration tests.** Fail closed on production debug mode and
   unsafe secrets/host configuration. Review HTTPS, secure cookies and trusted
   proxy settings together. The development `.env.example` explicitly disables
   several HTTPS switches and therefore overrides their production defaults when
   copied unchanged. Prepare an explicit staging configuration and run
   `python manage.py check --deploy` against it.
3. **Repeatable staging release.** Choose a primary hosting path. Define React
   root/SPA routing, Django `/api/`, persistent media storage, TLS and a controlled
   migration/release step. The current Docker entrypoint and Procfile run
   migrations and static collection on startup; the frontend build is separate.
   Add non-sensitive liveness/readiness checks and rehearse the real cross-role
   flow without exposing private details in health responses.
4. **Recovery and error visibility.** Rehearse restoring both the database and
   media into a separate environment, recording the backup, restore result and
   recovery steps. Existing backup instructions are not evidence of a successful
   restore. Verify error reporting, request correlation and a support route.
5. **Abuse controls across deployment workers.** Review authentication,
   registration, uploads, booking and QR endpoints. The current login throttle
   uses Django's default process-local cache; multi-worker deployment needs a
   deliberate shared-cache or proxy-level strategy. Redis is an option, not a
   prerequisite for beginning hardening.

Keep the present monolith. MySQL support and transactional services already
exist; introducing microservices or replacing the database is not required for
this milestone. Dependency pinning and repeatable upgrade checks should follow
the initial gate; `requirements.txt` currently contains version ranges.

Build the later payment foundation around explicit currencies, immutable order
and commission snapshots, separate payment/fulfillment state, idempotent
verification and recorded refunds/settlements. Provider-specific integration and
live charging remain later release gates, after the merchant arrangement and
gateway are selected.
