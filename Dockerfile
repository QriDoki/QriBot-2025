FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖和字体配置工具
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    fontconfig \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建字体目录
RUN mkdir -p /usr/share/fonts/truetype/misans && \
    mkdir -p /usr/share/fonts/truetype/noto

# 复制字体文件到系统字体目录
COPY assets/MiSans-Normal.ttf /usr/share/fonts/truetype/misans/
COPY assets/NotoColorEmoji-Regular.ttf /usr/share/fonts/truetype/noto/

# 复制 fontconfig 配置文件
COPY fonts.conf /etc/fonts/local.conf

# 更新字体缓存
RUN fc-cache -fv

# 创建日志目录
RUN mkdir -p /app/logs

# 复制项目文件
COPY pyproject.toml ./
COPY bot.py ./
COPY plugins/ ./plugins/
COPY assets/ ./assets/

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 设置环境变量 - 配置 fontconfig 使用系统字体
ENV FONTCONFIG_PATH=/etc/fonts
ENV FC_LANG=zh_CN

# 暴露端口（如果需要）
# EXPOSE 8080

# 启动命令
CMD ["python", "bot.py"]
