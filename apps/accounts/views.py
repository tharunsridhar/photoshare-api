from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.generics import RetrieveDestroyAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    RequestVerifyTokenSerializer,
    ResetPasswordSerializer,
    UserReadSerializer,
    UserUpdateSerializer,
    VerifyRequestSerializer,
)
from apps.accounts.services import forgot_password, request_verify, reset_password, verify_token
from apps.accounts.tokens import InvalidTokenError, make_access_token


class RegisterView(APIView):
    """POST /auth/register - the only unauthenticated write in the app.
    RegisterSerializer's email field inherits the model's unique=True, so
    DRF auto-validates the duplicate-email case into a 400 without any
    extra code here."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserReadSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /auth/jwt/login - form-encoded (OAuth2-password-style), not
    JSON, matching the FastAPI port's fastapi-users login endpoint exactly
    so an existing frontend/client doesn't need to change how it calls this."""

    permission_classes = [AllowAny]
    parser_classes = [FormParser, MultiPartParser, JSONParser]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active:
            return Response({"detail": "LOGIN_BAD_CREDENTIALS"}, status=status.HTTP_400_BAD_REQUEST)
        token = make_access_token(user)
        return Response({"access_token": token, "token_type": "bearer"}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """A single stateless JWT can't be server-side invalidated without a
    blacklist (which this app deliberately doesn't have - see the FastAPI
    port's auth_backend for the same tradeoff), so this is a no-op that
    just confirms the request was authenticated."""

    def post(self, request):
        return Response(status=status.HTTP_200_OK)


class VerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = verify_token(serializer.validated_data["token"])
        except InvalidTokenError:
            return Response({"detail": "VERIFY_USER_BAD_TOKEN"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserReadSerializer(user).data, status=status.HTTP_200_OK)


class RequestVerifyTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RequestVerifyTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"]).first()
        if user is not None and not user.is_verified:
            request_verify(user)
        # always 202, whether the email exists or is already verified -
        # otherwise this becomes an account-enumeration oracle
        return Response(status=status.HTTP_202_ACCEPTED)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"]).first()
        if user is not None:
            forgot_password(user)
        return Response(status=status.HTTP_202_ACCEPTED)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reset_password(serializer.validated_data["token"], serializer.validated_data["password"])
        except InvalidTokenError:
            return Response({"detail": "RESET_PASSWORD_BAD_TOKEN"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)


class MeView(APIView):
    def get(self, request):
        return Response(UserReadSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserReadSerializer(request.user).data)


class UserDetailView(RetrieveDestroyAPIView):
    """GET/DELETE /users/{id} - admin-only, unlike /users/me. The FastAPI
    port's fastapi-users get_users_router has the same restriction (only a
    superuser can read/delete arbitrary users; anyone can read/update
    themselves via /users/me)."""

    queryset = User.objects.all()
    serializer_class = UserReadSerializer
    permission_classes = [IsAdminUser]
