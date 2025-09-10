FROM python:3.12-slim
WORKDIR .
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "./mybot_1/main.py"]
CMD ["python", "./mybot_4/main.py"]
CMD ["python", "./mybot_8/main.py"]
CMD ["python", "./crypto_always/main.py"]
