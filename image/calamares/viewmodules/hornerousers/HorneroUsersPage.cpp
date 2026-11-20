// SPDX-License-Identifier: GPL-3.0-or-later
#include "HorneroUsersPage.h"

#include <QCheckBox>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QVBoxLayout>

#include <algorithm>

HorneroUsersPage::HorneroUsersPage( HorneroUsersConfig* config, QWidget* parent )
    : QWidget( parent )
    , m_config( config )
{
    auto* main = new QVBoxLayout( this );

    auto* intro = new QLabel(
        tr( "Optional. Leave everything empty to keep the current install: root stays locked "
            "and no additional users are created." ) );
    intro->setWordWrap( true );
    main->addWidget( intro );

    auto* rootBox = new QGroupBox( tr( "Root password (optional, separate)" ) );
    auto* rootLayout = new QVBoxLayout( rootBox );
    m_rootPassword = new QLineEdit();
    m_rootPassword->setEchoMode( QLineEdit::Password );
    m_rootPassword->setPlaceholderText( tr( "Empty = root locked" ) );
    m_rootPasswordConfirm = new QLineEdit();
    m_rootPasswordConfirm->setEchoMode( QLineEdit::Password );
    m_rootPasswordConfirm->setPlaceholderText( tr( "Confirm root password" ) );
    rootLayout->addWidget( m_rootPassword );
    rootLayout->addWidget( m_rootPasswordConfirm );
    rootLayout->addWidget( new QLabel( tr( "At least 12 characters. Independent from the main user password; there is no reuse option." ) ) );
    main->addWidget( rootBox );

    auto* usersBox = new QGroupBox( tr( "Additional users" ) );
    auto* usersLayout = new QVBoxLayout( usersBox );
    m_rowsLayout = new QVBoxLayout();
    usersLayout->addLayout( m_rowsLayout );
    auto* addButton = new QPushButton( tr( "Add user" ) );
    usersLayout->addWidget( addButton );
    main->addWidget( usersBox );

    m_error = new QLabel();
    m_error->setWordWrap( true );
    main->addWidget( m_error );
    main->addStretch();

    auto onChange = [ this ]() {
        syncToConfig();
        m_error->setText( m_config->errorString() );
        Q_EMIT changed();
    };
    connect( m_rootPassword, &QLineEdit::textChanged, this, onChange );
    connect( m_rootPasswordConfirm, &QLineEdit::textChanged, this, onChange );
    connect( addButton, &QPushButton::clicked, this, [ this, onChange ]() {
        m_rows.append( createRow() );
        m_rowsLayout->addWidget( m_rows.last().widget );
        // Wire the new row.
        const Row& row = m_rows.last();
        connect( row.login, &QLineEdit::textChanged, this, onChange );
        connect( row.fullname, &QLineEdit::textChanged, this, onChange );
        connect( row.password, &QLineEdit::textChanged, this, onChange );
        connect( row.passwordConfirm, &QLineEdit::textChanged, this, onChange );
        connect( row.admin, &QCheckBox::toggled, this, onChange );
        for ( auto* check : row.groupChecks )
        {
            connect( check, &QCheckBox::toggled, this, onChange );
        }
        onChange();
    } );
}

HorneroUsersPage::Row
HorneroUsersPage::createRow()
{
    Row row;
    row.widget = new QWidget();
    auto* layout = new QVBoxLayout( row.widget );
    row.login = new QLineEdit();
    row.login->setPlaceholderText( tr( "Login (e.g. ana)" ) );
    row.fullname = new QLineEdit();
    row.fullname->setPlaceholderText( tr( "Full name" ) );
    row.password = new QLineEdit();
    row.password->setEchoMode( QLineEdit::Password );
    row.password->setPlaceholderText( tr( "Password (at least 12 characters)" ) );
    row.passwordConfirm = new QLineEdit();
    row.passwordConfirm->setEchoMode( QLineEdit::Password );
    row.passwordConfirm->setPlaceholderText( tr( "Confirm password" ) );
    layout->addWidget( row.login );
    layout->addWidget( row.fullname );
    layout->addWidget( row.password );
    layout->addWidget( row.passwordConfirm );

    auto* groupsLayout = new QHBoxLayout();
    for ( const auto& group : m_config->allowedGroups() )
    {
        auto* check = new QCheckBox( group );
        row.groupChecks.append( check );
        groupsLayout->addWidget( check );
    }
    layout->addLayout( groupsLayout );

    row.admin = new QCheckBox( tr( "Administrator (adds to wheel — sudo access)" ) );
    layout->addWidget( row.admin );
    auto* warn = new QLabel( tr( "Warning: administrator users can gain root via sudo." ) );
    warn->setWordWrap( true );
    layout->addWidget( warn );

    auto* removeButton = new QPushButton( tr( "Remove this user" ) );
    layout->addWidget( removeButton );
    connect( removeButton, &QPushButton::clicked, row.widget, [ this, rowWidget = row.widget ]() {
        m_rows.erase( std::remove_if( m_rows.begin(),
                                      m_rows.end(),
                                      [ rowWidget ]( const Row& candidate ) { return candidate.widget == rowWidget; } ),
                      m_rows.end() );
        rowWidget->deleteLater();
        syncToConfig();
        m_error->setText( m_config->errorString() );
        Q_EMIT changed();
    } );
    return row;
}

void
HorneroUsersPage::rebuildGroupChecks()
{
    // Groups come from hornerousers.conf (allowlist mirror); rows created
    // after configuration is set pick them up in createRow().
}

void
HorneroUsersPage::syncToConfig()
{
    m_config->setRootPassword( m_rootPassword->text() );
    m_config->setRootPasswordConfirm( m_rootPasswordConfirm->text() );
    QVector< HorneroExtraUser > users;
    for ( const auto& row : m_rows )
    {
        HorneroExtraUser user;
        user.login = row.login->text().trimmed();
        user.fullname = row.fullname->text();
        user.password = row.password->text();
        user.passwordConfirm = row.passwordConfirm->text();
        for ( auto* check : row.groupChecks )
        {
            if ( check->isChecked() )
            {
                user.groups.append( check->text() );
            }
        }
        user.admin = row.admin->isChecked();
        users.append( user );
    }
    m_config->setUsers( users );
}
