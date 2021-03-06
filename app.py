import os
from flask import Flask, redirect, request, session, url_for, jsonify, send_file, make_response, Response
import requests
from datetime import datetime, timedelta
import json
import requests
from geniClient import *
from profiles import Relation, Profile
from simplekv.memory import DictStore
from flaskext.kvsession import KVSessionExtension
import threading
import thread
import time
from db import saveProfile, getTopProfiles, updateTop50
from sets import Set
from mail import sendEmail
from rq import Queue
from worker import conn

q = Queue(connection=conn)
app = Flask(__name__)

# a DictStore will store everything in memory
store = DictStore()
# this will replace the app's session handling
KVSessionExtension(store, app)

@app.route('/')
def index():
    return send_file('templates/login.html')

@app.route('/login')
def login():
    return redirect(buildAuthUrl())

@app.route('/home')
def home():
    code = request.args.get('code')
    tokenResponse = getNewToken(code)
    setTokens(tokenResponse)
    session['currentStep'] = 0
    return send_file('templates/index.html')

@app.route('/getUniqueCount')
def getUniqueCount():
    email = request.args.get('email')
    includeInTop50 = request.args.get('includeTop50')
    myProfileFlag = request.args.get('myProfile')
    stepCount = request.args.get('stepCount')
    otherId = request.args.get('otherId')
    data = {}
    steps = []
    visitedSet = Set()
    if myProfileFlag == 'true':
        if not email:
            for step in range(0, int(stepCount)):
                stepData = getStepProfiles(step, visitedSet, None)
                steps.append(stepData)
        else:
            print 'email:' + email
            print 'creating a backgroundJob'
            params = {}
            params['accessToken'] = session['accessToken']
            params['email'] = email
            params['includeInTop50'] = includeInTop50
            params['stepCount'] = stepCount
            q.enqueue('app.createBackgroundJob', params)
            data = {}
            data['backgroundMessage'] = 'job started'
            return jsonify(data)
    else:
        #Other profiles
        profileData = getOtherProfile(session['accessToken'], otherId)
        profileData = json.loads(profileData)
        if not email:
            for step in range(0, int(stepCount)):
                stepData = getStepProfiles(step, visitedSet, profileData['id'])
                steps.append(stepData)
        else:
            print 'creating a backgroundJob'
            params = {}
            params['accessToken'] = session['accessToken']
            params['email'] = email
            params['otherId'] = profileData['id']
            params['includeInTop50'] = includeInTop50
            params['stepCount'] = stepCount
            q.enqueue('app.createBackgroundJob', params)
            data = {}
            data['backgroundMessage'] = 'job started'
            return jsonify(data)

    data['steps'] = steps

    #Insert into DB if required
    if includeInTop50 == 'on':
        updateTop50(session['stepUserLink'], stepCount, session['totalProfiles'])

    session['nextStepProfiles'] = None
    session['totalProfiles'] = None
    session['stepUserLink'] = None
    #session['visited-' + node['id']] = True
    return jsonify(data)

def getStepProfiles(count, visitedSet, profileId):
    currentStep = count
    uniqueCount = 0
    nextStepProfiles = ''
    if currentStep == 0:
        profileData = getProfileDetails(session['accessToken'], profileId)
        session['loginProfileId'] = profileData['id']
        session['stepUserLink'] = profileData['geniLink']
        session[profileData['id']] = profileData
        loginProfileId = session['loginProfileId']
        profileData = session[loginProfileId]
        visitedSet.add(loginProfileId)
        #session['visited-' + loginProfileId] = True
        for node in profileData['relations']:
            uniqueCount = uniqueCount + 1
            nextStepProfiles = nextStepProfiles + '*' + node['id']  # *** delimiter
            #session['visited-' + node['id']] = True
            visitedSet.add(node['id'])

        session['nextStepProfiles'] = nextStepProfiles[1:]
        session['totalProfiles'] = uniqueCount
    else:
        nextStepProfiles = session['nextStepProfiles']
        profileIds = nextStepProfiles.split('*')
        nextStepProfiles = ''
        for profileId in profileIds:
            try:
                if session[profileId] != None:
                    profileData = session[profileId]
            except KeyError:
                profileData = getProfileDetails(session['accessToken'], profileId)
            #Got profile data, process each relation
            session[profileData['id']] = profileData
            for node in profileData['relations']:
                nodeId = node['id']
                if nodeId in visitedSet:
                    pass
                else:
                    nextStepProfiles = nextStepProfiles + '*' + node['id']
                    uniqueCount = uniqueCount + 1
                    visitedSet.add(node['id'])
        session['nextStepProfiles'] = nextStepProfiles[1:]
        session['totalProfiles'] = session['totalProfiles'] + uniqueCount
    currentStep = currentStep + 1
    session['currentStep'] = currentStep
    return {'step':currentStep, 'profiles':uniqueCount, 'total':session['totalProfiles']}

