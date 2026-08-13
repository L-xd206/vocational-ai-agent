"""预置组织机构测试数据（幂等，可重复执行）

用法：python manage.py seed_organizations
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organizations.models import Class, Organization, Student


class Command(BaseCommand):
    help = "预置组织机构、班级、学生测试数据（幂等）"

    def handle(self, *args, **options):
        self.seed_orgs()
        self.seed_classes_and_students()
        self.stdout.write(self.style.SUCCESS(
            f"seed_organizations 完成：{Organization.objects.count()} 机构，{Class.objects.count()} 班级，{Student.objects.count()} 学生"
        ))

    def seed_orgs(self):
        with transaction.atomic():
            root, created = Organization.objects.get_or_create(
                name="智能制造职业技术学院",
                org_type="学校",
                defaults={"description": "一所以智能制造为特色的全日制高等职业院校"},
            )
            self.stdout.write(f"{'已创建' if created else '已存在'}：{root.name}")

            oa, created = Organization.objects.get_or_create(
                name="教务处", org_type="科室", parent=root,
                defaults={"description": "负责教学管理、学籍管理、实训统筹"},
            )
            self.stdout.write(f"  {'已创建' if created else '已存在'}：{oa.name}")

            college, created = Organization.objects.get_or_create(
                name="智能制造学院", org_type="学院", parent=root,
                defaults={"description": "培养智能制造领域高素质技术技能人才"},
            )
            self.stdout.write(f"  {'已创建' if created else '已存在'}：{college.name}")

            for dept_name, desc in [
                ("工业机器人技术", "工业机器人技术专业教学与科研"),
                ("机电一体化技术", "机电一体化技术专业教学与实训"),
                ("数控技术", "数控技术专业教学与实训"),
            ]:
                dept, created = Organization.objects.get_or_create(
                    name=dept_name, org_type="专业", parent=college,
                    defaults={"description": desc},
                )
                self.stdout.write(f"    {'已创建' if created else '已存在'}：{dept.name}")

    def seed_classes_and_students(self):
        with transaction.atomic():
            org1 = Organization.objects.filter(name="工业机器人技术", org_type="专业").first()
            org2 = Organization.objects.filter(name="数控技术", org_type="专业").first()
            if not org1:
                self.stdout.write("⚠ 无专业节点，跳过班级/学生 seed")
                return
            c1, _ = Class.objects.get_or_create(
                code="CLS-2024-01",
                defaults={"name": "机器人2401班", "major": "工业机器人技术", "grade": "2024级", "teacher": "张老师", "org": org1},
            )
            c2, _ = Class.objects.get_or_create(
                code="CLS-2024-02",
                defaults={"name": "机电2401班", "major": "机电一体化技术", "grade": "2024级", "teacher": "李老师", "org": Organization.objects.filter(name="机电一体化技术", org_type="专业").first()},
            )
            c3, _ = Class.objects.get_or_create(
                code="CLS-2022-01",
                defaults={"name": "数控2201班", "major": "数控技术", "grade": "2022级", "teacher": "陈老师", "status": "graduated", "org": org2},
            )
            self.stdout.write(f"班级：{Class.objects.count()} 条")

            # 学生（幂等：按学号去重）
            students_data = [
                ("张晨希", "2024010101", "工业机器人技术", "2024级", c1, "13800002163"),
                ("李婉清", "2024010102", "机电一体化技术", "2024级", c1, "13600008842"),
            ]
            for name, sid, major, grade, cls, phone in students_data:
                s, created = Student.objects.get_or_create(
                    student_id=sid,
                    defaults={"name": name, "major": major, "grade": grade, "class_group": cls, "phone": phone},
                )
            self.stdout.write(f"学生：{Student.objects.count()} 条")