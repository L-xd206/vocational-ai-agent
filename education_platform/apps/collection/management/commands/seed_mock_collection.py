"""为岗位采集模块准备可重复使用的模拟招聘数据。"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.collection.models import CrawlSource, CrawlTask
from apps.collection.services import save_crawl_result
from apps.collection.tasks import start_analysis_for_task
from apps.industry.models import Job


MOCK_REQUIREMENTS = [
    "负责FANUC、ABB或KUKA工业机器人的示教操作、程序编写、单步验证和自动运行，能够按照工艺要求完成轨迹调整。",
    "能够建立工具坐标系和工件坐标系，完成TCP标定、负载参数设置，并验证机器人定位结果是否符合工艺要求。",
    "使用RobotStudio、RoboGuide或RoboDK开展离线编程、轨迹仿真和碰撞检查，输出可下装并验证的机器人程序。",
    "完成机器人控制柜与PLC之间的I/O信号配置和联锁调试，能够使用PROFINET或EtherNet/IP排查通信异常。",
    "负责机器人视觉定位项目的相机标定、手眼标定、模板配置和抓取点验证，保证视觉引导抓取运行稳定。",
    "落实机器人工作站安全规范，检查安全门、急停、安全光栅和安全回路，确认安全条件满足后方可启动设备。",
    "根据示教器报警、伺服状态和控制柜日志诊断机器人故障，完成复位、原因定位和维修后的功能验证。",
    "执行工业机器人本体和控制柜的预防性维护，包括润滑、线缆检查、风扇清洁、程序备份和电池更换记录。",
    "能够阅读机械装配图、电气原理图和气动回路图，依据图纸完成末端执行器、传感器与气路的安装检查。",
    "完成夹具和末端执行器的更换、气爪行程调整、传感器位置校准，并验证抓取、搬运和放置动作。",
    "分析机器人工作节拍，通过轨迹平滑、速度参数和等待条件优化缩短循环时间，同时保证安全与加工质量。",
    "按照产品质量要求检查机器人作业结果，记录偏差、不合格原因和调整过程，确保生产数据可以追溯。",
    "配合MES或SCADA系统完成机器人工作站状态、产量和报警数据采集，检查数据上传与设备实际状态一致。",
    "编写机器人程序修改记录、调试报告、点检表和故障处理记录，并对现场操作人员进行基础操作培训。",
    "执行机器人工作站6S和交接班管理，核对程序版本、工装状态、设备异常和未完成事项并形成交接记录。",
]


class Command(BaseCommand):
    help = "写入模拟招聘数据；可选立即调用AI生成岗位候选能力树"

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            default="工业机器人编程与操作员",
            help="接收模拟招聘数据的现有岗位名称",
        )
        parser.add_argument(
            "--analyze",
            action="store_true",
            help="写入后立即调用已配置的大模型进行候选能力分析",
        )

    @transaction.atomic
    def _create_demo_task(self, job, source):
        task = CrawlTask.objects.create(
            job=job,
            source=source,
            trigger_type="manual",
            status="completed",
            total_keywords=len(job.search_keywords or [job.name]),
            total_results=len(MOCK_REQUIREMENTS),
            new_results=0,
            scheduled_at=timezone.now(),
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        new_count = 0
        results = []
        for index, requirement in enumerate(MOCK_REQUIREMENTS, start=1):
            item = {
                "title": job.name,
                "company": f"AI分析演示企业{index:02d}",
                "city": ["杭州", "宁波", "嘉兴", "绍兴", "湖州"][index % 5],
                "salary": "8000-14000元/月",
                "education": "大专及以上",
                "requirements": requirement,
                "headcount": str(1 + index % 3),
                "date": timezone.localdate().isoformat(),
                "source": "中国公共招聘网（模拟数据）",
                "source_url": f"https://demo.local/mohrss/{job.id}/{index}",
                "mock_data": True,
            }
            _, created = save_crawl_result(task, item)
            new_count += int(created)
            results.append(item)
        task.new_results = new_count
        task.results_json = results
        task.save(update_fields=["new_results", "results_json"])
        return task

    def handle(self, *args, **options):
        job_name = options["job"].strip()
        jobs = Job.objects.filter(
            name=job_name,
            is_enabled=True,
            chain__is_enabled=True,
        ).select_related("chain")
        if jobs.count() != 1:
            raise CommandError(
                f"启用状态下名称为“{job_name}”的岗位数量是 {jobs.count()}，请使用 --job 指定唯一岗位"
            )
        job = jobs.get()
        try:
            source = CrawlSource.objects.get(code="mohrss")
        except CrawlSource.DoesNotExist as exc:
            raise CommandError("未找到中国公共招聘网采集源，请先执行 migrate") from exc

        task = self._create_demo_task(job, source)
        self.stdout.write(self.style.SUCCESS(
            f"已为 {job.chain.name} / {job.name} 创建模拟采集任务 #{task.id}："
            f"共 {task.total_results} 条，首次新增 {task.new_results} 条"
        ))
        if not options["analyze"]:
            self.stdout.write("未调用AI；需要分析时加参数 --analyze")
            return

        self.stdout.write("正在调用大模型生成候选能力树...")
        batch = start_analysis_for_task(task.id)
        batch.refresh_from_db()
        if batch.status != "completed":
            raise CommandError(
                f"AI分析未完成：批次 #{batch.id}，状态={batch.status}，错误={batch.error_message}"
            )
        counts = {
            node_type: batch.nodes.filter(node_type=node_type).count()
            for node_type in ["ability", "unit", "point"]
        }
        virtual_count = batch.nodes.filter(matched_node__isnull=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"AI分析成功：批次 #{batch.id}，岗位能力 {counts['ability']} 个，"
            f"能力单元 {counts['unit']} 个，知识点/技能点 {counts['point']} 个，"
            f"其中AI新增虚体节点 {virtual_count} 个"
        ))
