# sms_serial_verification
A project to products sms serial verification

### How to run
1. Install python3, pip3, virtualenv, MySQL in your system.
2. Clone the project `https://github.com/iranianclever/sms_serial_verification && cd sms_serial_verification`
3. In the app folder, rename the `config.py.sample` to `config.py` and do proper changes.
4. DB config are in config.py. Create a database based on the name in config.py; make it UTF8 compatible (Collation: utf8md4_bin).
5. Create a virtualenv using `virtualenv -p python venv`
6. Connect to virtualenv using `source venv/bin/active`
7. From the project folder, install packages using `pip install -r requirements.txt`
8. Now environment is ready. Run it by `python app/main.py`

## Example of creating db and granting access:

> Note this is just a sample. You have to find your own systems commands.

```
CREATE DATABASE smsmysql;
USER smsmysql;
CREATE USER 'smsmysql'@'localhost' IDENTIFIED BY 'test' PASSWORD NEVER EXPIRE;
GRANT ALL PRIVILEGES ON smsmysql.* TO 'smsmysql'@'localhost';
```
