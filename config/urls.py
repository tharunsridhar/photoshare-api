from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    db_status = "ok"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_status = "error"
    status_code = 200 if db_status == "ok" else 503
    return JsonResponse({"status": "ok" if db_status == "ok" else "error", "database": db_status}, status=status_code)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_check, name="health"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.posts.urls")),
]