def createBackgroundJob(params):
    print 'i am in createBackgroundJob'
    data = {}
    localSession = {}
    steps = []
    visitedSet = Set()
    otherId = params.get('otherId', '')
    stepCount = params['stepCount']
    includeInTop50 = params['includeInTop50']
    if otherId == '':
        for step in range(0, int(stepCount)):
                stepData = getStepProfilesThread(params['accessToken'], step, visitedSet, None, localSession)
                steps.append(stepData)
        data['profileId'] = localSession['loginProfileId']
    else:
        for step in range(0, int(stepCount)):
                stepData = getStepProfilesThread(params['accessToken'], step, visitedSet, params['otherId'], localSession)
                steps.append(stepData)
        data['profileId'] = params['otherId']

    #if top50 checked
    if includeInTop50 == 'on':
        updateTop50(localSession['stepUserLink'], stepCount, localSession['totalProfiles'])

    # Send email
    data['steps'] = steps
    sendEmail(params['email'], data)

def getStepProfilesThread(accessToken, count, visitedSet, profileId, localSession):
    currentStep = count
    uniqueCount = 0
    nextStepProfiles = ''
    if currentStep == 0:
        profileData = getProfileDetails(accessToken, profileId)
        localSession['loginProfileId'] = profileData['id']
        localSession['stepUserLink'] = profileData['geniLink']
        localSession[profileData['id']] = profileData
        loginProfileId = localSession['loginProfileId']
        profileData = localSession[loginProfileId]
        visitedSet.add(loginProfileId)
        #session['visited-' + loginProfileId] = True
        for node in profileData['relations']:
            uniqueCount = uniqueCount + 1
            nextStepProfiles = nextStepProfiles + '*' + node['id']  # *** delimiter
            #session['visited-' + node['id']] = True
            visitedSet.add(node['id'])

        localSession['nextStepProfiles'] = nextStepProfiles[1:]
        localSession['totalProfiles'] = uniqueCount
    else:
        nextStepProfiles = localSession['nextStepProfiles']
        profileIds = nextStepProfiles.split('*')
        nextStepProfiles = ''
        for profileId in profileIds:
            try:
                if localSession[profileId] != None:
                    profileData = localSession[profileId]
            except KeyError:
                profileData = getProfileDetails(accessToken, profileId)
            #Got profile data, process each relation
            localSession[profileData['id']] = profileData
            for node in profileData['relations']:
                nodeId = node['id']
                if nodeId in visitedSet:
                    pass
                else:
                    nextStepProfiles = nextStepProfiles + '*' + node['id']
                    uniqueCount = uniqueCount + 1
                    visitedSet.add(node['id'])
        localSession['nextStepProfiles'] = nextStepProfiles[1:]
        localSession['totalProfiles'] = localSession['totalProfiles'] + uniqueCount
    currentStep = currentStep + 1
    localSession['currentStep'] = currentStep
    return {'step':currentStep, 'profiles':uniqueCount, 'total':localSession['totalProfiles']}


#Dummy steps
    """steps = []
    steps.append({'step':1,'profiles':10,'total':10})
    steps.append({'step':2,'profiles':10,'total':20})
    steps.append({'step':3,'profiles':10,'total':30})
    steps.append({'step':4,'profiles':10,'total':40})
    data = {}
    data['steps'] = steps"""

@app.route('/getProfile', methods=['GET'])
def getProfile():
    accessToken = session['accessToken']
    profileId = request.args.get('profileId')
    if not accessToken:
        redirect(url_for('login'))
    #Load from session if already there.
    try:
        if session[profileId] != None:
            profileData = session[profileId]
            return jsonify(profileData)
    except KeyError:
        pass

    profileData = getProfileDetails(accessToken, profileId)
    if profileId == None:
        session['loginProfileId'] = profileData['id']
    #session[profileData['id']] = profileData
    if profileData != None:
        session[profileData['id']] = profileData
    return jsonify(profileData)

