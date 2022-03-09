from flask import Flask
app = Flask(__name__)

@app.route('/')
def main_page():
    '''Main run def'''
    return 'Hello World'


app.route('/v1/getsms')
def get_sms():
    pass


def send_sms():
    pass


def check_serial():
    pass
