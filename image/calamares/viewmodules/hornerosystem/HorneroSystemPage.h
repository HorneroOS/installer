// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HORNEROUSYSTEM_PAGE_H
#define HORNEROUSYSTEM_PAGE_H

#include "HorneroSystemConfig.h"

#include <QWidget>

class QCheckBox;
class QComboBox;
class QLabel;

class HorneroSystemPage : public QWidget
{
    Q_OBJECT
public:
    explicit HorneroSystemPage( HorneroSystemConfig* config, QWidget* parent = nullptr );
    void syncToConfig();

Q_SIGNALS:
    void changed();

private:
    HorneroSystemConfig* m_config;
    QComboBox* m_primary;
    QComboBox* m_fallback;
    QComboBox* m_bootloader;
    QComboBox* m_swap;
    QCheckBox* m_bluetooth;
    QCheckBox* m_timesyncd;
    QCheckBox* m_offline;
    QLabel* m_note;
    QLabel* m_error;
};

#endif
