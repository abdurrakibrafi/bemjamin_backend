# 3D Head Scanner & Biometric Analysis Backend 🧠

A robust Django REST API backend designed to manage user authentication, process image datasets into 3D head models, calculate precise biometric measurements, and generate medical/fitting PDF reports. The system is containerized with Docker and uses Celery/Redis for asynchronous processing.

---

## 🚀 Key Features

### 1. Advanced Authentication & RBAC

- **JWT Authentication:** Secure stateless authentication using SimpleJWT
- **OTP Verification:** Email-based One-Time Password verification for signups and password resets
- **Approval Workflow:** New users are set to PENDING until approved by an Admin via the Dashboard
- **Role-Based Access Control:** Distinct roles (Admin, Doctor, Provider, Client, etc.)

### 2. 3D Scanning Pipeline (The Core)

- **Image Processing:** Accepts a front-facing image + multiple supplementary images
- **External AI Integration:** Connects to the KeenTools API to reconstruct a 3D head model from 2D photos
- **Asynchronous Processing:** Uses Celery & Redis to handle the heavy 3D generation pipeline in the background without blocking the UI
- **Biometric Analysis:** Uses trimesh and numpy to analyze the generated .obj file and calculate specific metrics (e.g., Head Width, Ear-to-Ear, Eye-to-Eye, Circumference)

### 3. Reporting & Output

- **PDF Generation:** Auto-generates detailed PDF reports containing user details, the front image, and a table of all biometric measurements
- **3D Model Serving:** Securely serves .obj and .glb files for frontend visualization

### 4. Administrative Dashboard

- **Analytics:** Visual stats for user growth and scan volume
- **User Management:** Approve, Block, or Delete users
- **Scan Oversight:** View all user scans, request re-scans, and download reports
- **Push Notifications:** Send global push notifications via Firebase (FCM)

### 5. Tech Stack

- **Framework:** Django 5, Django Rest Framework
- **Database:** PostgreSQL (Production) / SQLite (Dev)
- **Async Tasks:** Celery + Redis
- **Storage:** AWS S3 (Media) or Local Storage
- **Notifications:** Firebase Cloud Messaging (FCM) + SMTP Email
- **Math/3D:** trimesh, numpy

---

## 🛠 System Architecture: "What is happening?"

### The Scanning Workflow

1. **Upload:** A user uploads 5+ photos via `POST /api/scans/`
2. **Transaction:** The request is saved, and a Celery task `process_scan_and_save` is triggered on commit
3. **Pipeline Execution** (`scans/processing/pipeline.py`):
   - The worker initializes a session with the KeenTools API
   - Images are uploaded to the external computation engine
   - The system polls for completion
   - Once done, an .obj file is downloaded
4. **Measurement** (`scans/mesh_measurements.py`):
   - The mesh is aligned to principal axes
   - Landmarks (nose tip, ears, chin) are identified mathematically
   - Distances (Euclidean and Surface) are calculated
5. **Completion:** The database is updated with measurements, the status is set to COMPLETED, and a push notification is sent to the user

---

## ⚙️ Installation & Setup

### Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.12+, Redis, and PostgreSQL if running locally without Docker

### Option 1: Docker (Recommended)

**1. Clone the repository:**

```bash
git clone https://github.com/kaisarfardin6620/benjaminkley.git
cd benjaminkley
```

**2. Create a `.env` file:**

Copy the example below into a `.env` file in the root directory.

**3. Build and Run:**

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`.  
Nginx (if enabled) will be at `http://localhost:8080`.

### Option 2: Local Setup

**1. Create Virtual Env:**

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
```

**2. Install Dependencies:**

```bash
pip install -r requirements.txt
```

**3. Services:**

Ensure a Redis server is running:

```bash
redis-server
```

**4. Run Migrations & Server:**

```bash
python manage.py migrate
python manage.py runserver
```

**5. Run Celery Worker (in a separate terminal):**

```bash
celery -A benjaminkley worker -l info
```

---

## 🔑 Environment Variables (.env)

Create a `.env` file in the root directory:

```ini
# Core
SECRET_KEY=your_django_secret_key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
SERVER_BASE_URL=http://localhost:8000

