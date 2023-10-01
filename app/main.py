import os
import re
import time
import requests
from flask import Flask, jsonify, flash, request, Response, redirect, url_for, abort, render_template
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from pandas import read_excel
from werkzeug.utils import secure_filename
import MySQLdb
import config
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# Sample flask object
app = Flask(__name__)

limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

UPLOAD_FOLDER = config.UPLOAD_FOLDER
ALLOWED_EXTENSIONS = config.ALLOWED_EXTENSIONS
CALL_BACK_TOKEN = config.CALL_BACK_TOKEN

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# config
app.config.update(
    # DEBUG=True,
    SECRET_KEY=config.SECRET_KEY
)


class User(UserMixin):

    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "%d" % (self.id)


user = User(0)

# some protected url


@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            rows, failures = import_database_from_excel(file_path)
            flash(
                f'Imported {rows} of serials and {failures} rows of failure', 'success')
            os.remove(file_path)  # Remove file from file_path
            return redirect('/')

    # Init mysql connection
    db = MySQLdb.connect(host=config.MYSQL_HOST, user=config.MYSQL_USERNAME,
                         passwd=config.MYSQL_PASSWORD, db=config.MYSQL_DB_NAME)

    cur = db.cursor()
    cur.execute("SELECT * FROM PROCESSED_SMS ORDER BY date DESC LIMIT 5000;")
    all_smss = cur.fetchall()
    smss = []
    for sms in all_smss:
        sender, message, answer, date = sms
        smss.append({'sender': sender, 'message': message,
                    'answer': answer, 'date': date})
        print(smss)

    return render_template('index.html', data={'smss': smss})


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('20 per minute')
def login():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if password == config.PASSWORD and username == config.USERNAME:
            login_user(user)
            return redirect('/')
        else:
            return abort(401)
    else:
        return render_template('login.html')


@app.route('/check_one_serial', methods=['POST'])
@login_required
def check_one_serial():
    serial_to_check = request.form['serial']
    answer = check_serial(normalize_string(serial_to_check))
    flash(answer, 'info')

    return redirect('/')


# somewhere to logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'success')
    return redirect('/login')


# handle login failed
@app.errorhandler(401)
def page_not_found(error):
    flash('Login problem', 'danger')
    return redirect('/login')


# callback to reload the user object
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


@app.route('/v1/ok')
def health_check():
    ret = {'message': 'ok'}
    return jsonify(ret), 200


def send_sms(receptor, message):
    """ This function will get a MSISDN and a message, then uses KaveNegar to send sms.  """
    url = f'https://api.kavenegar.com/v1/{config.API_KEY}/sms/send.json'
    data = {'message': message, 'receptor': receptor}
    response = requests.post(url, data)
    print(
        f'message *{message}* send to receptor: {receptor}. status code is {response.status_code}')


def normalize_string(data, fixed_size=30):
    """ Normalization of digits and letters, this function will convert invalid values to valid value to read from database. """
    from_persian_char = '۱۲۳۴۵۶۷۸۹۰'
    from_arabic_char = '١٢٣٤٥٦٧٨٩٠'
    to_char = '1234567890'
    for i in range(len(to_char)):
        data = data.replace(from_persian_char[i], to_char[i])
        data = data.replace(from_arabic_char[i], to_char[i])
    data = data.upper()
    data = re.sub(r'\W+', '', data)  # remove any non alphanumeric character
    all_alpha = ''
    all_digit = ''
    for c in data:
        if c.isalpha():
            all_alpha += c
        elif c.isdigit():
            all_digit += c

    missing_zeros = fixed_size - len(all_alpha) - len(all_digit)

    data = all_alpha + '0' * missing_zeros + all_digit

    return data


