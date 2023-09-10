from flask import Flask, jsonify, request

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
    ret = {'message': 'processed!'}
    return jsonify(ret), 200


def send_sms():
    pass


def check_serial():
    pass


if __name__ == '__main__':
    app.run('0.0.0.0', 5000, debug=True)
