#!/bin/bash
set -e

ISO_PATH="/home/ahron/codespace/LuigiOS/dist/luigios-2026.07.28-x86_64.iso"
BOOT_DIR="/boot/luigios"
ISO_DEST="/home/ahron/luigios/luigios.iso"

echo "=== LuigiOS EFI Bootstrap Script ==="
echo "This script will:"
echo "1. Extract kernel and initramfs to /boot/luigios"
echo "2. Copy the ISO to /home/ahron/luigios/"
echo "3. Add a Limine boot entry"
echo ""

# Check if ISO exists
if [ ! -f "$ISO_PATH" ]; then
    echo "Error: ISO not found at $ISO_PATH"
    exit 1
fi

# Step 1: Create directories and extract boot files
echo "Step 1: Extracting kernel and initramfs to ESP..."
pkexec bash -c "
    mkdir -p $BOOT_DIR
    bsdtar -xf '$ISO_PATH' -C '$BOOT_DIR' \
        arch/boot/x86_64/vmlinuz-linux-cachyos-lts \
        arch/boot/x86_64/initramfs-linux-cachyos-lts.img
    chown -R root:root '$BOOT_DIR'
    chmod 755 '$BOOT_DIR'
"
echo "✓ Boot files extracted to $BOOT_DIR"

# Step 2: Copy ISO to root filesystem
echo ""
echo "Step 2: Copying ISO to root filesystem..."
mkdir -p /home/ahron/luigios
cp "$ISO_PATH" "$ISO_DEST"
echo "✓ ISO copied to $ISO_DEST"

# Step 3: Find and update Limine config
echo ""
echo "Step 3: Adding Limine boot entry..."
LIMINE_CONF=$(pkexec find /boot -name "limine.conf" 2>/dev/null | head -1)

if [ -z "$LIMINE_CONF" ]; then
    echo "Warning: Could not find limine.conf automatically"
    echo "Please manually add this entry to your Limine configuration:"
    echo ""
    echo "/LuigiOS Live:"
    echo "    protocol: linux"
    echo "    kernel_path: boot:///luigios/vmlinuz-linux-cachyos-lts"
    echo "    module_path: boot:///luigios/initramfs-linux-cachyos-lts.img"
    echo "    cmdline: archisobasedir=arch img_dev=/dev/nvme0n1p2 img_loop=/home/ahron/luigios/luigios.iso"
else
    echo "Found Limine config at: $LIMINE_CONF"
    
    # Create backup
    pkexec cp "$LIMINE_CONF" "${LIMINE_CONF}.backup"
    echo "✓ Backup created at ${LIMINE_CONF}.backup"
    
    # Add the boot entry
    pkexec bash -c "cat >> '$LIMINE_CONF' << 'EOF'

/LuigiOS Live:
    protocol: linux
    kernel_path: boot:///luigios/vmlinuz-linux-cachyos-lts
    module_path: boot:///luigios/initramfs-linux-cachyos-lts.img
    cmdline: archisobasedir=arch img_dev=/dev/nvme0n1p2 img_loop=/home/ahron/luigios/luigios.iso
EOF"
    echo "✓ Boot entry added to Limine config"
fi

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "The LuigiOS live image is now in your EFI boot menu."
echo "On next reboot, select 'LuigiOS Live' from the Limine menu."
echo ""
echo "Files created:"
echo "  - $BOOT_DIR/vmlinuz-linux-cachyos-lts"
echo "  - $BOOT_DIR/initramfs-linux-cachyos-lts.img"
echo "  - $ISO_DEST"
echo ""
echo "To remove this entry later:"
echo "  1. Edit your Limine config and remove the '/LuigiOS Live:' section"
echo "  2. rm -rf $BOOT_DIR /home/ahron/luigios"
