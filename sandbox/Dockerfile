FROM python:3.13-slim

WORKDIR /sandbox

# Install common math & analysis libraries so generated code doesn't fail offline
RUN pip install --no-cache-dir numpy pandas scipy

# Create a non-root user for process isolation
RUN useradd -m sandboxuser
USER sandboxuser

CMD ["python3"]