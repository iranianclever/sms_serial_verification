import os
import re
import time
import datetime
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

# Create limiter to prevent brute force
limiter = Limiter(app=app, key_func=get_remote_address,
                  storage_uri="memory://")

# Constant configs
MAX_FLASH = 10
UPLOAD_FOLDER = config.UPLOAD_FOLDER
ALLOWED_EXTENSIONS = config.ALLOWED_EXTENSIONS
CALL_BACK_TOKEN = config.CALL_BACK_TOKEN

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'danger'


def allowed_file(filename):
    """ Check the extension of the passed filename to be in the allowed extensions """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# A secure key to protect app
app.config.update(SECRET_KEY=config.SECRET_KEY)


class User(UserMixin):
    """ A minimal and singleton user class used only for administrative tasks """

    def __init__(self, id):
        """ Constructor initialize user id """
        self.id = id

    def __repr__(self):
        return "%d" % (self.id)


user = User(0)


def init_processed_sms_table_in_db():
    """ This function is important for holder sms status and request to server for products or other. """
    # Init mysql connection
    db = get_database_connection()

    cur = db.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS PROCESSED_SMS (status ENUM('OK', 'FAILURE', 'DOUBLE', 'NOT-FOUND'), sender CHAR(20), message VARCHAR(400), answer VARCHAR(400), date DATETIME, INDEX(date, status));")
    db.commit()
    db.close()


@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    """ Creates database if method is post otherwise shows the homepage with some stats see import_database_from_excel() for more details on database creation """
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

    # Init processed_sms table in database
    init_processed_sms_table_in_db()

    # Init mysql connection
    db = get_database_connection()

    cur = db.cursor()

    # Get last 5000 sms
    cur.execute("SELECT * FROM PROCESSED_SMS ORDER BY date DESC LIMIT 5000;")
    all_smss = cur.fetchall()
    smss = []
    for sms in all_smss:
        status, sender, message, answer, date = sms
        smss.append({'status': status, 'sender': sender, 'message': message,
                    'answer': answer, 'date': date})

    # Collect some stats for the GUI
    cur.execute("SELECT count(*) FROM PROCESSED_SMS WHERE status = 'OK';")
    num_ok = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM PROCESSED_SMS WHERE status = 'FAILURE';")
    num_failure = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM PROCESSED_SMS WHERE status = 'DOUBLE';")
    num_double = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM PROCESSED_SMS WHERE status = 'NOT-FOUND';")
    num_notfound = cur.fetchone()[0]

    return render_template('index.html', data={'smss': smss, 'ok': num_ok, 'failure': num_failure, 'double': num_double, 'notfound': num_notfound})


def get_database_connection():
    return MySQLdb.connect(host=config.MYSQL_HOST, user=config.MYSQL_USERNAME,
                           passwd=config.MYSQL_PASSWORD, db=config.MYSQL_DB_NAME, charset='utf8')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('20 per minute')
def login():
    """ User login: only for admin user (System has no other user than admin)
    Note: there is a 10 tries per minute limitation to admin login to avoid minimize password factoring """
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
    """ To check whether a serail number is valid or not """
    serial_to_check = request.form['serial']
    status, answer = check_serial(serial_to_check)
    flash(f'{status} - {answer}', 'info')

    return redirect('/')


@app.route('/logout')
@login_required
def logout():
    """ Logs out the admin user """
    logout_user()
    flash('Logged out', 'success')
    return redirect('/login')


# handle login failed
@app.errorhandler(401)
def unauthorized(error):
    """ Handling login failures """
    flash('Login problem', 'danger')
    return redirect('/login')


# callback to reload the user object
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


