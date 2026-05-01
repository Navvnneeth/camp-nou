# Supabase Database Setup

Yes, this project can use Supabase. The backend uses SQLAlchemy with PostgreSQL, and Supabase gives you a hosted PostgreSQL database.

## 1. Create the database

1. Create a Supabase project.
2. Open **Project Settings > Database**.
3. Copy the PostgreSQL connection string.
4. Use the direct connection string for local development, and include `?sslmode=require`.
## 2. Configure the backend

Create `server/.env`:

```env
DATABASE_URL=postgresql://postgres:<password>@<host>:5432/postgres?sslmode=require
```

The old `NEON_DB_URL` variable still works, but `DATABASE_URL` is preferred.

## 3. Install and run

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

On startup, the API creates the required tables:

- `rooms`
- `students`
- `classrooms`
- `subjects`
- `faculty`
- `subject_faculty_mapping`
- `timetable`
- `app_users`
- `room_bookings`

## 4. Run the frontend

```bash
cd client
npm install
npm run dev
```

If your API is not on `http://localhost:8000/api/v1`, create `client/.env`:

```env
VITE_API_BASE=http://localhost:8000/api/v1
```

## 5. Demo login accounts

These accounts are seeded automatically the first time `/auth/login` is called:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@campnou.edu` | `admin123` |
| Faculty | `faculty@campnou.edu` | `faculty123` |
| Club | `codingclub@campnou.edu` | `club123` |
| Club | `artsclub@campnou.edu` | `club123` |

## Flow

1. Administrator uploads rooms, students, and subject-faculty Excel sheets.
2. Administrator generates timetables.
3. Faculty logs in, views generated timetables, and uses **Download PDF**.
4. Club logs in and requests a room booking.
5. Administrator sees the booking notification and accepts or rejects it.
6. Approved bookings appear on the shared club calendar.
