FROM python:3.11-slim

# 1) Системные зависимости Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Фиксируем место, куда Playwright кладёт браузеры (внутрь образа)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 4) Устанавливаем Chromium в этот путь
RUN python -m playwright install chromium

# 5) Копируем проект
COPY . .

# 6) Запуск
CMD ["python", "bot.py"]
