# 海角下载自动化 Telegram 机器人 (Haijiao Downloader Telegram Bot)

基于 Python 3.11 异步生态构建的轻量级、自动化下载 Telegram Bot。支持海角社区动态域名探活、受保护文章排版抓取、加密多媒体流解密、Markdown 本地排版归档、Rclone 异步上传 OneDrive、VPS 防爆盘自适应清理以及 OpenList Web 访问链接生成。

---

## 🌟 核心特性

1. **Telegram 交互友好**：
   - 支持直接发送帖子链接、纯数字 ID 或作者主页链接。
   - 识别作者主页时，自动弹出 Inline Keyboard 交互式引导选择下载页码范围（最新 1 页、前 3 页、前 5 页、全量或自定义页码）。
   - 内置管理员 Telegram ID 白名单拦截校验（`AuthMiddleware`）。
2. **发布页动态域名解析**：
   - 自动定时或在失效时抓取 `https://hjw2026.com` 提取最新备选线路，并发测速选择最低延迟的活跃镜像站。
3. **高保真排版与媒体解密**：
   - 解析原始正文 DOM 树，保留段落顺序与图片/视频的原始插入相对位置，生成规范的带 YAML Frontmatter 的 `post.md`。
   - 内置多媒体流式解密引擎（支持混淆/自定义头图片流还原、HLS/m3u8 AES-128 分片并发拉取、解密与合并封装为标准 `.mp4`）。
4. **篇级双工流水线与智能防爆盘 (DiskGuard)**：
   - 单帖作为流水线原子单位，下载解密完成后即刻加入后台上传队列（边下边传）。
   - 实时监控 VPS 磁盘空间，低于安全阈值（默认 2GB）时自动暂停新帖下载，待 Rclone 上传完成并彻底删除本地文件后自动唤醒。
5. **OpenList 联动**：
   - 上传至 OneDrive 后，自动根据目录规则生成 OpenList Web 端直达访问链接，在 Telegram 中一键打开。

---

## 📂 项目结构

```
haijiao-downloader-telegram/
├── .env.example              # 环境变量配置模板
├── .gitignore
├── README.md                 # 项目说明与快速上手
├── requirements.txt          # Python 依赖清单
├── Dockerfile                # 容器化构建文件
├── docker-compose.yml        # Docker Compose 编排
├── docs/                     # 完整架构与开发规范文档
│   ├── superpowers/specs/    # 架构设计 Spec
│   ├── architecture.md       # 系统架构与核心机制说明
│   ├── git-flow-guide.md     # Git Flow 本地与协作规范
│   ├── deployment.md         # VPS 部署与配置指南
│   └── api-and-models.md     # 核心数据模型与接口规范
├── src/
│   ├── main.py               # 程序统一启动入口
│   ├── config.py             # 全局配置管理 (Pydantic Settings)
│   ├── models.py             # Pydantic 数据模型定义
│   ├── bot/                  # Telegram Bot 交互层 (Aiogram v3)
│   │   ├── bot_app.py        # Bot 实例与路由组装
│   │   ├── handlers/         # 基础与下载路由处理器
│   │   ├── middlewares/      # 白名单鉴权拦截中间件
│   │   └── keyboards/        # Inline Keyboard 交互键盘
│   ├── core/                 # 核心调度与业务引擎
│   │   ├── resolver.py       # 动态域名提取与测速探活
│   │   ├── crawler.py        # 帖子内容与作者主页解析器
│   │   ├── decryptor.py      # 多媒体流解密 (AES / HLS / 混淆图片)
│   │   ├── renderer.py       # Markdown 排版生成器
│   │   ├── disk_guard.py     # 磁盘空间监控与安全自适应控制器
│   │   ├── pipeline.py       # 双工流水线调度器 (下载+上传并行)
│   │   └── uploader.py       # Rclone 执行器与 OpenList 链接映射
│   └── utils/                # 工具库
│       ├── logger.py         # 结构化彩色日志
│       └── http_client.py    # 异步 HTTP 客户端
└── tests/                    # 单元与集成测试套件
```

---

## 🚀 快速开始

### 1. 复制配置文件

```bash
cp .env.example .env
nano .env
```

配置核心参数：
- `BOT_TOKEN`: 你的 Telegram Bot Token（通过 [@BotFather](https://t.me/BotFather) 获取）
- `ALLOWED_USER_IDS`: 允许使用机器人的 Telegram 用户 ID（逗号分隔）
- `RCLONE_REMOTE_DEST`: OneDrive 目标上传路径（如 `onedrive:Media/Haijiao`）
- `OPENLIST_BASE_URL`: 你的 OpenList 访问域名（如 `https://pan.example.com`）
- `OPENLIST_MOUNT_PATH`: OneDrive 在 OpenList 中的挂载路径（如 `/Media/Haijiao`）

### 2. 方式 A：Docker Compose 一键部署 (推荐)

```bash
docker compose up -d --build
docker compose logs -f
```

### 3. 方式 B：本地/VPS 原生 Python 运行

```bash
# 1. 安装系统依赖 (Linux)
sudo apt update && sudo apt install -y rclone ffmpeg

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动服务
python src/main.py
```

### 4. 运行全套测试

```bash
pytest -v
```
