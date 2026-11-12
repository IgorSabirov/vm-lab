FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL org.opencontainers.image.source="https://github.com/IgorSabirov/vm-lab"
LABEL org.opencontainers.image.description="Pinned vm-lab numerical CI environment; no scientific model bundled"
COPY requirements-ci.txt /opt/vm-lab/requirements-ci.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /opt/vm-lab/requirements-ci.txt
RUN useradd --create-home --uid 10001 researcher
USER 10001
WORKDIR /workspace
CMD ["python", "--version"]
