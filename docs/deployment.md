# VPS 部署与环境配置指南 (Deployment & Configuration Guide)

本文档介绍如何在 Linux VPS（如 Debian / Ubuntu / CentOS）上完成系统的环境依赖安装、Rclone 配置、OpenList 映射配置以及通过 Docker 或 Systemd 运行服务。

---

## 1. 基础环境与依赖要求

- **操作系统**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+ 等)
- **Python**: 3.10+ (推荐 3.11)
- **外部工具**:
  - `rclone` (用于将本地媒体同步至 OneDrive)
  - `ffmpeg` (用于 TS 视频切片合并转封装)

---

## 2. 外部依赖工具安装

### 2.1 安装 Rclone 与 FFmpeg (以 Ubuntu/Debian 为例)

```bash
# 更新源并安装基础工具
sudo apt update
sudo apt install -y curl wget ffmpeg git

# 安装官方最新版 Rclone
sudo -v ; curl https://rclone.org/install.sh | sudo bash
```

### 2.2 配置 Rclone 对接 OneDrive

```bash
# 启动交互式配置引导
rclone config

# 按照提示选择新建 remote：
# 1. Name: onedrive (或自定义名称)
# 2. Type: 选 Microsoft OneDrive (通常是选项 31 左右)
# 3. 按照提示完成网页端 OAuth 授权
# 4. 测试连接：
rclone lsd onedrive:
```

---

## 3. 项目部署方式一：Docker Compose 容器化部署 (推荐)

### 3.1 编写 `docker-compose.yml`

```yaml
version: "3.8"

services:
  haijiao-bot:
    build: .
    container_name: haijiao-downloader-telegram
    restart: unless-stopped
    volumes:
      # 挂载宿主机的 rclone 配置文件
      - ~/.config/rclone/rclone.conf:/root/.config/rclone/rclone.conf:ro
      # 挂载临时下载目录
      - ./downloads_temp:/app/downloads_temp
      # 挂载配置文件
      - ./.env:/app/.env:ro
    environment:
      - PYTHONUNBUFFERED=1
```

### 3.2 编写 `Dockerfile`

```dockerfile
FROM python:3.11-slim

# 安装系统依赖 (ffmpeg, rclone, ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    rclone \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建临时下载目录
RUN mkdir -p downloads_temp

CMD ["python", "src/main.py"]
```

### 3.3 启动服务

```bash
# 复制并修改环境变量配置
cp .env.example .env
nano .env

# 构建并后台启动
docker compose up -d --build

# 查看实时运行日志
docker compose logs -f
```

---

## 4. 项目部署方式二：Systemd 守护进程运行 (原生 Python)

### 4.1 安装 Python 依赖

```bash
# 进入项目目录并创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4.2 创建 Systemd 服务文件

创建 `/etc/systemd/system/haijiao-bot.service`：

```ini
[Unit]
Description=Haijiao Downloader Telegram Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/haijiao-downloader-telegram
ExecStart=/root/haijiao-downloader-telegram/venv/bin/python src/main.py
Restart=always
RestartSec=5
EnvironmentFile=/root/haijiao-downloader-telegram/.env

[Install]
WantedBy=multi-user.target
```

### 4.3 管理命令

```bash
# 重载服务并设置开机自启
sudo systemctl daemon-reload
sudo systemctl enable haijiao-bot
sudo systemctl start haijiao-bot

# 查看运行状态与日志
sudo systemctl status haijiao-bot
sudo journalctl -u haijiao-bot -f
```

---

## 5. OpenList 联动与链接映射说明

1. 假设 OneDrive 存储结构为：
   `onedrive:Media/Haijiao/{author_folder}/{post_folder}/`
2. 假设你的 OpenList 站点地址为 `https://pan.mydomain.com`，且将上述 OneDrive 挂载于 `/Media/Haijiao` 路径下。
3. 在 `.env` 中配置：
   ```ini
   OPENLIST_BASE_URL=https://pan.mydomain.com
   OPENLIST_MOUNT_PATH=/Media/Haijiao
   ```
4. 任务完成后，Bot 将输出如下直达链接：
   `https://pan.mydomain.com/Media/Haijiao/{author_name}_{author_id}/[{post_id}]%20{title}/`
   用户点击即可在 OpenList 网页端直接浏览文章排版与视频。
