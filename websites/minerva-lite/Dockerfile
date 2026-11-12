FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir flask==3.0.0 jinja2==3.1.3 itsdangerous==2.2.0 click==8.1.7
# copy common utilities from project root (build context is project root)
COPY ./common /app/common
# copy only the minerva-lite service files into /app
COPY . /app
EXPOSE 8000
CMD ["python", "app.py"]
