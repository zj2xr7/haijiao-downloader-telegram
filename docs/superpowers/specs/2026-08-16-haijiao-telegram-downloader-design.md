# 海角下载机器人系统架构设计与规范 (Design Specification)

## 1. 项目背景与目标

本项目旨在构建一个高可用、轻量级、自动化运行的 Telegram 下载机器人系统（Haijiao Downloader Telegram Bot）。
系统运行在资源紧凑型 VPS 上，能够根据用户发送的海角社区网址（单帖 URL 或作者主页 URL），全自动完成**动态域名探活解析**、**受保护文章排版抓取**、**加密图片与多媒体流解密**、**本地 Markdown 排版归档**、**基于 Rclone 的异步云端上传（OneDrive）**、**本地磁盘即时清理**以及**OpenList 访问链接生成与 Telegram 消息回调**。

---

## 2. 核心设计约束与应对策略

| 核心约束 / 难点 | 应对策略与设计方案 |
| :--- | :--- |
| **VPS 磁盘空间极小** (如 5GB~20GB，但可容纳单篇帖子) | 引入 **DiskGuard（磁盘自适应守护控制器）** 与 **篇级双工流水线（Post-level Pipeline）**。下载完单篇立即加入后台上传队列；上传校验成功立即彻底删除本地文件；当剩余可用磁盘空间低于阈值（`MIN_FREE_DISK_GB`，默认 2GB）时，自动挂起新帖下载，待释放后自动唤醒。 |
| **目标站点域名频繁变动** | 内置 **动态域名解析器 (`core/resolver.py`)**。从发布页 `https://hjw2026.com` 提取最新备选线路，通过异步轻量并发测速选取最优节点，支持自动重探与热切换。 |
| **图片与视频加密保护** | 内置 **流式解密器 (`core/decryptor.py`)**。支持图片文件头混淆/AES解密与 HLS/m3u8 AES-128 分片多线程拉取、解密与合并转封装，生成通用 `.mp4` 和标准图片格式。 |
| **排版保真度与阅读体验** | 内置 **Markdown 渲染引擎 (`core/renderer.py`)**。解析原始 HTML 排版逻辑，提取段落、标题、引用及媒体插入相对位置，生成带 YAML 元数据的 `post.md`，并在相对路径下的 `images/` 和 `videos/` 保存媒体。 |
| **安全性与多租户隔离** | 采用 **Telegram 用户 ID 白名单鉴权中间件**，仅限授权管理员使用；作者页支持交互式分页选择（Inline Keyboards），避免无节制全量下载造成资源耗尽。 |

---

## 3. 系统架构与模块划分

```mermaid
flowchart TD
    User([Telegram 用户]) <-->|发送指令 / 接收通知| Bot[Telegram Bot (aiogram v3)]
    
    subgraph BotLayer [Bot 交互层]
        Bot --> AuthMiddleware[白名单鉴权中间件]
        AuthMiddleware --> Router[命令与回调路由器]
        Router --> FSM[FSM 状态机 (作者分页引导)]
    end
    
    subgraph EngineLayer [核心业务调度层]
        Router --> TaskQueue[异步任务调度队列]
        TaskQueue --> DiskGuard[DiskGuard 磁盘安全门禁]
        DiskGuard --> Crawler[海角解析器 (Crawler)]
        
        Resolver[动态域名解析器] -.->|提供最新域名| Crawler
        Crawler --> Decryptor[多媒体流式解密器]
        Decryptor --> Renderer[Markdown 排版生成器]
        Renderer --> LocalFS[(本地暂存目录)]
    end
    
    subgraph PipelineLayer [并发上传与清理层]
        LocalFS --> Uploader[Rclone 异步上传执行器]
        Uploader -->|rclone copy| OneDrive[(OneDrive 云存储)]
        Uploader -->|上传成功| Cleaner[即时清理器]
        Cleaner -->|释放空间| LocalFS
        Cleaner -.->|空间释放通知| DiskGuard
        Uploader --> OpenListMapper[OpenList 链接映射器]
        OpenListMapper --> Bot
    end
    
    subgraph ExternalServices [外部依赖]
        PubSite[发布页 https://hjw2026.com] -.-> Resolver
        OneDrive -.-> OpenListWeb[OpenList Web 站点]
    end
```

