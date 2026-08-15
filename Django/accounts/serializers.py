"""账号模块序列化器。"""
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """用户信息（含角色）。name 映射到 Django User.first_name 作为显示名。"""

    name = serializers.CharField(source="first_name", required=False, allow_blank=True)
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "name", "role", "is_active", "is_staff", "date_joined"]
        read_only_fields = ["id", "is_staff", "date_joined"]

    def get_role(self, obj) -> str:
        return "admin" if obj.is_staff else "operator"


class UserCreateSerializer(serializers.ModelSerializer):
    """管理员新建用户。role=admin 时置 is_staff=True。"""

    name = serializers.CharField(source="first_name", required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=["operator", "admin"], default="operator")
    password = serializers.CharField(write_only=True, required=True, min_length=6)

    class Meta:
        model = User
        fields = ["username", "name", "password", "role", "is_active"]

    def create(self, validated_data):
        role = validated_data.pop("role", "operator")
        user = User(
            username=validated_data.pop("username"),
            first_name=validated_data.pop("first_name", ""),
            is_active=validated_data.pop("is_active", True),
            is_staff=(role == "admin"),
        )
        user.set_password(validated_data.pop("password"))
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """管理员更新用户：改姓名/角色/停用/重置密码。"""

    name = serializers.CharField(source="first_name", required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=["operator", "admin"], required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=6)

    class Meta:
        model = User
        fields = ["name", "role", "is_active", "password"]

    def update(self, instance, validated_data):
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", None)
        if role is not None:
            instance.is_staff = role == "admin"
        if password:
            instance.set_password(password)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class LoginSerializer(TokenObtainPairSerializer):
    """登录成功返回 access/refresh，并附带用户信息。"""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
