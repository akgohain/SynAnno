# import global configs
import synanno

# import the package app
from synanno import app

# flask util functions
from flask import render_template, session, send_file, flash

# flask ajax requests
from flask_cors import cross_origin

# for type hinting
from jinja2 import Template 
# enable multiple return types
from typing import Union

# manage paths and files
import os

# to zip folder
import shutil


@app.route('/export_annotate')
def export_annotate() -> Template:
    ''' Renders final view of the annotation process that lets the user download the JSON.

        Return:
            Export-annotate view
    '''

    # disable the 'Start New Process' button as long as the user did not download the masks or JSON
    # the user can always interrupt a process using the home button, but we want to prevent data loss
    return render_template('export_annotate.html', disable_snp='disabled')

@app.route('/export_draw')
def export_draw() -> Template:
    ''' Renders final view of the draw process that lets the user download the custom masks.

        Return:
            Export-draw view
    '''
    
    # disable the 'Start New Process' button as long as the user did not download the masks or JSON
    # the user can always interrupt a process using the home button, but we want to prevent data loss
    return render_template('export_draw.html', disable_snp='disabled')

@app.route('/export_data/<string:data_type>', methods=['GET'])
def export_data(data_type) -> Union[Template, app.response_class]:
    ''' Download the JSON or the custom masks.

        Args:
            data_type: Specifies the data type for download | json, or masks

        Return:
            Either sends the JSON or the masks to the users download folder
            or rerenders the export view if there is now file that could be downloaded
    '''
    if data_type == 'json':
        # exporting the final json
        if session.get('data') and session.get('n_pages'):
            return send_file(os.path.join(os.path.join(app.root_path,app.config['UPLOAD_FOLDER']), app.config['JSON']), as_attachment=True, attachment_filename=app.config['JSON'])
        else:
            flash('Now file - session data is empty.', 'error')
            # rerender export-draw and enable the 'Start New Process' button
            return render_template('export_annotate.html', disable_snp=' ')
    elif data_type == 'mask':
        total_folder_path = os.path.join(os.path.join(app.root_path,app.config['STATIC_FOLDER']),'custom_masks')
        if os.path.exists(total_folder_path):
            # create zip of folder
            shutil.make_archive(total_folder_path, 'zip', total_folder_path)
            return send_file(os.path.join(os.path.join(app.root_path,app.config['STATIC_FOLDER']), 'custom_masks.zip'), as_attachment=True)
        else:
            flash('The folder containing custom masks is empty. Did you draw custom masks?', 'error')
            # rerender export-draw and enable the 'Start New Process' button
            return render_template('export_draw.html', disable_snp=' ')    


@app.route('/reset')
def reset() -> Template:
    ''' Resets all process by pooping all the session content, resting the process bar, resting the timer,
        deleting the h5 source and target file, deleting the JSON, the images, masks and zip folder.

        Return:
            Renders the landing-page view.
    '''

    # reset progress bar 
    synanno.progress_bar_status = {'status':'Loading Source File', 'percent':0}

    # reset time
    synanno.proofread_time = dict.fromkeys(synanno.proofread_time, None)

    # pop all the session content.
    for key in list(session.keys()):
        session.pop(key)

    # upload folder
    upload_folder = os.path.join(app.config['PACKAGE_NAME'],app.config['UPLOAD_FOLDER'])

    # delete all the uploaded h5 files
    if os.path.exists(os.path.join('.', upload_folder)):
        for filename in os.listdir(os.path.join('.', upload_folder)):
            file_path = os.path.join(
                os.path.join('.', upload_folder), filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (file_path, e))

    # delete json file.
    if os.path.isfile(os.path.join(os.path.join(app.config['PACKAGE_NAME'], app.config['UPLOAD_FOLDER']),app.config['JSON'])):
        os.remove(os.path.join(os.path.join(app.config['PACKAGE_NAME'], app.config['UPLOAD_FOLDER']),app.config['JSON']))

    # delete static images
    static_folder = os.path.join(app.config['PACKAGE_NAME'], app.config['STATIC_FOLDER'])
    image_folder = os.path.join(static_folder, 'Images')
    
    if os.path.exists(os.path.join(image_folder, 'Img')):
        try:
            shutil.rmtree(os.path.join(image_folder, 'Img'))
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (image_folder, e))

    if os.path.exists(os.path.join(image_folder, 'Syn')):
        try:
            shutil.rmtree(os.path.join(image_folder, 'Syn'))
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (image_folder, e))

    # delete masks zip file.
    if os.path.isfile(os.path.join(static_folder, 'custom_masks.zip')):
        os.remove(os.path.join(static_folder, 'custom_masks.zip'))

    # delete custom masks
    mask_folder = os.path.join(static_folder, 'custom_masks')
    if os.path.exists(mask_folder):
        try:
            shutil.rmtree(mask_folder)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (mask_folder, e))

    return render_template('landingpage.html')
