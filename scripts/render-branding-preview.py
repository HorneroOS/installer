#!/usr/bin/env python3
"""Render the Calamares branding stylesheet offscreen (developer tool).

Builds stand-in widgets that use the same Qt classes and object names as the
Calamares 3.4 window (mainApp, sidebarApp, view-button-*, exec-progress,
partition tree, users form, summary, requirements list, dialogs) and applies
image/calamares/branding/hornero/stylesheet.qss to them. It is NOT the real
installer: Calamares paints some parts itself (partition bars, requirement
rows, the sidebar list) from the application palette, which only a real
Calamares run shows. Needs PySide6 (not a CI dependency).

Usage: QT_QPA_PLATFORM=offscreen scripts/render-branding-preview.py OUT_DIR [--size WxH] [--scale N]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
QSS = ROOT / "image/calamares/branding/hornero/stylesheet.qss"
BANNER = ROOT / "image/calamares/branding/hornero/installer-banner.svg"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--size", default="1280x800")
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    width, height = (int(v) for v in args.size.split("x"))

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtSvgWidgets import QSvgWidget
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGroupBox,
        QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QProgressBar,
        QPushButton, QRadioButton, QScrollArea, QStackedWidget, QTableWidget,
        QTableWidgetItem, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
        QVBoxLayout, QWidget,
    )

    app = QApplication(sys.argv)
    qss = QSS.read_text(encoding="utf-8")
    args.out.mkdir(parents=True, exist_ok=True)

    def window(title: str, build) -> QWidget:
        main = QWidget()
        main.setObjectName("mainApp")
        main.resize(width, height)
        root = QHBoxLayout(main)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QWidget()
        side.setObjectName("sidebarApp")
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        steps = QListWidget()
        for i, name in enumerate(("Welcome", "Location", "Keyboard", "Partitions", "Users", "Summary", "Install", "Finish")):
            steps.addItem(name)
        steps.setCurrentRow(title_index[title])
        sl.addWidget(steps)
        root.addWidget(side)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 16, 24, 16)
        build(bl)
        nav = QHBoxLayout()
        nav.addWidget(QPushButton("About"))
        nav.addStretch()
        back = QPushButton("Back"); back.setObjectName("view-button-back")
        nxt = QPushButton("Next"); nxt.setObjectName("view-button-next"); nxt.setDefault(True)
        cancel = QPushButton("Cancel"); cancel.setObjectName("view-button-cancel")
        for b in (back, nxt, cancel):
            nav.addWidget(b)
        bl.addLayout(nav)
        root.addWidget(body, 1)
        main.setStyleSheet(qss)
        return main

    title_index = {"welcome": 0, "partition": 3, "users": 4, "summary": 5, "install": 6, "finish": 7}

    def welcome(bl):
        banner = QSvgWidget(str(BANNER))
        banner.setFixedSize(600, 180)
        bl.addWidget(banner)
        lst = QListWidget()
        for text in ("Enough storage space", "Enough working memory", "Connected to the internet", "Running as administrator"):
            lst.addItem(text)
        lst.setCurrentRow(1)
        bl.addWidget(lst)
        lang = QComboBox(); lang.addItems(["English (United States)", "Español (Argentina)"])
        bl.addWidget(lang)
        row = QHBoxLayout()
        for name, oid in (("Support", "supportButton"), ("Known issues", "knownIssuesButton"), ("Release notes", "releaseNotesButton")):
            b = QPushButton(name); b.setObjectName(oid); row.addWidget(b)
        row.addStretch()
        bl.addLayout(row)

    def partition(bl):
        bl.addWidget(QLabel("Select a storage device"))
        combo = QComboBox(); combo.addItems(["Virtual disk 40 GiB (vda)"]); bl.addWidget(combo)
        grp = QGroupBox("Erase disk"); gl = QVBoxLayout(grp)
        r1 = QRadioButton("Erase disk"); r1.setChecked(True)
        gl.addWidget(r1); gl.addWidget(QRadioButton("Replace a partition")); gl.addWidget(QRadioButton("Manual partitioning"))
        gl.addWidget(QCheckBox("Encrypt system"))
        bl.addWidget(grp)
        tree = QTreeWidget(); tree.setHeaderLabels(["Name", "File system", "Mount point", "Size"])
        for vals in (("vda1", "fat32", "/boot", "512 MiB"), ("vda2", "btrfs", "/", "39.5 GiB")):
            tree.addTopLevelItem(QTreeWidgetItem(list(vals)))
        tree.setCurrentItem(tree.topLevelItem(1))
        bl.addWidget(tree)

    def users(bl):
        form = QFormLayout()
        for label, pw in (("What is your name?", False), ("Computer name", False), ("Password", True), ("Repeat password", True)):
            e = QLineEdit(); e.setEchoMode(QLineEdit.Password if pw else QLineEdit.Normal)
            if not pw:
                e.setText("sample")
            form.addRow(label, e)
        bl.addLayout(form)
        bl.addWidget(QCheckBox("Log in automatically without asking for the password"))
        tabs = QTabWidget(); tabs.addTab(QLabel("Details"), "ACCOUNT"); tabs.addTab(QLabel("Other"), "ADVANCED")
        bl.addWidget(tabs)
        bl.addStretch()

    def summary(bl):
        area = QScrollArea(); inner = QWidget(); inner.setObjectName("scrollAreaWidgetContents")
        il = QVBoxLayout(inner)
        for text in ("Location: America/Argentina/Buenos_Aires", "Erase disk /dev/vda (btrfs, encrypted)", "Install: HorneroOS Desktop (Hyprland)"):
            il.addWidget(QLabel(text))
        il.addStretch()
        area.setWidget(inner); area.setWidgetResizable(True)
        bl.addWidget(area)
        table = QTableWidget(3, 2); table.setHorizontalHeaderLabels(["Package", "Size"])
        for r, (a, b) in enumerate((("hornero-shell", "12 MiB"), ("hornero-config", "9 MiB"), ("ttf-ibm-plex", "6 MiB"))):
            table.setItem(r, 0, QTableWidgetItem(a)); table.setItem(r, 1, QTableWidgetItem(b))
        bl.addWidget(table)

    def install(bl):
        bl.addStretch()
        msg = QLabel("Installing packages (37/212)"); msg.setObjectName("exec-message")
        bar = QProgressBar(); bar.setObjectName("exec-progress"); bar.setValue(42)
        bl.addWidget(msg); bl.addWidget(bar)
        bl.addStretch()

    def finish(bl):
        bl.addWidget(QLabel("All done. HorneroOS has been installed on your computer."))
        bl.addWidget(QCheckBox("Restart now"))
        tool = QToolButton(); tool.setText("Details"); tool.setCheckable(True); tool.setChecked(True)
        bl.addWidget(tool)
        bl.addStretch()

    pages = {"welcome": welcome, "partition": partition, "users": users, "summary": summary,
             "install": install, "finish": finish}
    for name, build in pages.items():
        w = window(name, build)
        w.show()
        app.processEvents()
        w.grab().save(str(args.out / f"{name}.png"))
        w.close()

    dlg = QDialog()
    dlg.setStyleSheet(qss)
    dl = QVBoxLayout(dlg)
    dl.addWidget(QLabel("Continue with setup?"))
    dl.addWidget(QLabel("The installer will make changes to your disk."))
    row = QHBoxLayout()
    for t in ("Set up now", "Cancel"):
        row.addWidget(QPushButton(t))
    dl.addLayout(row)
    dlg.resize(420, 160)
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(args.out / "dialog.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