def import_database_from_excel(filepath):
    """ Gets an excel file name and imports lookup data (data and failures) from it.
    the first sheet contains serial data like:
     Row - Reference Number - Description - Start Serial - End Serial - Date
    and the 2nd (1) contains a column of invalid serials.

    This data will be written into the sqlite database located at config.DATA_FILE_PATH
    in two tables. 'serials' and 'invalids'

    return two integers: (number of serial rows, number of invalid rows)
    """
    # df contains lookup data in the form of

    # TODO: make sure that the data is imported correctly, we need to backup the old one

    # Init mysql connection
    db = MySQLdb.connect(host=config.MYSQL_HOST, user=config.MYSQL_USERNAME,
                         passwd=config.MYSQL_PASSWORD, db=config.MYSQL_DB_NAME)

    # Our mysql database will contain two tables: serials and invalids
    cur = db.cursor()

    # Remove the serials table if exists, then create the new one
    cur.execute('DROP TABLE IF EXISTS serials;')
    cur.execute("""CREATE TABLE serials (
        id INTEGER PRIMARY KEY,
        ref VARCHAR(200),
        description VARCHAR(200),
        start_serial CHAR(30),
        end_serial CHAR(30),
        date DATETIME
    );""")
    db.commit()

    df = read_excel(filepath, 0)
    serial_counter = 0
    for index, (line, ref, description, start_serial, end_serial, date) in df.iterrows():
        start_serial = normalize_string(start_serial)
        end_serial = normalize_string(end_serial)
        cur.execute('INSERT INTO serials VALUES (%s, %s, %s, %s, %s, %s);',
                    (line, ref, description, start_serial, end_serial, date))
        # TODO: do some more error handling
        if serial_counter % 10 == 0:
            db.commit()
        serial_counter += 1
    db.commit()

    # Now lets save the invalid serials

    # Remove the invalid table if exists, then create the new one
    cur.execute('DROP TABLE IF EXISTS invalids;')
    cur.execute("""CREATE TABLE invalids(
                invalid_serial CHAR(30)
    );""")
    db.commit()
    invalid_counter = 0
    df = read_excel(filepath, 1)
    for index, (failed_serial, ) in df.iterrows():
        failed_serial = normalize_string(failed_serial)
        cur.execute('INSERT INTO invalids VALUES (%s);', (failed_serial, ))
        # TODO: do some more error handling
        if invalid_counter % 10 == 0:
            db.commit()
        invalid_counter += 1
    db.commit()

    db.close()

    return (serial_counter, invalid_counter)


def check_serial(serial):
    """ this function will get one serial number and return appropriate answer to that, after consulting the db. """
    # Init mysql connection
    db = MySQLdb.connect(host=config.MYSQL_HOST, user=config.MYSQL_USERNAME,
                         passwd=config.MYSQL_PASSWORD, db=config.MYSQL_DB_NAME)
    cur = db.cursor()

    results = cur.execute(
        "SELECT * FROM invalids WHERE invalid_serial = %s;", (serial, ))
    if results > 0:
        db.close()
        # TODO: return the string provided by the customer
        return 'This serial is among failed ones'

    results = cur.execute(
        "SELECT * FROM serials WHERE start_serial <= %s and end_serial >= %s;", (serial, serial))
    if results > 1:
        db.close()
        return 'I found your serial'  # TODO: fix with proper message
    elif results == 1:
        ret = cur.fetchone()
        desc = ret[2]
        db.close()
        # TODO: return string provided by the customer.
        return 'I found your serial: ' + desc

    db.close()
    return 'It was not in the db'


@app.route(f'/v1/{CALL_BACK_TOKEN}/process', methods=['POST'])
def process():
    """ This is a callback from curl requests. will get sender and message and will check if it is valid, then answers back. """
    # Note: You need to call back token to send request (post) to process function
    data = request.form
    sender = data['from']
    message = normalize_string(data['message'])
    print(f'Received: {message} from {sender}')

    answer = check_serial(message)

    # Init mysql connection
    db = MySQLdb.connect(host=config.MYSQL_HOST, user=config.MYSQL_USERNAME,
                         passwd=config.MYSQL_PASSWORD, db=config.MYSQL_DB_NAME)

    cur = db.cursor()

    now = time.strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("INSERT INTO PROCESSED_SMS (sender, message, answer, date) VALUES (%s, %s, %s, %s)",
                (sender, message, answer, now))
    db.commit()
    db.close()

    send_sms(sender, answer)
    ret = {'message': 'processed!'}
    return jsonify(ret), 200


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    # import_database_from_excel('data.xlsx')
    app.run('0.0.0.0', 5000, debug=True)
