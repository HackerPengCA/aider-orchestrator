import unittest
from unittest.mock import patch

import llm_client


class JsonResponseTests(unittest.TestCase):
    def test_extracts_json_from_markdown_wrapper(self):
        raw = 'Here is the plan:\n```json\n[{"task":"Inspect files","type":"analysis"}]\n```'

        value = llm_client._extract_json(raw, list)

        self.assertEqual(value[0]["task"], "Inspect files")

    def test_rejects_truncated_json(self):
        with self.assertRaisesRegex(ValueError, "complete JSON"):
            llm_client._extract_json('{"action":"retry","reason":"cut off', dict)

    @patch.object(
        llm_client,
        "chat",
        side_effect=[
            '{"action":"retry","reason":"cut off',
            '{"action":"retry","reason":"fixed"}',
        ],
    )
    def test_request_json_repairs_truncated_response(self, chat):
        value = llm_client._request_json(
            [{"role": "user", "content": "decide"}],
            dict,
            label="test",
            max_tokens=2048,
        )

        self.assertEqual(value, {"action": "retry", "reason": "fixed"})
        self.assertEqual(chat.call_count, 2)


class PlanNormalizationTests(unittest.TestCase):
    def test_accepts_description_aliases_and_infers_types(self):
        plan = llm_client._normalize_plan_steps(
            [
                {"step": 9, "type": "python", "task": "Build report"},
                {"title": "Run tests", "command": "pytest"},
            ]
        )

        self.assertEqual(
            plan,
            [
                {
                    "step": 1,
                    "type": "script",
                    "task": "Build report",
                    "description": "Build report",
                    "filename": "step_1.py",
                },
                {
                    "step": 2,
                    "title": "Run tests",
                    "command": "pytest",
                    "type": "command",
                    "description": "Run tests",
                },
            ],
        )

    def test_rejects_missing_description(self):
        with self.assertRaisesRegex(ValueError, "missing a description"):
            llm_client._normalize_plan_steps([{"type": "analysis"}])

    @patch.object(
        llm_client,
        "chat",
        return_value=(
            '{"action":"retry","reason":"fix it",'
            '"updated_step":{"type":"script","task":"Try again"}}'
        ),
    )
    def test_analyze_result_normalizes_updated_step(self, _chat):
        decision = llm_client.analyze_result(
            "task",
            [],
            {"step": 3, "type": "script", "description": "Original"},
            "",
            "failed",
            1,
        )

        self.assertEqual(decision["action"], "retry")
        self.assertEqual(decision["updated_step"]["step"], 3)
        self.assertEqual(decision["updated_step"]["description"], "Try again")
        self.assertEqual(decision["updated_step"]["filename"], "step_3.py")


class ScriptPromptTests(unittest.TestCase):
    @patch.object(llm_client, "chat", return_value="print('ok')")
    def test_script_prompt_has_no_quant_project_assumptions(self, chat):
        llm_client.generate_script(
            "Inspect JavaScript bundles for checksum logic",
            {"README.md": "Website capture analysis"},
        )

        system_prompt = chat.call_args.args[0][0]["content"]
        self.assertNotIn("strategy", system_prompt.lower())
        self.assertNotIn("backtest", system_prompt.lower())
        self.assertIn("Never import a project-local module", system_prompt)


if __name__ == "__main__":
    unittest.main()
