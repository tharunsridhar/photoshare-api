from django.urls import path

from apps.accounts.views import (
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    RequestVerifyTokenView,
    ResetPasswordView,
    UserDetailView,
    VerifyView,
)

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="register"),
    path("auth/jwt/login", LoginView.as_view(), name="login"),
    path("auth/jwt/logout", LogoutView.as_view(), name="logout"),
    path("auth/verify", VerifyView.as_view(), name="verify"),
    path("auth/request-verify-token", RequestVerifyTokenView.as_view(), name="request-verify-token"),
    path("auth/forgot-password", ForgotPasswordView.as_view(), name="forgot-password"),
    path("auth/reset-password", ResetPasswordView.as_view(), name="reset-password"),
    path("users/me", MeView.as_view(), name="me"),
    path("users/<uuid:pk>", UserDetailView.as_view(), name="user-detail"),
]
