// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HORNEROUSERS_VIEWSTEP_H
#define HORNEROUSERS_VIEWSTEP_H

#include "DllMacro.h"
#include "utils/PluginFactory.h"
#include "viewpages/ViewStep.h"

#include <QObject>

class HorneroUsersConfig;
class HorneroUsersPage;

class PLUGINDLLEXPORT HorneroUsersViewStep : public Calamares::ViewStep
{
    Q_OBJECT
public:
    explicit HorneroUsersViewStep( QObject* parent = nullptr );
    ~HorneroUsersViewStep() override;

    QString prettyName() const override;
    QWidget* widget() override;
    bool isNextEnabled() const override;
    bool isBackEnabled() const override;
    bool isAtBeginning() const override;
    bool isAtEnd() const override;
    Calamares::JobList jobs() const override;
    void onLeave() override;
    void setConfigurationMap( const QVariantMap& configurationMap ) override;

private:
    HorneroUsersPage* m_widget = nullptr;
    HorneroUsersConfig* m_config;
};

CALAMARES_PLUGIN_FACTORY_DECLARATION( HorneroUsersViewStepFactory )

#endif
