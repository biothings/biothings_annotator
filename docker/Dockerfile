FROM python:3.10 AS builder

ARG ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git
ARG ANNOTATOR_BRANCH=main

WORKDIR /build/annotator
RUN git clone -b ${ANNOTATOR_BRANCH} --recursive ${ANNOTATOR_REPO} .
RUN pip wheel --wheel-dir=/build/wheels /build/annotator


FROM python:3.10-slim
RUN apt update -q -y && apt install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN apt-get update -y && apt-get install vim -y && apt-get install sudo -y && apt-get install telnet -y
RUN useradd -m annotator && usermod -aG sudo annotator
USER annotator
RUN python -m venv /home/annotator/venv
COPY --from=builder --chown=annotator:annotator /build/wheels /home/annotator/wheels
RUN /home/annotator/venv/bin/pip install /home/annotator/wheels/*.whl && rm -rf /home/annotator/wheels
COPY --from=builder --chown=annotator:annotator /build/annotator /home/annotator/biothings_annotator

STOPSIGNAL SIGINT

WORKDIR /home/annotator/
EXPOSE 9999

ENTRYPOINT ["/home/annotator/venv/bin/python", "/home/annotator/biothings_annotator/biothings_annotator"]
