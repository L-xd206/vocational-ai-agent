# 公司 Linux 服务器部署说明

本项目按 `公司端口转换 -> Nginx:8000 -> Gunicorn:8001 -> Django` 部署。

## 端口约定

- `8000`：Nginx 监听端口，公司网关只转发到这个端口。
- `8001`：Gunicorn 回环地址端口，只允许服务器本机访问，禁止映射或开放。
- 公司若提供外部 HTTPS，需让网关传递 `Host` 和 `X-Forwarded-Proto: https`。

## 首次安装（CentOS 7 x86_64）

```bash
yum install -y git nginx gcc gcc-c++ make

cd /tmp
curl -fL -o miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-py311_24.5.0-0-Linux-x86_64.sh
echo "38b203bb1f2be78b735ebc00162f29e8e73fcd9a619ed5980490a72193ee1f58  miniconda.sh" | sha256sum -c -
bash miniconda.sh -b -p /opt/miniconda3
/opt/miniconda3/bin/python --version

cd /srv
git clone https://github.com/L-xd206/vocational-ai-agent.git
cd /srv/vocational-ai-agent/education_platform

/opt/miniconda3/bin/python -m venv .venv
./.venv/bin/pip install --upgrade pip wheel
./.venv/bin/pip install -r requirements-production.txt
mkdir -p data output collectedstatic
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，填入服务器地址、Django 密钥和 DeepSeek 密钥。DeepSeek Key 只能存在于服务器 `.env`，不能提交 Git。

公司外层尚未提供 HTTPS 时，先设置：

```env
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=服务器内网IP,公司提供的外部域名或IP
DJANGO_CSRF_TRUSTED_ORIGINS=http://公司提供的外部地址
DJANGO_SECURE_SSL_REDIRECT=false
DJANGO_SESSION_COOKIE_SECURE=false
DJANGO_CSRF_COOKIE_SECURE=false
```

公司外层启用 HTTPS 且传递 `X-Forwarded-Proto: https` 后，将来源改成 `https://...`，并把三个安全开关改为 `true`。

## 初始化项目

```bash
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py seed_judge_demo
./.venv/bin/python manage.py collectstatic --noinput
./.venv/bin/python manage.py check
```

## 注册服务

```bash
cp deploy/vocational-ai.service /etc/systemd/system/
cp deploy/nginx-vocational-ai.conf /etc/nginx/conf.d/vocational-ai.conf

chown -R nginx:nginx data output collectedstatic
chown nginx:nginx .env
chmod 600 .env

systemctl daemon-reload
systemctl enable --now vocational-ai
nginx -t
systemctl enable --now nginx
```

## 公司做端口转换前的服务器内测

```bash
curl -I http://127.0.0.1:8000/login.html
systemctl status vocational-ai --no-pager
journalctl -u vocational-ai -n 100 --no-pager
```

公司网络侧应把评委访问地址转发到 `服务器内网IP:8000`。安全组或防火墙只允许公司网关访问 `8000`；不要开放 `8001`。

## 后续更新

```bash
cd /srv/vocational-ai-agent
git pull --ff-only origin main
cd education_platform
./.venv/bin/pip install -r requirements-production.txt
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py collectstatic --noinput
systemctl restart vocational-ai
nginx -t && systemctl reload nginx
```