# Database (Leave empty to use SQLite)
DATABASE_URL=postgres://user:password@db:5432/dbname

# Email (SMTP)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password

# 3D API (KeenTools)
KEENTOOLS_SECRET_KEY=your_keentools_key
KEENTOOLS_API_BASE_URL=https://api.keentools.io/

# AWS S3 (Optional - set USE_S3_STORAGE=True)
USE_S3_STORAGE=False
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_STORAGE_BUCKET_NAME=xxx
AWS_S3_REGION_NAME=us-east-1

# Redis / Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Firebase (FCM)
# Ensure serviceAccountKey.json is present in the root
```

---

## 📚 API Documentation

**Base URL:** `/api/`

**Response Format:** All endpoints return a standard wrapper:

```json
{
    "success": true,
    "code": 200,
    "message": "...",
    "data": { ... }
}
```

### 1. Authentication (`/api/auth/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/login/` | Get Access & Refresh Token (Requires email/password + optional FCM token) |
| POST | `/signup/` | Register new user. Triggers email OTP |
| POST | `/signup/verify/` | Verify email using OTP code |
| POST | `/password/reset/request-otp/` | Request OTP for password reset |
| POST | `/password/reset/verify-otp/` | Verify reset OTP to get a change ticket |
| POST | `/password/reset/set-new/` | Set new password using change ticket |
| GET | `/profile/` | Get current user profile details |
| PUT | `/profile/update/` | Update profile info (Multipart/form-data for image) |
| DELETE | `/profile/delete/` | Permanently delete account |

### 2. Scanning (`/api/scans/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List all scans belonging to the user |
| POST | `/` | Create a scan. Required: `image_front`, `extra_images` (list), `name` (Multipart) |
| GET | `/{id}/` | Get details (status, measurements, model URL) |
| GET | `/{id}/download-pdf/` | Download the generated PDF report |
| GET | `/{id}/view-pdf/` | View PDF in browser |

### 3. Dashboard (Admin Only) (`/api/dashboard/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stats/` | Get total users, total scans, and % change |
| GET | `/users/` | List all users (Paginated) |
| POST | `/users/{id}/approve/` | Approve a pending user account |
| POST | `/users/{id}/block/` | Suspend a user account |
| GET | `/scans/` | List all scans in the system |
| POST | `/scans/{id}/rescan/` | Trigger a status reset to "Processing" for a scan |
| POST | `/push-notifications/send/` | Send a push notification to all active devices |

### 4. Support & Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/contact/submit/` | Submit a support ticket/message |
| GET | `/api/notifications/` | List in-app notifications for the logged-in user |
| POST | `/api/notifications/mark-all-as-read/` | Mark all notifications as read |

---

## 📂 Project Structure

```
benjaminkley/
├── authentication/       # User models, JWT, Signals, OTP logic
├── scans/               # Scan models, Mesh Processing (trimesh), PDF Gen
│   ├── processing/      # Pipeline to talk to External 3D API
│   └── mesh_measurements.py  # The geometric math logic
├── dashboard/           # Admin views, Stats, User Management
├── notifications/       # Internal DB notifications & Firebase integration
├── core/                # Utils, Custom Renderers (JSON wrapper)
├── contact_support/     # Simple contact form app
├── manage.py
├── Dockerfile
└── docker-compose.yml
```

---

## ⚠️ Common Issues & Troubleshooting

### 3D Model not generating

- Check if the Celery Worker is running
- Verify `KEENTOOLS_API_BASE_URL` and keys in `.env`
- Check `scans/processing/pipeline.py` logs for API timeouts

### Email not sending

- If using Gmail, ensure "App Password" is used, not your login password
- Check `EMAIL_PORT` (usually 587 for TLS)

### PDF Images missing

- `reportlab` requires absolute file paths. Ensure `MEDIA_ROOT` is correctly mapped in `settings.py`

---

## 🔗 Repository

**GitHub:** [benjaminkley](https://github.com/kaisarfardin6620/benjaminkley.git)

---

## 📜 License

This project is licensed under the MIT License.