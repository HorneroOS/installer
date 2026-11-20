// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HORNEROUSERS_PAGE_H
#define HORNEROUSERS_PAGE_H

#include "HorneroUsersConfig.h"

#include <QWidget>

class QCheckBox;
class QLineEdit;
class QLabel;
class QVBoxLayout;

class HorneroUsersPage : public QWidget
{
    Q_OBJECT
public:
    explicit HorneroUsersPage( HorneroUsersConfig* config, QWidget* parent = nullptr );
    void syncToConfig();

Q_SIGNALS:
    void changed();

private:
    struct Row
    {
        QWidget* widget = nullptr;
        QLineEdit* login = nullptr;
        QLineEdit* fullname = nullptr;
        QLineEdit* password = nullptr;
        QLineEdit* passwordConfirm = nullptr;
        QVector< QCheckBox* > groupChecks;
        QCheckBox* admin = nullptr;
    };
    Row createRow();
    void rebuildGroupChecks();

    HorneroUsersConfig* m_config;
    QLineEdit* m_rootPassword;
    QLineEdit* m_rootPasswordConfirm;
    QLabel* m_error;
    QVBoxLayout* m_rowsLayout;
    QVector< Row > m_rows;
};

#endif
