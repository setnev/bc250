FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils genisoimage openssh-client python3 curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /lab
ENTRYPOINT ["qemu-system-x86_64"]
