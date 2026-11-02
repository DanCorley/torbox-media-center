FROM python:3.10.12-slim-bookworm

WORKDIR /app
COPY requirements.txt .

# Install common dependencies
RUN pip install $(grep -v "fuse\|git+" requirements.txt)

# Install build dependencies
RUN apt-get update && \
    apt-get install -y git pkg-config libfuse-dev gcc make

# Architecture-specific installations
ARG TARGETPLATFORM
RUN echo "Building for $TARGETPLATFORM" && \
    case "$TARGETPLATFORM" in \
        "linux/amd64"|"linux/arm64") \
            pip install fuse-python \
            ;; \
        "linux/arm/v7"|"linux/arm/v8") \
            pip install git+https://github.com/libfuse/python-fuse \
            ;; \
        *) \
            echo "Unsupported platform: $TARGETPLATFORM" && exit 1 \
            ;; \
    esac

COPY . .

ENV TORBOX_API_KEY=
ENV MOUNT_METHOD=strm
ENV MOUNT_PATH=/torbox

# Healthcheck for the authenticated control API. Uses only the Python standard
# library so the slim image needs no curl/wget. It exits 0 when the control API
# is disabled (the default) and probes GET /health with the bearer token when
# CONTROL_ENABLED=true. A 401/connection error means unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD python -c "import os,sys,urllib.request; enabled=os.getenv('CONTROL_ENABLED','false').lower()=='true'; sys.exit(0) if not enabled else urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+os.getenv('CONTROL_PORT','8787')+'/health', headers={'Authorization':'Bearer '+os.getenv('CONTROL_TOKEN','')}), timeout=5).read()"

CMD ["python", "main.py"]