@app.route('/getUniqueCountOld')
def getUniqueCountOld():
    uniqueCount = 0
    nextStepProfiles = ''
    currentStep = session['currentStep']
    if currentStep == 0:
        profileData = getProfileDetails(session['accessToken'], None)
        session['loginProfileId'] = profileData['id']
        session[profileData['id']] = profileData
        loginProfileId = session['loginProfileId']
        profileData = session[loginProfileId]
        session['visited-' + loginProfileId] = True
        for node in profileData['relations']:
            uniqueCount = uniqueCount + 1
            nextStepProfiles = nextStepProfiles + '*' + node['id']  # *** delimiter
            session['visited-' + node['id']] = True

        session['nextStepProfiles'] = nextStepProfiles[1:]
        session['totalProfiles'] = uniqueCount
    else:
        nextStepProfiles = session['nextStepProfiles']
        profileIds = nextStepProfiles.split('*')
        nextStepProfiles = ''
        for profileId in profileIds:
            try:
                if session[profileId] != None:
                    profileData = session[profileId]
            except KeyError:
                profileData = getProfileDetails(session['accessToken'], profileId)
            #Got profile data, process each relation
            session[profileData['id']] = profileData
            for node in profileData['relations']:
                nodeId = node['id']
                try:
                    if session['visited-' + nodeId] == True:
                        pass
                except KeyError:
                    nextStepProfiles = nextStepProfiles + '*' + node['id']
                    uniqueCount = uniqueCount + 1
                    session['visited-' + node['id']] = True
        session['nextStepProfiles'] = nextStepProfiles[1:]
        session['totalProfiles'] = session['totalProfiles'] + uniqueCount
    currentStep = currentStep + 1
    session['currentStep'] = currentStep
    return jsonify({'step':currentStep, 'uniqueCount':uniqueCount, 'total':session['totalProfiles']})

@app.route('/top')
def top():
    #accessToken = session['accessToken']
    steps = getTopProfiles()
    data = {}
    data['top50'] = steps
    return jsonify(data)

#DUMMY CODE
"""steps = []
    steps.append({'profileId':1234,'profileLink':'google.com','steps':10,'profiles':10})
    steps.append({'profileId':12342,'profileLink':'google.com','steps':10,'profiles':20})
    steps.append({'profileId':12343,'profileLink':'google.com','steps':10,'profiles':30})
    steps.append({'profileId':12344,'profileLink':'google.com','steps':10,'profiles':40})"""

@app.route('/logout')
def logout():
    accessToken = session['accessToken']
    invalidateToken(accessToken)
    session.clear()
    return send_file('templates/login.html')

@app.errorhandler(500)
def page_not_found(error):
    print error
    return 'This page does not exist', 500

@app.route('/getJsonTest', methods=['GET'])
def getJsonTest():
    geniFile = open('./geni.json','r')
    contents = geniFile.read()
    jsoncontents = json.loads(contents)
    p = Profile(jsoncontents['focus']['id'], 'publicUrl',
            'firstName' + ' ' + 'lastName', [], jsoncontents['focus']['gender'])
    contents = jsoncontents['nodes']
    for node in contents:
        if node.startswith('profile') and jsoncontents['focus']['id'] != contents[node]['id']:
            p.addRelation(contents[node]['first_name'] + ' ' + contents[node]['last_name'],
                      contents[node]['gender'], contents[node]['id'])
    data = {}
    data['id'] = p.id
    data['name'] = p.name
    data['gender'] = p.gender
    data['geniLink'] = p.geniLink
    relations = []
    for node in p.relations:
        relations.append({'id':node.id,'name':node.name,'gender':node.gender})
    data['relations'] = relations
    return jsonify(data)

def setTokens(tokenResponse):
    tokenResponse = json.loads(tokenResponse)
    session['accessToken'] = tokenResponse['access_token']
    session['refreshToken'] = tokenResponse['refresh_token']
    session['tokenExpiration'] = tokenResponse['expires_in']
    print session['accessToken']

app.secret_key = '12345abcde'

if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.debug = False
    #app.testing = True
    app.secret_key = '12345abcde'
    app.run(host='localhost', port=port)
