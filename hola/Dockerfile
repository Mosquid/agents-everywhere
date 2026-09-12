FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py call_recording.py agent_tools.py setup-orange.py seed-people.py demo-people.json .
CMD ["python", "agent.py", "start"]