### 3.1 模块职责清单

1. **`src/bot/`**:
   - `handlers/base.py`: 处理 `/start`, `/help`, `/status` 等基础命令。
   - `handlers/download.py`: 接收单帖 URL、作者主页 URL，处理参数提取与 FSM 交互。
   - `middlewares/auth.py`: 校验 `telegram_user_id in ALLOWED_USER_IDS`。
   - `keyboards/inline.py`: 生成作者页分页选择（如“下载第 1-3 页”、“全部”、“自定义”）的 Inline Keyboard。

2. **`src/core/`**:
   - `resolver.py`: 负责异步拉取 `https://hjw2026.com`，清洗出域名列表，并发测速并缓存最优活跃域名，具备故障重测机制。
   - `crawler.py`: 负责归一化 URL、抓取帖子详情/作者主页列表 API 或 HTML。
   - `decryptor.py`: 负责解密媒体数据流，合成标准格式文件。
   - `renderer.py`: 负责将帖子内容与媒体相对路径序列化为 `post.md`。
   - `disk_guard.py`: 负责检测 VPS 磁盘剩余容量，通过 `asyncio.Event` 提供门禁通行证（Acquire / Wait）。
   - `pipeline.py`: 负责协调单帖下载工作流与后台上传工作流的生命周期。
   - `uploader.py`: 负责构造并执行 `rclone copy` 命令，上传完成后调用清理逻辑，并按映射规则输出 OpenList 直达 URL。

---

## 4. 详细流程与数据流

### 4.1 单帖处理时序 (Single Post Flow)

1. 用户向 Bot 发送帖子链接（如 `https://hjwxxx.com/post/details?pid=123456` 或包含 `123456` 的文本）。
2. `bot` 鉴权通过，响应「⏳ 任务已接收，正在解析...」。
3. `resolver` 确保持有当前最优活跃域名。
4. `pipeline` 申请 `disk_guard` 许可。若磁盘空间 $\ge 2\text{GB}$，立即进入抓取阶段；否则进入等待队列。
5. `crawler` 抓取帖子元数据与正文结构，定位所有加密图片与视频 URL。
6. `decryptor` 并发下载并解密图片与视频分片，合并至本地临时目录：
   `downloads_temp/{author_id}_{author_name}/[{post_id}] {title}/`
7. `renderer` 写入 `post.md`。
8. 帖子落盘完成后，立即入队 `uploader`（上传通道异步执行）。
9. `disk_guard` 允许下一个就绪帖子的下载开始。
10. `uploader` 调用 `rclone copy` 将该帖子目录完整推送到 OneDrive 指定目录。
11. Rclone 进程退出码为 0，`cleaner` 立即执行 `shutil.rmtree()` 删除该帖子本地目录，同时触发 `disk_guard` 空间刷新。
12. `uploader` 根据环境变量 `OPENLIST_BASE_URL` 与远程路径拼接出分享链接，并通过 Telegram Bot 回调发送完成卡片（包含标题、作者、媒体统计与直达按钮）。

### 4.2 作者页批量处理时序 (Author Flow)

1. 用户发送作者主页链接。
2. `bot` 解析作者 ID，拉取第一页元数据及总页数，向用户展示选择菜单（Inline Keyboard）：
   - `[下载第 1 页]`
   - `[下载前 3 页]`
   - `[下载前 5 页]`
   - `[全部下载]`
   - `[自定义范围 (输入如 2-4)]`
3. 用户点击或输入指定页码范围后，`crawler` 批量分页获取该范围内的所有帖子 ID。
4. 将所有帖子任务顺序追加到 `pipeline` 队列中，以单帖为原子单位流式执行「下载解密 $\rightarrow$ 提交上传 $\rightarrow$ 清理落盘 $\rightarrow$ 发送进度」。

