FROM python:3.11-slim

# 安装系统依赖 (ffmpeg, rclone, ca-certificates, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    rclone \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 设置 Python 模块查找路径和输出无缓冲
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建 rclone 默认目录和临时下载目录
RUN mkdir -p /root/.config/rclone downloads_temp

CMD ["python", "-m", "src.main"]
