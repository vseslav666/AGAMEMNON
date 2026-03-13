# start with Alpine Linux
FROM alpine:3.23.3

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
        nano \
        openssl-dev \
        pcre2-dev \
        perl \
        perl-authen-radius \
        perl-ldap \
        perl-net-ip \
        perl-sys-syslog \
        procps \
        py3-pip \
        python3 \
        py3-psycopg2 \
        tcpdump \
        tzdata \
        vim \
        wget \
        unzip \
    && echo "! installation is finished !"

RUN pip3 install --no-cache-dir --break-system-packages pyotp

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

COPY mavis_tacplus_totp.py /usr/local/bin/mavis_tacplus_totp.py
RUN chmod +x /usr/local/bin/mavis_tacplus_totp.py

# run tac_plus-ng directly in foreground with debug output to container logs
CMD ["/usr/local/sbin/tac_plus-ng", "-d", "5", "/etc/tac_plus-ng/tac_plus-ng.cfg"]
