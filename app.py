from flask import Flask
app = Flask(__name__)

@app.route('/')
def main_page():
    '''Main run def'''
    return 'Hello World'
