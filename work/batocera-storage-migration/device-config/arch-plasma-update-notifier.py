#!/usr/bin/env python3
"""Small package update tray for the persistent Arch Plasma userspace."""

from __future__ import annotations

import subprocess
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


class UpdateTray(QSystemTrayIcon):
    def __init__(self) -> None:
        super().__init__(QIcon.fromTheme("system-software-update"))
        self.setToolTip("Checking for system updates")
        menu = QMenu()
        check_action = QAction("Check for Updates", menu)
        check_action.triggered.connect(self.check)
        update_action = QAction("Install Updates", menu)
        update_action.triggered.connect(self.install)
        quit_action = QAction("Quit Update Notifier", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(check_action)
        menu.addAction(update_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self.activate)
        self.timer = QTimer(self)
        self.timer.setInterval(4 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        QTimer.singleShot(15000, self.check)

    def activate(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.install()

    def check(self) -> None:
        arch = subprocess.run(
            ["checkupdates"], capture_output=True, text=True, check=False
        ).stdout.splitlines()
        flatpak = subprocess.run(
            ["flatpak", "--user", "remote-ls", "--updates", "--columns=application"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()
        count = len([line for line in arch + flatpak if line.strip()])
        if count:
            message = f"{count} Arch/Flatpak updates available"
            self.setIcon(QIcon.fromTheme("software-update-available"))
            self.showMessage("System Updates", message, self.icon(), 8000)
        else:
            message = "Arch userspace and Flatpak apps are up to date"
            self.setIcon(QIcon.fromTheme("system-software-update"))
        self.setToolTip(message)

    @staticmethod
    def install() -> None:
        subprocess.Popen(["/usr/local/bin/arch-plasma-update"])


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
tray = UpdateTray()
tray.show()
sys.exit(app.exec())
