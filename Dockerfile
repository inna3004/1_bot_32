FROM python:3.11-slim

ENV PROJECT_ROOT /app
ENV SRC_DIR ./src

RUN mkdir $PROJECT_ROOT

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y build-essential libpq-dev python3-dev && \
    apt-get clean

# Копируем requirements.txt
COPY requirements.txt $PROJECT_ROOT/

WORKDIR $PROJECT_ROOT

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . $PROJECT_ROOT/

# Создаем необходимые папки
RUN mkdir -p storage logs bot_session

# Запускаем бота
CMD ["python", "run_bot.py"]

