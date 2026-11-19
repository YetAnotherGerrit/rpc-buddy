#!/bin/sh
# Removes the parts of io.qt.PySide.BaseApp that RPC Buddy does not use at
# runtime. Runs as a cleanup command after /app/cleanup-BaseApp.sh.
#
# If you start using another Qt module (e.g. QtDBus), add it to KEEP.
set -eu

KEEP="QtCore QtGui QtWidgets QtNetwork"

SP=$(echo /app/lib/python3*/site-packages)
P="$SP/PySide6"

# LLVM/Clang: only needed to generate Python bindings
rm -f /app/lib/libLLVM* /app/lib/libclang*

# Optional extras shipped with the BaseApp
rm -rf "$SP"/numpy "$SP"/numpy.libs "$SP"/numpy-*.dist-info \
    "$SP"/OpenGL "$SP"/pyopengl-*.dist-info \
    "$SP"/shiboken6_generator "$SP"/shiboken6_generator-*.dist-info

# PySide6 bindings for Qt modules we don't use
for f in "$P"/Qt*.abi3.so; do
    module=$(basename "$f" .abi3.so)
    case " $KEEP " in
        *" $module "*) ;;
        *) rm -f "$f" ;;
    esac
done
rm -f "$P"/libpyside6qml.abi3.so*

# Type stubs, headers, build files, bundled FFmpeg (QtMultimedia) and tools
rm -f "$P"/*.pyi
rm -rf "$P"/Qt "$P"/glue "$P"/include "$P"/lib "$P"/typesystems
for tool in assistant balsam balsamui designer linguist lrelease lupdate \
    qmlformat qmllint qmlls qsb; do
    rm -f "$P/$tool"
done

rm -f /app/cleanup-pyside.sh