@app.route('/v1/ok')
def health_check():
    """ Will return message: OK when called. for monitoring systems. """
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
    for this_character in data:
        if this_character.isalpha():
            all_alpha += this_character
        elif this_character.isdigit():
            all_digit += this_character

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

    # Init mysql connection
    db = get_database_connection()

    # Our mysql database will contain two tables: serials and invalids
    cur = db.cursor()

    total_flashes = 0

    try:
        # Remove the serials table if exists, then create the new one
        cur.execute('DROP TABLE IF EXISTS serials;')
        cur.execute("""CREATE TABLE serials (
            id INTEGER PRIMARY KEY,
            ref VARCHAR(200),
            description VARCHAR(200),
            start_serial CHAR(30),
            end_serial CHAR(30),
            date DATETIME,
            INDEX (start_serial, end_serial)
        );""")
        db.commit()
    except Exception as e:
        flash(
            f'Problem dropping and creating new table in database, {e}', 'danger')

    df = read_excel(filepath, 0)
    serial_counter = 1
    line_number = 1

    for _, (line, ref, description, start_serial, end_serial, date) in df.iterrows():
        line_number += 1
        try:
            start_serial = normalize_string(start_serial)
            end_serial = normalize_string(end_serial)
            cur.execute('INSERT INTO serials VALUES (%s, %s, %s, %s, %s, %s);',
                        (line, ref, description, start_serial, end_serial, date))
            serial_counter += 1
        except Exception as e:
            total_flashes += 1
            if total_flashes < MAX_FLASH:
                flash(
                    f'Error inserting line {line_number} from serials sheet SERIALS, {e}', 'danger')
            elif total_flashes == MAX_FLASH:
                flash(f'Too many errors!', 'danger')

        if line_number % 20 == 0:
            try:
                db.commit()
            except Exception as e:
                flash(
                    f'Problem committing serials into db around {line_number} (Or previous 20 ones); {e}')
        db.commit()

    # Now lets save the invalid serials

    try:
        # Remove the invalid table if exists, then create the new one
        cur.execute('DROP TABLE IF EXISTS invalids;')
        cur.execute("""CREATE TABLE invalids(
                    invalid_serial CHAR(30),
                    INDEX (invalid_serial)
        );""")
        db.commit()
    except Exception as e:
        flash(f'Error dropping and creating INVALIDS tables, {e}', 'danger')

    invalid_counter = 1
    # total_flashes = 0
    line_number = 1
    df = read_excel(filepath, 1)
    for _, (failed_serial, ) in df.iterrows():
        line_number += 1
        try:
            failed_serial = normalize_string(failed_serial)
            cur.execute('INSERT INTO invalids VALUES (%s);', (failed_serial, ))
            invalid_counter += 1
        except Exception as e:
            total_flashes += 1
            if total_flashes < MAX_FLASH:
                flash(
                    f'Error inserting line {line_number} from series sheet INVALIDS, {e}', 'danger')
            elif total_flashes == MAX_FLASH:
                flash(f'Too many errors!', 'danger')

        if line_number % 20 == 0:
            try:
                db.commit()
            except Exception as e:
                flash(
                    f'Problem committing invalid serials into db around {line_number} (Or previous 20 ones); {e}')

    db.commit()
    db.close()

    return (serial_counter, invalid_counter)


def check_serial(serial):
    """ this function will get one serial number and return appropriate answer to that, after consulting the db. """

    original_serial = serial
    serial = normalize_string(serial)

    # Init mysql connection
    db = get_database_connection()

    with db.cursor() as cur:
        # Get result invalid serial from db
        results = cur.execute(
            "SELECT * FROM invalids WHERE invalid_serial = %s;", (serial, ))
        # Check results invalid
        if results > 0:
            answer = f"""{original_serial}
    این شماره هولوگرام یافت نشد. لطفا دوباره سعی کنید و یا با واحد پشتیبانی تماس حاصل فرمایید.
    ساختار صحیح شماره هولوگرام به صورت دو حرف انگلیسی و ۷ یا ۸ رقم در دنباله آن می باشد. مثال FA1234567
    شماره تماس با بخش پشتیبانی فروش شرکت ایران تم
    ۰۲۱-۰۰۰۰۰۰۰۰"""
            return 'FAILURE', answer

        # Get result serial valid from db
        results = cur.execute(
            "SELECT * FROM serials WHERE start_serial <= %s and end_serial >= %s;", (serial, serial))
        # Double status result
        if results > 1:
            answer = f"""{original_serial}
    این شماره هولوگرام مورد تایید است.
    برای اطلاعات بیشتر از نوع محصول با بخش پشتیبانی فروش شرکت ایران تم تماس حاصل فرمایید.
    ۰۲۱-۰۰۰۰۰۰۰۰"""
            return 'DOUBLE', answer
        # Check results valid individual
        elif results == 1:
            ret = cur.fetchone()
            desc = ret[2]
            ref_number = ret[1]
            date = ret[5].date()
            answer = f"""{original_serial}
    {ref_number}
    {desc}
    Hologram date: {date}
    Genuine product of Schneider Electric
    شماره تماس با بخش پشتیبانی فروش شرکت ایران تم
    ۰۲۱-۰۰۰۰۰۰۰۰
    """
            return 'OK', answer

    # Return not found status if results not found any serials
    answer = f"""{original_serial}
این شماره هولوگرام یافت نشد. لطفا دوباره سعی کنید و یا با واحد پشتیبانی تماس حاصل فرمایید.
ساختار صحیح شماره هولوگرام بصورت دو حرف انگلیسی و ۷ یا ۸ رقم در دنباله آن می باشد. مثال: 
FA1234567
شماره تماس با بخش پشتیبانی فروش شرکت ایران تم:
۰۲۱-۰۰۰۰۰۰۰۰"""
    return 'NOT-FOUND', answer


@app.route(f'/v1/{CALL_BACK_TOKEN}/process', methods=['POST'])
def process():
    """ This is a callback from curl requests. will get sender and message and will check if it is valid, then answers back.
    This is secured by 'CALL_BACK_TOKEN' in order to avoid mal-intended calls. """
    # Note: You need to call back token to send request (post) to process function
    data = request.form
    sender = data['from']
    message = data['message']

    status, answer = check_serial(message)

    # Init mysql connection
    db = get_database_connection()

    cur = db.cursor()

    now = time.strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("INSERT INTO PROCESSED_SMS (status, sender, message, answer, date) VALUES (%s, %s, %s, %s, %s)",
                (status, sender, message, answer, now))
    db.commit()
    db.close()

    send_sms(sender, answer)
    ret = {'message': 'processed!'}
    return jsonify(ret), 200


@app.errorhandler(404)
def page_not_found(error):
    """ Redirect to 404 page in page not found status. """
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run('0.0.0.0', 5000, debug=True)
