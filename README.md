# 海角下载自动化 Telegram 机器人 (Haijiao Downloader Telegram Bot)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)](https://www.python.org/)
[![Aiogram: 3.x](https://img.shields.io/badge/aiogram-3.x-blue.svg)](https://docs.aiogram.dev/)
[![Docker: Ready](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

一个轻量级、全自动化的海角社区 Telegram 下载机器人。
专为**低配置、小磁盘 VPS** 量身打造，具备**边下载边上传**、**上传成功即刻清理**的防爆盘双工流水线，实现从链接提交到 OpenList Web 浏览的全流程自动化。

---

## 🌟 核心特性

- 🌐 **发布页动态域名探活与解密**：
  - 自动从 `https://hjw2026.com` 提取并解密 AES-256 加密的最新线路池与备用镜像。
  - 并发测速并智能选取延迟最低的活跃镜像域名，支持线路失效自动切换与重试。
- 📝 **高保真排版还原**：
  - 解析文章 DOM 树结构，精准保留段落顺序与图片/视频的原始插入相对位置。
  - 生成带 YAML 元数据的规范 `post.md`。
- 🔐 **多媒体流式解密**：
  - 自动修复与解密带有混淆头部/加密特征的图片，校验 Magic Header 还原为标准格式。
  - 并发拉取 HLS/m3u8 AES-128 加密 TS 切片及 Key，解密并转封装为通用 `.mp4`。
- 🛡️ **智能防爆盘守护者 (DiskGuard)**：
  - 实时监控 VPS 磁盘空间，低于安全阈值（默认 2GB）时自动暂停新帖下载。
  - 采用**篇级双工流水线**，下载完单帖立即交由后台 Rclone 异步上传，上传校验成功即刻彻底删除本地文件并唤醒后续下载。
- 📂 **OpenList Web 索引直达**：
  - 自动根据存储目录规则生成 OpenList Web 端访问链接，在 Telegram 中附带一键打开按钮。
- 🤖 **Telegram 交互友好 & 快捷命令**：
  - 输入 `/` 即可弹出内置快捷命令菜单（/start, /status, /help, /dl）。
  - 消息内命令高亮，点击任意蓝色命令（如 /status）即可自动发送并执行。
  - 发送作者主页链接时，自动弹出 Inline Keyboard 交互式选择下载页码范围（最新 1 页、前 3 页、前 5 页、全量或自定义页码）。
  - 内置管理员 ID 白名单拦截，防止未经授权的滥用。
- ⚙️ **简洁清晰的 YAML 配置**：使用易读的 `config.yaml` 集中管理所有配置项。

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

## ⚙️ 配置文件说明 (`config.yaml`)

项目采用 YAML 格式管理配置。从模板复制生成：
```bash
cp config.example.yaml config.yaml
nano config.yaml
```

### 完整配置项详细参数表

| 顶级节点 | 参数键名 (`Key`) | 类型 | 默认值 / 示例 | 详细功能说明 |
| :--- | :--- | :--- | :--- | :--- |
| **`bot`** | `token` | `string` | `"123456:ABC..."` | **[必填]** 从 [@BotFather](https://t.me/BotFather) 获取的 Telegram 机器人 Token。 |
| | `allowed_user_ids` | `array[int]` | `[123456789]` | **[鉴权白名单]** 允许使用该 Bot 的 Telegram 账号数字 ID 列表。留空 `[]` 则表示公开访问不设白名单。 |
| **`network`** | `publish_page_url` | `string` | `"https://hjw2026.com"` | **[永久发布页地址]** 用于自动抓取并解密最新海角可用镜像线路与备用线路。 |
| | `domain_refresh_interval_hours`| `int` | `6` | **[域名缓存有效期]** 测速选出的活跃域名在本地缓存的小时数，过期后自动重新探活测速。 |
| | `request_timeout_seconds` | `int` | `30` | **[网络请求超时]** HTTP 抓取与分片下载的全局超时时间（单位：秒）。 |
| | `max_download_concurrency` | `int` | `2` | **[单帖多媒体下载并发数]** 控制单个帖子内图片及 TS 视频分片的最大下载并发量。 |
| **`storage`** | `temp_download_dir` | `string` | `"./downloads_temp"` | **[本地临时缓存目录]** 临时存储抓取的排版和解密后的媒体文件，上传成功后系统自动彻底清理。 |
| | `min_free_disk_gb` | `float` | `2.0` | **[DiskGuard 磁盘安全红线]** VPS 剩余空间低于该阈值（GB）时自动暂停新下载，待后台上传完成释放空间后自动唤醒。 |
| **`rclone`** | `config_path` | `string` | `""` | **[自定义 rclone 配置路径]** 留空时默认读取系统 `~/.config/rclone/rclone.conf`。 |
| | `remote_dest` | `string` | `"onedrive:Media/Haijiao"`| **[网盘上传目标路径]** 格式为 `Remote配置名:远端根目录`。 |
| | `max_upload_concurrency` | `int` | `2` | **[后台上传任务并发上限]** 允许同时向网盘上传的帖子任务数量。 |
| **`openlist`** | `base_url` | `string` | `"https://pan.example.com"`| **[OpenList 站点 URL]** 你的 OpenList 网站访问基础域名（末尾不要带斜杠 `/`）。 |
| | `mount_path` | `string` | `"/Media/Haijiao"` | **[OpenList 挂载路径]** OneDrive 在 OpenList 中挂载的虚拟路径（以斜杠 `/` 开头）。 |

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

#### 2. 配置 Python 虚拟环境并安装依赖
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

## 📖 Telegram 机器人操作与命令

启动机器人后，在对话框输入 `/` 即可自动弹出命令菜单；消息中的所有蓝色命令均可**直接点击发送**：

| 指令 / 操作 | 用户操作示例 | 机器人响应与功能说明 |
| :--- | :--- | :--- |
| **单帖下载** | 直接发送帖子链接：<br>`https://hjw2026.com/post/details?pid=12345`<br>或纯数字 ID：`12345`<br>或指令：`/dl 12345` | 1. 自动提取 ID 并查询最新活跃镜像<br>2. 抓取正文排版，解密图片与视频<br>3. 生成 `post.md` 并排入后台上传队列<br>4. 上传至 OneDrive 后彻底删除本地文件<br>5. 发送完成卡片与 OpenList 直达按钮 |
| **作者批量下载** | 直接发送作者主页链接：<br>`https://hjw2026.com/user/home?uid=9988`<br>或指令：`/dl https://...uid=9988` | 1. 自动解析作者昵称与总作品页数<br>2. 弹出交互式按钮引导选择下载范围：<br>&nbsp;&nbsp;• `[📄 下载第 1 页]`<br>&nbsp;&nbsp;• `[📚 下载前 3 页]`<br>&nbsp;&nbsp;• `[📦 全部下载]`<br>&nbsp;&nbsp;• `[✏️ 自定义页码 (如 1-3 或 2,4)]`<br>3. 选定后后台以双工流水线批量自动处理 |
| **/status** | 点击或发送：`/status` | 查看 VPS 磁盘剩余容量、DiskGuard 防爆盘阈值、当前正在使用的海角镜像域名与网盘挂载配置 |
| **/help** | 点击或发送：`/help` | 输出系统使用指南、支持的链接格式与操作提示 |
| **/start** | 点击或发送：`/start` | 重新展示欢迎信息与功能概览 |

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

测试套件已覆盖：
- 结构化 YAML 配置读取与模型校验
- 发布页 AES-256 加密配置解析与域名探活
- 文章 HTML 排版与 DOM 树提取
- 图片 Header 混淆修复与 HLS AES-128 TS 分片解密
- DiskGuard 空间检测与并发信号量控制
- Rclone 异步上传、本地彻底清理与 OpenList 链接拼装
- 全链路端到端集成测试

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
