# 项目架构

项目采用模块化单体架构：一个 Django 项目、一个数据库、多个职责明确的业务 app。

## 顶层目录

| 目录 | 职责 |
| --- | --- |
| `config/` | Django 全局配置、根路由、ASGI/WSGI |
| `apps/` | 可运行的业务模块 |
| `ai/` | AI 客户端、提示词和生成服务 |
| `templates/` | Django 页面模板 |
| `static/` | JavaScript、CSS、图片等静态资源 |
| `data/` | SQLite 数据库、页面样例与受控数据；`data/seeds/` 存放初始化样例 |
| `output/` | 本地 AI 运行产物，已忽略，不提交 |
| `docs/` | 项目技术文档与历史教程 |
| `scripts/legacy/` | 不参与 Web 服务的历史命令行工具，仅供参考或离线处理 |

根目录只保留 Django 必需的 `manage.py`。不在根目录放业务模块、AI 客户端、页面或临时脚本。

## App 职责

| App | 业务范围 |
| --- | --- |
| `accounts` | 登录、用户、角色与权限 |
| `organizations` | 学院、专业、班级、教师 |
| `industry` | 产业链、岗位 |
| `collection` | 招聘数据采集与任务 |
| `capabilities` | 岗位能力、能力单元、知识点/技能点 |
| `curriculum` | 课程、负责人、课程能力映射 |
| `resources` | 教学资源库 |
| `teaching` | 教学安排、试题 |
| `learning` | 学习计划、学习档案 |
| `notifications` | 通知、操作日志 |

## 开发规则

1. 新数据实体放入所属 app 的 `models.py`，再创建迁移。
2. 写操作放 `services.py`，查询组合放 `selectors.py`，HTTP 请求处理放 `views.py`。
3. 每个 app 自己维护 `urls.py`；`config/urls.py` 只做 `include()` 汇总。
4. AI 调用统一经过 `ai/services.py`；不要在业务视图中直连模型服务。
5. 旧脚本只允许放在 `scripts/legacy/`，新功能不依赖它们。

## 现有主流程

`产业链 → 岗位 → 招聘数据采集 → AI 生成能力图谱 → 岗位能力树`

后续流程：

`岗位能力树 → 学院/课程负责人 → 课程能力映射 → 教学资源与教学任务 → 学习档案`

## 数据库兼容

代码包使用 `apps.industry`、`apps.collection`、`apps.capabilities`，但 Django 内部 app 标签仍为 `chain`、`crawl`、`ability`，以兼容已有 SQLite 表与迁移记录。新代码只使用新导入路径。
