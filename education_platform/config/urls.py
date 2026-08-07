from django.contrib import admin
from django.urls import include, path
from django.shortcuts import render, redirect


def index_view(request):
    """主框架（需登录）"""
    if not request.user.is_authenticated:
        return redirect("/login.html")
    return render(request, "index.html")


urlpatterns = [
    path("", index_view),
    path("index.html", index_view),
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.industry.urls")),
    path("", include("apps.collection.urls")),
    path("", include("apps.capabilities.urls")),
    path("", include("apps.organizations.urls")),
    path("", include("apps.curriculum.urls")),
    path("", include("apps.resources.urls")),
    path("", include("apps.teaching.urls")),
    path("", include("apps.learning.urls")),
    path("", include("apps.notifications.urls")),
]
