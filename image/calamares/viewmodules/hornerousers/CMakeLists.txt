# SPDX-License-Identifier: BSD-2-Clause
# HorneroOS custom viewmodule: extra users + optional separate root password.
# Injected into the pinned Calamares 3.4.3 tree by packaging/calamares/PKGBUILD
# before cmake runs (src/modules/hornerousers). It deliberately does not link
# users_internal: the stock users module stays the single owner of the
# primary account; this page only writes the create-extra-users.py selection.
find_package(${qtname} ${QT_VERSION} CONFIG REQUIRED Core Gui Widgets)

calamares_add_plugin(hornerousers
    TYPE viewmodule
    EXPORT_MACRO PLUGINDLLEXPORT_PRO
    SOURCES
        HorneroUsersViewStep.cpp
        HorneroUsersPage.cpp
        HorneroUsersConfig.cpp
    LINK_PRIVATE_LIBRARIES
        ${qtname}::Core
        ${qtname}::Gui
        ${qtname}::Widgets
    SHARED_LIB
)
