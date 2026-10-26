import unittest

from app import filename_from_url, normalized_url, safe_filename, same_host


class HelperTests(unittest.TestCase):
    def test_normalized_url_resolves_relative_link(self):
        self.assertEqual(
            normalized_url("../files/report.pdf", "https://example.com/docs/page"),
            "https://example.com/files/report.pdf",
        )

    def test_normalized_url_rejects_non_http_scheme(self):
        self.assertIsNone(normalized_url("javascript:alert(1)"))

    def test_same_host_ignores_path_and_port(self):
        self.assertTrue(same_host("https://example.com:8443/a", "example.com"))
        self.assertFalse(same_host("https://sub.example.com/a", "example.com"))

    def test_filename_from_url_adds_pdf_extension(self):
        self.assertEqual(filename_from_url("https://example.com/files/report"), "report.pdf")

    def test_safe_filename_removes_path_separators(self):
        result = safe_filename("../../bad:name.pdf")
        self.assertNotIn("/", result)
        self.assertNotIn(":", result)


if __name__ == "__main__":
    unittest.main()
