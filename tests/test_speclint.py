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
        self.assertEqual(payload["score_breakdown"]["base_score"], 100)
        self.assertIn("severity_counts", payload)
        self.assertTrue(payload["issues"])
        self.assertTrue(payload["rewritten_spec"])

    def test_unless_clause_is_not_contradiction_by_default(self):
        report = analyze_spec(
            title="Project deletion",
            spec_text=(
                "Project owners can delete projects. "
                "All project data is removed unless billing records must be kept. "
                "The user gets a confirmation."
            ),
        )

        self.assertNotIn("contradiction", {issue.type.value for issue in report.issues})
        self.assertIn("score_breakdown", report.model_dump())

    def test_ownership_transfer_requires_receiver_consent(self):
        report = analyze_spec(
            title="Transfer workspace ownership",
            spec_text=(
                "The current workspace owner can transfer ownership to another team member. "
                "The new owner gets full admin access and the previous owner becomes a regular member. "
                "The system sends a confirmation email to both parties. "
                "Ownership transfer is permanent."
            ),
        )

        issue_types = {issue.type.value for issue in report.issues}
        self.assertIn("consent_gap", issue_types)
        self.assertEqual(report.severity_counts["critical"], 1)
        self.assertLess(report.score, 75)
        self.assertIn("transfer", report.intent.actions)
        self.assertIn("send", report.intent.actions)
        self.assertIn("Primary object: workspace ownership.", report.rewritten_spec)
        self.assertNotIn("action the email", report.rewritten_spec)
        self.assertTrue(
            any("receiving party has not accepted" in test.when for test in report.acceptance_tests)
        )


if __name__ == "__main__":
    unittest.main()
