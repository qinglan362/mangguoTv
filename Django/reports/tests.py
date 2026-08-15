"""reports 模块报告生成测试。"""
from django.test import TestCase

from reports.models import Report
from reports.services.report_service import _period_range, generate_report
from topics.models import Topic


class ReportGenerationTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(name="报表主题", platforms=["mock"])

    def test_generate_daily_report(self):
        """生成日报：报告落库，状态 done。"""
        report = generate_report(self.topic, "daily")
        self.assertEqual(report.status, "done")
        self.assertTrue(Report.objects.filter(topic=self.topic, period_type="daily").exists())
        self.assertTrue(report.summary)

    def test_period_range_daily_is_full_day(self):
        """M17：日报统计窗口锚定 report_date 全天，而非仅当下时刻。"""
        from datetime import date
        from django.utils import timezone

        start, end = _period_range("daily", date(2026, 8, 1))
        self.assertEqual(start.date(), date(2026, 8, 1))
        self.assertEqual(end - start, timezone.timedelta(days=1))
