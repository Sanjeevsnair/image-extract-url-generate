# Create Dockerfile
FROM python:3.9-slim
RUN pip install streamlit spire.pdf requests pillow
COPY app.py .
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]