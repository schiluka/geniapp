import os
from flask import Flask, redirect, request, session, url_for, jsonify, send_file, make_response, render_template
import requests
from datetime import datetime, timedelta
import json
import requests

app = Flask(__name__)

BASE_URL = 'https://www.geni.com/'
REDIRECT_URL = 'http://mysterious-citadel-7993.herokuapp.com/home'
#REDIRECT_URL = 'http://localhost:5000/home'

@app.route('/')
def index():
    print 'in /'
    return send_file('templates/login.html')

@app.route('/login')
def login():
    params = {
        'client_id': '0FxhNjhtYXRPKRqDBOCJgJOhukrg1xIACIZr0LZO',
        'redirect_uri': REDIRECT_URL
    }
    return redirect(buildAuthUrl('platform/oauth/authorize', params=params))

def buildAuthUrl(endpoint, params=''):
    if params != '':
        params = '&'.join(['%s=%s' % (k, v) for k, v in params.iteritems()])
    url = '%s%s?%s' % (BASE_URL, endpoint, params)
    return url

@app.route('/home')
def home():
    print 'in /home'
    code = request.args.get('code')
    print 'code-' + code
    print 'expires-' + request.args.get('expires_in')
    tokenResponse = getNewTokenFromApi(code)
    print 'got token!!!!'
    print tokenResponse
    session['accessToken'] = tokenResponse['access_token']
    session['refreshToken'] = tokenResponse['refresh_token']
    session['tokenExpiration'] = tokenResponse['expires_in']
    return send_file('templates/home.html')

@app.route('/getProfile', methods=['GET'])
def getProfile():
    print 'in /getProfile'
    #profileId = request.args.get('profileId')
    #record = json.loads(request.data)
    FAM_URL = 'https://www.geni.com/api/profile/immediate-family'
    PROF_URL = 'https://www.geni.com/api/profile'
    #print profileId
    #profileResponse = requests.get(PROFILE_URL);//6000000024491145741
    accessToken = session['accessToken']
    payload = {'access_token':accessToken}
    profileResponse = requests.get(FAM_URL, params=payload)
    print profileResponse.text
    return profileResponse.text

@app.route('/logout')
def logout():
    #Call invalidate token api
    accessToken = session['accessToken']
    payload = {'access_token':accessToken}
    INVALIDATE_URL = 'https://www.geni.com/platform/oauth/invalidate_token'
    invResponse = requests.get(INVALIDATE_URL, params=payload)
    print invResponse.text
    session.clear()
    return send_file('templates/login.html')
    #return redirect(url_for('/'))

def getNewTokenFromApi(code):
    url = 'https://www.geni.com/platform/oauth/request_token'
    params = {
              'client_id': '0FxhNjhtYXRPKRqDBOCJgJOhukrg1xIACIZr0LZO',
              'client_secret': '0t72HNiBHuNCGhnD2Y7a9zu65lJaomls4UPXJCe0',
              'code': code,
              'redirect_url': REDIRECT_URL
    }
    print 'calling request token api'
    tokenResponse = requests.get(url, params=params)
    print 'called request token api'
    print tokenResponse.text
    tokenResponse = tokenResponse.json
    return tokenResponse

if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.debug = False
    app.secret_key = '12345567890'
    app.run(host='localhost', port=port)