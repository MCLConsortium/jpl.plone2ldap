# encoding: utf-8

u'''Export Plone usernames and passwords to LDAP.'''

app = globals().get('app', None)  # ``app`` comes from ``instance run`` magic.

from AccessControl.SecurityManagement import newSecurityManager, noSecurityManager
from AccessControl.SecurityManager import setSecurityPolicy
from Products.CMFCore.tests.base.security import PermissiveSecurityPolicy, OmnipotentUser
from Products.CMFCore.utils import getToolByName
from zope.component.hooks import setSite
import logging, argparse, sys, ldap, getpass, ldap.modlist


# Set up logging
_logger = logging.getLogger('setupldap')
_logger.setLevel(logging.DEBUG)
_console = logging.StreamHandler(sys.stderr)
_formatter = logging.Formatter('%(levelname)-8s %(message)s')
_console.setFormatter(_formatter)
_logger.addHandler(_console)


# Set up command-line options
_argParser = argparse.ArgumentParser(description=u'Installs Plone usernames and passwords into LDAP', prog='plone2ldap')
_argParser.add_argument('-D', '--system-dn', metavar='DN', help='Set LDAP admin username to DN, default "%(default)s"',
    default='uid=admin,ou=system')
_argParser.add_argument('-w', '--password', help='Set LDAP admin password to PASSWORD')
_argParser.add_argument('-W', '--prompt', action='store_true', help='Prompt for LDAP admin password; suppresses "-w"')
_argParser.add_argument('-H', '--ldap-url', default='ldap://localhost',
    help='URL to LDAP server, default "%(default)s"')
_argParser.add_argument('-b', '--base-dn', metavar='DN', default='o=users', help='Base DN which to insert users')
_argParser.add_argument('-o', '--overwrite', action='store_true', default=False,
    help='Overwrite existing LDAP users, default "%(default)s"')
_argParser.add_argument('-v', '--verbose', action='store_true', help='Be overly verbose')
_argParser.add_argument('plone', nargs=1, metavar='PLONE-OBJ',
    help='Use the Plone object named PLONE-OBJ in the database')


def setupZope(app):
    _logger.debug(u'Setting up Zope & security')
    acl_users = app.acl_users
    setSecurityPolicy(PermissiveSecurityPolicy())
    newSecurityManager(None, OmnipotentUser().__of__(acl_users))


def getPortal(app, plone):
    _logger.debug(u'Getting portal named %s', plone)
    portal = getattr(app, plone)
    setSite(portal)
    return portal


def installUsers(app, systemDN, password, url, baseDN, overwrite, plone):
    setupZope(app)
    portal = getPortal(app, plone)
    _logger.debug(u'Connecting to LDAP server at %s', url)
    con = ldap.initialize(url)
    _logger.debug(u'Binding as %s', systemDN)
    con.bind_s(systemDN, password)
    _logger.debug(u"Getting portal's pluggable authentication service")
    pas = portal.acl_users
    users = pas.source_users
    passwords = dict(users._user_passwords)
    _logger.debug(u'Getting portal_membership')
    membership = getToolByName(portal, 'portal_membership')
    for member in membership.listMembers():
        userID = member.getName()
        _logger.debug(u'Considering %s', userID)
        existing = con.search_s(baseDN, ldap.SCOPE_ONELEVEL, filterstr='(uid={})'.format(userID))
        dn = 'uid=' + userID + ',' + baseDN
        if existing:
            if not overwrite:
                _logger.info('Found %s already in LDAP, not ovewriting', dn)
                continue
            else:
                _logger.info('Deleting existing %s in LDAP', dn)
                con.delete_s(dn)
        name, email = member.getProperty('fullname'), member.getProperty('email')
        modlist = ldap.modlist.addModlist({
            'objectClass': ['top', 'person', 'organizationalPerson', 'inetOrgPerson'],
            'userPassword': [passwords[userID]],
            'sn': [name.split()[-1]],
            'uid': [userID],
            'mail': [email],
            'cn': [name]
        })
        _logger.info('Adding %s to LDAP', dn)
        con.add_s(dn, modlist)


def main(argv):
    options = _argParser.parse_args(argv)
    if options.verbose:
        _logger.setLevel(logging.DEBUG)
    systemDN = options.system_dn
    password = options.password
    if password is None or options.prompt:
        password = getpass.getpass(u'Password for {}: '.format(systemDN))
    global app
    installUsers(app, systemDN, password, options.ldap_url, options.base_dn, options.overwrite, options.plone[0])
    return True


if __name__ == '__main__':
    # The [3:] works around plone.recipe.zope2instance-4.2.6's bin/interpreter script issue
    sys.exit(0 if main(sys.argv[3:]) is True else -1)
