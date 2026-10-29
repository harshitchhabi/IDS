# Engelen et al.'s fixed CICFlowMeter (WTMC 2021), pinned to a commit. Same build as the
# upstream Dockerfile, but on a pinned Alpine instead of alpine:latest so the image is
# reproducible. Network access is needed only at build time; the extractor runs offline
# (`docker run --network none`) over pcaps.
FROM alpine:3.20 AS builder
ARG CFM_COMMIT=4dd5319ad36457010d7a406505790b17a5828108
RUN apk add --no-cache git unzip openjdk8 libpcap-dev
RUN git clone https://github.com/GintsEngelen/CICFlowMeter.git /CICFlowMeter \
 && cd /CICFlowMeter && git checkout ${CFM_COMMIT}
WORKDIR /CICFlowMeter
RUN ./gradlew --no-daemon distZip \
 && UNZIP_DISABLE_ZIPBOMB_DETECTION=TRUE unzip -o build/distributions/CICFlowMeter-*.zip -d build/distributions

FROM alpine:3.20
RUN apk add --no-cache openjdk8-jre libpcap-dev
WORKDIR /CICFlowMeter
COPY --from=builder /CICFlowMeter/build/distributions/CICFlowMeter-* .
# The cli resolves -Djava.library.path=../lib/native relative to bin/.
WORKDIR /CICFlowMeter/bin
ENTRYPOINT ["./cfm"]
