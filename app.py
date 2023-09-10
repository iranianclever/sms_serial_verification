from flask import Flask, jsonify, request
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


def check_serial():
    pass


if __name__ == '__main__':
    app.run('0.0.0.0', 5000, debug=True)
