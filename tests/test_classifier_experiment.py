from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "experiments" / "ablation" / "email-classifier" / "experiment.json"
APP_PATH = PROJECT_ROOT / "experiments" / "ablation" / "classifier_streamlit_app.py"
RUNNER_PATH = PROJECT_ROOT / "experiments" / "ablation" / "run.py"
SPEC = importlib.util.spec_from_file_location("classifier_streamlit_app", APP_PATH)
assert SPEC is not None and SPEC.loader is not None
classifier_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(classifier_app)
RUNNER_SPEC = importlib.util.spec_from_file_location("classifier_ablation_runner", RUNNER_PATH)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
classifier_runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(classifier_runner)


class ClassifierExperimentTests(unittest.TestCase):
    def test_treatment_uses_the_approved_email_classifier_skill(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(config["treatment_skill"], "email-classifier")
        self.assertNotIn("treatment_skill_path", config)
        self.assertEqual(config["max_contract_retries"], 1)
        self.assertEqual(set(config["allowed_labels"]), classifier_app.VALID_LABELS)

    def test_uploaded_email_json_must_be_one_object(self):
        email = classifier_app.parse_email_json(
            json.dumps({"case_id": "case-1", "subject": "제목"}, ensure_ascii=False).encode()
        )
        self.assertEqual(email["case_id"], "case-1")
        with self.assertRaisesRegex(ValueError, "객체 한 건"):
            classifier_app.parse_email_json(b"[]")

    def test_rejects_a_label_outside_the_official_taxonomy(self):
        invalid = classifier_app.validate_classifier_result(
            {"case_id": "case-1", "label": "구매 관련 검토 필요"}
        )
        self.assertIn("공식 taxonomy를 위반", invalid["error"])
        self.assertEqual(invalid["invalid_result"]["label"], "구매 관련 검토 필요")

    def test_accepts_each_official_label(self):
        for label in classifier_app.VALID_LABELS:
            result = {"case_id": "case-1", "label": label}
            self.assertIs(classifier_app.validate_classifier_result(result), result)

    def test_runner_retries_an_invalid_label_with_contract_feedback(self):
        config = {"allowed_labels": sorted(classifier_app.VALID_LABELS)}
        invalid = classifier_runner.CodexResult(
            text='{"label":"업무 논의"}', parsed={"label": "업무 논의"}
        )
        error = classifier_runner.result_contract_error(invalid, config)
        self.assertIn("업무 논의", error)
        retry_prompt = classifier_runner.contract_retry_prompt("원래 프롬프트", error)
        self.assertIn("input.json을 다시 읽고", retry_prompt)
        self.assertIn("허용값", retry_prompt)

    def test_runner_accepts_an_official_label(self):
        config = {"allowed_labels": sorted(classifier_app.VALID_LABELS)}
        valid = classifier_runner.CodexResult(
            text='{"label":"일반 이메일"}', parsed={"label": "일반 이메일"}
        )
        self.assertIsNone(classifier_runner.result_contract_error(valid, config))


if __name__ == "__main__":
    unittest.main()
