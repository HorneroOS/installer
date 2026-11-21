// SPDX-License-Identifier: GPL-3.0-or-later
#include "HorneroUsersViewStep.h"

#include "HorneroUsersConfig.h"
#include "HorneroUsersPage.h"

CALAMARES_PLUGIN_FACTORY_DEFINITION( HorneroUsersViewStepFactory, registerPlugin< HorneroUsersViewStep >(); )

HorneroUsersViewStep::HorneroUsersViewStep( QObject* parent )
    : Calamares::ViewStep( parent )
    , m_config( new HorneroUsersConfig( this ) )
{
    connect( m_config, &HorneroUsersConfig::validityChanged, this, [ this ]() {
        Q_EMIT nextStatusChanged( isNextEnabled() );
    } );
    Q_EMIT nextStatusChanged( true );
}

HorneroUsersViewStep::~HorneroUsersViewStep()
{
    if ( m_widget && m_widget->parent() == nullptr )
    {
        m_widget->deleteLater();
    }
}

QString
HorneroUsersViewStep::prettyName() const
{
    return tr( "Additional users" );
}

QWidget*
HorneroUsersViewStep::widget()
{
    if ( !m_widget )
    {
        m_widget = new HorneroUsersPage( m_config );
        connect( m_widget, &HorneroUsersPage::changed, this, [ this ]() {
            Q_EMIT nextStatusChanged( isNextEnabled() );
        } );
    }
    return m_widget;
}

bool
HorneroUsersViewStep::isNextEnabled() const
{
    if ( m_widget )
    {
        m_widget->syncToConfig();
    }
    return m_config->isValid();
}

bool
HorneroUsersViewStep::isBackEnabled() const
{
    return true;
}

bool
HorneroUsersViewStep::isAtBeginning() const
{
    return true;
}

bool
HorneroUsersViewStep::isAtEnd() const
{
    return true;
}

Calamares::JobList
HorneroUsersViewStep::jobs() const
{
    return Calamares::JobList();
}

void
HorneroUsersViewStep::onLeave()
{
    // Only writer of the backend selection. Untouched page writes nothing,
    // so shellprocess@extra-users stays an absent-file no-op. Failure to
    // write is not logged with any payload (it contains passwords).
    if ( m_widget )
    {
        m_widget->syncToConfig();
    }
    m_config->writeSelection();
}

void
HorneroUsersViewStep::setConfigurationMap( const QVariantMap& configurationMap )
{
    m_config->setConfigurationMap( configurationMap );
}
