import unittest
from unittest.mock import Mock, patch

from mod_translator import normalize_plamo_format_marker_output, translate_with_plamo


def completion(text):
    response = Mock(status_code=200, text="")
    response.json.return_value = {
        "choices": [{"text": text, "finish_reason": "stop"}]
    }
    return response


class PlamoFormatMarkerRecoveryTests(unittest.TestCase):
    @patch("mod_translator.requests.post")
    def test_malformed_printf_marker_is_restored_before_validation(self, post):
        source = "Set time to %s for the next day. You are now on day %s. Raw daytime is now %s."
        post.return_value = completion(
            "翌日の時刻を<mc_fmt_0>に設定する。現在は昼の%mc_fmt_1$sである。"
            "現在の昼の時刻は<mc_fmt_2>である。"
        )
        result = translate_with_plamo(
            {"time": source}, model_name="plamo-3-translate-8b-i1",
            history_size=0
        )
        self.assertEqual(
            result["time"],
            "翌日の時刻を%sに設定する。現在は昼の%sである。"
            "現在の昼の時刻は%sである。"
        )
        post.assert_called_once()

    def test_only_original_printf_conversion_is_recovered(self):
        markers = [("<mc_fmt_0>", "%s"), ("<mc_fmt_1>", "%d")]
        self.assertEqual(
            normalize_plamo_format_marker_output("%mc_fmt_0$s %mc_fmt_1$d", markers),
            "<mc_fmt_0> <mc_fmt_1>"
        )
        self.assertEqual(
            normalize_plamo_format_marker_output("%mc_fmt_0$d", markers),
            "%mc_fmt_0$d"
        )
        self.assertEqual(
            normalize_plamo_format_marker_output("%mc_fmt_0$s %mc_fmt_0$s", markers),
            "%mc_fmt_0$s %mc_fmt_0$s"
        )
        self.assertEqual(
            normalize_plamo_format_marker_output("<mc_fmt_0> %mc_fmt_0$s", markers),
            "<mc_fmt_0> %mc_fmt_0$s"
        )


if __name__ == "__main__":
    unittest.main()
