from flask import Flask, jsonify, request, Response, redirect, url_for, session, abort
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from pandas import read_excel
import requests
import re
import sqlite3
import config


# Sample flask object
app = Flask(__name__)


# config
app.config.update(
    DEBUG=True,
    SECRET_KEY=config.SECRET_KEY
)


# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):

    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "%d" % (self.id)


# create some users with ids 1 to 20
user = User(0)

# some protected url


@app.route('/')
@login_required
def home():
    return Response('Hello World!')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':  # TODO: stop the brute force
        username = request.form['username']
        password = request.form['password']
        if password == config.PASSWORD and username == config.USERNAME:
            login_user(user)
            return redirect('/')
        else:
            return abort(401)
    else:
        return Response("""
        <form action="" method="post">
            <p><input type="text" name="username" /></p>
            <p><input type="password" name="password" /></p>
            <p><input type="submit" value="Login" /></p>
        </form>
""")


# somewhere to logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return Response('<p>Logged out</p>')


# handle login failed
@app.errorhandler(401)
def page_not_found(error):
    return Response('<p>Logon failed!</p>')


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

    # TODO: make sure that the data is imported correctly, we nned to backup the old one
    # TODO: do some normalization

    # Our sqlite database will contain two tables: serials and invalids
    conn = sqlite3.connect(config.DATABASE_FILE_PATH)
    cur = conn.cursor()

    # Remove the serials table if exists, then create the new one
    cur.execute('DROP TABLE IF EXISTS serials')
    cur.execute("""CREATE TABLE IF NOT EXISTS serials (
        id INTEGER PRIMARY KEY,
        ref TEXT,
        desc TEXT,
        start_serial TEXT,
        end_serial TEXT,
        date DATE
    );""")
    conn.commit()

    df = read_excel(filepath, 0)
    serial_counter = 0
    for index, (line, ref, desc, start_serial, end_serial, date) in df.iterrows():
        start_serial = normalize_string(start_serial)
        end_serial = normalize_string(end_serial)
        query = f'INSERT INTO serials VALUES ("{line}", "{ref}", "{desc}", "{start_serial}", "{end_serial}", "{date}");'
        cur.execute(query)
        # TODO: do some more error handling
        if serial_counter % 10 == 0:
            conn.commit()
        serial_counter += 1
    conn.commit()

    # Remove the invalid table if exists, then create the new one
    cur.execute('DROP TABLE IF EXISTS invalids')
    cur.execute("""CREATE TABLE IF NOT EXISTS invalids(
                invalid_serial TEXT PRIMARY KEY
    );""")
    conn.commit()
    invalid_counter = 0
    df = read_excel(filepath, 1)
    for index, (failed_serial, ) in df.iterrows():
        query = f'INSERT INTO invalids VALUES ("{failed_serial}");'
        cur.execute(query)
        # TODO: do some more error handling
        if invalid_counter % 10 == 0:
            conn.commit()
        invalid_counter += 1
    conn.commit()

    conn.close()

    return (serial_counter, invalid_counter)


def check_serial(serial):
    """ this function will get one serial number and return appropriate answer to that, after consulting the db. """
    conn = sqlite3.connect(config.DATABASE_FILE_PATH)
    cur = conn.cursor()

    query = f"SELECT * FROM invalids WHERE invalid_serial == '{serial}';"
    results = cur.execute(query)
    if len(results.fetchall()) == 1:
        # TODO: return the string provided by the customer
        return 'This serial is among failed ones'

    query = f"SELECT * FROM serials WHERE start_serial < '{serial}' AND end_serial > '{serial}';"
    results = cur.execute(query)
    if len(results.fetchall()) == 1:
        # TODO: return string provided by the customer.
        return 'I found your serial'

    return 'It was not in the db'


@app.route('/v1/process', methods=['POST'])
def process():
    """ This is a callback from curl requests. will get sender and message and will check if it is valid, then answers back. """
    data = request.form
    sender = data['from']
    message = normalize_string(data['message'])
    print(f'Received: {message} from {sender}')  # TODO: logging

    answer = check_serial(message)

    send_sms(sender, answer)
    ret = {'message': 'processed!'}
    return jsonify(ret), 200


if __name__ == '__main__':
    import_database_from_excel('./data.xlsx')
    app.run('0.0.0.0', 5000, debug=True)
