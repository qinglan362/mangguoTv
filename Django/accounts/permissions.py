"""账号模块自定义权限。"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """管理员：已登录且 is_staff=True（superuser 亦为 staff）。"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
