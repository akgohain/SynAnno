from crypt import methods
from flask import render_template, session, request, Response, jsonify

# import the package app
from synanno import app
from flask_cors import cross_origin

import json

# for access to the timing variable
import synanno
import datetime

import os
import time


global delete_fp
delete_fp = False

@app.route('/categorize')
def categorize():
    if synanno.proofread_time["finish_grid"] is None:
        synanno.proofread_time["finish_grid"] = datetime.datetime.now()
        synanno.proofread_time["difference_grid"] = synanno.proofread_time["finish_grid"] - synanno.proofread_time["start_grid"]
    if synanno.proofread_time["start_categorize"] is None:
        synanno.proofread_time["start_categorize"] = datetime.datetime.now()
    return render_template('categorize.html', pages=session.get('data'))


@app.route('/pass_flags', methods=['GET','POST'])
@cross_origin()
def pass_flags():
    global delete_fp

    flags = request.get_json()['flags']
    data = session.get('data')
    pages = len(data)

    # first update all flags and then delete the FP
    false_positives = {p:[] for p in range(0,pages)}

    # updated all flags
    for flag in flags:
        page_nr, img_nr, f = dict(flag).values()
        # deleting false positives
        if f == "falsePositive" and delete_fp:
            false_positives[int(page_nr)].append(int(img_nr))
        else:
            data[int(page_nr)][int(img_nr)]['Error_Description'] = str(f)

    if delete_fp:
        # delete the FPs
        for p in range(0,pages):
            # sort the indexes that should be deleted
            # adjust them based on the # of images deleted and the page number
            false_positives[p] = [ (fp - i) for i, fp in enumerate(sorted(false_positives[p]))]
            for id in false_positives[p]:
                del data[p][id]

    # stop the time
    if synanno.proofread_time["finish_categorize"] is None:
        synanno.proofread_time["finish_categorize"] = datetime.datetime.now()
        synanno.proofread_time["difference_categorize"] = synanno.proofread_time["finish_categorize"] - synanno.proofread_time["start_categorize"]

    # update the json
    final_filename = 'results-' + session.get('filename')
    # Exporting the final json and pop session
    if session.get('data') and session.get('n_pages'):
        final_file = dict()
        final_file['Data'] = sum(session['data'], [])
        final_file['Proofread Time'] = synanno.proofread_time
        with open(os.path.join(app.config['PACKAGE_NAME'],os.path.join(app.config['UPLOAD_FOLDER']),final_filename), 'w') as f:
            json.dump(final_file, f, default=json_serial)

        time.sleep(len(data)*0.3*session['per_page'])

        # pass the data to the session
        session['data'] = data

        # returning a JSON formatted response to trigger the ajax success logic
        return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 
    else:
        return json.dumps({'success':True}), 400, {'ContentType':'application/json'} 

@app.route('/custom_flag', methods=['GET','POST'])
@cross_origin()
def custom_flag():
    # used by frontend to retrieve custom error messages from the JSON
    page = request.get_json()['page']
    img_id = request.get_json()['img_id']
    data = session.get('data')
    return jsonify(message=data[int(page)][int(img_id)]["Error_Description"])

# handle non json serializable data 
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime.timedelta)):
        return str(obj)
    if isinstance(obj, (datetime.datetime)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))