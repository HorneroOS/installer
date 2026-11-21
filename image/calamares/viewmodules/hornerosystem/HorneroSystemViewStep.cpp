// SPDX-License-Identifier: GPL-3.0-or-later
#include "HorneroSystemViewStep.h"

#include "HorneroSystemConfig.h"
#include "HorneroSystemPage.h"

CALAMARES_PLUGIN_FACTORY_DEFINITION( HorneroSystemViewStepFactory, registerPlugin< HorneroSystemViewStep >(); )

HorneroSystemViewStep::HorneroSystemViewStep( QObject* parent )
    : Calamares::ViewStep( parent )
    , m_config( new HorneroSystemConfig( this ) )
{
    connect( m_config, &HorneroSystemConfig::validityChanged, this, [ this ]() {
        Q_EMIT nextStatusChanged( isNextEnabled() );
    } );
    Q_EMIT nextStatusChanged( true );
}

HorneroSystemViewStep::~HorneroSystemViewStep()
{
    if ( m_widget && m_widget->parent() == nullptr )
    {
        m_widget->deleteLater();
    }
}

QString
HorneroSystemViewStep::prettyName() const
{
    return tr( "System" );
}

QWidget*
HorneroSystemViewStep::widget()
{
    if ( !m_widget )
    {
        m_widget = new HorneroSystemPage( m_config );
        connect( m_widget, &HorneroSystemPage::changed, this, [ this ]() {
            Q_EMIT nextStatusChanged( isNextEnabled() );
        } );
    }
    return m_widget;
}

bool
HorneroSystemViewStep::isNextEnabled() const
{
    if ( m_widget )
    {
        m_widget->syncToConfig();
    }
    return m_config->isValid();
}

bool
HorneroSystemViewStep::isBackEnabled() const
{
    return true;
}

bool
HorneroSystemViewStep::isAtBeginning() const
{
    return true;
}

bool
HorneroSystemViewStep::isAtEnd() const
{
    return true;
}

Calamares::JobList
HorneroSystemViewStep::jobs() const
{
    return Calamares::JobList();
}

void
HorneroSystemViewStep::onLeave()
{
    // Only writer of the backend selection. This page will sit before
    // Partition in the show sequence once its VM gate passes, so the
    // systemd-boot firmware gate blocks Next before any disk write.
    // Untouched page writes nothing (preview32 absent-file no-op).
    if ( m_widget )
    {
        m_widget->syncToConfig();
    }
    m_config->writeSelection();
}

void
HorneroSystemViewStep::setConfigurationMap( const QVariantMap& configurationMap )
{
    m_config->setConfigurationMap( configurationMap );
}
