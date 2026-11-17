class TestLogout:
    def test_post_clears_session(self, client, active_user):
        client.post("/auth/login", data={"email": active_user.email, "password": "testpassword1"})
        client.post("/auth/logout")
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_post_redirects_to_login(self, client, active_user):
        client.post("/auth/login", data={"email": active_user.email, "password": "testpassword1"})
        resp = client.post("/auth/logout")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_get_method_not_allowed(self, client, active_user):
        client.post("/auth/login", data={"email": active_user.email, "password": "testpassword1"})
        resp = client.get("/auth/logout")
        assert resp.status_code == 405

    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]
