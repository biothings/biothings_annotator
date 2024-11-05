FROM python:3.12 AS builder

ARG ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git
ARG ANNOTATOR_BRANCH=main

WORKDIR /build/annotator
RUN git clone -b ${ANNOTATOR_BRANCH} --recursive ${ANNOTATOR_REPO} .
RUN git rev-parse HEAD > /build/annotator/version.txt
RUN pip wheel --wheel-dir=/build/wheels /build/annotator

FROM python:3.12-slim
RUN apt update -q -y && apt install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN useradd -m annotator && usermod -aG sudo annotator
USER annotator
WORKDIR /home/annotator/
RUN python -m venv /home/annotator/venv
COPY --from=builder --chown=annotator:annotator /build/wheels /home/annotator/wheels
RUN /home/annotator/venv/bin/pip install /home/annotator/wheels/*.whl && rm -rf /home/annotator/wheels

WORKDIR /home/annotator/configuration
COPY --from=builder --chown=annotator:annotator /build/annotator/biothings_annotator/application/configuration/default.json /home/annotator/configuration
COPY --from=builder --chown=annotator:annotator /build/annotator/version.txt /home/annotator/configuration/version.txt

STOPSIGNAL SIGINT
EXPOSE 9001

ENTRYPOINT ["/home/annotator/venv/bin/python", "-m", "biothings_annotator"]
CMD ["--conf=/home/annotator/configuration/default.json"]
