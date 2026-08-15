"""账号与用户管理 API。"""
from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.permissions import IsAdmin
from accounts.serializers import (
    LoginSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

User = get_user_model()


def _revoke_user_tokens(user):
    """把用户已签发的全部 outstanding refresh token 加入黑名单。"""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )
    for ot in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=ot)


class LoginView(TokenObtainPairView):
    """登录：POST {username, password} → {access, refresh, user}。"""

    serializer_class = LoginSerializer
    # 登录接口限流（DEFAULT_THROTTLE_RATES["login"]），防止密码爆破
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


@api_view(["GET"])
def me(request):
    """当前登录用户信息。"""
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):
    """退出登录：若提供 refresh token 则加入黑名单吊销（配合轮换策略防重放）。

    AllowAny：用户在 access token 已过期时也应能触发退出（本地清 token）；
    refresh token 是 body 自证凭证，黑名单化它不会造成提权风险。
    """
    token = request.data.get("refresh")
    if token:
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            pass  # token 已失效/格式错误，忽略即可
    return Response({"detail": "已退出"})


class UserViewSet(viewsets.ModelViewSet):
    """用户管理（仅管理员）。停用/删除用户通过软停用 is_active。"""

    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    @action(detail=True, methods=["post"])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get("password")
        if not password or len(password) < 6:
            return Response({"detail": "密码至少 6 位"}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save(update_fields=["password"])
        # 吊销该用户已签发的所有 refresh token，强制旧会话失效
        _revoke_user_tokens(user)
        return Response({"detail": "密码已重置"})

    def destroy(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "不能停用当前登录账号"}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
