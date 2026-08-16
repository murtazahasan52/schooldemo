# SchoolFlow ERP prototype

Working full-stack school-management prototype with a responsive UI, SQLite database, seeded demo users and role-enforced APIs.

## Run

Requires Python 3.9+ only (no packages to install):

```sh
python3 app.py
```

Open `http://localhost:8000`.

Demo login: `admin@greenfield.edu.in` / `Demo@123`. Other seeded roles: `principal`, `teacher`, and `accounts` at `@greenfield.edu.in`, same password.

## Included flows

- Cookie-authenticated login, role permissions, school/branch scoping and server-side audit trail
- School and academic-year settings
- Student and parent records, subjects/classes, staff
- Daily attendance persistence
- Fee invoices, payment receipts and balances
- Exams and marks entry
- Search, pagination, CSV student export and browser print for fees

The local `schoolflow.db` is created and seeded on first run. Delete that file to reset demo data.
