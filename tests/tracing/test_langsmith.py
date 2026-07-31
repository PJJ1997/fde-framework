import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tracing.langsmith import setup_tracing


class LangSmithTracingTests(unittest.TestCase):
    def test_setup_tracing_uses_central_environment_loader(self):
        def populate_environment():
            os.environ.update({
                "LANGSMITH_TRACING": "true",
                "LANGSMITH_API_KEY": "langsmith-test-key",
                "LANGSMITH_PROJECT": "test-project",
            })

        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch(
            "tracing.langsmith.load_environment",
            side_effect=populate_environment,
        ), redirect_stdout(output):
            setup_tracing()

        rendered = output.getvalue()
        self.assertIn("LangSmith enabled", rendered)
        self.assertIn("project=test-project", rendered)
        self.assertNotIn("langsmith-test-key", rendered)


if __name__ == "__main__":
    unittest.main()
