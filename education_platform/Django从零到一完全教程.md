# 🚀 Django 从零到一完全教程

> 以「岗位能力生成」项目为实战案例，手把手教你 Django 开发。
>
> **适合人群**：零基础小白，只要会一点 Python 就能跟下来。
>
> **学完能做什么**：独立开发一个完整的 Web 后端系统（API + 数据库 + 后台管理）。

---

## 目录

1. [Django 是什么？](#1-django-是什么)
2. [项目环境搭建](#2-项目环境搭建)
3. [Django 项目结构详解](#3-django-项目结构详解)
4. [配置系统 settings.py](#4-配置系统-settingspy)
5. [路由系统 urls.py](#5-路由系统-urlspy)
6. [模型层 Model — 定义数据库](#6-模型层-model--定义数据库)
7. [视图层 View — 写业务逻辑](#7-视图层-view--写业务逻辑)
8. [数据库迁移 Migration](#8-数据库迁移-migration)
9. [Django Admin 后台管理](#9-django-admin-后台管理)
10. [前后端交互 — API 开发实战](#10-前后端交互--api-开发实战)
11. [模板与静态文件 — 前端页面](#11-模板与静态文件--前端页面)
12. [用户认证系统](#12-用户认证系统)
13. [启动与运行](#13-启动与运行)
14. [常用命令速查表](#14-常用命令速查表)
15. [进阶主题](#15-进阶主题)

---

## 1. Django 是什么？

### 1.1 一句话解释

**Django = Python 写的大型网站后端的"乐高积木套装"**。它帮你把网页系统中最常见的功能（数据库操作、用户登录、API 接口、后台管理）都预制好了，你只需要"组装"而不是"从零造轮子"。

### 1.2 通俗比喻

| 概念 | 比喻 |
|------|------|
| **Django 项目** | 一栋大楼 |
| **App（应用）** | 大楼里的一个功能区域（比如停车场、食堂、健身房） |
| **Model（模型）** | 数据库中的一张表（比如"用户表"、"订单表"） |
| **View（视图）** | 处理请求的"服务员"——客人点什么菜，服务员就去厨房取什么 |
| **URL（路由）** | 大楼的"门牌号码"——`/api/chain/list` 就是去"产业链列表"房间 |
| **Template（模板）** | 前端 HTML 页面 |

### 1.3 你的项目做了什么

你的项目名叫「**岗位能力生成**」，核心功能是：

```
用户创建产业链 → AI 生成岗位 → 爬取招聘信息 → AI 提取能力图谱
```

用 Django 的术语说就是：

- `chain` app：管理产业链和岗位
- `crawl` app：爬取招聘数据
- `ability` app：AI 生成能力图谱
- `accounts` app：用户账号管理（预留）

---

## 2. 项目环境搭建

### 2.1 安装 Python

Django 是用 Python 写的，你需要先安装 Python。去 [python.org](https://www.python.org/downloads/) 下载安装包，安装时**勾选"Add Python to PATH"**。

验证安装：

```bash
python --version
# 输出类似：Python 3.13.x
```

### 2.2 安装 Django

打开终端（命令行），执行：

```bash
pip install django
```

验证安装：

```bash
python -m django --version
# 输出类似：6.0.7
```

> 📌 你的项目用的是 **Django 6.0.7**，这是比较新的版本。

### 2.3 创建 Django 项目（了解即可，你已经创建好了）

如果你是第一次创建 Django 项目，执行：

```bash
django-admin startproject config .
```

这个命令会生成 `manage.py` 和 `config/` 文件夹。`.` 表示在当前目录创建，这样不会多套一层文件夹。

> ✅ **你的项目已经创建好了**，`config` 就是你项目的配置目录。

### 2.4 创建 App（应用）

每个 Django 项目由多个 App 组成。你已经创建了 4 个 App：

```bash
# 你的项目已经执行过了，不需要再跑
python manage.py startapp chain    # 产业链 + 岗位管理
python manage.py startapp crawl    # 招聘数据爬取
python manage.py startapp ability  # 能力图谱生成
python manage.py startapp accounts # 用户账号管理
```

每次创建 App 后，Django 会自动生成一系列文件（后面会详细讲）。

---

## 3. Django 项目结构详解

来看看你的项目目录树：

```
岗位能力生成/
├── manage.py              # 🔑 Django 命令入口，所有操作都从这里发起
├── config/                # 🏠 项目全局配置
│   ├── __init__.py        #    空文件，告诉 Python 这是一个包
│   ├── settings.py        #    🌟 核心配置文件（数据库、app注册等）
│   ├── urls.py            #    🌟 URL 路由表（哪个网址访问哪个功能）
│   ├── wsgi.py            #    生产环境部署用（一般不用管）
│   └── asgi.py            #    WebSocket 部署用（一般不用管）
│
├── chain/                 # 📦 App1: 产业链 & 岗位管理
│   ├── __init__.py
│   ├── admin.py           #    后台管理配置
│   ├── apps.py            #    App 元信息
│   ├── models.py          #    🌟 数据库表定义（Chain、Job）
│   ├── views.py           #    🌟 业务逻辑（API 接口实现）
│   ├── tests.py           #    单元测试
│   └── migrations/        #    📜 数据库变更记录（类似 Git 的 commit 记录）
│       └── 0001_initial.py
│
├── crawl/                 # 📦 App2: 招聘爬取
│   ├── models.py          #    数据库表定义（CrawlTask、JobListing）
│   ├── views.py           #    爬取启动 / 状态查询 API
│   └── ...
│
├── ability/               # 📦 App3: 能力图谱
│   ├── models.py          #    数据库表定义（AbilityMap）
│   ├── views.py           #    生成 / 查询能力图谱 API
│   └── ...
│
├── accounts/              # 📦 App4: 用户管理（预留）
│   └── ...
│
├── frontend/              # 🎨 前端静态页面
│   ├── index.html         #    主框架页面
│   ├── login.html         #    登录页面
│   ├── 能力图谱库.html     #    能力图谱管理页
│   ├── 用户管理.html       #    用户管理页
│   ├── 角色管理.html       #    角色管理页
│   ├── 个人中心.html       #    个人中心页
│   └── components/
│       └── sidebar-menu.js #   侧边栏组件
│
├── data/
│   └── db.sqlite3         # 🗄️ SQLite 数据库文件（实际数据存这里）
│
└── output/                # 📤 输出文件（能力图谱导出）
```

### 3.1 核心文件职责速查

| 文件 | 作用 | 类比 |
|------|------|------|
| `manage.py` | 一切操作的入口 | 大楼的前台电话 |
| `settings.py` | 全局配置 | 大楼的水电燃气总阀 |
| `urls.py` | URL → View 的映射 | 大楼的楼层指引牌 |
| `models.py` | 数据库表结构定义 | 仓库的货架设计图 |
| `views.py` | 处理请求、返回数据 | 各个窗口的服务员 |
| `admin.py` | 后台管理页面配置 | 物业管理系统 |

---

## 4. 配置系统 settings.py

打开你的 `config/settings.py`，我们逐段讲解：

### 4.1 基础路径

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# BASE_DIR = 岗位能力生成/   （项目根目录）
```

`BASE_DIR` 是项目的根目录，后续所有路径都以它为基准。`Path(__file__).resolve().parent.parent` 的意思是：当前文件的爷爷目录 = 项目根目录。

```
config/settings.py  →  parent = config/  →  parent = 岗位能力生成/
```

### 4.2 密钥与调试模式

```python
SECRET_KEY = "django-edu-platform-2026-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]
```

| 配置 | 说明 | 你的项目 |
|------|------|---------|
| `SECRET_KEY` | 加密签名用的密钥（生产环境要保密！） | 固定字符串（开发用没问题） |
| `DEBUG = True` | 开发模式：显示详细错误信息 | ✅ 开发中，开着 |
| `ALLOWED_HOSTS = ["*"]` | 允许哪些域名访问 | `"*"` = 任何域名都能访问 |

> ⚠️ **正式上线时**：`DEBUG` 必须设为 `False`，`SECRET_KEY` 要从环境变量读取，`ALLOWED_HOSTS` 要限定为实际域名。

### 4.3 注册 App

```python
INSTALLED_APPS = [
    "django.contrib.admin",        # 后台管理系统
    "django.contrib.auth",         # 用户认证（登录/注册/权限）
    "django.contrib.contenttypes", # 内容类型框架
    "django.contrib.sessions",     # 会话管理（记住登录状态）
    "django.contrib.messages",     # 消息提示
    "django.contrib.staticfiles",  # 静态文件管理
    "accounts",                    # 👈 你的 App
    "chain",                       # 👈 你的 App
    "crawl",                       # 👈 你的 App
    "ability",                     # 👈 你的 App
]
```

**关键规则**：每创建一个 App，必须在这里注册，否则 Django 不认识它。

前 6 个是 Django 自带的内置 App，后 4 个是你自己的 App。这和装软件一样——告诉 Django "我有这些功能模块"。

### 4.4 中间件（Middleware）

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",       # 安全防护
    "django.contrib.sessions.middleware.SessionMiddleware", # 会话处理
    "django.middleware.common.CommonMiddleware",            # 通用功能
    "django.middleware.csrf.CsrfViewMiddleware",            # CSRF 防攻击
    "django.contrib.auth.middleware.AuthenticationMiddleware", # 用户认证
    "django.contrib.messages.middleware.MessageMiddleware", # 消息传递
]
```

中间件 = **请求的"安检流水线"**。一个请求进来，要依次通过这些中间件才能到达你的 View。

```
用户请求 → Security → Session → Common → CSRF → Auth → Messages → 你的View
```

你的项目没有自定义中间件，用默认的就行。

### 4.5 模板配置（Templates）

```python
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "frontend"],  # 👈 模板文件放在 frontend/ 目录
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [...],
        },
    },
]
```

| 配置项 | 说明 | 你的设置 |
|--------|------|---------|
| `DIRS` | 模板搜索路径 | `frontend/` 目录 |
| `APP_DIRS` | 是否自动在每个 App 的 `templates/` 下找模板 | `True` |

> 你的 HTML 文件统一放在 `frontend/` 目录，所以 `DIRS` 指向它。如果某个 App 也有自己的模板文件夹，`APP_DIRS=True` 也能找到。

### 4.6 数据库配置

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",           # 使用 SQLite
        "NAME": BASE_DIR / "data" / "db.sqlite3",          # 数据库文件位置
    }
}
```

| 配置 | 说明 |
|------|------|
| `ENGINE` | 数据库类型：SQLite / PostgreSQL / MySQL |
| `NAME` | 数据库文件路径 |

**你的项目用的是 SQLite**——这是一个单文件数据库，无需安装任何软件，非常适合开发和小型项目。数据全部存在 `data/db.sqlite3` 这一个文件里。

> 📌 **什么时候换数据库**：SQLite 适合开发和轻量部署。如果用户量很大（成千上万并发），就要换成 PostgreSQL 或 MySQL。

**换成 MySQL 示例**（了解即可）：
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "mydatabase",
        "USER": "root",
        "PASSWORD": "password",
        "HOST": "127.0.0.1",
        "PORT": "3306",
    }
}
```

### 4.7 国际化与静态文件

```python
LANGUAGE_CODE = "zh-hans"       # 界面语言：简体中文
TIME_ZONE = "Asia/Shanghai"     # 时区：上海（UTC+8）
USE_I18N = True                  # 开启国际化
USE_TZ = True                    # 使用时区

STATIC_URL = "/static/"          # 静态文件的 URL 前缀
STATICFILES_DIRS = [BASE_DIR / "frontend"]  # 静态文件存放目录

LOGIN_URL = "/login.html"        # 未登录时跳转到登录页
```

`STATICFILES_DIRS` 和模板 `DIRS` 都指向 `frontend/`——这意味着你的 HTML、CSS、JS 都在同一个目录下。

---

## 5. 路由系统 urls.py

### 5.1 什么是路由？

路由就是 **"网址 → 功能"的映射表**。用户访问某个网址，Django 根据这张表找到对应的 View 函数来处理。

打开你的 `config/urls.py`：

```python
from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect

# 导入各个 App 的 View 函数
from chain.views import page_chain_list, page_user_list, page_role_list
from chain.views import api_chain_list, api_chain_detail, api_chain_create, ...
from crawl.views import api_crawl_start, api_crawl_status
from ability.views import api_ability_generate, api_ability_tree, api_ability_text

urlpatterns = [
    # 页面路由
    path("", index_view),                              # 首页
    path("login.html", login_view),                    # 登录页
    path("index.html", index_view),                    # 主页（需登录）
    path("能力图谱库.html", page_chain_list),           # 能力图谱页面
    path("admin/", admin.site.urls),                   # Django 后台

    # 登录 API
    path("api/auth/login", api_login),                 # POST 登录
    path("api/auth/logout", api_logout),               # 退出登录
    path("api/auth/me", api_user_info),                # 获取当前用户信息

    # 产业链 API
    path("api/chain/list", api_chain_list),            # GET  获取产业链列表
    path("api/chain/create", api_chain_create),        # POST 创建产业链+AI生成岗位
    path("api/chain/<int:chain_id>/detail", ...),      # GET  产业链详情
    path("api/chain/<int:chain_id>/delete", ...),      # DELETE 删除产业链

    # 岗位 API
    path("api/job/create", api_job_create),            # POST 手动新增岗位
    path("api/job/<int:job_id>/update", ...),          # POST 更新岗位
    path("api/job/<int:job_id>/delete", ...),          # DELETE 删除岗位

    # 爬虫 API
    path("api/crawl/start", api_crawl_start),          # POST 启动爬取
    path("api/crawl/<int:task_id>/status", ...),       # GET  查询爬取进度

    # 能力图谱 API
    path("api/ability/generate", api_ability_generate), # POST 生成能力图谱
    path("api/ability/<int:job_id>/tree", ...),         # GET  获取能力图谱树
    path("api/ability/<int:job_id>/text", ...),         # GET  获取原始文本
]
```

### 5.2 path() 函数详解

```python
path("api/chain/list", api_chain_list)
#     ↑ 网址路径         ↑ 对应的 View 函数
```

当用户访问 `http://你的域名/api/chain/list` 时，Django 调用 `api_chain_list` 函数。

### 5.3 路径参数 `<int:xxx>`

```python
path("api/chain/<int:chain_id>/detail", api_chain_detail)
#                  ↑ 捕获整数，传给 View 函数
```

`<int:chain_id>` 表示"这里有一个整数，把它叫做 `chain_id`"。举例：

| 用户访问的 URL | View 收到的参数 |
|---------------|---------------|
| `/api/chain/1/detail` | `chain_id=1` |
| `/api/chain/99/detail` | `chain_id=99` |

对应的 View 函数签名：

```python
def api_chain_detail(request, chain_id):  # chain_id 自动从 URL 中提取
    ...
```

### 5.4 路由的两种风格

你的项目使用了两种风格的页面路由：

```python
path("chain-list.html", page_chain_list),    # 英文别名
path("能力图谱库.html", page_chain_list),     # 中文原名
```

两个 URL 指向同一个 View 函数——这样中英文都能访问。

---

## 6. 模型层 Model — 定义数据库

**Model 就是用 Python 代码描述数据库的表结构**。你不需要写 SQL，Django 自动帮你翻译。

### 6.1 你的第一个 Model：产业链 Chain

打开 `chain/models.py`：

```python
from django.db import models

class Chain(models.Model):
    """产业链"""
    name = models.CharField("产业链名称", max_length=100, unique=True)
    description = models.CharField("描述", max_length=500, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "chain"                # 数据库表名
        verbose_name = "产业链"            # 单数显示名
        verbose_name_plural = verbose_name # 复数显示名

    def __str__(self):
        return self.name                   # 打印时显示名字
```

**逐行解释**：

```python
class Chain(models.Model):  # 继承 models.Model → Django 就知道这是个数据库表
```

```python
name = models.CharField("产业链名称", max_length=100, unique=True)
#     ↑                  ↑               ↑               ↑
#   CharField          显示名         最多100字        不能重复
#   （字符串类型）
```

```python
description = models.CharField("描述", max_length=500, blank=True)
#                                                  blank=True = 可以为空
```

```python
created_at = models.DateTimeField("创建时间", auto_now_add=True)
#                                            ↑ 创建时自动填入当前时间
```

**这个 Python 类对应数据库中的一张表**：

| Python Model | 对应 SQL（自动生成） |
|-------------|---------------------|
| `class Chain(models.Model)` | `CREATE TABLE chain (...)` |
| `name = models.CharField(...)` | `name VARCHAR(100) NOT NULL UNIQUE` |
| `created_at = models.DateTimeField(...)` | `created_at DATETIME NOT NULL` |

### 6.2 岗位 Model：Job（外键关系）

```python
class Job(models.Model):
    chain = models.ForeignKey(
        Chain,                              # 关联的 Model
        on_delete=models.CASCADE,           # 产业链删除时，岗位也跟着删除
        related_name="jobs",                # 反向查询名：chain.jobs.all()
        verbose_name="所属产业链"
    )
    name = models.CharField("标准岗位名", max_length=100)
    aliases = models.JSONField("别名列表", default=list)         # JSON 数组
    search_keywords = models.JSONField("搜索关键词", default=list)
    is_confirmed = models.BooleanField("已确认", default=False)  # 布尔值
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "job"
        verbose_name = "岗位"
        unique_together = [("chain", "name")]  # 同一个产业链下岗位名不能重复

    def __str__(self):
        return f"{self.chain.name} / {self.name}"
```

**重点：外键 ForeignKey**

```
Chain (产业链)                    Job (岗位)
┌──────────────┐                ┌──────────────────────┐
│ id: 1        │ ←─────────── │ id: 1                 │
│ name: 新能源  │  一对多关系    │ chain_id: 1 (外键)    │
│              │  一个产业链    │ name: 光伏运维技术员    │
│              │  下面有多个岗位  ├──────────────────────┤
│              │ ←─────────── │ id: 2                 │
│              │              │ chain_id: 1 (外键)    │
│              │              │ name: 新能源整机装配工   │
└──────────────┘              └──────────────────────┘
```

- `on_delete=models.CASCADE`：产业链被删除，它下面的岗位也自动删除（级联删除）。
- `related_name="jobs"`：让你可以用 `chain.jobs.all()` 直接拿到某个产业链的所有岗位，非常方便。

**实际使用示例**：
```python
chain = Chain.objects.get(id=1)         # 拿到"新能源"产业链
all_jobs = chain.jobs.all()             # 拿到新能源下面的所有岗位
# 等价于：Job.objects.filter(chain_id=1)
```

**JSONField 的使用**：
```python
job.aliases = ["光伏运维", "光伏电站运维"]  # 存一个 Python 列表
job.save()
# 数据库里存的是：["光伏运维", "光伏电站运维"]  （JSON 格式）
```

### 6.3 爬取任务 Model：CrawlTask

打开 `crawl/models.py`：

```python
class CrawlTask(models.Model):
    job = models.ForeignKey(
        "chain.Job",                    # 可以跨 App 引用！"app名.Model名"
        on_delete=models.CASCADE,
        related_name="crawl_tasks",
        verbose_name="岗位"
    )
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[                       # 限定可选值
            ("pending", "待执行"),
            ("running", "执行中"),
            ("completed", "已完成"),
            ("failed", "失败"),
        ]
    )
    total_keywords = models.IntegerField(default=0)
    total_results = models.IntegerField(default=0)
    results_json = models.JSONField("原始结果", default=list)
    created_at = models.DateTimeField(auto_now_add=True)
```

**`choices` 参数**：限定字段只能取某些值，同时提供了中文显示名。

```python
task = CrawlTask.objects.get(id=1)
print(task.status)          # "running"
print(task.get_status_display())  # "执行中"  ← Django 自动生成的方法
```

### 6.4 招聘信息 Model：JobListing

```python
class JobListing(models.Model):
    task = models.ForeignKey(CrawlTask, on_delete=models.CASCADE, related_name="listings")
    title = models.CharField("岗位名称", max_length=200)
    company = models.CharField("公司", max_length=200)
    city = models.CharField("城市", max_length=100, blank=True)
    salary = models.CharField("薪资", max_length=100, blank=True)
    education = models.CharField("学历", max_length=50, blank=True)
    requirements = models.TextField("任职要求", blank=True)  # TextField = 不限长度文本
    headcount = models.CharField("招聘人数", max_length=20, blank=True)
    post_date = models.CharField("发布日期", max_length=50, blank=True)
    source = models.CharField("来源", max_length=100, blank=True)
```

### 6.5 能力图谱 Model：AbilityMap

打开 `ability/models.py`：

```python
class AbilityMap(models.Model):
    job = models.OneToOneField(          # 一对一关系：一个岗位只有一份能力图谱
        "chain.Job",
        on_delete=models.CASCADE,
        related_name="ability_map",
        verbose_name="岗位"
    )
    abilities_json = models.JSONField("能力列表JSON", default=list)
    total_abilities = models.IntegerField("能力项数", default=0)
    total_skills = models.IntegerField("技能点数", default=0)
    raw_text = models.TextField("原始AI输出", blank=True)
    created_at = models.DateTimeField("生成时间", auto_now_add=True)
```

**ForeignKey vs OneToOneField**：

| 关系 | 字段 | 举例 |
|------|------|------|
| 一对多 | `ForeignKey` | 一个产业链 → 多个岗位 |
| 一对一 | `OneToOneField` | 一个岗位 → 一份能力图谱 |
| 多对多 | `ManyToManyField` | 一个学生 → 多门课程，一门课程 → 多个学生 |

### 6.6 Model 字段类型速查表

| 字段类型 | 数据库类型 | 用途 | 示例 |
|---------|-----------|------|------|
| `CharField(max_length=N)` | VARCHAR(N) | 短文本 | 名字、标题、城市 |
| `TextField()` | TEXT | 长文本 | 文章内容、招聘要求 |
| `IntegerField()` | INTEGER | 整数 | 数量、计数 |
| `BooleanField()` | BOOLEAN | 布尔值 | 是否确认、是否激活 |
| `DateTimeField()` | DATETIME | 日期时间 | 创建时间、更新时间 |
| `JSONField()` | JSON | JSON 数据 | 列表、字典等结构化数据 |
| `ForeignKey()` | 外键 | 关联其他表 | 岗位属于哪个产业链 |
| `OneToOneField()` | 唯一外键 | 一对一关联 | 岗位的能力图谱 |

#### 通用参数

| 参数 | 说明 |
|------|------|
| `verbose_name="显示名"` | 在 Admin 后台显示的字段名 |
| `max_length=100` | 最大长度（CharField 必填） |
| `blank=True` | 表单中可以为空 |
| `default=值` | 默认值 |
| `unique=True` | 值必须唯一 |
| `auto_now_add=True` | 创建时自动填当前时间 |
| `auto_now=True` | 每次保存时自动更新为当前时间 |

---

## 7. 视图层 View — 写业务逻辑

**View 就是处理请求、返回数据的函数**。前端发来一个请求，View 去数据库查数据（或做其他处理），然后返回 JSON 或 HTML。

### 7.1 最简单的 View：返回页面

```python
# chain/views.py

def page_chain_list(request):
    """产业链管理页面"""
    return render(request, "能力图谱库.html")
```

`render(request, "模板名")` = "把指定的 HTML 文件返回给浏览器"。第一个参数 `request` 是 Django 自动传入的请求对象。

对应的 URL：
```python
path("能力图谱库.html", page_chain_list)
```

### 7.2 返回 JSON 的 API View

```python
from django.http import JsonResponse
from .models import Chain

def api_chain_list(request):
    """获取所有产业链"""
    chains = Chain.objects.prefetch_related("jobs").all()
    return JsonResponse({
        "chains": [{
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "job_count": c.jobs.count(),
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
        } for c in chains]
    })
```

**逐行讲解**：

```python
chains = Chain.objects.prefetch_related("jobs").all()
#        ↑             ↑                        ↑
#    Model 的         预加载关联数据              获取所有记录
#    管理器           （性能优化）                （SELECT * FROM chain）
```

等价于先执行 `SELECT * FROM chain`，再一次性查出所有关联的 jobs，避免 N+1 查询问题。

```python
return JsonResponse({...})
#      ↑
#   自动把 Python 字典转成 JSON，设置 Content-Type: application/json
```

**实际效果**：访问 `http://localhost:8000/api/chain/list` 返回：

```json
{
  "chains": [
    {
      "id": 1,
      "name": "新能源",
      "description": "",
      "job_count": 5,
      "created_at": "2026-07-31 21:28"
    }
  ]
}
```

### 7.3 带路径参数的 View

```python
def api_chain_detail(request, chain_id):  # chain_id 来自 URL
    try:
        chain = Chain.objects.prefetch_related("jobs").get(id=chain_id)
        #                                          ↑ get() 获取单条记录
    except Chain.DoesNotExist:             # 找不到时的异常处理
        return JsonResponse({"error": "产业链不存在"}, status=404)
        #                                              ↑ HTTP 状态码

    return JsonResponse({
        "id": chain.id,
        "name": chain.name,
        "jobs": [{
            "id": j.id, "name": j.name,
            "aliases": j.aliases, "is_confirmed": j.is_confirmed,
        } for j in chain.jobs.all()],
    })
```

**QuerySet 常用方法**：

| 方法 | 说明 | 示例 |
|------|------|------|
| `.all()` | 获取所有记录 | `Chain.objects.all()` |
| `.get(id=1)` | 获取一条记录（找不到会报错） | `Chain.objects.get(id=1)` |
| `.filter(name="新能源")` | 条件过滤（返回多条） | `Chain.objects.filter(name__contains="新")` |
| `.first()` | 取第一条 | `Chain.objects.first()` |
| `.count()` | 计数 | `Chain.objects.count()` |
| `.order_by("-created_at")` | 排序（`-` 表示倒序） | `Chain.objects.order_by("-id")` |
| `.exists()` | 判断是否存在 | `Chain.objects.filter(name="x").exists()` |
| `.delete()` | 删除 | `chain.delete()` |

### 7.4 处理 POST 请求（创建数据）

```python
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

@csrf_exempt                          # 豁免 CSRF 检查（API 常用）
@require_http_methods(["POST"])       # 只允许 POST 请求
def api_chain_create(request):
    try:
        data = json.loads(request.body)  # 解析 POST 的 JSON 数据
        chain_name = data.get("name", "").strip()

        if not chain_name:
            return JsonResponse({"error": "请输入产业链名称"}, status=400)

        # get_or_create：如果有就返回，没有就创建
        chain, created = Chain.objects.get_or_create(name=chain_name)

        if not created:
            return JsonResponse({"error": f"产业链 [{chain_name}] 已存在"}, status=400)

        # 调用 AI 生成岗位（你项目自己的函数）
        from step1_gen_jobs import gen_jobs
        ai_result = gen_jobs(chain_name)

        # 批量创建岗位
        saved_jobs = []
        for job_data in ai_result.get("jobs", []):
            job = Job.objects.create(     # create() = 创建并保存到数据库
                chain=chain,
                name=job_data.get("name", ""),
                aliases=job_data.get("aliases", []),
                search_keywords=job_data.get("search_keywords", []),
                is_confirmed=False,
            )
            saved_jobs.append({"id": job.id, "name": job.name})

        return JsonResponse({
            "chain_id": chain.id,
            "name": chain.name,
            "jobs": saved_jobs,
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的JSON"}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()          # 在控制台打印完整错误
        return JsonResponse({"error": str(e)}, status=500)
```

### 7.5 处理 UPDATE 请求

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_job_update(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
        data = json.loads(request.body)

        # 只更新传了值的字段
        if "aliases" in data:
            job.aliases = data["aliases"]
        if "search_keywords" in data:
            job.search_keywords = data["search_keywords"]
        if "is_confirmed" in data:
            job.is_confirmed = data["is_confirmed"]
        if "name" in data:
            job.name = data["name"]

        job.save()  # 保存到数据库

        return JsonResponse({"id": job.id, "name": job.name, "is_confirmed": job.is_confirmed})

    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
```

### 7.6 处理 DELETE 请求

```python
@csrf_exempt
@require_http_methods(["DELETE"])
def api_chain_delete(request, chain_id):
    try:
        chain = Chain.objects.get(id=chain_id)
        chain.delete()      # 删除！因为 ForeignKey 设置了 CASCADE，关联的岗位也会被删
        return JsonResponse({"deleted": True})
    except Chain.DoesNotExist:
        return JsonResponse({"error": "产业链不存在"}, status=404)
```

### 7.7 后台线程执行耗时任务

```python
import threading

def _run_crawl(task_id: int):
    """后台执行爬取"""
    task = CrawlTask.objects.get(id=task_id)
    task.status = "running"
    task.save()

    from step2_crawl_jobs import crawl_single_job
    keywords = task.job.search_keywords or [task.job.name]
    result = crawl_single_job({"name": task.job.name, "search_keywords": keywords}, pages=3)

    task.total_results = result.get("total_results", 0)
    task.status = "completed"
    task.save()

    # 保存爬取到的招聘信息
    for item in result.get("results", []):
        JobListing.objects.create(
            task=task,
            title=item.get("title", ""),
            company=item.get("company", ""),
            # ...
        )


@csrf_exempt
@require_http_methods(["POST"])
def api_crawl_start(request):
    data = json.loads(request.body)
    job = Job.objects.get(id=data.get("job_id"))

    task = CrawlTask.objects.create(job=job, status="pending", ...)

    # 新开一个线程去执行爬取，不阻塞当前请求
    t = threading.Thread(target=_run_crawl, args=(task.id,), daemon=True)
    t.start()

    return JsonResponse({"task_id": task.id, "status": "pending"})
```

**为什么用线程？** 爬取可能需要几十秒，如果用同步方式，用户就要等几十秒才能看到响应。新开线程后，API 立即返回 `task_id`，前端可以用这个 ID 轮询进度。

**前端查询进度**：
```python
def api_crawl_status(request, task_id):
    task = CrawlTask.objects.get(id=task_id)
    return JsonResponse({
        "task_id": task.id,
        "status": task.status,        # "pending" / "running" / "completed" / "failed"
        "total_results": task.total_results,
    })
```

### 7.8 装饰器速查

| 装饰器 | 作用 | 使用场景 |
|--------|------|---------|
| `@csrf_exempt` | 跳过 CSRF 验证 | API 接口（非浏览器表单提交） |
| `@require_http_methods(["POST"])` | 限制请求方法 | 只接受 POST 的接口 |
| `@login_required` | 要求用户已登录 | 需要登录才能访问的页面 |
| `@require_http_methods(["DELETE"])` | 限制请求方法 | 只接受 DELETE 的接口 |

---

## 8. 数据库迁移 Migration

### 8.1 迁移是什么？

**Migration = 数据库的"版本控制"**。每次你修改 models.py（增减字段、新建表等），都需要创建并执行迁移，让数据库结构跟上代码。

```
修改 models.py  →  makemigrations（生成迁移脚本）  →  migrate（应用到数据库）
```

### 8.2 核心命令

```bash
# 1. 生成迁移脚本（告诉 Django "我的模型改了，生成 SQL 脚本"）
python manage.py makemigrations

# 2. 应用到数据库（把 SQL 脚本真正执行到数据库）
python manage.py migrate

# 3. 查看迁移状态
python manage.py showmigrations
```

### 8.3 你的项目的迁移文件

打开 `chain/migrations/0001_initial.py`，这是 Django 自动生成的：

```python
class Migration(migrations.Migration):
    initial = True                    # 标记为初始迁移
    dependencies = []                 # 不依赖其他迁移

    operations = [
        migrations.CreateModel(       # 创建 Chain 表
            name='Chain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, ...)),
                ('name', models.CharField(max_length=100, unique=True, ...)),
                ('description', models.CharField(blank=True, max_length=500, ...)),
                ('created_at', models.DateTimeField(auto_now_add=True, ...)),
            ],
        ),
        migrations.CreateModel(       # 创建 Job 表
            name='Job',
            fields=[...],
        ),
    ]
```

`crawl/migrations/0001_initial.py` 的依赖关系：
```python
dependencies = [
    ('chain', '0001_initial'),   # 依赖 chain 的迁移先执行
]
```

**执行顺序**：`chain → crawl → ability`（按依赖关系，先创建 Chain 表，再创建引用它的 CrawlTask 表）。

### 8.4 迁移的日常使用

```bash
# 修改 models.py 后：
python manage.py makemigrations    # 生成迁移文件

# 部署到服务器时：
python manage.py migrate           # 一把执行所有未应用的迁移

# 如果出错了，回退：
python manage.py migrate chain 0001  # 回退到 chain 的第 0001 号迁移
```

---

## 9. Django Admin 后台管理

Django 自带一个功能强大的后台管理系统，可以让你在网页上直接管理数据库数据。

### 9.1 注册 Model 到 Admin

你的 `chain/admin.py` 目前是空的。要启用后台管理，需要这样写：

```python
# chain/admin.py
from django.contrib import admin
from .models import Chain, Job

@admin.register(Chain)
class ChainAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "description", "created_at"]  # 列表页显示的列
    search_fields = ["name"]                                      # 搜索字段
    ordering = ["-created_at"]                                    # 默认排序


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "chain", "is_confirmed", "created_at"]
    list_filter = ["is_confirmed", "chain"]  # 侧边栏过滤器
    search_fields = ["name"]
```

**注册后的效果**：

1. 访问 `http://localhost:8000/admin/`
2. 用超级管理员账号登录
3. 看到 Chain 和 Job 两个模块
4. 可以增删改查，不用写一行前端代码！

### 9.2 创建超级管理员

```bash
python manage.py createsuperuser
```

按提示输入用户名、邮箱、密码即可。

### 9.3 同时在多个 App 中注册

把 `crawl/models.py` 的 CrawlTask 和 JobListing 也注册上：

```python
# crawl/admin.py
from django.contrib import admin
from .models import CrawlTask, JobListing

@admin.register(CrawlTask)
class CrawlTaskAdmin(admin.ModelAdmin):
    list_display = ["id", "job", "status", "total_results", "created_at"]
    list_filter = ["status"]


@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "company", "city", "salary", "task"]
    list_filter = ["city", "education"]
    search_fields = ["title", "company", "requirements"]
    list_per_page = 50  # 每页显示 50 条
```

---

## 10. 前后端交互 — API 开发实战

### 10.1 前后端如何通信？

```
前端（HTML/JS）                      后端（Django）
    │                                    │
    │  fetch("/api/chain/list")          │
    │ ─────────────────────────────────> │
    │       GET 请求                      │  Django 路由匹配
    │                                    │  → api_chain_list()
    │                                    │  → 查数据库
    │  {"chains": [...]}                 │  → 返回 JSON
    │ <───────────────────────────────── │
    │       200 OK                       │
    │                                    │
    │  fetch("/api/chain/create", {      │
    │    method: "POST",                 │
    │    body: JSON.stringify({          │
    │      name: "新能源"                 │
    │    })                              │
    │  })                                │
    │ ─────────────────────────────────> │
    │       POST 请求                     │  → api_chain_create()
    │                                    │  → 创建 Chain
    │  {"chain_id": 1, "jobs": [...]}    │  → 调用 AI 生成岗位
    │ <───────────────────────────────── │
    │       200 OK                       │
```

### 10.2 前端 JavaScript 调用示例

```javascript
// 📌 获取产业链列表
async function loadChains() {
    const response = await fetch("/api/chain/list");
    const data = await response.json();
    console.log(data.chains);  // [{id: 1, name: "新能源", ...}, ...]
}

// 📌 创建新产业链（触发 AI 生成岗位）
async function createChain(name) {
    const response = await fetch("/api/chain/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name })
    });
    const data = await response.json();
    if (response.ok) {
        console.log("创建成功！AI 生成了", data.jobs.length, "个岗位");
    } else {
        console.error("创建失败：", data.error);
    }
}

// 📌 删除产业链
async function deleteChain(chainId) {
    const response = await fetch(`/api/chain/${chainId}/delete`, {
        method: "DELETE"
    });
    const data = await response.json();
    console.log(data.deleted);  // true
}

// 📌 启动爬取
async function startCrawl(jobId) {
    const response = await fetch("/api/crawl/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId })
    });
    const data = await response.json();
    // 轮询进度
    pollCrawlStatus(data.task_id);
}

// 📌 轮询爬取进度
async function pollCrawlStatus(taskId) {
    const response = await fetch(`/api/crawl/${taskId}/status`);
    const data = await response.json();
    console.log(`状态: ${data.status}, 结果数: ${data.total_results}`);
    if (data.status === "running" || data.status === "pending") {
        setTimeout(() => pollCrawlStatus(taskId), 2000);  // 2秒后再查
    }
}
```

### 10.3 HTTP 状态码速查

| 状态码 | 含义 | 你的项目中使用 |
|--------|------|---------------|
| 200 OK | 成功 | 正常返回数据 |
| 400 Bad Request | 客户端错误（参数不对） | "请输入产业链名称"、"无效的JSON" |
| 401 Unauthorized | 未登录 | "账号或密码错误" |
| 404 Not Found | 资源不存在 | "产业链不存在"、"岗位不存在" |
| 405 Method Not Allowed | 请求方法不对 | "仅支持POST" |
| 500 Internal Server Error | 服务器出错 | `str(e)` |

---

## 11. 模板与静态文件 — 前端页面

### 11.1 模板渲染

你的项目将 HTML 文件直接放在 `frontend/` 目录下，通过 `render()` 返回：

```python
# config/urls.py
def index_view(request):
    if not request.user.is_authenticated:  # 检查是否已登录
        return redirect("/login.html")      # 没登录就跳转到登录页
    return render(request, "index.html")    # 已登录就返回主页
```

### 11.2 静态文件配置

```python
# settings.py
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "frontend"]
```

**这意味着**：`frontend/components/sidebar-menu.js` 在浏览器中通过 `/static/components/sidebar-menu.js` 访问。

**在 HTML 中引用**：
```html
<!-- frontend/index.html -->
<script src="/static/components/sidebar-menu.js"></script>
```

### 11.3 Django 模板语法（你暂时没用，但值得了解）

Django 自带模板引擎，可以在 HTML 中嵌入 Python 变量和逻辑：

```html
<!-- 假设 View 传了变量：{"chains": chains, "user_name": "张三"} -->

<h1>欢迎，{{ user_name }}</h1>       <!-- 变量插值 -->

<ul>
{% for chain in chains %}             <!-- 循环 -->
    <li>{{ chain.name }} - {{ chain.job_count }} 个岗位</li>
{% empty %}                           <!-- 列表为空时显示 -->
    <li>还没有产业链</li>
{% endfor %}
</ul>

{% if user.is_admin %}                <!-- 条件判断 -->
    <button>删除</button>
{% endif %}
```

> 你的项目用的是纯前端渲染（SPA 风格），HTML 通过 iframe 切换页面，数据通过 JS 调用 API 获取。两种方式各有优劣——前后端分离更灵活，模板渲染更简单。

---

## 12. 用户认证系统

Django 自带的 `django.contrib.auth` 提供了完整用户系统。

### 12.1 登录 API（你项目中的实现）

```python
# config/urls.py
@csrf_exempt
def api_login(request):
    import json
    from django.contrib.auth import authenticate, login
    from django.http import JsonResponse

    if request.method != "POST":
        return JsonResponse({"error": "仅支持POST"}, status=405)

    data = json.loads(request.body)
    user = authenticate(                # 验证用户名密码
        request,
        username=data.get("username"),
        password=data.get("password")
    )
    if user:
        login(request, user)            # 创建登录会话
        return JsonResponse({"ok": True, "user": {"name": user.username, "role": "专业负责人"}})
    return JsonResponse({"error": "账号或密码错误"}, status=401)
```

**登录流程**：
```
用户提交用户名+密码 → authenticate() 验证 → login() 创建 Session → 返回成功
```

### 12.2 退出登录

```python
def api_logout(request):
    from django.contrib.auth import logout
    from django.http import JsonResponse
    logout(request)       # 清除 Session
    return JsonResponse({"ok": True})
```

### 12.3 获取当前登录用户

```python
def api_user_info(request):
    from django.http import JsonResponse
    if request.user.is_authenticated:
        return JsonResponse({"name": request.user.username, "role": "专业负责人"})
    return JsonResponse({"error": "未登录"}, status=401)
```

### 12.4 检查登录状态的方式

```python
# 方式一：在 View 中手动检查
if not request.user.is_authenticated:
    return redirect("/login.html")

# 方式二：用装饰器（更简洁）
from django.contrib.auth.decorators import login_required

@login_required
def my_protected_view(request):
    # 只有登录用户才能访问
    ...
```

---

## 13. 启动与运行

### 13.1 开发服务器启动

```bash
# 进入项目目录
cd 岗位能力生成

# 启动开发服务器
python manage.py runserver
```

输出：
```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
August 01, 2026 - 20:30:00
Django version 6.0.7, using settings 'config.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

然后在浏览器访问 `http://127.0.0.1:8000/`（或 `http://localhost:8000/`）。

### 13.2 常用启动参数

```bash
# 指定端口
python manage.py runserver 8080        # 用 8080 端口

# 允许局域网访问（手机、其他电脑用你的IP访问）
python manage.py runserver 0.0.0.0:8000

# 指定配置文件
python manage.py runserver --settings=config.production
```

### 13.3 你的项目启动后可以访问的页面

| URL | 说明 |
|-----|------|
| `http://localhost:8000/` | 主框架页（需登录） |
| `http://localhost:8000/login.html` | 登录页 |
| `http://localhost:8000/能力图谱库.html` | 能力图谱管理 |
| `http://localhost:8000/用户管理.html` | 用户管理 |
| `http://localhost:8000/admin/` | Django 后台管理 |
| `http://localhost:8000/api/chain/list` | 产业链列表 API（JSON） |

---

## 14. 常用命令速查表

### 14.1 项目管理

```bash
# 创建新项目
django-admin startproject 项目名

# 创建新 App
python manage.py startapp App名

# 启动开发服务器
python manage.py runserver

# 进入 Django Shell（交互式测试）
python manage.py shell
```

### 14.2 数据库

```bash
# 生成迁移文件
python manage.py makemigrations

# 应用迁移
python manage.py migrate

# 查看迁移 SQL（不执行，只预览）
python manage.py sqlmigrate chain 0001

# 查看迁移状态
python manage.py showmigrations
```

### 14.3 用户管理

```bash
# 创建超级管理员
python manage.py createsuperuser

# 修改密码
python manage.py changepassword 用户名
```

### 14.4 调试工具

```bash
# Django Shell 交互式测试
python manage.py shell

# 进入 Shell 后可以这样测试：
>>> from chain.models import Chain, Job
>>> Chain.objects.all()                          # 查看所有产业链
>>> Chain.objects.create(name="测试产业链")       # 创建一条记录
>>> Job.objects.filter(chain__name="新能源").count()  # 统计新能源下面的岗位数
>>> chain = Chain.objects.first()
>>> chain.jobs.all()                             # 查看某个产业链的所有岗位
```

### 14.5 其他

```bash
# 检查项目配置是否有问题
python manage.py check

# 列出所有 URL 路由
python manage.py show_urls    # 需要安装 django-extensions

# 导出数据
python manage.py dumpdata chain.Chain --indent 2 > chain_data.json

# 导入数据
python manage.py loaddata chain_data.json
```

---

## 15. 进阶主题

### 15.1 项目的完整数据流

你的项目的核心业务流程：

```
① 用户创建产业链
   POST /api/chain/create {"name": "新能源"}
   → chain/views.py: api_chain_create()
   → 创建 Chain 记录
   → 调用 AI (step1_gen_jobs) 生成岗位列表
   → 批量创建 Job 记录
   → 返回 chain_id + jobs

② 用户查看产业链详情
   GET /api/chain/1/detail
   → chain/views.py: api_chain_detail()
   → 查 Chain + 关联 Job
   → 返回 JSON

③ 用户启动爬取
   POST /api/crawl/start {"job_id": 1}
   → crawl/views.py: api_crawl_start()
   → 创建 CrawlTask (status=pending)
   → 启动后台线程执行爬取 (step2_crawl_jobs)
   → 爬取完成后保存 JobListing
   → 更新 CrawlTask (status=completed)

④ 用户生成能力图谱
   POST /api/ability/generate {"job_id": 1}
   → ability/views.py: api_ability_generate()
   → 检查是否有已完成的 CrawlTask
   → 启动后台线程调用 AI (step3_gen_abilities)
   → 解析 AI 输出，保存 AbilityMap

⑤ 前端查询结果
   GET /api/ability/1/tree
   → ability/views.py: api_ability_tree()
   → 返回能力图谱树形 JSON
   → 前端渲染展示
```

### 15.2 Django 的请求处理完整流程

```
用户输入网址并回车
       │
       ▼
┌─────────────────┐
│  浏览器发送请求    │  GET http://localhost:8000/api/chain/list
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  WSGI/ASGI      │  接收 HTTP 请求，转成 Django 能理解的格式
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  中间件管道       │  Security → Session → Common → CSRF → Auth → Messages
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  URL 路由匹配    │  /api/chain/list → api_chain_list 函数
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  View 函数执行   │  查数据库、处理数据
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  返回响应        │  JsonResponse({"chains": [...]})
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  浏览器收到 JSON  │  JS 解析并渲染到页面
└─────────────────┘
```

### 15.3 ORM 查询进阶示例

当你熟悉基础操作后，可以试试这些更高级的查询：

```python
# 链式过滤
jobs = Job.objects.filter(chain__name="新能源", is_confirmed=True).order_by("-created_at")

# 跨表查询：找出有完成爬取任务的岗位
from crawl.models import CrawlTask
jobs_with_data = Job.objects.filter(crawl_tasks__status="completed").distinct()

# 聚合统计
from django.db.models import Count, Avg
chains = Chain.objects.annotate(job_count=Count("jobs")).filter(job_count__gt=0)
# 等价于：SELECT chain.*, COUNT(job.id) as job_count FROM chain
#         LEFT JOIN job ON chain.id = job.chain_id
#         GROUP BY chain.id HAVING COUNT(job.id) > 0

# 批量更新
Job.objects.filter(chain_id=1).update(is_confirmed=True)

# 使用 values_list 只取特定字段（性能更好）
job_names = list(Job.objects.filter(chain_id=1).values_list("name", flat=True))
# ["光伏运维技术员", "新能源整机装配工", ...]
```

### 15.4 安全性注意事项

```python
# ❌ 不安全：直接拼接 SQL
cursor.execute(f"SELECT * FROM chain WHERE name = '{user_input}'")

# ✅ 安全：用 Django ORM，自动防 SQL 注入
Chain.objects.filter(name=user_input)

# ❌ 不安全：生产环境暴露 DEBUG
DEBUG = True
ALLOWED_HOSTS = ["*"]

# ✅ 安全：生产配置
DEBUG = False
ALLOWED_HOSTS = ["你的域名.com"]
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")  # 从环境变量读取
```

### 15.5 推荐的下一步学习

1. **Django REST Framework (DRF)** — 如果你要写更多 API，DRF 比手写 View 更规范、更省代码
2. **Django 模板系统** — 如果你要做传统的服务端渲染页面
3. **celery + redis** — 把后台线程换成真正的异步任务队列（更稳定、可监控）
4. **PostgreSQL** — 把 SQLite 换成生产级数据库
5. **Docker 部署** — 打包成容器，方便在服务器上运行

### 15.6 你项目中的外部依赖

```bash
# 爬取相关
pip install html2text requests    # 网页抓取 + HTML转文本

# AI 调用相关
pip install openai                # 调用讯飞星火/豆包/DeepSeek 等 API

# （可选）JS 渲染的爬取
pip install crawl4ai             # 对 JS 渲染页面用浏览器引擎抓取
```

---

## 附录：你的项目全貌总结

```
┌────────────────────────────────────────────────────────────────┐
│                     岗位能力生成 系统架构                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   frontend/                    config/                         │
│   ┌──────────────┐            ┌──────────────┐                │
│   │ index.html   │            │ settings.py  │ 全局配置         │
│   │ login.html   │            │ urls.py      │ URL 路由         │
│   │ 能力图谱库.html│            │ wsgi.py      │ 部署入口         │
│   │ 用户管理.html │            └──────────────┘                │
│   │ 角色管理.html │                                            │
│   └──────────────┘            manage.py — 命令行入口            │
│                                                                │
│   ┌────────────────────────────────────────────────────┐      │
│   │                    Django ORM                       │      │
│   │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐ │      │
│   │  │ chain/      │  │ crawl/       │  │ ability/  │ │      │
│   │  │ Chain       │  │ CrawlTask    │  │ AbilityMap│ │      │
│   │  │ Job         │  │ JobListing   │  │           │ │      │
│   │  └─────────────┘  └──────────────┘  └───────────┘ │      │
│   └──────────────────────┬─────────────────────────────┘      │
│                          │                                     │
│   data/db.sqlite3  ←────┘  SQLite 数据库                       │
│                                                                │
│   ┌────────────────────────────────────────────────────┐      │
│   │  AI 脚本 (Django 外部调用)                           │      │
│   │  step1_gen_jobs.py     ← AI 生成岗位                  │      │
│   │  step2_crawl_jobs.py   ← 爬取招聘网站                 │      │
│   │  step3_gen_abilities.py ← AI 提取能力图谱             │      │
│   └────────────────────────────────────────────────────┘      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

> 🎉 **恭喜你读完了！** 这份教程覆盖了 Django 的核心概念，并以你的项目代码为例进行了详细讲解。
>
> 建议的学习路线：
> 1. 先把项目跑起来（`python manage.py runserver`）
> 2. 在浏览器里访问各个页面，F12 看网络请求
> 3. 打开 Django Shell（`python manage.py shell`），手动创建几条数据
> 4. 尝试修改 `chain/views.py` 中的某个 API，加一个新字段
> 5. 试着新建一个 App，写一个简单的 Model + View + URL
>
> **遇到问题怎么办？**
> - Django 官方文档（中文）：https://docs.djangoproject.com/zh-hans/
> - 在终端看错误信息（`DEBUG=True` 时会显示详细堆栈）
> - 用 `print()` 在 View 里打印变量调试
> - Django Shell 里测试 ORM 查询
