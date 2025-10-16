FROM python:3.11-slim

ENV PROJECT_ROOT /app
# todo в твоем проекте нет такой папки, удалить строку ниже
#ENV SRC_DIR ./src
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
COPY .. $PROJECT_ROOT/

# Создаем необходимые папки
# todo не надо руками создавать. папка storage скопируется в предыдущей команде, logs
# и bot_session создадутся сами в процессе работы проекта (если предусмотрено реализацией, но нигде не увидела
# запись логов в файл в папку лог, и чтобы что-то записывалось в папке bot_session). удалить строку ниже
#RUN mkdir -p storage logs bot_session

# Запускаем бота
CMD ["python", "run_bot.py"]