---

## 5. 存储规范与数据格式

### 5.1 目录组织结构

```
OneDrive 远端与本地组织一致：
{RCLONE_REMOTE_DEST}/
└── {author_name}_{author_id}/
    └── [{post_id}] {sanitized_title}/
        ├── post.md
        ├── images/
        │   ├── 01.jpg
        │   ├── 02.jpg
        │   └── ...
        └── videos/
            ├── 01.mp4
            └── ...
```

### 5.2 `post.md` 排版格式规范

```markdown
---
title: "帖子标题"
author: "作者昵称"
author_id: "998877"
post_id: "123456"
publish_time: "2026-08-15 18:30:00"
source_url: "https://hjw2026.com/post/details?pid=123456"
downloaded_at: "2026-08-16 00:30:00"
---

# 帖子标题

> 👤 **原作者**: [作者昵称](https://hjw2026.com/user/home?uid=998877)  
> 📅 **发布时间**: 2026-08-15 18:30:00  
> 🆔 **帖子编号**: 123456  

---

这里是正文第 1 段内容...

![图片 1](./images/01.jpg)

这里是正文第 2 段内容...

<video controls src="./videos/01.mp4" width="100%"></video>

这里是正文结语...
```

---

## 6. 配置规范与环境变量

在项目根目录提供 `.env.example`，支持通过环境变量或 `.env` 加载配置：

```ini
# ========================
# Telegram Bot 配置
# ========================
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
# 授权用户 Telegram ID 列表，逗号分隔
ALLOWED_USER_IDS=123456789,987654321

# ========================
# 发布页与网络配置
# ========================
PUBLISH_PAGE_URL=https://hjw2026.com
DOMAIN_REFRESH_INTERVAL_HOURS=6
REQUEST_TIMEOUT_SECONDS=30
MAX_DOWNLOAD_CONCURRENCY=2

# ========================
# VPS 磁盘与流水线调度
# ========================
TEMP_DOWNLOAD_DIR=./downloads_temp
# 磁盘安全红线（单位 GB）：低于此容量暂停新帖下载
MIN_FREE_DISK_GB=2.0

# ========================
# Rclone 与云存储配置
# ========================
# Rclone 配置文件路径（若为空使用系统默认 ~/.config/rclone/rclone.conf）
RCLONE_CONFIG_PATH=
# 远程目标路径（如 onedrive:Haijiao 或 myremote:Media/Haijiao）
RCLONE_REMOTE_DEST=onedrive:Media/Haijiao
# 上传并发控制
MAX_UPLOAD_CONCURRENCY=2

# ========================
# OpenList 链接映射配置
# ========================
# OpenList Web 访问基础 URL（不带末尾斜杠）
OPENLIST_BASE_URL=https://pan.example.com
# OneDrive 在 OpenList 中的挂载路径（以斜杠开头）
OPENLIST_MOUNT_PATH=/Media/Haijiao
```

---

## 7. 异常处理与容错机制

1. **发布页访问异常或域名被墙**：
   - 内置多备用 DNS 解析与重试策略；若无法连接发布页，降级使用环境变量指定的默认备用域名。
2. **下载中断与媒体损坏**：
   - 单文件支持 Range 请求断点续传（如可用）与 3 次退避重试；若某媒体最终失败，不中断整帖排版，在 `post.md` 中标注 `<!-- [Failed to download media: url] -->` 并将成功部分正常打包上传，在 Telegram 汇报警告。
3. **Rclone 上传中断**：
   - 捕获异常退出码，不执行删除操作；保留本地目录并在间隔后触发自动重试（最多重试 3 次）。
4. **VPS 磁盘突发占满**：
   - `DiskGuard` 在单帖解密过程中定期复核空间，若单帖体积超出 VPS 剩余空间，触发紧急告警并中断该任务，立即清理残余临时文件避免 VPS 宕机。
