FROM alpine:3.22 AS download
RUN apk add --no-cache curl tar bzip2
ARG TARGETARCH
RUN case "$TARGETARCH" in \
      amd64) checksum=0ffc7fc0633049edbcf88170ac037d2665ceaf1f0884a00b15f6c2b81313c825 ;; \
      arm64) checksum=eda48ad1744e7be9bdd1cb515e7229e9c7ecdc3cf82c6621a64670505b3d485b ;; \
      *) exit 1 ;; \
    esac && \
    curl -fsSL --retry 3 "https://github.com/motis-project/motis/releases/download/v2.11.3/motis-linux-${TARGETARCH}.tar.bz2" -o /tmp/motis.tar.bz2 && \
    echo "$checksum  /tmp/motis.tar.bz2" | sha256sum -c - && \
    mkdir /out && tar -xjf /tmp/motis.tar.bz2 -C /out ./motis && \
    curl -fsSL --retry 3 https://raw.githubusercontent.com/motis-project/motis/v2.11.3/LICENSE -o /out/LICENSE

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata
COPY --from=download /out/motis /usr/local/bin/motis
COPY --from=download /out/LICENSE /usr/share/licenses/motis/LICENSE
WORKDIR /workspace
EXPOSE 8080
ENTRYPOINT ["motis"]
