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

## 2. Rclone 配置（极简模式）

只需将包含 OneDrive 授权信息的 `rclone.conf` 直接放在项目根目录下即可（与 `docker-compose.yml` 同级）：

```text
haijiao-downloader-telegram/
├── rclone.conf          <-- 直接放这里！
├── config.yaml          <-- 配置文件
└── docker-compose.yml
```

---

## 3. Docker Compose 一键启动

### 3.1 `docker-compose.yml` 挂载规则

```yaml
services:
  haijiao-bot:
    build: .
    container_name: haijiao-downloader-telegram
    restart: unless-stopped
    volumes:
      # 映射项目根目录下的 rclone.conf 到容器内的默认配置路径
      - ./rclone.conf:/root/.config/rclone/rclone.conf
      # 映射 yaml 配置文件 (只读)
      - ./config.yaml:/app/config.yaml:ro
      # 映射临时下载目录
      - ./downloads_temp:/app/downloads_temp
    environment:
      - PYTHONPATH=/app
      - PYTHONUNBUFFERED=1
```

### 3.2 启动与验证

```bash
# 1. 复制并编辑 config.yaml
cp config.example.yaml config.yaml
nano config.yaml

# 2. 启动服务
docker compose up -d --build

# 3. 验证容器内 Rclone 连通性 (假设 remote 名称为 e5)
docker compose exec haijiao-bot rclone lsd e5:

# 4. 查看实时日志
docker compose logs -f
```
