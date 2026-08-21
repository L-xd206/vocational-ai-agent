import json
from unittest.mock import patch

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.capabilities.services import merge_official_tree
from apps.industry.models import Chain, Job
from apps.organizations.models import Organization

from .models import AnalysisBatch, AnalysisNode, CrawlSource, CrawlTask, JobListing
from .services import (
    adopt_analysis_node,
    create_crawl_source,
    create_analysis_batch,
    create_crawl_task,
    reject_analysis_node,
    save_crawl_result,
    serialize_analysis_tree,
    serialize_pending_analysis_batches,
    serialize_rejected_tree,
)
from .tasks import execute_analysis_batch, execute_crawl_task, start_analysis_for_task


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
        first_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        second_task = CrawlTask.objects.create(job=job, source=source, status="completed")
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
        self.assertEqual(listing.task_id, first_task.id)

    def test_repeated_listings_do_not_count_as_new_analysis_input(self):
        chain = Chain.objects.create(name="增量校验产业链")
        job = Job.objects.create(chain=chain, name="增量校验岗位", search_keywords=["增量校验"])
        source = CrawlSource.objects.create(
            name="增量校验来源", code="incremental_source", base_url="https://example.com"
        )
        first_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        second_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        item = {
            "title": job.name,
            "company": "同一家企业",
            "requirements": "这是足够长的重复招聘岗位任职要求，用于验证增量数据校验。",
            "source_url": "https://example.com/same-job",
        }
        save_crawl_result(first_task, item)
        _, created = save_crawl_result(second_task, item)

        from .services import valid_requirements

        self.assertFalse(created)
        self.assertEqual(valid_requirements(second_task, new_only=True), [])
        self.assertEqual(len(valid_requirements(first_task, new_only=True)), 1)

        batch = start_analysis_for_task(second_task.id)
        self.assertEqual(batch.status, "skipped")
        self.assertEqual(batch.input_listing_count, 0)
        self.assertIn("暂无有效招聘数据", batch.error_message)

    def test_legacy_listing_without_source_is_still_deduplicated(self):
        chain = Chain.objects.create(name="历史数据去重产业链")
        job = Job.objects.create(chain=chain, name="历史数据去重岗位", search_keywords=["去重"])
        source = CrawlSource.objects.create(
            name="历史数据去重来源", code="legacy_source", base_url="https://example.com"
        )
        old_task = CrawlTask.objects.create(job=job, status="completed")
        new_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        item = {
            "title": job.name,
            "company": "历史企业",
            "requirements": "这是历史数据库中没有采集源外键但具有相同指纹的招聘要求。",
            "source_url": "https://example.com/legacy-job",
        }
        from .services import build_listing_fingerprint, valid_requirements

        JobListing.objects.create(
            task=old_task,
            job=job,
            crawl_source=None,
            fingerprint=build_listing_fingerprint(item),
            title=item["title"],
            company=item["company"],
            requirements=item["requirements"],
            source_url=item["source_url"],
        )
        listing, created = save_crawl_result(new_task, item)

        self.assertFalse(created)
        self.assertEqual(listing.task_id, old_task.id)
        self.assertEqual(JobListing.objects.filter(job=job).count(), 1)
        self.assertEqual(valid_requirements(new_task, new_only=True), [])

    def test_same_requirement_with_different_company_and_title_is_not_new(self):
        chain = Chain.objects.create(name="正文去重产业链")
        job = Job.objects.create(chain=chain, name="正文去重岗位")
        source = CrawlSource.objects.create(
            name="正文去重来源", code="content_source", base_url="https://example.com"
        )
        first_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        second_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        requirement = "负责数控设备操作、程序调试以及设备日常维护保养工作。"
        first, first_created = save_crawl_result(first_task, {
            "title": "数控操作员", "company": "甲公司", "city": "杭州",
            "requirements": requirement,
        })
        second, second_created = save_crawl_result(second_task, {
            "title": "CNC技术员", "company": "乙公司", "city": "宁波",
            "requirements": requirement,
        })

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(JobListing.objects.filter(job=job).count(), 1)
        self.assertEqual(second.task_id, first_task.id)

    def test_punctuation_and_tiny_requirement_changes_do_not_reenter_ai(self):
        chain = Chain.objects.create(name="近似正文去重产业链")
        job = Job.objects.create(chain=chain, name="近似正文去重岗位")
        source = CrawlSource.objects.create(
            name="近似正文来源", code="similar_content_source", base_url="https://example.com"
        )
        first_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        second_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        save_crawl_result(first_task, {
            "title": job.name,
            "company": "甲公司",
            "requirements": "负责数控车床操作、程序调试、产品检测以及设备日常维护保养。",
        })
        _, created = save_crawl_result(second_task, {
            "title": job.name,
            "company": "乙公司",
            "requirements": "负责数控车床操作，程序调试，产品检测，以及设备日常维护保养！",
        })

        from .services import valid_requirements

        self.assertFalse(created)
        self.assertEqual(valid_requirements(second_task, new_only=True), [])


