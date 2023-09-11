from flask import Flask, jsonify, request
from pandas import read_excel
import sqlite3
import requests
import config

# Sample flask object
app = Flask(__name__)

@app.route("/")
def main_page():
    ''' This is the main page of the site '''
    return "<p>Main page</p>"


@app.route('/v1/process', methods=['POST'])
def process():
    """ This is a callback from curl requests. will get sender and message and will check if it is valid, then answers back.  """
    data = request.form
    sender = data['from']
    message = data['message']
    print(f'Received: {message} from {sender}')
    send_sms(sender, 'Hi ' + message)
    ret = {'message': 'processed!'}
    return jsonify(ret), 200


def send_sms(receptor, message):
    """ This function will get a MSISDN and a message, then uses KaveNegar to send sms.  """
    url = f'https://api.kavenegar.com/v1/{config.API_KEY}/sms/send.json'
    data = {'message': message, 'receptor': receptor}
    response = requests.post(url, data)
    print(f'message *{message}* send to receptor: {receptor}. status code is {response.status_code}')

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
        query = f'INSERT INTO serials VALUES ("{line}", "{ref}", "{desc}", "{start_serial}", "{end_serial}", "{date}");'
        cur.execute(query)
        # TODO: do some more error handling
        if serial_counter % 10:
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
    for index, failed_serial_row in df.iterrows():
        failed_serial = failed_serial_row.values[0]
        query = f'INSERT INTO invalids VALUES ("{failed_serial}")'
        cur.execute(query)
        # TODO: do some more error handling
        if invalid_counter % 10:
            conn.commit()
        invalid_counter += 1
    conn.commit()

    conn.close()

    return (serial_counter, invalid_counter)


def check_serial():
    pass


if __name__ == '__main__':
    # app.run('0.0.0.0', 5000, debug=True)
    a, b = import_database_from_excel('./data.xlsx')
    print(f'inserted {a} rows and {b} invalids')
