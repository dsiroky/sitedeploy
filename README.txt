**sitedeploy** is a replacement for sitecopy.

  * supported protocols: FTP, SSH (via `paramiko <http://www.lag.net/paramiko/>`_)
  * fast synchronization

``~/.sitedeployrc`` example::

  site bigcompany
    server ftp.bigcompany.com
    remote /bigcompanysite.com/www
    local /var/www/big
    protocol ftp
    username foo
    password xxxx
    permissions all
    exclude templates_c
    exclude *.log

  site smallcompany
    server ftp.smallc.com
    remote /html/
    local /var/www/small
    protocol ftp
    permissions all
    username bar
    password xxxx

Basic steps:
  #. initialize (need to be performed only once)::

      $ sitesitedeploy.py -i bigcompany
  
  #. update changes::

      $ sitesitedeploy.py -u bigcompany
