"""
Django settings for facturacion project.
"""
from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# ======================
# CORE
# ======================
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret")
DEBUG = os.environ.get("DEBUG", "0") == "1"

# Hosts
# En Heroku: ALLOWED_HOSTS="facturacion-d28198aaf688.herokuapp.com"
# En local: no es necesario, pero igual soporta localhost
raw_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in raw_hosts.split(",") if h.strip()]

if DEBUG:
    ALLOWED_HOSTS += ["127.0.0.1", "localhost"]

# CSRF (Heroku y cualquier dominio que pongas en ALLOWED_HOSTS)
CSRF_TRUSTED_ORIGINS = []
for h in ALLOWED_HOSTS:
    if h not in ["127.0.0.1", "localhost"]:
        CSRF_TRUSTED_ORIGINS.append(f"https://{h}")

# ======================
# APPS
# ======================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",

    # Cloudinary (solo si instalaste cloudinary + cloudinary_storage)
    "cloudinary",
    "cloudinary_storage",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "facturacion.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "facturacion.wsgi.application"

# ======================
# DATABASE
# ======================
# Local: SQLite si no hay DATABASE_URL
# Heroku: DATABASE_URL (Postgres)
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ======================
# AUTH PASSWORD VALIDATORS
# ======================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ======================
# I18N / TZ
# ======================
LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# ======================
# STATIC (Whitenoise)
# ======================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# OJO: si tu carpeta real es BASE_DIR/core/static, esto está bien.
# Si no existe, evita crasheos en deploy.
static_dir = BASE_DIR / "core" / "static"
STATICFILES_DIRS = [static_dir] if static_dir.exists() else []

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ======================
# MEDIA (Local vs Cloudinary)
# ======================
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
    "API_KEY": CLOUDINARY_API_KEY,
    "API_SECRET": CLOUDINARY_API_SECRET,
}

# Usa Cloudinary SOLO si están las 3 vars
USE_CLOUDINARY = all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])

if USE_CLOUDINARY:
    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
else:
    # En local sin credenciales, se guarda en MEDIA_ROOT
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# ======================
# SECURITY (Heroku)
# ======================
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
