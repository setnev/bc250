"""Prevent misleading aggregate throughput and invented timing coverage."""
from pathlib import Path
import runpy
import unittest

summarize = runpy.run_path(str(Path(__file__).with_name('catalog-results.py')))['inference_performance']


class PerformanceAccounting(unittest.TestCase):
    def test_unequal_duration_turns_use_total_runtime_work(self):
        rows = [{'assistant': {'content': 'x'}, 'timings': {'predicted_n': n, 'predicted_ms': t}}
                for n, t in [(10, 100), (90, 300)]]
        result = summarize(rows)['decode']
        self.assertEqual(result['tokens_per_second_from_totals'], 250)
        self.assertEqual(result['recorded_tokens'], 100)

    def test_missing_or_failed_request_is_not_zero_latency_or_throughput(self):
        rows = [{'assistant': {'content': 'x'}, 'timings': {'predicted_n': 7}},
                {'assistant': {'content': 'y'}, 'timings': {'predicted_n': 8, 'predicted_ms': 0}},
                {'inference_error': 'HTTPError'}]
        result = summarize(rows)
        self.assertIsNone(result['decode']['tokens_per_second_from_totals'])
        self.assertEqual(result['decode']['responses_without_usable_paired_runtime_timings'], 2)
        self.assertEqual(result['first_content_or_tool_delta_samples'], 0)
        self.assertIsNone(result['first_content_or_tool_delta_median_seconds'])
        self.assertEqual(result['inference_errors'], 1)

    def test_cached_tokens_do_not_inflate_uncached_prefill_rate(self):
        row = {'assistant': {'content': 'x'},
               'timings': {'prompt_n': 10, 'prompt_ms': 100, 'cache_n': 990},
               'first_content_or_tool_delta_seconds': 2}
        result = summarize([row])
        self.assertEqual(result['uncached_prefill']['tokens_per_second_from_totals'], 100)
        self.assertEqual(result['recorded_cached_prompt_tokens'], 990)
        self.assertEqual(result['first_content_or_tool_delta_p95_seconds'], 2)


if __name__ == '__main__':
    unittest.main()
