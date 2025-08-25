from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ===== Static & Media =====
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "app" / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ===== Security =====
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key")  # nhớ đổi ở prod!
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

# ===== Installed Apps =====
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "app",

    "app.apps",

    "ckeditor", "ckeditor_uploader",

    "rest_framework", "rest_framework.authtoken", "django_filters",
    "drf_yasg",
    "oauth2_provider",
    "corsheaders",

    "django.contrib.sites",
    "allauth", "allauth.account", "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    "dj_rest_auth",
    "dj_rest_auth.registration",
]

SITE_ID = int(os.getenv("SITE_ID", "1"))

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "api.urls"

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
                "django.template.context_processors.media",
            ],
        },
    },
]

WSGI_APPLICATION = "api.wsgi.application"

# ===== Database (MySQL) =====
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "findjobdb"),
        "USER": os.getenv("DB_USER", "root"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": int(os.getenv("DB_PORT", "3306")),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}

# Nếu dùng PyMySQL
import pymysql
pymysql.install_as_MySQLdb()

# ===== Auth =====
AUTH_USER_MODEL = "app.User"
AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_AUTHENTICATION_METHOD = "username"
ACCOUNT_EMAIL_VERIFICATION = "none"

# ===== DRF =====
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",  # nếu dùng Token
        # "rest_framework_simplejwt.authentication.JWTAuthentication",  # nếu dùng JWT
        "oauth2_provider.contrib.rest_framework.OAuth2Authentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny" if DEBUG else "rest_framework.permissions.IsAuthenticated"
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

# ===== OAuth2 (tùy chọn) =====
OAUTH2_PROVIDER = {
    "OAUTH2_BACKEND_CLASS": "oauth2_provider.oauth2_backends.JSONOAuthLibCore",
    # "SCOPES": {"read": "Read scope", "write": "Write scope"},
}

# ===== CKEditor =====
CKEDITOR_UPLOAD_PATH = "ckeditors/lessons/"

# ===== Cloudinary =====
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# ===== Email =====
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# ===== Third-party Keys =====
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "key": "",
        }
    }
}

# ===== CORS =====
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL", "1") == "1"

# ===== Password Validators =====
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ===== I18N / TZ =====
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Ho_Chi_Minh")
USE_I18N = True
USE_TZ = True

# ===== Defaults =====
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
