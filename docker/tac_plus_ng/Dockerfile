# start with Alpine Linux
FROM alpine:3.20

# system setup with all requirements
RUN apk add --no-cache \
        bash \
        bash-completion \
        bind-tools \
        build-base \
        c-ares-dev \
        curl \
        curl-dev \
        less \
        freeradius-client-dev \
        libretls-dev \
        linux-pam-dev \
        logrotate \
        nano \
        openssl-dev \
        pcre2-dev \
        perl \
        perl-authen-radius \
        perl-ldap \
        perl-net-ip \
        perl-sys-syslog \
        procps \
        tcpdump \
        tzdata \
        vim \
        wget \
        unzip \
    && echo "! installation is finished !"

# download and install MarcJHuber event-driven-servers / tac_plus-ng repository
RUN wget https://github.com/MarcJHuber/event-driven-servers/archive/refs/heads/master.zip -O event-driven-servers-master.zip && \
    unzip event-driven-servers-master.zip && \
    cd event-driven-servers-master && \
    ./configure && \
    make && \
    make install && \
    # copy sample configuration file
    cp /event-driven-servers-master/tac_plus-ng/sample/tac_plus-ng.cfg /usr/local/etc/tac_plus-ng.cfg && \
    # cleanup
    rm -rf /event-driven-servers-master* && \
    echo "! service setup successful !"

# shell QoL defaults
RUN printf '%s\n' \
    '[[ -f /usr/share/bash-completion/bash_completion ]] && . /usr/share/bash-completion/bash_completion' \
    'export TERM=${TERM:-xterm-256color}' \
    'alias ll="ls -alF"' \
    'alias la="ls -A"' \
    'alias l="ls -CF"' \
    > /etc/profile.d/qol.sh

# container runtime helpers
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY logrotate/tac_plus-ng /etc/logrotate.d/tac_plus-ng
RUN chmod +x /usr/local/bin/entrypoint.sh

# run tac_plus-ng with stdout + file logging
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
