// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef HORNEROUSERS_CONFIG_H
#define HORNEROUSERS_CONFIG_H

#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantMap>
#include <QVector>

struct HorneroExtraUser
{
    QString login;
    QString fullname;
    QString password;
    QString passwordConfirm;
    QStringList groups;
    bool admin = false;
    bool isEmpty() const
    {
        return login.isEmpty() && fullname.isEmpty() && password.isEmpty() && passwordConfirm.isEmpty()
            && groups.isEmpty() && !admin;
    }
};

class HorneroUsersConfig : public QObject
{
    Q_OBJECT
public:
    explicit HorneroUsersConfig( QObject* parent = nullptr );

    void setConfigurationMap( const QVariantMap& map );

    QString selectionPath() const { return m_selectionPath; }
    QStringList allowedGroups() const { return m_allowedGroups; }
    int minPasswordLength() const { return m_minPasswordLength; }

    void setRootPassword( const QString& value ) { m_rootPassword = value; }
    void setRootPasswordConfirm( const QString& value ) { m_rootPasswordConfirm = value; }
    void setUsers( const QVector< HorneroExtraUser >& users ) { m_users = users; }
    QVector< HorneroExtraUser > activeUsers() const;

    bool isEmptySelection() const;
    bool isValid() const;
    QString errorString() const;
    bool writeSelection() const;

Q_SIGNALS:
    void validityChanged();

private:
    QString m_selectionPath = QStringLiteral( "/run/hornero-installer/extra-users.json" );
    QStringList m_allowedGroups;
    int m_minPasswordLength = 12;
    QString m_rootPassword;
    QString m_rootPasswordConfirm;
    QVector< HorneroExtraUser > m_users;
};

#endif
