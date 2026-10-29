# Production SSH host: OpenSSH with one test user the benign client logs in as.
# Password auth is on because the benign admin sessions and the adversary's slow
# guessing both exercise it. Lab-internal only; no port published to the host.
FROM alpine:3.20
RUN apk add --no-cache openssh bash shadow \
 && ssh-keygen -A \
 && adduser -D -s /bin/bash admin \
 && echo 'admin:correct-horse-battery' | chpasswd \
 && mkdir -p /var/log && touch /var/log/auth.log
COPY sshd_config /etc/ssh/sshd_config
COPY motd /etc/motd
EXPOSE 22
# -e sends sshd logs to stderr so they land in the container log (and the pcap
# carries the sessions regardless).
CMD ["/usr/sbin/sshd", "-D", "-e"]