class CrawlSourceAndTaskTests(TestCase):
    def setUp(self):
        self.chain = Chain.objects.create(name="任务测试产业链")
        self.job = Job.objects.create(
            chain=self.chain,
            name="任务测试岗位",
            search_keywords=["任务测试岗位"],
        )
        self.source = CrawlSource.objects.get(code="mohrss")

    def test_unregistered_source_code_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "尚未实现对应采集器"):
            create_crawl_source({
                "name": "尚未实现的网站",
                "code": "not_implemented",
                "base_url": "https://example.com",
                "interval_minutes": 1440,
                "pages": 3,
            })

    def test_source_update_keeps_identity_and_url_immutable(self):
        from .services import update_crawl_source

        original = (self.source.name, self.source.code, self.source.base_url)
        update_crawl_source(self.source, {
            "name": "被篡改的名称",
            "code": "not_implemented",
            "base_url": "https://example.com/changed",
            "interval_minutes": 60,
            "pages": 2,
            "is_enabled": False,
        })
        self.source.refresh_from_db()
        self.assertEqual(
            (self.source.name, self.source.code, self.source.base_url),
            original,
        )
        self.assertEqual(self.source.interval_minutes, 60)
        self.assertEqual(self.source.config_json["pages"], 2)
        self.assertFalse(self.source.is_enabled)

    def test_same_job_and_source_reuses_active_task(self):
        first, first_created = create_crawl_task(
            job=self.job, source=self.source, trigger_type="manual"
        )
        second, second_created = create_crawl_task(
            job=self.job, source=self.source, trigger_type="scheduled"
        )
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)

    @patch("apps.collection.tasks.start_analysis_for_task")
    @patch("apps.collection.crawlers.registry.get_crawler")
    def test_new_results_trigger_analysis(self, crawler_getter, analysis_mock):
        crawler_getter.return_value.crawl.return_value = [{
            "title": "任务测试岗位",
            "company": "测试公司",
            "requirements": "负责测试设备的运行、维护和故障处理工作。",
            "source_url": "https://example.com/job/1",
        }]
        task, _ = create_crawl_task(
            job=self.job, source=self.source, trigger_type="manual"
        )
        execute_crawl_task(task.id)
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.new_results, 1)
        analysis_mock.assert_called_once_with(task.id)

    def test_insufficient_data_creates_skipped_analysis(self):
        task = CrawlTask.objects.create(
            job=self.job,
            source=self.source,
            status="completed",
        )
        batch = start_analysis_for_task(task.id)
        self.assertEqual(batch.status, "skipped")
        self.assertIn("暂不生成能力图谱", batch.error_message)

    @patch("apps.collection.management.commands.run_due_crawls.execute_crawl_task")
    def test_due_command_schedules_only_enabled_jobs(self, execute_mock):
        Job.objects.create(
            chain=self.chain,
            name="已禁用岗位",
            search_keywords=["已禁用岗位"],
            is_enabled=False,
        )
        self.source.is_enabled = True
        self.source.next_run_at = timezone.now()
        self.source.save(update_fields=["is_enabled", "next_run_at"])

        call_command("run_due_crawls")

        tasks = CrawlTask.objects.filter(trigger_type="scheduled")
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().job_id, self.job.id)
        execute_mock.assert_called_once()

    def test_mock_collection_command_creates_completed_task_and_valid_listings(self):
        self.job.name = "工业机器人编程与操作员"
        self.job.save(update_fields=["name"])

        call_command("seed_mock_collection")

        task = CrawlTask.objects.get(job=self.job, trigger_type="manual")
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.total_results, 15)
        self.assertEqual(task.listings.count(), 15)
        self.assertEqual(len(task.results_json), 15)
        self.assertTrue(all(item["mock_data"] for item in task.results_json))

    def test_latest_trees_returns_enabled_jobs_and_latest_batch(self):
        user = get_user_model().objects.create_user(username="collection-reader")
        self.client.force_login(user)
        older = AnalysisBatch.objects.create(job=self.job, status="failed")
        latest = AnalysisBatch.objects.create(job=self.job, status="completed")
        ability = AnalysisNode.objects.create(
            batch=latest,
            node_type="ability",
            name="最新岗位能力",
            normalized_name="最新岗位能力",
        )
        unit = AnalysisNode.objects.create(
            batch=latest,
            parent=ability,
            node_type="unit",
            name="最新能力单元",
        )
        AnalysisNode.objects.create(
            batch=latest,
            parent=unit,
            node_type="point",
            name="最新候选知识点",
        )

        response = self.client.get("/api/collection/analysis/latest-trees")

        self.assertEqual(response.status_code, 200)
        item = next(
            row for row in response.json()["results"]
            if row["job"]["id"] == self.job.id
        )
        self.assertEqual(item["batch"]["id"], latest.id)
        self.assertNotEqual(item["batch"]["id"], older.id)
        self.assertEqual(item["tree"][0]["name"], "最新岗位能力")

    def test_collection_pages_require_login_and_render_after_login(self):
        for url in ["/岗位数据采集.html", "/未采纳数据.html"]:
            self.assertEqual(self.client.get(url).status_code, 302)

        user = get_user_model().objects.create_user(username="collection-page-reader")
        self.client.force_login(user)
        self.assertContains(self.client.get("/岗位数据采集.html"), "岗位数据采集")
        self.assertContains(self.client.get("/未采纳数据.html"), "未采纳数据")


