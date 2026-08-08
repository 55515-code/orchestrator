#!/usr/bin/env bash
set -euo pipefail

apply=false
if [[ "${1:-}" == "--apply" ]]; then
  apply=true
elif (($#)); then
  printf 'usage: %s [--apply]\n' "$0" >&2
  exit 2
fi

domain=fabric-ubuntu
state_root=/home/ahron/.local/share/local-substrate
image_root="$state_root/images"
ssh_root="$state_root/ssh"
base_image="$image_root/ubuntu-24.04-server-cloudimg-amd64.img"
disk="$image_root/$domain.qcow2"
key="$ssh_root/id_ed25519"
user_data="$state_root/$domain-user-data.yaml"
image_url=https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img
sums_url=https://cloud-images.ubuntu.com/releases/noble/release/SHA256SUMS

printf 'Rootless VM plan:\n'
printf '  domain: %s\n' "$domain"
printf '  libvirt: qemu:///session\n'
printf '  resources: 8 vCPU, 16 GiB RAM, 64 GiB sparse qcow2\n'
printf '  SSH: fabric@127.0.0.1:22222\n'
printf '  base: %s\n' "$image_url"

if ! $apply; then
  printf '\nDry run only. Re-run with --apply; no root authorization is needed.\n'
  exit 0
fi

mkdir -p "$image_root" "$ssh_root"
chmod 700 "$state_root" "$ssh_root"

if [[ ! -f "$key" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C local-substrate-fabric -f "$key"
fi

if [[ ! -f "$base_image" ]]; then
  temp_image="$base_image.part"
  temp_sums="$image_root/SHA256SUMS.part"
  curl --fail --location --retry 3 --output "$temp_image" "$image_url"
  curl --fail --location --retry 3 --output "$temp_sums" "$sums_url"
  expected="$(
    awk '$2 == "*ubuntu-24.04-server-cloudimg-amd64.img" ||
         $2 == "ubuntu-24.04-server-cloudimg-amd64.img" {print $1}' "$temp_sums"
  )"
  [[ "$expected" =~ ^[0-9a-f]{64}$ ]] ||
    { printf 'Could not resolve the official image checksum.\n' >&2; exit 1; }
  printf '%s  %s\n' "$expected" "$temp_image" | sha256sum --check -
  mv "$temp_image" "$base_image"
  mv "$temp_sums" "$image_root/SHA256SUMS"
fi

if [[ ! -f "$disk" ]]; then
  qemu-img create -f qcow2 -F qcow2 -b "$base_image" "$disk" 64G
fi

public_key="$(<"$key.pub")"
{
  printf '%s\n' '#cloud-config'
  printf '%s\n' 'hostname: fabric-ubuntu'
  printf '%s\n' 'users:'
  printf '%s\n' '  - default'
  printf '%s\n' '  - name: fabric'
  printf '%s\n' '    groups: [adm, sudo]'
  printf '%s\n' '    sudo: ALL=(ALL) NOPASSWD:ALL'
  printf '%s\n' '    shell: /bin/bash'
  printf '%s\n' '    ssh_authorized_keys:'
  printf '      - %s\n' "$public_key"
  printf '%s\n' 'ssh_pwauth: false'
  printf '%s\n' 'package_update: true'
  printf '%s\n' 'packages: [qemu-guest-agent, podman, git, build-essential, python3]'
  printf '%s\n' 'runcmd:'
  printf '%s\n' '  - [systemctl, enable, --now, qemu-guest-agent]'
  printf '%s\n' '  - [touch, /var/lib/cloud/instance/fabric-ready]'
} >"$user_data"
chmod 600 "$user_data"

if virsh --connect qemu:///session dominfo "$domain" >/dev/null 2>&1; then
  printf 'Domain already defined; preserving it.\n'
  virsh --connect qemu:///session start "$domain" 2>/dev/null || true
  exit 0
fi

virt-install \
  --connect qemu:///session \
  --name "$domain" \
  --memory 16384 \
  --vcpus 8 \
  --cpu host-passthrough \
  --import \
  --disk "path=$disk,format=qcow2,bus=virtio" \
  --osinfo ubuntu24.04 \
  --boot uefi \
  --network 'user,backend.type=passt,model=virtio,portForward0.proto=tcp,portForward0.range0.start=22222,portForward0.range0.to=22' \
  --graphics none \
  --console pty,target.type=serial \
  --channel unix,target.type=virtio,target.name=org.qemu.guest_agent.0 \
  --cloud-init "user-data=$user_data,clouduser-ssh-key=$key.pub,disable=on" \
  --noautoconsole

printf 'Rootless VM defined and started.\n'
