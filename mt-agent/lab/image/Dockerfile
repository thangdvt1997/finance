# MT lab: Wine + Xvfb + x11vnc + xdotool. Dung chung cho MT4 va MT5 (moi container 1 WINEPREFIX rieng).
FROM ubuntu:22.04
ARG WINE_VER=9.0.0.0~jammy-1
ENV DEBIAN_FRONTEND=noninteractive WINEARCH=win64 WINEDEBUG=-all DISPLAY=:1 LANG=C.UTF-8
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg wget xvfb x11vnc xdotool x11-utils imagemagick python3 xauth fluxbox procps cabextract unzip p7zip-full \
 && mkdir -pm755 /etc/apt/keyrings \
 && curl -fsSL https://dl.winehq.org/wine-builds/winehq.key -o /etc/apt/keyrings/winehq-archive.key \
 && curl -fsSL https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/winehq-jammy.sources -o /etc/apt/sources.list.d/winehq-jammy.sources \
 && apt-get update && apt-get install -y --install-recommends winehq-stable=${WINE_VER} wine-stable=${WINE_VER} wine-stable-amd64=${WINE_VER} wine-stable-i386:i386=${WINE_VER} winetricks \
 && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
