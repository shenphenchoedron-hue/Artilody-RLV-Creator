# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Artilody RLV Creator.   Build:  pyinstaller packaging/rlvcreator.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from rlvcreator import __version__  # noqa: E402

APP = "Artilody RLV Creator"
icon = os.path.join(SPECPATH, "icon.ico" if sys.platform == "win32" else "icon.icns")

datas = [(os.path.join(ROOT, "rlvcreator", "resources"), "rlvcreator/resources")]
datas += collect_data_files("imageio_ffmpeg", includes=["binaries/*"])
binaries = collect_dynamic_libs("imageio_ffmpeg")

excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
            "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtBluetooth",
            "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
            "PySide6.QtWebSockets", "PySide6.QtQuick3D", "PySide6.QtGraphs", "numpy", "PIL", "pytest"]

a = Analysis(
    [os.path.join(ROOT, "rlvcreator", "__main__.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "imageio_ffmpeg"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="artilody-rlv-creator" if sys.platform.startswith("linux") else APP,
    console=False,
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="artilody-rlv-creator", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=APP + ".app",
        icon=icon,
        bundle_identifier="com.artilody.rlvcreator",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [{"CFBundleTypeName": "MPEG-4 Video", "CFBundleTypeRole": "Viewer",
                                       "LSItemContentTypes": ["public.mpeg-4"]}],
        },
    )
