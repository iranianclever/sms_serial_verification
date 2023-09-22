# sms_serial_verification
A project to products sms serial verification

## TODO
- [x]  Farhad seifi https://ngrok.com
- [x]  add db path to config.py.sample
- [x]  do more while normalizing, specially against SQLInjection. remove all non alpha numerical
- [ ]  Atomic problem when I'm committing every 10 inserts
- [x]  some health check url
- [x]  there is problem with JJ1000000 and JJ100
- [x]  create requirements.txt (pip freeze)
- [ ]  the insert will fail if there is a ' or " in excel file
- [x]  another 10 % problem :D
- [x]  refactor name str in normalize function
- [x]  in normalize, convert AB001 TO AB00001 (max len? say 15)
- [x]  dockerize (alpine? search for uwsgi)
- [x]  merge pull requests.. check I mean :)
- [x]  do proper inserts with INTO
- [x]  templates html
- [x]  H shafiee
- [x]  rate limit
- [x]  add call back token on kavenegar site
- [x]  we do not normalize the failed serials when importing!
- [x]  invalids can have duplicates
- [ ]  migrate to mysql