import unittest

from fastapi.testclient import TestClient

from backend.app.analyzer import analyze_spec
from backend.app.main import app


class SpecLintTests(unittest.TestCase):
    def test_invite_spec_flags_missing_edges(self):
        report = analyze_spec(
            title="Workspace invites",
            spec_text="Users can invite teammates to a workspace. Guests can view projects.",
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Permission boundary is underspecified", issue_titles)
        self.assertIn("Invitation lifecycle is incomplete", issue_titles)
        self.assertGreaterEqual(len(report.acceptance_tests), 3)
        self.assertLess(report.score, 90)

    def test_api_returns_compiler_style_report(self):
        client = TestClient(app)
        response = client.post(
            "/api/analyze",
            json={
                "title": "Exports",
                "spec_text": "Users should be able to quickly export all data.",
                "strictness": "balanced",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("score", payload)
        self.assertTrue(payload["issues"])
        self.assertTrue(payload["rewritten_spec"])


if __name__ == "__main__":
    unittest.main()

