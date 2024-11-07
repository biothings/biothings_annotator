FROM python:3.12 AS builder

ARG ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git
ARG ANNOTATOR_BRANCH=main

WORKDIR /build/annotator
RUN git clone -b ${ANNOTATOR_BRANCH} --recursive ${ANNOTATOR_REPO} .
RUN git rev-parse HEAD > /build/annotator/version.txt
RUN pip wheel --wheel-dir=/build/wheels /build/annotator

FROM caddy:2.8-builder AS caddy_builder
RUN xcaddy build

FROM python:3.12-slim
RUN apt update -q -y && apt install -y --no-install-recommends git supervisor curl telnet && rm -rf /var/lib/apt/lists/*
RUN useradd -m annotator && usermod -aG sudo annotator
USER annotator
WORKDIR /home/annotator/
RUN python -m venv /home/annotator/venv
COPY --from=builder --chown=annotator:annotator /build/wheels /home/annotator/wheels
RUN /home/annotator/venv/bin/pip install /home/annotator/wheels/*.whl && rm -rf /home/annotator/wheels

WORKDIR /home/annotator/configuration
COPY --from=builder --chown=annotator:annotator /build/annotator/biothings_annotator/application/configuration/default.json /home/annotator/configuration
COPY --from=builder --chown=annotator:annotator /build/annotator/version.txt /home/annotator/configuration/version.txt
COPY --from=caddy_builder /usr/bin/caddy /usr/bin/caddy

COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY Caddyfile /etc/caddy/Caddyfile

STOPSIGNAL SIGINT
EXPOSE 9000

ENTRYPOINT ["supervisord"]
CMD ["-c", "/etc/supervisor/supervisord.conf"]
