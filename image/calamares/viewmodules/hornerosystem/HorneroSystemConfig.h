// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HORNEROUSYSTEM_CONFIG_H
#define HORNEROUSYSTEM_CONFIG_H

#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantMap>

class HorneroSystemConfig : public QObject
{
    Q_OBJECT
public:
    explicit HorneroSystemConfig( QObject* parent = nullptr );

    void setConfigurationMap( const QVariantMap& map );

    QString selectionPath() const { return m_selectionPath; }
    QStringList kernels() const { return m_kernels; }
    int espMiB() const;

    void setPrimaryKernel( const QString& value ) { m_primaryKernel = value; Q_EMIT validityChanged(); }
    void setFallbackKernel( const QString& value ) { m_fallbackKernel = value; Q_EMIT validityChanged(); }
    void setBootloader( const QString& value ) { m_bootloader = value; Q_EMIT validityChanged(); }
    void setSwap( const QString& value ) { m_swap = value; Q_EMIT validityChanged(); }
    void setBluetooth( bool value ) { m_bluetooth = value; Q_EMIT validityChanged(); }
    void setTimesyncd( bool value ) { m_timesyncd = value; Q_EMIT validityChanged(); }
    void setOffline( bool value ) { m_offline = value; Q_EMIT validityChanged(); }

    QString firmware() const;  // "uefi" when /sys/firmware/efi exists, else "bios"
    bool isDefaultSelection() const;
    bool isValid() const;
    QString errorString() const;
    bool writeSelection() const;
    void storeBootloaderGlobal() const;

Q_SIGNALS:
    void validityChanged();

private:
    QString m_selectionPath = QStringLiteral( "/run/hornero-installer/system-selection.json" );
    QStringList m_kernels = { QStringLiteral( "linux" ), QStringLiteral( "linux-lts" ),
                              QStringLiteral( "linux-zen" ), QStringLiteral( "linux-hardened" ) };
    QString m_primaryKernel = QStringLiteral( "linux" );
    QString m_fallbackKernel;
    QString m_bootloader = QStringLiteral( "grub" );
    QString m_swap = QStringLiteral( "none" );
    bool m_bluetooth = true;
    bool m_timesyncd = true;
    bool m_offline = false;
};

#endif
