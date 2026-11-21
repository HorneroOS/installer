# SPDX-License-Identifier: BSD-2-Clause
# HorneroOS custom viewmodule: system choices (kernels, bootloader,
# swap, optional services, offline) for apply-system-plan.py.
# Injected into the pinned Calamares 3.4.3 tree by
# packaging/calamares/PKGBUILD before cmake runs
# (src/modules/hornerosystem). It only writes the system selection;
# the stock partition/users modules stay the owners of their pages.
find_package(${qtname} ${QT_VERSION} CONFIG REQUIRED Core Gui Widgets)

calamares_add_plugin(hornerosystem
    TYPE viewmodule
    EXPORT_MACRO PLUGINDLLEXPORT_PRO
    SOURCES
        HorneroSystemViewStep.cpp
        HorneroSystemPage.cpp
        HorneroSystemConfig.cpp
    LINK_PRIVATE_LIBRARIES
        ${qtname}::Core
        ${qtname}::Gui
        ${qtname}::Widgets
    SHARED_LIB
)
