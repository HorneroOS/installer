// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HORNEROUSYSTEM_VIEWSTEP_H
#define HORNEROUSYSTEM_VIEWSTEP_H

#include "DllMacro.h"
#include "utils/PluginFactory.h"
#include "viewpages/ViewStep.h"

#include <QObject>

class HorneroSystemConfig;
class HorneroSystemPage;

class PLUGINDLLEXPORT HorneroSystemViewStep : public Calamares::ViewStep
{
    Q_OBJECT
public:
    explicit HorneroSystemViewStep( QObject* parent = nullptr );
    ~HorneroSystemViewStep() override;

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
    HorneroSystemPage* m_widget = nullptr;
    HorneroSystemConfig* m_config;
};

CALAMARES_PLUGIN_FACTORY_DECLARATION( HorneroSystemViewStepFactory )

#endif
