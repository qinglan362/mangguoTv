"""accounts 模块认证/权限测试。"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AuthTests(TestCase):
    def setUp(self):
        cache.clear()  # 清空限流计数，避免跨测试累计
        self.client = APIClient()
        self.user = User.objects.create_user(username="tester", password="pw12345x", first_name="测试")

    def test_login_returns_tokens_and_user(self):
        resp = self.client.post("/api/auth/login/", {"username": "tester", "password": "pw12345x"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["username"], "tester")
        self.assertEqual(resp.data["user"]["role"], "operator")

    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 401)
        login = self.client.post("/api/auth/login/", {"username": "tester", "password": "pw12345x"}, format="json")
        token = login.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer %s" % token)
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["username"], "tester")

    def test_logout_blacklists_refresh(self):
        """H13 回归：logout 后对应 refresh token 再刷新应 401。"""
        login = self.client.post("/api/auth/login/", {"username": "tester", "password": "pw12345x"}, format="json")
        refresh = login.data["refresh"]
        out = self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
        self.assertEqual(out.status_code, 200)
        resp2 = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(resp2.status_code, 401)

    def test_login_throttled(self):
        """H12 回归：登录接口超过 20/min 后返回 429。"""
        for _ in range(20):
            self.client.post("/api/auth/login/", {"username": "tester", "password": "bad"}, format="json")
        resp = self.client.post("/api/auth/login/", {"username": "tester", "password": "bad"}, format="json")
        self.assertEqual(resp.status_code, 429)

    def test_operator_cannot_list_users(self):
        """权限回归：operator 访问用户管理应 403，admin 应 200。"""
        login = self.client.post("/api/auth/login/", {"username": "tester", "password": "pw12345x"}, format="json")
        token = login.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer %s" % token)
        resp = self.client.get("/api/users/")
        self.assertEqual(resp.status_code, 403)

        admin = User.objects.create_superuser(username="boss", password="pw12345x", first_name="管理员")
        login2 = self.client.post("/api/auth/login/", {"username": "boss", "password": "pw12345x"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer %s" % login2.data["access"])
        resp2 = self.client.get("/api/users/")
        self.assertEqual(resp2.status_code, 200)