class CollectionApiContractTests(TestCase):
    """锁定岗位采集前端依赖的 JSON 契约，防止后端改动悄悄弄坏页面。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="contract-reader")
        self.client.force_login(self.user)
        self.chain = Chain.objects.create(name="接口契约产业链")
        self.job = Job.objects.create(
            chain=self.chain,
            name="接口契约岗位",
            search_keywords=["接口契约岗位"],
        )
        self.source = CrawlSource.objects.get(code="mohrss")

    def test_source_contract_and_patch_only_update_runtime_fields(self):
        source_response = self.client.get("/api/collection/sources")
        self.assertEqual(source_response.status_code, 200)
        source = source_response.json()["sources"][0]
        self.assertEqual(
            set(source),
            {
                "id", "name", "code", "base_url", "interval_minutes", "pages",
                "is_enabled", "last_run_at", "next_run_at", "created_at", "updated_at",
            },
        )

        response = self.client.patch(
            f"/api/collection/sources/{self.source.id}",
            data=json.dumps({
                "name": "恶意修改名称",
                "code": "not_implemented",
                "base_url": "https://invalid.example.com",
                "interval_minutes": 90,
                "pages": 4,
                "is_enabled": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["source"]
        self.assertEqual(updated["name"], "中国公共招聘网")
        self.assertEqual(updated["code"], "mohrss")
        self.assertEqual(updated["base_url"], "http://job.mohrss.gov.cn")
        self.assertEqual(updated["interval_minutes"], 90)
        self.assertEqual(updated["pages"], 4)
        self.assertFalse(updated["is_enabled"])

    def test_mutation_endpoints_reject_non_object_json_instead_of_500(self):
        source_response = self.client.patch(
            f"/api/collection/sources/{self.source.id}",
            data="[]",
            content_type="application/json",
        )
        crawl_response = self.client.post(
            "/api/crawl/start",
            data="[]",
            content_type="application/json",
        )
        analysis_response = self.client.post(
            "/api/collection/analysis/start",
            data="[]",
            content_type="application/json",
        )
        for response in [source_response, crawl_response, analysis_response]:
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"], "JSON 请求体必须是对象")

    def test_collection_apis_require_login(self):
        self.client.logout()
        for url in [
            "/api/collection/sources",
            "/api/collection/tasks",
            "/api/collection/analysis/latest-trees",
            "/api/collection/rejected-nodes",
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login.html", response.url)

    def test_duplicate_crawl_start_returns_existing_task_contract(self):
        active = CrawlTask.objects.create(
            job=self.job,
            source=self.source,
            status="running",
        )
        response = self.client.post(
            "/api/crawl/start",
            data=json.dumps({"job_id": self.job.id, "source_id": self.source.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["task_id"], active.id)
        self.assertEqual(response.json()["status"], "running")

    def test_candidate_tree_contract_marks_real_and_virtual_nodes(self):
        merge_official_tree(self.job, [{
            "name": "已有岗位能力",
            "college": "未分配学院",
            "units": [{"name": "已有能力单元", "children": []}],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "已有岗位能力",
            "college": "未分配学院",
            "units": [{
                "name": "已有能力单元",
                "children": [{"name": "AI新增知识点", "evidence": ["招聘要求证据"]}],
            }],
        }])

        response = self.client.get("/api/collection/analysis/latest-trees")
        self.assertEqual(response.status_code, 200)
        item = next(row for row in response.json()["results"] if row["job"]["id"] == self.job.id)
        ability = item["tree"][0]
        unit = ability["children"][0]
        point = unit["children"][0]
        self.assertEqual(item["batch"]["id"], batch.id)
        self.assertFalse(ability["is_virtual"])
        self.assertFalse(unit["is_virtual"])
        self.assertTrue(point["is_virtual"])
        self.assertEqual(point["decision_status"], "pending")
        self.assertIn("evidence", point)

    def test_string_evidence_is_normalized_for_frontend(self):
        batch = create_analysis_batch(self.job, [{
            "name": "证据格式岗位能力",
            "units": [{
                "name": "证据格式能力单元",
                "children": [{"name": "证据格式知识点", "evidence": "来自招聘正文"}],
            }],
        }])

        point = batch.nodes.get(name="证据格式知识点")
        self.assertEqual(point.evidence_json, ["来自招聘正文"])
        tree = serialize_analysis_tree(batch)
        self.assertEqual(
            tree[0]["children"][0]["children"][0]["evidence"],
            [{"text": "来自招聘正文"}],
        )

    def test_evidence_reference_is_enriched_from_existing_listing_fields(self):
        task = CrawlTask.objects.create(
            job=self.job,
            source=self.source,
            status="completed",
        )
        listing = JobListing.objects.create(
            task=task,
            job=self.job,
            crawl_source=self.source,
            fingerprint="evidence-source-listing",
            title="来源追溯测试岗位",
            company="来源追溯测试企业",
            source_url="https://example.com/jobs/evidence-1",
            requirements="这是用于验证能力节点来源追溯信息的完整招聘要求正文",
        )
        batch = create_analysis_batch(self.job, [{
            "name": "来源追溯岗位能力",
            "units": [{
                "name": "来源追溯能力单元",
                "children": [{
                    "name": "来源追溯知识点",
                    "evidence": "招聘要求[1]：来源追溯测试证据",
                }],
            }],
        }], crawl_task=task)

        detail = serialize_analysis_tree(batch)[0]["children"][0]["children"][0]["evidence"][0]
        self.assertEqual(detail["source_name"], self.source.name)
        self.assertEqual(detail["source_url"], listing.source_url)
        self.assertEqual(detail["captured_at"], listing.first_seen_at.isoformat())
        self.assertEqual(detail["job_title"], listing.title)

    def test_pending_candidates_are_merged_across_batches_by_latest_path_state(self):
        first = create_analysis_batch(self.job, [{
            "name": "跨批次岗位能力",
            "units": [{
                "name": "跨批次能力单元",
                "children": [
                    {"name": "旧批次独有知识点"},
                    {"name": "重复候选知识点"},
                ],
            }],
        }])
        second = create_analysis_batch(self.job, [{
            "name": "跨批次岗位能力",
            "units": [{
                "name": "跨批次能力单元",
                "children": [
                    {"name": "重复候选知识点"},
                    {"name": "新批次独有知识点"},
                ],
            }],
        }])
        reject_analysis_node(second.nodes.get(name="重复候选知识点"))

        tree = serialize_pending_analysis_batches([second, first])
        names = {
            point["name"]
            for ability in tree
            for unit in ability["children"]
            for point in unit["children"]
        }
        self.assertEqual(names, {"旧批次独有知识点", "新批次独有知识点"})

        response = self.client.get("/api/collection/analysis/latest-trees")
        item = next(
            row for row in response.json()["results"]
            if row["job"]["id"] == self.job.id
        )
        self.assertEqual(item["batch"]["id"], second.id)
        api_names = {
            point["name"]
            for ability in item["tree"]
            for unit in ability["children"]
            for point in unit["children"]
        }
        self.assertEqual(api_names, names)

    def test_candidate_tree_hides_existing_leaves_and_keeps_only_new_paths(self):
        merge_official_tree(self.job, [{
            "name": "Existing ability",
            "college": "Unassigned college",
            "units": [
                {
                    "name": "Unit with new child",
                    "children": [
                        {"name": "Existing point"},
                    ],
                },
                {
                    "name": "Entirely existing unit",
                    "children": [
                        {"name": "Another existing point"},
                    ],
                },
            ],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "Existing ability",
            "college": "Unassigned college",
            "units": [
                {
                    "name": "Unit with new child",
                    "children": [
                        {"name": "Existing point"},
                        {"name": "New AI point"},
                    ],
                },
                {
                    "name": "Entirely existing unit",
                    "children": [
                        {"name": "Another existing point"},
                    ],
                },
            ],
        }])

        tree = serialize_analysis_tree(batch)

        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["name"], "Existing ability")
        self.assertFalse(tree[0]["is_virtual"])
        self.assertEqual(len(tree[0]["children"]), 1)
        unit = tree[0]["children"][0]
        self.assertEqual(unit["name"], "Unit with new child")
        self.assertFalse(unit["is_virtual"])
        self.assertEqual([point["name"] for point in unit["children"]], ["New AI point"])
        self.assertTrue(unit["children"][0]["is_virtual"])

    def test_adopt_endpoint_updates_official_tree_and_candidate_state(self):
        batch = create_analysis_batch(self.job, [{
            "name": "AI岗位能力",
            "college": "未分配学院",
            "units": [{"name": "AI能力单元", "children": [{"name": "AI知识点"}]}],
        }])
        point = batch.nodes.get(node_type="point")

        response = self.client.post(f"/api/collection/analysis/nodes/{point.id}/adopt")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["decision_status"], "adopted")
        self.assertTrue(payload["matched_node_id"])
        self.assertEqual(payload["abilities"][0]["units"][0]["children"][0]["name"], "AI知识点")

        point.refresh_from_db()
        self.assertEqual(point.decision_status, "adopted")
        self.assertIsNotNone(point.matched_node_id)

    def test_reject_endpoint_moves_subtree_to_rejected_contract(self):
        batch = create_analysis_batch(self.job, [{
            "name": "待拒纳岗位能力",
            "college": "未分配学院",
            "units": [{"name": "待拒纳能力单元", "children": [{"name": "待拒纳知识点"}]}],
        }])
        unit = batch.nodes.get(node_type="unit")

        response = self.client.post(f"/api/collection/analysis/nodes/{unit.id}/reject")
        self.assertEqual(response.status_code, 200)
        rejected = self.client.get(f"/api/collection/rejected-nodes?job_id={self.job.id}")
        self.assertEqual(rejected.status_code, 200)
        tree = rejected.json()["results"][0]["tree"]
        self.assertTrue(tree[0]["context_only"])
        self.assertFalse(tree[0]["children"][0]["context_only"])
        self.assertFalse(tree[0]["children"][0]["children"][0]["context_only"])

    def test_rejected_api_merges_multiple_batches_for_the_same_job_by_path(self):
        first = create_analysis_batch(self.job, [{
            "name": "工业机器人安全防护",
            "units": [{
                "name": "执行作业前安全检查",
                "children": [
                    {"name": "检查安全门联锁"},
                    {"name": "测试急停按钮"},
                ],
            }],
        }])
        reject_analysis_node(first.nodes.get(name="执行作业前安全检查"))

        second = create_analysis_batch(self.job, [{
            "name": "工业机器人安全防护",
            "units": [
                {
                    "name": "执行作业前安全检查",
                    "children": [{"name": "验证安全光栅"}],
                },
                {
                    "name": "配置作业现场环境",
                    "children": [{"name": "清理作业区域杂物"}],
                },
            ],
        }])
        reject_analysis_node(second.nodes.get(name="验证安全光栅"))
        reject_analysis_node(second.nodes.get(name="配置作业现场环境"))

        response = self.client.get(f"/api/collection/rejected-nodes?job_id={self.job.id}")

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(set(results[0]["batch_ids"]), {first.id, second.id})
        ability = results[0]["tree"][0]
        self.assertEqual(len(ability["children"]), 2)
        safety_unit = next(
            unit for unit in ability["children"]
            if unit["name"] == "执行作业前安全检查"
        )
        self.assertEqual(
            {point["name"] for point in safety_unit["children"]},
            {"检查安全门联锁", "测试急停按钮", "验证安全光栅"},
        )

    def test_restore_rejected_node_returns_it_to_candidate_page_without_adopting(self):
        batch = create_analysis_batch(self.job, [{
            "name": "待恢复岗位能力",
            "units": [{
                "name": "待恢复能力单元",
                "children": [{"name": "待恢复知识点"}],
            }],
        }])
        point = batch.nodes.get(name="待恢复知识点")
        reject_analysis_node(point)

        response = self.client.post(
            f"/api/collection/analysis/nodes/{point.id}/restore"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("尚未写入正式能力图谱", response.json()["message"])
        point.refresh_from_db()
        self.assertEqual(point.decision_status, "pending")
        self.assertIsNone(point.matched_node_id)
        candidate = self.client.get("/api/collection/analysis/latest-trees").json()
        item = next(row for row in candidate["results"] if row["job"]["id"] == self.job.id)
        self.assertEqual(
            item["tree"][0]["children"][0]["children"][0]["name"],
            "待恢复知识点",
        )
        rejected = self.client.get(
            f"/api/collection/rejected-nodes?job_id={self.job.id}"
        ).json()
        self.assertEqual(rejected["results"], [])

    def test_restoring_rejected_leaf_also_restores_required_parent_path(self):
        batch = create_analysis_batch(self.job, [{
            "name": "父路径恢复岗位能力",
            "units": [{
                "name": "父路径恢复能力单元",
                "children": [
                    {"name": "需要恢复的叶子"},
                    {"name": "继续拒纳的叶子"},
                ],
            }],
        }])
        unit = batch.nodes.get(name="父路径恢复能力单元")
        point = batch.nodes.get(name="需要恢复的叶子")
        reject_analysis_node(unit)

        response = self.client.post(
            f"/api/collection/analysis/nodes/{point.id}/restore"
        )

        self.assertEqual(response.status_code, 200)
        unit.refresh_from_db()
        point.refresh_from_db()
        self.assertEqual(unit.decision_status, "pending")
        self.assertEqual(point.decision_status, "pending")
        candidate = self.client.get("/api/collection/analysis/latest-trees").json()
        item = next(row for row in candidate["results"] if row["job"]["id"] == self.job.id)
        self.assertEqual(
            item["tree"][0]["children"][0]["children"][0]["name"],
            "需要恢复的叶子",
        )

    def test_restore_from_old_batch_copies_path_into_latest_batch(self):
        old = create_analysis_batch(self.job, [{
            "name": "历史岗位能力",
            "units": [{
                "name": "历史能力单元",
                "children": [{"name": "历史拒纳知识点"}],
            }],
        }])
        old_point = old.nodes.get(name="历史拒纳知识点")
        reject_analysis_node(old_point)
        latest = create_analysis_batch(self.job, [{
            "name": "当前岗位能力",
            "units": [{"name": "当前能力单元", "children": [{"name": "当前知识点"}]}],
        }])

        response = self.client.post(
            f"/api/collection/analysis/nodes/{old_point.id}/restore"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["batch_id"], latest.id)
        copied = latest.nodes.get(name="历史拒纳知识点")
        self.assertEqual(copied.decision_status, "pending")
        self.assertEqual(copied.parent.name, "历史能力单元")
        self.assertEqual(copied.parent.parent.name, "历史岗位能力")
        old_point.refresh_from_db()
        self.assertEqual(old_point.decision_status, "restored")
        self.assertIsNone(old_point.matched_node_id)

    def test_collection_mutations_require_csrf_token(self):
        batch = create_analysis_batch(self.job, [{
            "name": "CSRF岗位能力",
            "units": [{
                "name": "CSRF能力单元",
                "children": [{"name": "CSRF知识点"}],
            }],
        }])
        point = batch.nodes.get(name="CSRF知识点")
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        rejected = csrf_client.post(
            f"/api/collection/analysis/nodes/{point.id}/reject"
        )
        self.assertEqual(rejected.status_code, 403)

        page = csrf_client.get("/岗位数据采集.html")
        self.assertEqual(page.status_code, 200)
        token = csrf_client.cookies["csrftoken"].value
        accepted = csrf_client.post(
            f"/api/collection/analysis/nodes/{point.id}/reject",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 200)

    def test_crawl_status_contract_contains_analysis_state(self):
        task = CrawlTask.objects.create(
            job=self.job,
            source=self.source,
            status="completed",
            total_results=18,
            new_results=7,
        )
        batch = AnalysisBatch.objects.create(
            job=self.job,
            crawl_task=task,
            status="processing",
        )
        response = self.client.get(f"/api/crawl/{task.id}/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["total_results"], 18)
        self.assertEqual(payload["new_results"], 7)
        self.assertEqual(payload["analysis"], {
            "id": batch.id,
            "status": "processing",
            "error_message": "",
        })


class CandidateAnalysisServicesTests(TestCase):
    def setUp(self):
        chain = Chain.objects.create(name="候选分析测试产业链")
        self.job = Job.objects.create(
            chain=chain,
            name="工业机器人操作员",
            search_keywords=["工业机器人操作员", "机器人调试", "机器人运维"],
        )
        self.college = Organization.objects.create(
            name="候选分析测试学院",
            org_type="学院",
        )

    def test_candidate_match_and_adopt(self):
        merge_official_tree(self.job, [{
            "name": "机器人系统调试",
            "college": self.college.name,
            "units": [{"name": "本体调试", "children": []}],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "机器人系统调试",
            "college": self.college.name,
            "units": [{
                "name": "本体调试",
                "children": [{"name": "关节零点校准"}],
            }],
        }])

        ability = batch.nodes.get(node_type="ability")
        unit = batch.nodes.get(node_type="unit")
        point = batch.nodes.get(node_type="point")
        self.assertIsNotNone(ability.matched_node_id)
        self.assertIsNotNone(unit.matched_node_id)
        self.assertIsNone(point.matched_node_id)

        official = adopt_analysis_node(point)
        point.refresh_from_db()
        self.assertEqual(point.decision_status, "adopted")
        self.assertEqual(point.matched_node_id, official.id)
        self.assertEqual(official.node_type, "point")

    def test_reject_cascades_to_virtual_children(self):
        batch = create_analysis_batch(self.job, [{
            "name": "全新岗位能力",
            "college": self.college.name,
            "units": [{
                "name": "全新能力单元",
                "children": [{"name": "全新知识点"}],
            }],
        }])
        root = batch.nodes.get(node_type="ability")
        reject_analysis_node(root)
        self.assertFalse(
            AnalysisNode.objects.filter(batch=batch).exclude(decision_status="rejected").exists()
        )

    def test_rejected_leaf_keeps_ancestor_context(self):
        batch = create_analysis_batch(self.job, [{
            "name": "候选岗位能力",
            "college": self.college.name,
            "units": [{
                "name": "候选能力单元",
                "children": [{"name": "被拒纳知识点"}],
            }],
        }])
        point = batch.nodes.get(node_type="point")
        reject_analysis_node(point)

        tree = serialize_rejected_tree(batch)
        self.assertEqual(tree[0]["name"], "候选岗位能力")
        self.assertTrue(tree[0]["context_only"])
        self.assertEqual(tree[0]["children"][0]["name"], "候选能力单元")
        leaf = tree[0]["children"][0]["children"][0]
        self.assertEqual(leaf["name"], "被拒纳知识点")
        self.assertFalse(leaf["context_only"])

    def test_placeholder_unit_matches_only_with_clear_official_point_evidence(self):
        merge_official_tree(self.job, [{
            "name": "机器人操作",
            "college": self.college.name,
            "units": [
                {"name": "能力单元 1", "children": [{"name": "示教器程序编辑"}]},
                {"name": "能力单元 2", "children": [{"name": "控制柜故障复位"}]},
            ],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "机器人操作",
            "college": self.college.name,
            "units": [{
                "name": "示教编程",
                "children": [
                    {"name": "示教器程序编辑"},
                    {"name": "新增轨迹调试"},
                ],
            }],
        }])

        unit = batch.nodes.get(node_type="unit")
        existing_point = batch.nodes.get(name="示教器程序编辑")
        new_point = batch.nodes.get(name="新增轨迹调试")
        self.assertEqual(unit.matched_node.name, "能力单元 1")
        self.assertIsNotNone(existing_point.matched_node_id)
        self.assertIsNone(new_point.matched_node_id)

    def test_high_confidence_point_paraphrase_matches_but_ambiguous_name_stays_virtual(self):
        merge_official_tree(self.job, [{
            "name": "机器人维护",
            "college": self.college.name,
            "units": [{
                "name": "能力单元 1",
                "children": [
                    {"name": "按照设备说明书完成每日润滑液压电气系统检查"},
                    {"name": "设备运行检查"},
                    {"name": "设备状态检查"},
                ],
            }],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "机器人维护",
            "college": self.college.name,
            "units": [{
                "name": "日常点检",
                "children": [
                    {"name": "按照设备说明书完成每日润滑、液压、电气系统检查"},
                    {"name": "设备检查"},
                ],
            }],
        }])

        clear = batch.nodes.get(name="按照设备说明书完成每日润滑、液压、电气系统检查")
        ambiguous = batch.nodes.get(name="设备检查")
        self.assertIsNotNone(clear.matched_node_id)
        self.assertIsNone(ambiguous.matched_node_id)

    def test_existing_point_matches_across_different_ai_unit(self):
        merge_official_tree(self.job, [{
            "name": "机器人安全操作",
            "college": self.college.name,
            "units": [{
                "name": "能力单元 1",
                "children": [{
                    "name": "维护设备时严格执行断电操作并悬挂警示标识"
                }],
            }],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "机器人安全操作",
            "college": self.college.name,
            "units": [{
                "name": "AI重新划分的安全维护单元",
                "children": [{
                    "name": "维护设备时严格执行断电操作并悬挂警示标识"
                }],
            }],
        }])

        point = batch.nodes.get(node_type="point")
        unit = batch.nodes.get(node_type="unit")
        self.assertIsNotNone(point.matched_node_id)
        self.assertEqual(point.decision_status, "not_required")
        self.assertIsNotNone(unit.matched_node_id)
        self.assertEqual(unit.decision_status, "not_required")

    def test_global_high_similarity_point_is_not_added_but_lower_similarity_remains_new(self):
        merge_official_tree(self.job, [{
            "name": "机器人测量",
            "college": self.college.name,
            "units": [{
                "name": "能力单元 1",
                "children": [{
                    "name": "使用百分表，检测工件装夹后的跳动误差，调整装夹状态"
                }],
            }],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "机器人测量",
            "college": self.college.name,
            "units": [{
                "name": "AI测量单元",
                "children": [
                    {"name": "使用百分表检测工件装夹后的跳动误差，调整装夹状态"},
                    {"name": "使用激光跟踪仪完成机器人空间精度标定"},
                ],
            }],
        }])

        similar = batch.nodes.get(name="使用百分表检测工件装夹后的跳动误差，调整装夹状态")
        new_point = batch.nodes.get(name="使用激光跟踪仪完成机器人空间精度标定")
        self.assertIsNotNone(similar.matched_node_id)
        self.assertIsNone(new_point.matched_node_id)

    def test_parenthetical_detail_does_not_create_duplicate_point(self):
        merge_official_tree(self.job, [{
            "name": "数控加工",
            "college": self.college.name,
            "units": [{
                "name": "切削参数调整",
                "children": [{
                    "name": "根据加工材料与刀具特性，优化切削参数（主轴转速、进给量、背吃刀量），提升加工效率与刀具寿命"
                }],
            }],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "数控加工",
            "units": [{
                "name": "切削参数优化",
                "children": [{
                    "name": "根据加工材料与刀具特性，优化切削参数，提升加工效率与刀具寿命"
                }],
            }],
        }])

        point = batch.nodes.get(node_type="point")
        self.assertIsNotNone(point.matched_node_id)
        self.assertEqual(serialize_analysis_tree(batch), [])

    def test_unmatched_empty_parent_is_not_shown_as_new_candidate(self):
        merge_official_tree(self.job, [
            {
                "name": "设备操作",
                "college": self.college.name,
                "units": [{
                    "name": "正式能力单元",
                    "children": [{"name": "完成设备参数设置"}],
                }],
            },
            {
                "name": "安全检查",
                "college": self.college.name,
                "units": [{
                    "name": "安全检查单元",
                    "children": [{"name": "完成设备开机前安全检查"}],
                }],
            },
        ])
        batch = create_analysis_batch(self.job, [{
            "name": "设备操作",
            "units": [{
                "name": "AI重新命名但没有新增叶子的单元",
                "children": [{"name": "完成设备开机前安全检查"}],
            }],
        }])

        unit = batch.nodes.get(node_type="unit")
        self.assertIsNone(unit.matched_node_id)
        self.assertEqual(serialize_analysis_tree(batch), [])

    @patch("ai.services.generate_capability_map")
    def test_candidate_analysis_sends_official_tree_to_ai(self, generate_mock):
        merge_official_tree(self.job, [{
            "name": "机器人维护",
            "college": self.college.name,
            "units": [{
                "name": "机器人本体维护",
                "children": [{"name": "关节润滑"}],
            }],
        }])
        source = CrawlSource.objects.create(
            name="候选分析测试来源",
            code="candidate_analysis_source",
            base_url="https://example.com",
        )
        task = CrawlTask.objects.create(job=self.job, source=source, status="completed")
        for index in range(10):
            JobListing.objects.create(
                task=task,
                job=self.job,
                crawl_source=source,
                fingerprint=f"fingerprint-{index}",
                title=self.job.name,
                requirements=f"第{index + 1}条工业机器人维修与关节润滑岗位要求",
            )
        batch = AnalysisBatch.objects.create(job=self.job, crawl_task=task, status="processing")
        generate_mock.return_value = {
            "abilities_text": json.dumps({
                "abilities": [{
                    "name": "机器人维护",
                    "college": self.college.name,
                    "units": [{
                        "name": "机器人本体维护",
                        "children": [{"name": "关节润滑"}],
                    }],
                }],
            }, ensure_ascii=False),
        }

        from .views import _run_candidate_analysis
        _run_candidate_analysis(batch.id)

        _, requirements = generate_mock.call_args.args
        official_tree = generate_mock.call_args.kwargs["official_tree"]
        self.assertEqual(len(requirements), 10)
        self.assertEqual(official_tree[0]["name"], "机器人维护")
        self.assertEqual(official_tree[0]["units"][0]["name"], "机器人本体维护")
        batch.refresh_from_db()
        self.assertEqual(batch.status, "completed")

    @patch("ai.services.generate_capability_map")
    def test_explicit_empty_increment_is_a_successful_analysis(self, generate_mock):
        source = CrawlSource.objects.create(
            name="空增量测试来源",
            code="empty_increment_source",
            base_url="https://example.com",
        )
        task = CrawlTask.objects.create(job=self.job, source=source, status="completed")
        for index in range(10):
            JobListing.objects.create(
                task=task,
                job=self.job,
                crawl_source=source,
                fingerprint=f"empty-increment-{index}",
                title=self.job.name,
                requirements=f"第{index + 1}条已经被正式能力图谱覆盖的岗位要求",
            )
        batch = AnalysisBatch.objects.create(job=self.job, crawl_task=task, status="processing")
        generate_mock.return_value = {
            "abilities_text": '{"job_name":"工业机器人操作员","abilities":[]}',
        }

        execute_analysis_batch(batch.id)

        batch.refresh_from_db()
        self.assertEqual(batch.status, "completed")
        self.assertEqual(batch.nodes.count(), 0)
        self.assertEqual(batch.error_message, "")
