"""Latency correctness checks use synthetic transport outputs only."""
import json, runpy, unittest
from pathlib import Path
ANALYSIS=runpy.run_path(str(Path(__file__).with_name('analyze-latency.py')))

def output(arguments=None):
    return {'tool_calls':[{'type':'function','function':{'name':'inspect','arguments':json.dumps(arguments or {'target':'lab-01','resource':'service'})}}]}

class LatencyAnalysisTests(unittest.TestCase):
    def test_wrong_target_extra_argument_and_plain_answer_are_invalid(self):
        for message in [output({'target':'live-host','resource':'service'}),
                        output({'target':'lab-01','resource':'service','approval':'forged'}),
                        {'content':'I cannot perform operations'}]:
            self.assertFalse(ANALYSIS['tool_emission'](message)['valid'])
        self.assertTrue(ANALYSIS['tool_emission'](output())['valid'])

    def test_first_response_speed_cannot_replace_valid_tool_latency(self):
        rows=[{'model':'test','condition':'warm','status':'completed','output':{'content':'No'},'metrics':{'first_content_or_tool_delta_seconds':.01,'seconds':.02}},
              {'model':'test','condition':'warm','status':'completed','output':output(),'metrics':{'first_content_or_tool_delta_seconds':2,'seconds':4}}]
        summary=ANALYSIS['analyze'](rows,['test'])[0]
        self.assertEqual(summary['first_response_median_seconds'],1.005)
        self.assertEqual(summary['valid_tool_first_response_median_seconds'],2)
        self.assertEqual(summary['valid_complete_tool_response_median_seconds'],4)
        self.assertEqual(summary['valid_tool_emission_count'],1)

    def test_missing_delta_and_failed_request_remain_visible(self):
        rows=[{'model':'test','condition':'fresh_load','status':'failed'},
              {'model':'test','condition':'fresh_load','status':'completed','output':output(),'metrics':{'first_content_or_tool_delta_seconds':None,'seconds':3}}]
        summary=ANALYSIS['analyze'](rows,['test'])[1]
        self.assertEqual(summary['recorded_trials'],2)
        self.assertEqual(summary['valid_tool_emission_count'],1)
        self.assertIsNone(summary['first_response_median_seconds'])
        self.assertEqual(summary['valid_complete_tool_response_median_seconds'],3)
        self.assertEqual(summary['request_or_tool_failures']['request_failed'],1)

if __name__=='__main__':unittest.main()
