from django.test import TestCase

from apps.industry.models import Chain, Job

from .models import CrawlSource, CrawlTask, JobListing
from .services import save_crawl_result


class ListingDeduplicationTests(TestCase):
    def test_same_listing_is_updated_instead_of_duplicated(self):
        chain = Chain.objects.create(name="采集测试产业链")
        job = Job.objects.create(
            chain=chain,
            name="采集测试岗位",
            search_keywords=["采集测试岗位", "测试操作", "测试维护"],
        )
        source = CrawlSource.objects.create(
            name="测试招聘来源",
            code="test_source",
            base_url="https://example.com",
        )
        first_task = CrawlTask.objects.create(job=job, source=source)
        second_task = CrawlTask.objects.create(job=job, source=source)
        item = {
            "title": "采集测试岗位",
            "company": "测试公司",
            "city": "杭州",
            "requirements": "负责测试设备操作、调试与维护工作。",
            "source_url": "https://example.com/jobs/1",
        }

        _, first_created = save_crawl_result(first_task, item)
        listing, second_created = save_crawl_result(second_task, item)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(JobListing.objects.count(), 1)
        self.assertEqual(listing.task_id, second_task.id)
