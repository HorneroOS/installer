// SPDX-License-Identifier: GPL-3.0-or-later
#include "HorneroSystemConfig.h"

#include "GlobalStorage.h"
#include "JobQueue.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>

#include <fcntl.h>
#include <unistd.h>

HorneroSystemConfig::HorneroSystemConfig( QObject* parent )
    : QObject( parent )
    , m_offline( QFileInfo::exists( QStringLiteral( "/run/hornero-installer/offline-mode" ) ) )
{
}

void
HorneroSystemConfig::setConfigurationMap( const QVariantMap& map )
{
    if ( map.contains( QStringLiteral( "selectionPath" ) ) )
    {
        m_selectionPath = map.value( QStringLiteral( "selectionPath" ) ).toString();
    }
    if ( map.contains( QStringLiteral( "kernels" ) ) )
    {
        m_kernels = map.value( QStringLiteral( "kernels" ) ).toStringList();
    }
    Q_EMIT validityChanged();
}

QString
HorneroSystemConfig::firmware() const
{
    return QDir( QStringLiteral( "/sys/firmware/efi" ) ).exists() ? QStringLiteral( "uefi" )
                                                                  : QStringLiteral( "bios" );
}

int
HorneroSystemConfig::espMiB() const
{
    const int count = m_fallbackKernel.isEmpty() ? 1 : 2;
    const int base = 1024;
    return base + 256 * ( count - 1 );
}

bool
HorneroSystemConfig::isDefaultSelection() const
{
    return m_primaryKernel == QStringLiteral( "linux" ) && m_fallbackKernel.isEmpty()
        && m_bootloader == QStringLiteral( "grub" ) && m_swap == QStringLiteral( "none" )
        && m_bluetooth && m_timesyncd && !m_offline;
}

bool
HorneroSystemConfig::isValid() const
{
    return errorString().isEmpty();
}

QString
HorneroSystemConfig::errorString() const
{
    if ( !m_kernels.contains( m_primaryKernel ) )
    {
        return tr( "Unknown primary kernel: %1" ).arg( m_primaryKernel );
    }
    if ( !m_fallbackKernel.isEmpty() )
    {
        if ( !m_kernels.contains( m_fallbackKernel ) )
        {
            return tr( "Unknown fallback kernel: %1" ).arg( m_fallbackKernel );
        }
        if ( m_fallbackKernel == m_primaryKernel )
        {
            return tr( "The fallback kernel must differ from the primary kernel." );
        }
    }
    // Pre-partition gate: with Next blocked here, a non-qualifying
    // systemd-boot selection writes nothing at all.
    if ( m_bootloader == QStringLiteral( "systemd-boot" ) && firmware() != QStringLiteral( "uefi" ) )
    {
        return tr( "systemd-boot needs UEFI: this machine booted in legacy BIOS mode. "
                   "Choose GRUB or reboot the installer in UEFI mode." );
    }
    if ( m_offline && ( m_primaryKernel != QStringLiteral( "linux" ) || !m_fallbackKernel.isEmpty() ) )
    {
        return tr( "Offline installation only carries the default 'linux' kernel; "
                   "reconnect or keep the default kernel." );
    }
    return QString();
}

void
HorneroSystemConfig::storeBootloaderGlobal() const
{
    auto* storage = Calamares::JobQueue::instance()->globalStorage();
    if ( storage )
    {
        storage->insert( QStringLiteral( "hornero_bootloader" ), m_bootloader );
    }
}

bool
HorneroSystemConfig::writeSelection() const
{
    if ( isDefaultSelection() )
    {
        storeBootloaderGlobal();
        QFile::remove( m_selectionPath );
        return true;  // Untouched/reset page: backend absent-file no-op (preview32).
    }
    if ( !isValid() )
    {
        return false;
    }
    storeBootloaderGlobal();
    const QFileInfo info( m_selectionPath );
    QDir().mkpath( info.absolutePath() );

    QJsonObject services;
    services.insert( QStringLiteral( "bluetooth" ), m_bluetooth );
    services.insert( QStringLiteral( "timesyncd" ), m_timesyncd );
    QJsonObject appearance;
    // Record-only, single proven theme: no consumer reads other values
    // yet, so no theme selector is offered (installer#113).
    appearance.insert( QStringLiteral( "theme" ), QStringLiteral( "hornero-signal-night" ) );
    appearance.insert( QStringLiteral( "shellPreset" ), QStringLiteral( "cockpit" ) );
    QJsonObject root;
    root.insert( QStringLiteral( "primaryKernel" ), m_primaryKernel );
    if ( m_fallbackKernel.isEmpty() )
    {
        root.insert( QStringLiteral( "fallbackKernel" ), QJsonValue::Null );
    }
    else
    {
        root.insert( QStringLiteral( "fallbackKernel" ), m_fallbackKernel );
    }
    root.insert( QStringLiteral( "bootloader" ), m_bootloader );
    root.insert( QStringLiteral( "firmware" ), firmware() );
    root.insert( QStringLiteral( "encryption" ), QStringLiteral( "none" ) );
    root.insert( QStringLiteral( "swap" ), m_swap );
    root.insert( QStringLiteral( "services" ), services );
    root.insert( QStringLiteral( "appearance" ), appearance );
    root.insert( QStringLiteral( "offline" ), m_offline );
    const QByteArray payload = QJsonDocument( root ).toJson( QJsonDocument::Indented );

    const int fd = ::open( m_selectionPath.toLocal8Bit().constData(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600 );
    if ( fd < 0 )
    {
        return false;
    }
    QFile file;
    if ( !file.open( fd, QIODevice::WriteOnly, QFileDevice::AutoCloseHandle ) )
    {
        ::close( fd );
        return false;
    }
    file.setPermissions( QFileDevice::ReadOwner | QFileDevice::WriteOwner );
    return file.write( payload ) == payload.size() && file.flush();
}
