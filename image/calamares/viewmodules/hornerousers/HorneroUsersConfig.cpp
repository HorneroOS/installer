// SPDX-License-Identifier: GPL-3.0-or-later
#include "HorneroUsersConfig.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>

#include <fcntl.h>
#include <unistd.h>

HorneroUsersConfig::HorneroUsersConfig( QObject* parent )
    : QObject( parent )
{
}

void
HorneroUsersConfig::setConfigurationMap( const QVariantMap& map )
{
    if ( map.contains( QStringLiteral( "selectionPath" ) ) )
    {
        m_selectionPath = map.value( QStringLiteral( "selectionPath" ) ).toString();
    }
    if ( map.contains( QStringLiteral( "groups" ) ) )
    {
        m_allowedGroups = map.value( QStringLiteral( "groups" ) ).toStringList();
    }
    if ( map.contains( QStringLiteral( "minPasswordLength" ) ) )
    {
        m_minPasswordLength = map.value( QStringLiteral( "minPasswordLength" ) ).toInt();
    }
    Q_EMIT validityChanged();
}

QVector< HorneroExtraUser >
HorneroUsersConfig::activeUsers() const
{
    QVector< HorneroExtraUser > out;
    for ( const auto& user : m_users )
    {
        if ( !user.isEmpty() )
        {
            out.append( user );
        }
    }
    return out;
}

bool
HorneroUsersConfig::isEmptySelection() const
{
    return m_rootPassword.isEmpty() && activeUsers().isEmpty();
}

bool
HorneroUsersConfig::isValid() const
{
    return errorString().isEmpty();
}

QString
HorneroUsersConfig::errorString() const
{
    static const QRegularExpression loginRe( QStringLiteral( "^[a-z_][a-z0-9_-]{0,31}$" ) );
    if ( !m_rootPassword.isEmpty() )
    {
        if ( m_rootPassword.size() < m_minPasswordLength )
        {
            return tr( "Root password must be at least %1 characters." ).arg( m_minPasswordLength );
        }
        if ( m_rootPassword != m_rootPasswordConfirm )
        {
            return tr( "Root passwords do not match." );
        }
    }
    else if ( !m_rootPasswordConfirm.isEmpty() )
    {
        return tr( "Root passwords do not match." );
    }

    QStringList seen;
    for ( const auto& user : activeUsers() )
    {
        if ( !loginRe.match( user.login ).hasMatch() || user.login == QStringLiteral( "root" ) )
        {
            return tr( "Invalid login name: %1" ).arg( user.login );
        }
        if ( seen.contains( user.login ) )
        {
            return tr( "Duplicate login name: %1" ).arg( user.login );
        }
        seen.append( user.login );
        if ( user.fullname.contains( QLatin1Char( ':' ) ) || user.fullname.contains( QLatin1Char( '\n' ) )
             || user.fullname.size() > 128 )
        {
            return tr( "Invalid full name for %1." ).arg( user.login );
        }
        if ( user.password.size() < m_minPasswordLength )
        {
            return tr( "Password for %1 must be at least %2 characters." )
                .arg( user.login )
                .arg( m_minPasswordLength );
        }
        if ( user.password != user.passwordConfirm )
        {
            return tr( "Passwords for %1 do not match." ).arg( user.login );
        }
        for ( const auto& group : user.groups )
        {
            // wheel is never a group choice: it requires the admin flag.
            if ( group == QStringLiteral( "wheel" ) || !m_allowedGroups.contains( group ) )
            {
                return tr( "Group %1 is not allowed for %2." ).arg( group, user.login );
            }
        }
    }
    return QString();
}

bool
HorneroUsersConfig::writeSelection() const
{
    if ( isEmptySelection() )
    {
        QFile::remove( m_selectionPath );
        return true;  // Untouched/reset page: backend absent-file no-op (preview32).
    }
    if ( !isValid() )
    {
        return false;
    }
    const QFileInfo info( m_selectionPath );
    QDir().mkpath( info.absolutePath() );

    QJsonArray users;
    for ( const auto& user : activeUsers() )
    {
        QJsonArray groups;
        for ( const auto& group : user.groups )
        {
            groups.append( group );
        }
        QJsonObject entry;
        entry.insert( QStringLiteral( "login" ), user.login );
        entry.insert( QStringLiteral( "fullname" ), user.fullname );
        entry.insert( QStringLiteral( "password" ), user.password );
        entry.insert( QStringLiteral( "groups" ), groups );
        entry.insert( QStringLiteral( "admin" ), user.admin );
        users.append( entry );
    }
    QJsonObject root;
    if ( !m_rootPassword.isEmpty() )
    {
        root.insert( QStringLiteral( "rootPassword" ), m_rootPassword );
    }
    root.insert( QStringLiteral( "users" ), users );
    const QByteArray payload = QJsonDocument( root ).toJson( QJsonDocument::Indented );

    // Create with 0600 before any secret byte is written; never log payload.
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
