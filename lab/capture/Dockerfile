FROM alpine:3.20
RUN apk add --no-cache tcpdump iproute2
COPY capture.sh /capture.sh
RUN chmod +x /capture.sh
ENTRYPOINT ["/capture.sh"]
