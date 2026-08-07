# 项目架构

本项目采用模块化单体架构：一个 Django 项目、一个数据库、多个边界清晰的业务 app。
模块之间通过模型关系、service 函数和明确的 API 协作，不直接复制对方的业务逻辑。

## 目录职责

| 目录 | 职责 | 当前对应页面/能力 |
| --- | --- | --- |
| `config/` | 全局配置、根路由、ASGI/WSGI | 不承载业务代码 |
| `apps/accounts/` | 登录、用户、角色与权限 | 登录、用户管理、角色管理 |
| `apps/organizations/` | 学院、专业、班级、教师 | 系统管理中的组织机构、班级、教师归属 |
| `apps/industry/` | 产业链、岗位 | 能力图谱库的产业链、职业岗位两列 |
| `apps/collection/` | 招聘数据采集和采集任务 | 岗位采集、能力图谱生成前的数据来源 |
| `apps/capabilities/` | 岗位能力、能力单元、知识点/技能点 | 能力图谱库的岗位能力树 |
| `apps/curriculum/` | 课程、课程负责人、课程能力映射 | 课程管理与岗位能力下发 |
| `apps/resources/` | 教学资源 | 教育资源库 |
| `apps/teaching/` | 教学安排、试题 | 教学安排、课程试题 |
| `apps/learning/` | 学习计划、学习档案 | 学习空间 |
| `apps/notifications/` | 通知和操作日志 | 通知管理、系统日志 |
| `ai/` | AI 客户端、提示词、解析和任务适配 | AI 生成岗位、AI 分析能力图谱 |
| `templates/` | Django 渲染页面模板 | 当前全部 HTML 页面 |
| `static/` | CSS、JavaScript、图片等静态资源 | 侧边栏组件及后续前端资源 |

## 当前可用业务流

`产业链 → 岗位 → 招聘数据采集 → AI 分析 → 岗位能力 → 课程负责人 → 课程/资源/教学 → 学习档案`

其中前四段已可运行。课程、资源、教学、学习、组织机构、通知 app 已建立边界和代码入口，待对应原型开始实现时新增模型、迁移、服务和路由。

## 新功能放置规则

1. 新数据实体先放到所属 app 的 `models.py`，随后执行 `makemigrations` 和 `migrate`。
2. 读操作与列表组合查询放 `selectors.py`；新增、编辑、删除、状态流转等写操作放 `services.py`。
3. `views.py` 只做参数校验、调用 service、返回页面或 JSON；同一个 URL 只归一个 app 管理。
4. 本 app 需要调用 AI 时，只能调用 `ai/` 提供的函数，不直接在视图中连接模型服务。
5. `config/urls.py` 只 `include()` 各 app 的 `urls.py`，不能继续堆业务接口。
6. 跨 app 关联优先使用外键和 service；不要从一个 app 的视图直接复制另一个 app 的代码。

## 数据库兼容说明

原有的 Django app 标签 `chain`、`crawl`、`ability` 被保留为内部兼容标签，因此已经存在的 SQLite 表和迁移记录无需重建。代码包名称已分别迁移为 `apps.industry`、`apps.collection`、`apps.capabilities`；新代码应只使用新路径导入。

原根目录的 `step1_gen_jobs.py`、`step2_crawl_jobs.py`、`step3_gen_abilities.py` 与 `spark_assistant.py` 仅作为兼容入口；实际实现已分别迁移至 `ai/` 和 `apps/collection/tasks.py`。新代码不要再从根目录导入它们。
