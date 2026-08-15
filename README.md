# 海角下载自动化 Telegram 机器人 (Haijiao Downloader Telegram Bot)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)](https://www.python.org/)
[![Aiogram: 3.x](https://img.shields.io/badge/aiogram-3.x-blue.svg)](https://docs.aiogram.dev/)
[![Docker: Ready](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

一个轻量级、全自动化的海角社区 Telegram 下载机器人。
专为**低配置、小磁盘 VPS** 量身打造，具备**边下载边上传**、**上传成功即刻清理**的防爆盘双工流水线，实现从链接提交到 OpenList Web 浏览的全流程自动化。

---

## 🌟 核心特性

- 🌐 **发布页动态域名探活**：从 `https://hjw2026.com` 自动抓取最新线路并进行并发测速，智能选取延迟最低的活跃镜像域名，支持失效自动切换。
- 📝 **高保真排版还原**：解析文章 DOM 树结构，精准保留段落顺序与图片/视频的原始插入相对位置，生成带 YAML 元数据的规范 `post.md`。
- 🔐 **多媒体流式解密**：
  - 自动修复与解密带有混淆头部/加密特征的图片，校验 Magic Header 还原为标准格式。
  - 并发拉取 HLS/m3u8 AES-128 加密 TS 切片及 Key，解密并转封装为通用 `.mp4`。
- 🛡️ **智能防爆盘守护者 (DiskGuard)**：
  - 实时监控 VPS 磁盘空间，低于安全阈值（默认 2GB）时自动暂停新帖下载。
  - 采用**篇级双工流水线**，下载完单帖立即交由后台 Rclone 异步上传，上传校验成功即刻彻底删除本地文件并唤醒后续下载。
- 📂 **OpenList Web 索引直达**：
  - 自动根据存储目录规则生成 OpenList Web 端访问链接，在 Telegram 中附带一键打开按钮。
- 🤖 **Telegram 交互友好 & 白名单鉴权**：
  - 支持直接粘贴单帖链接或纯 ID 解析。
  - 发送作者主页链接时，自动弹出 Inline Keyboard 交互式选择下载页码范围（最新 1 页、前 3 页、前 5 页、全量或自定义页码）。
  - 内置管理员 ID 白名单拦截，防止未经授权的滥用。
- ⚙️ **简洁 YAML 配置**：使用易读的 `config.yaml` 替代复杂的环境变量。

---

## 🛠️ 前置准备工作

在正式运行机器人前，请准备好以下信息：

### 1. 获取 Telegram Bot Token
1. 在 Telegram 中搜索官方机器人 [@BotFather](https://t.me/BotFather) 并发送 `/newbot`。
2. 按照提示设置机器人名称和用户名，成功后将获得一段 Token（例如：`123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`）。

### 2. 获取你的 Telegram User ID
1. 在 Telegram 中搜索 [@userinfobot](https://t.me/userinfobot) 并发送 `/start`。
2. 记录返回的 `Id` 数字（例如：`123456789`），用于配置访问白名单。

### 3. 配置 Rclone 对接 OneDrive
确保 VPS 已安装并在本地配置好了 Rclone 对接 OneDrive：
```bash
# 安装 rclone (Linux)
curl https://rclone.org/install.sh | sudo bash

# 配置并添加 OneDrive remote (例如 remote 命名为 onedrive)
rclone config

# 验证连接是否成功
rclone lsd onedrive:
```

---

## 🚀 部署指南

### 方式 A：Docker Compose 一键部署 (强烈推荐)

#### 1. 克隆代码并进入项目目录
```bash
git clone https://github.com/zj2xr7/haijiao-downloader-telegram.git
cd haijiao-downloader-telegram
```

#### 2. 生成并编辑配置文件 `config.yaml`
```bash
cp config.example.yaml config.yaml
nano config.yaml
```

将你的 Bot Token、用户 ID、OneDrive 目标路径及 OpenList 域名填入：
```yaml
bot:
  token: "你的_TELEGRAM_BOT_TOKEN"
  allowed_user_ids:
    - 你的_TELEGRAM_USER_ID

network:
  publish_page_url: "https://hjw2026.com"
  domain_refresh_interval_hours: 6
  request_timeout_seconds: 30
  max_download_concurrency: 2

storage:
  temp_download_dir: "./downloads_temp"
  min_free_disk_gb: 2.0

rclone:
  config_path: ""
  remote_dest: "onedrive:Media/Haijiao"
  max_upload_concurrency: 2

openlist:
  base_url: "https://pan.yourdomain.com"
  mount_path: "/Media/Haijiao"
```

#### 3. 启动容器
```bash
docker compose up -d --build
```

#### 4. 查看实时运行日志
```bash
docker compose logs -f
```

---

### 方式 B：Linux VPS 原生 Python 运行

#### 1. 安装系统依赖工具
```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv rclone ffmpeg
```

#### 2. 配置 Python 虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. 初始化配置文件
```bash
cp config.example.yaml config.yaml
nano config.yaml
```

#### 4. 运行服务
```bash
python src/main.py
```

#### 5. (可选) 配置 Systemd 开机自启守护进程
创建 `/etc/systemd/system/haijiao-bot.service`：
```ini
[Unit]
Description=Haijiao Downloader Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/haijiao-downloader-telegram
ExecStart=/root/haijiao-downloader-telegram/venv/bin/python -m src.main
Restart=always
RestartSec=5
Environment=PYTHONPATH=/root/haijiao-downloader-telegram

[Install]
WantedBy=multi-user.target
```
启动并启用自启：
```bash
sudo systemctl daemon-reload
sudo systemctl enable haijiao-bot
sudo systemctl start haijiao-bot
sudo journalctl -u haijiao-bot -f
```

---

## 📖 Telegram 机器人使用教程

| 操作场景 | 用户操作示例 | 机器人响应与处理流程 |
| :--- | :--- | :--- |
| **单帖下载** | 直接发送帖子链接：<br>`https://hjw2026.com/post/details?pid=12345`<br>或纯数字 ID：`12345` | 1. 自动提取 ID 并查询最新活跃镜像<br>2. 抓取正文排版，解密图片与视频<br>3. 生成 `post.md` 并排入后台上传队列<br>4. 上传至 OneDrive 后删除本地文件<br>5. 发送完成卡片与 OpenList 直达按钮 |
| **作者批量下载** | 直接发送作者主页链接：<br>`https://hjw2026.com/user/home?uid=9988` | 1. 自动解析作者昵称与总页数<br>2. 弹出交互式按钮引导选择下载范围：<br>&nbsp;&nbsp;• `[📄 下载第 1 页]`<br>&nbsp;&nbsp;• `[📚 下载前 3 页]`<br>&nbsp;&nbsp;• `[📦 全部下载]`<br>&nbsp;&nbsp;• `[✏️ 自定义页码 (如 1-3 或 2,4)]`<br>3. 选定后后台以双工流水线批量自动处理 |
| **查看系统状态** | 发送指令：`/status` | 显示 VPS 磁盘剩余容量、DiskGuard 防爆盘阈值、当前正在使用的海角镜像域名与网盘挂载配置 |
| **查看帮助** | 发送指令：`/help` 或 `/start` | 输出系统使用指南与支持的链接格式 |

---

## 📁 归档与存储目录结构

上传至 OneDrive 及 OpenList 浏览的目录结构如下：

```
Media/Haijiao/
└── {作者昵称}_{作者ID}/
    └── [{帖子ID}] {帖子标题}/
        ├── post.md          # 还原原文排版的 Markdown 文件 (包含相对路径图片/视频引用)
        ├── images/          # 解密后的标准图片格式 (01.jpg, 02.jpg ...)
        │   ├── 01.jpg
        │   └── 02.jpg
        └── videos/          # 解密并合并转封装后的 MP4 视频
            └── 01.mp4
```

---

## 🧪 开发者指南与单元测试

运行项目测试套件：
```bash
pytest -v
```

项目测试覆盖了配置解析、动态域名探活、HTML 排版解析、AES-128 TS 分片解密、DiskGuard 空间控制、Rclone 上传与端到端集成测试。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
