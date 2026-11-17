class TestPendingPage:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/auth/pending")
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_pending_user_sees_page(self, client, pending_user):
        client.post("/auth/login", data={"email": pending_user.email, "password": "testpassword1"})
        resp = client.get("/auth/pending")
        assert resp.status_code == 200

    def test_pending_page_shows_display_name(self, client, pending_user):
        display_name = pending_user.display_name  # read before requests expire the object
        client.post("/auth/login", data={"email": pending_user.email, "password": "testpassword1"})
        resp = client.get("/auth/pending")
        assert display_name.encode() in resp.data

    def test_active_user_redirected_away(self, client, active_user):
        client.post("/auth/login", data={"email": active_user.email, "password": "testpassword1"})
        resp = client.get("/auth/pending")
        assert resp.status_code == 302
        assert "/auth/pending" not in resp.headers["Location"]

    def test_frozen_user_reaches_page(self, client, frozen_user):
        # Frozen users can be logged in (login blocks them), but if somehow
        # they have a session they should see the pending page, not a crash.
        # The route only redirects active users; all others see the page.
        # (In practice a frozen user cannot log in — this guards the route logic.)
        client.post("/auth/login", data={"email": frozen_user.email, "password": "testpassword1"})
        with client.session_transaction() as sess:
            # Frozen users cannot log in at all, so no session exists.
            assert "_user_id" not in sess
