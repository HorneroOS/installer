// SPDX-License-Identifier: GPL-3.0-or-later
#include "HorneroSystemPage.h"

#include <QCheckBox>
#include <QComboBox>
#include <QGroupBox>
#include <QLabel>
#include <QVBoxLayout>

HorneroSystemPage::HorneroSystemPage( HorneroSystemConfig* config, QWidget* parent )
    : QWidget( parent )
    , m_config( config )
{
    auto* main = new QVBoxLayout( this );
    auto* intro = new QLabel( tr( "Optional system choices. Leaving everything at its default "
                                  "installs exactly the current HorneroOS preview system." ) );
    intro->setWordWrap( true );
    main->addWidget( intro );

    auto* kernelBox = new QGroupBox( tr( "Kernels" ) );
    auto* kernelLayout = new QVBoxLayout( kernelBox );
    m_primary = new QComboBox();
    m_primary->addItems( m_config->kernels() );
    m_fallback = new QComboBox();
    m_fallback->addItem( tr( "None" ), QString() );
    for ( const auto& kernel : m_config->kernels() )
    {
        m_fallback->addItem( kernel, kernel );
    }
    kernelLayout->addWidget( new QLabel( tr( "Primary kernel" ) ) );
    kernelLayout->addWidget( m_primary );
    kernelLayout->addWidget( new QLabel( tr( "Fallback kernel (a second kernel adds its headers)" ) ) );
    kernelLayout->addWidget( m_fallback );
    main->addWidget( kernelBox );

    auto* bootBox = new QGroupBox( tr( "Bootloader, swap and services" ) );
    auto* bootLayout = new QVBoxLayout( bootBox );
    m_bootloader = new QComboBox();
    m_bootloader->addItem( QStringLiteral( "grub" ) );
    m_bootloader->addItem( QStringLiteral( "systemd-boot" ) );
    m_swap = new QComboBox();
    m_swap->addItem( QStringLiteral( "none" ) );
    m_swap->addItem( QStringLiteral( "file" ) );
    m_swap->addItem( tr( "partition (only without LUKS; no hibernation)" ), QStringLiteral( "partition" ) );
    m_bluetooth = new QCheckBox( tr( "Bluetooth service" ) );
    m_bluetooth->setChecked( true );
    m_timesyncd = new QCheckBox( tr( "Time synchronisation (systemd-timesyncd)" ) );
    m_timesyncd->setChecked( true );
    m_offline = new QCheckBox( tr( "Offline installation (default kernel only)" ) );
    bootLayout->addWidget( new QLabel( tr( "Bootloader" ) ) );
    bootLayout->addWidget( m_bootloader );
    bootLayout->addWidget( new QLabel( tr( "Swap" ) ) );
    bootLayout->addWidget( m_swap );
    bootLayout->addWidget( m_bluetooth );
    bootLayout->addWidget( m_timesyncd );
    bootLayout->addWidget( m_offline );
    main->addWidget( bootBox );

    m_note = new QLabel();
    m_note->setWordWrap( true );
    main->addWidget( m_note );
    m_error = new QLabel();
    m_error->setWordWrap( true );
    main->addWidget( m_error );
    main->addStretch();

    auto onChange = [ this ]() {
        syncToConfig();
        m_error->setText( m_config->errorString() );
        m_note->setText( m_bootloader->currentText() == QStringLiteral( "systemd-boot" )
                             ? tr( "systemd-boot needs UEFI and an EFI system partition of at "
                                   "least %1 MiB; size it on the Partition page. A swap "
                                   "partition is aborted if you enable LUKS there." )
                                   .arg( m_config->espMiB() )
                             : tr( "A swap partition is aborted if you enable LUKS on the "
                                   "Partition page. Hibernation is not offered." ) );
        Q_EMIT changed();
    };
    connect( m_primary, &QComboBox::currentTextChanged, this, onChange );
    connect( m_fallback, &QComboBox::currentTextChanged, this, onChange );
    connect( m_bootloader, &QComboBox::currentTextChanged, this, onChange );
    connect( m_swap, &QComboBox::currentTextChanged, this, onChange );
    connect( m_bluetooth, &QCheckBox::toggled, this, onChange );
    connect( m_timesyncd, &QCheckBox::toggled, this, onChange );
    connect( m_offline, &QCheckBox::toggled, this, onChange );
    onChange();
}

void
HorneroSystemPage::syncToConfig()
{
    m_config->setPrimaryKernel( m_primary->currentText() );
    m_config->setFallbackKernel( m_fallback->currentData().toString() );
    m_config->setBootloader( m_bootloader->currentText() );
    const QString swap = m_swap->currentData().toString();
    m_config->setSwap( swap.isEmpty() ? m_swap->currentText() : swap );
    m_config->setBluetooth( m_bluetooth->isChecked() );
    m_config->setTimesyncd( m_timesyncd->isChecked() );
    m_config->setOffline( m_offline->isChecked() );
}
